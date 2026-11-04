use crate::{
    config::{self, Configuration},
    crypto,
    error::{Error, Result, require},
    json,
    oidc::{Client, Transport},
};
use serde_json::{Value, json};
use sqlx::{
    ConnectOptions, PgPool, Row, SqlitePool,
    postgres::{PgConnectOptions, PgPoolOptions, PgSslMode},
    sqlite::{SqliteConnectOptions, SqlitePoolOptions, SqliteRow},
};
use std::{
    collections::BTreeMap,
    fs::File,
    io::Read,
    time::{Duration, SystemTime, UNIX_EPOCH},
};
use tokio::sync::Mutex;

pub struct Broker {
    pub db: SqlitePool,
    pg: PgPool,
    pub clients: BTreeMap<String, Client>,
    pub transport: Transport,
    pub rotation: Mutex<()>,
}
pub struct Session {
    pub username: String,
    pub csrf: String,
    pub expires: i64,
    pub subject: String,
    pub auth_time: i64,
    pub administrator: bool,
    pub digest: String,
}
pub fn now() -> Result<i64> {
    Ok(SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|_| Error(503))?
        .as_secs() as i64)
}
pub fn field(row: &SqliteRow, name: &str) -> Result<String> {
    Ok(row.try_get(name)?)
}
pub fn number(row: &SqliteRow, name: &str) -> Result<i64> {
    Ok(row.try_get(name)?)
}
pub fn cookie(input: Option<&str>, name: &str) -> Result<Option<String>> {
    let mut found = None;
    for part in input.unwrap_or("").split(';') {
        if let Some((key, value)) = part.trim().split_once('=')
            && key == name
        {
            require(found.is_none(), 401)?;
            found = Some(value.to_owned());
        }
    }
    Ok(found.filter(|s| crypto::secret(s)))
}
pub fn set_cookie(name: &str, value: &str, age: i64) -> String {
    format!("{name}={value}; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age={age}")
}
pub fn session_cookie(value: &str, age: i64) -> String {
    set_cookie("__Host-mrj_session", value, age)
}
pub fn transaction_cookie_name(state: &str) -> Result<String> {
    require(crypto::secret(state), 400)?;
    Ok(format!("__Host-mrj_oidc_{state}"))
}
fn tokens(response: crate::oidc::Response) -> Result<Value> {
    require(response.status == 200, 401)?;
    for key in ["access_token", "refresh_token", "id_token"] {
        require(
            response
                .document
                .get(key)
                .and_then(Value::as_str)
                .is_some_and(|s| crypto::text(s, 1, 16384)),
            503,
        )?;
    }
    Ok(response.document)
}
fn token<'a>(tokens: &'a Value, name: &str) -> Result<&'a str> {
    tokens.get(name).and_then(Value::as_str).ok_or(Error(503))
}

impl Broker {
    pub async fn connect(config: &Configuration) -> Result<Self> {
        let mut ca = Vec::new();
        File::open(&config.kanidm_ca_file)
            .map_err(|_| Error(503))?
            .take(1_048_577)
            .read_to_end(&mut ca)
            .map_err(|_| Error(503))?;
        let transport = Transport::new(config.kanidm_endpoint, &ca)?;
        let mut clients = BTreeMap::new();
        for client in &config.clients {
            let bytes = config::read_regular(&client.secret_file, 512, true)?;
            let secret = std::str::from_utf8(&bytes)
                .map_err(|_| Error(503))?
                .trim_end_matches(['\r', '\n']);
            require(
                (16..=256).contains(&secret.len())
                    && secret.bytes().all(|b| (33..=126).contains(&b)),
                503,
            )?;
            clients.insert(
                client.host.clone(),
                Client::new(client.client_id.clone(), secret.into()),
            );
        }
        let sqlite = SqliteConnectOptions::new()
            .filename(&config.state_database)
            .create_if_missing(false)
            .busy_timeout(Duration::from_secs(2))
            .disable_statement_logging();
        let db = SqlitePoolOptions::new()
            .max_connections(1)
            .acquire_timeout(Duration::from_secs(3))
            .connect_with(sqlite)
            .await?;
        let pg = PgPoolOptions::new()
            .max_connections(4)
            .acquire_timeout(Duration::from_secs(3))
            .connect_with(
                PgConnectOptions::new_without_pgpass()
                    .socket(&config.principal_database.host)
                    .port(config.principal_database.port)
                    .database(&config.principal_database.database)
                    .username(&config.principal_database.user)
                    .ssl_mode(PgSslMode::Disable)
                    .application_name("mrjam-identity")
                    .options([
                        ("statement_timeout", "5000"),
                        ("lock_timeout", "2000"),
                        ("search_path", "pg_catalog"),
                    ])
                    .disable_statement_logging(),
            )
            .await?;
        let broker = Self {
            db,
            pg,
            clients,
            transport,
            rotation: Mutex::new(()),
        };
        broker.schema().await?;
        Ok(broker)
    }
    pub fn client(&self, host: &str) -> Result<&Client> {
        self.clients.get(host).ok_or(Error(403))
    }
    pub async fn schema(&self) -> Result<()> {
        for sql in [
            "SELECT state,binding,client_id,host,verifier,nonce,retour,expires,stepup,invitation,notice FROM log_transactions LIMIT 0",
            "SELECT digest,host,subject,username,csrf,created,seen,expires,auth_time,access,refresh,nonce FROM log_sessions LIMIT 0",
            "SELECT subject,mail,duration,minimum,qualified_after FROM log_principaux LIMIT 0",
            "SELECT id,name,redirects,created FROM log_oauth_clients LIMIT 0",
            "SELECT id,client,session,redirect,state,challenge,expires FROM log_oauth_requests LIMIT 0",
            "SELECT digest,client,session,redirect,challenge,expires FROM log_oauth_codes LIMIT 0",
            "SELECT digest,client,session,kind,expires,revoked,family FROM log_oauth_tokens LIMIT 0",
        ] {
            sqlx::query(sql).execute(&self.db).await?;
        }
        let safe:bool=sqlx::query_scalar("SELECT NOT (rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls) AND has_function_privilege(current_user,'vision_gestion.identifier(text,text)','EXECUTE') FROM pg_roles WHERE rolname=current_user")
            .fetch_one(&self.pg).await?;
        require(safe, 503)
    }
    pub async fn ready(&self) -> Result<()> {
        self.schema().await?;
        for client in self.clients.values() {
            self.transport.discovery(client).await?;
        }
        Ok(())
    }
    pub(crate) async fn principal(&self, issuer: &str, subject: &str) -> Result<(String, bool)> {
        let value: String =
            sqlx::query_scalar("SELECT vision_gestion.identifier($1,$2)::text AS compte")
                .bind(issuer)
                .bind(subject)
                .fetch_one(&self.pg)
                .await?;
        let document = json::object(value.as_bytes(), 65536).map_err(|_| Error(503))?;
        let username = document
            .get("utilisateur")
            .and_then(Value::as_str)
            .filter(|s| crypto::text(s, 1, 64))
            .ok_or(Error(403))?;
        require(
            document.get("actif").and_then(Value::as_bool) == Some(true)
                && document.get("erreur").is_none_or(Value::is_null),
            403,
        )?;
        // Header values must never contain controls or non-ASCII bytes.
        require(username.bytes().all(|b| (33..=126).contains(&b)), 503)?;
        Ok((
            username.into(),
            document.get("administrateur").and_then(Value::as_bool) == Some(true),
        ))
    }
    pub async fn session(&self, host: &str, cookies: Option<&str>) -> Result<Option<Session>> {
        match cookie(cookies, "__Host-mrj_session")? {
            Some(secret) => self.session_digest(host, &crypto::hash(&secret)).await,
            None => Ok(None),
        }
    }
    pub async fn session_digest(&self, host: &str, digest: &str) -> Result<Option<Session>> {
        require(
            digest.len() == 64
                && digest
                    .bytes()
                    .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)),
            401,
        )?;
        let client = self.client(host)?;
        let _lock = self.rotation.lock().await;
        let now = now()?;
        let Some(row) =
            sqlx::query("SELECT * FROM log_sessions WHERE digest=? AND host=? AND expires>?")
                .bind(digest)
                .bind(host)
                .bind(now)
                .fetch_optional(&self.db)
                .await?
        else {
            return Ok(None);
        };
        let subject = field(&row, "subject")?;
        let (username, administrator) = self
            .principal(&crypto::issuer(&client.id), &subject)
            .await?;
        require(username == field(&row, "username")?, 403)?;
        let mut inspection = self
            .transport
            .introspect(client, &field(&row, "access")?)
            .await?;
        if inspection["active"] == false
            || inspection
                .get("exp")
                .and_then(Value::as_i64)
                .is_some_and(|t| t <= now + 60)
        {
            let refresh = field(&row, "refresh")?;
            let response = self
                .transport
                .exchange(
                    client,
                    "/oauth2/token",
                    Some(&[("grant_type", "refresh_token"), ("refresh_token", &refresh)]),
                )
                .await?;
            if response.status == 400 && response.document["error"] == "invalid_grant" {
                sqlx::query("DELETE FROM log_sessions WHERE digest=?")
                    .bind(digest)
                    .execute(&self.db)
                    .await?;
                return Ok(None);
            }
            require(response.status == 200, 503)?;
            let d = tokens(response)?;
            let access = token(&d, "access_token")?;
            let id = crypto::verify(
                token(&d, "id_token")?,
                &self.transport.jwks(client).await?,
                &client.id,
                &field(&row, "nonce")?,
                access,
                now,
            )?;
            require(id.subject == subject, 401)?;
            sqlx::query("UPDATE log_sessions SET access=?,refresh=? WHERE digest=?")
                .bind(access)
                .bind(token(&d, "refresh_token")?)
                .bind(digest)
                .execute(&self.db)
                .await?;
            inspection = self.transport.introspect(client, access).await?;
        }
        if inspection["active"] != true {
            sqlx::query("DELETE FROM log_sessions WHERE digest=?")
                .bind(digest)
                .execute(&self.db)
                .await?;
            return Ok(None);
        }
        sqlx::query("UPDATE log_sessions SET seen=? WHERE digest=?")
            .bind(now)
            .bind(digest)
            .execute(&self.db)
            .await?;
        Ok(Some(Session {
            username,
            csrf: field(&row, "csrf")?,
            expires: number(&row, "expires")?,
            subject,
            auth_time: number(&row, "auth_time")?,
            administrator,
            digest: digest.into(),
        }))
    }
    pub async fn elevated(&self, session: &Session) -> Result<bool> {
        let policy =
            sqlx::query("SELECT minimum,qualified_after FROM log_principaux WHERE subject=?")
                .bind(&session.subject)
                .fetch_optional(&self.db)
                .await?;
        let Some(policy) = policy else {
            return Ok(false);
        };
        let now = now()?;
        Ok(field(&policy, "minimum")? == "mfa"
            && number(&policy, "qualified_after")? <= session.auth_time
            && session.auth_time <= now
            && now - session.auth_time < 900)
    }
    pub async fn duration(&self, subject: &str) -> Result<i64> {
        let duration: Option<i64> =
            sqlx::query_scalar("SELECT duration FROM log_principaux WHERE subject=?")
                .bind(subject)
                .fetch_optional(&self.db)
                .await?;
        let duration = duration.unwrap_or(604800);
        require([604800, 2592000, 7776000].contains(&duration), 503)?;
        Ok(duration)
    }
    pub async fn begin(
        &self,
        host: &str,
        retour: &str,
        elevated: bool,
    ) -> Result<(String, String)> {
        let client = self.client(host)?;
        require(return_path(retour), 400)?;
        let state = crypto::random()?;
        let binding = crypto::random()?;
        let verifier = crypto::random()?;
        let nonce = crypto::random()?;
        let now = now()?;
        let mut tx = self.db.begin().await?;
        sqlx::query("DELETE FROM log_transactions WHERE expires<=?")
            .bind(now)
            .execute(&mut *tx)
            .await?;
        let count: i64 = sqlx::query_scalar("SELECT count(*) FROM log_transactions")
            .fetch_one(&mut *tx)
            .await?;
        require(count < 4096, 429)?;
        sqlx::query("INSERT INTO log_transactions VALUES(?,?,?,?,?,?,?,?,0,NULL,NULL)")
            .bind(crypto::hash(&state))
            .bind(crypto::hash(&binding))
            .bind(&client.id)
            .bind(host)
            .bind(&verifier)
            .bind(&nonce)
            .bind(retour)
            .bind(now + 600)
            .execute(&mut *tx)
            .await?;
        tx.commit().await?;
        let uri = format!("https://{host}/auth/retour");
        let challenge = crypto::challenge(&verifier);
        let mut query = crate::oidc::form(&[
            ("client_id", &client.id),
            ("response_type", "code"),
            ("scope", "openid email profile"),
            ("redirect_uri", &uri),
            ("state", &state),
            ("nonce", &nonce),
            ("code_challenge", &challenge),
            ("code_challenge_method", "S256"),
        ]);
        if elevated {
            query.push_str("&prompt=login&max_age=0");
        }
        Ok((
            format!("https://log.mrj.am/ui/oauth2?{query}"),
            set_cookie(&transaction_cookie_name(&state)?, &binding, 600),
        ))
    }
    pub async fn callback(
        &self,
        host: &str,
        state: &str,
        code: &str,
        cookies: Option<&str>,
    ) -> Result<(String, String, String)> {
        let client = self.client(host)?;
        require(crypto::secret(state) && crypto::text(code, 1, 8192), 400)?;
        let name = transaction_cookie_name(state)?;
        let proper = cookie(cookies, &name)?;
        let binding = match &proper {
            Some(value) => Some(value.clone()),
            None => cookie(cookies, "__Host-mrj_oidc")?,
        }
        .ok_or(Error(401))?;
        let now = now()?;
        // Atomic consumption before outbound exchange. Failed/timed-out code exchange is never retried.
        let row=sqlx::query("DELETE FROM log_transactions WHERE state=? AND binding=? AND client_id=? AND host=? AND expires>? RETURNING *")
            .bind(crypto::hash(state)).bind(crypto::hash(&binding)).bind(&client.id).bind(host).bind(now).fetch_optional(&self.db).await?.ok_or(Error(401))?;
        let verifier = field(&row, "verifier")?;
        let redirect = format!("https://{host}/auth/retour");
        let nonce = field(&row, "nonce")?;
        let d = tokens(
            self.transport
                .exchange(
                    client,
                    "/oauth2/token",
                    Some(&[
                        ("grant_type", "authorization_code"),
                        ("code", code),
                        ("code_verifier", &verifier),
                        ("redirect_uri", &redirect),
                    ]),
                )
                .await?,
        )?;
        let id = crypto::verify(
            token(&d, "id_token")?,
            &self.transport.jwks(client).await?,
            &client.id,
            &nonce,
            token(&d, "access_token")?,
            now,
        )?;
        let (username, _) = self.principal(&id.issuer, &id.subject).await?;
        let secret = crypto::random()?;
        let csrf = crypto::random()?;
        let duration = self.duration(&id.subject).await?;
        let mut tx = self.db.begin().await?;
        sqlx::query("DELETE FROM log_sessions WHERE expires<=?")
            .bind(now)
            .execute(&mut *tx)
            .await?;
        let count: i64 = sqlx::query_scalar("SELECT count(*) FROM log_sessions WHERE username=?")
            .bind(&username)
            .fetch_one(&mut *tx)
            .await?;
        require(count < 20, 429)?;
        sqlx::query("INSERT INTO log_sessions VALUES(?,?,?,?,?,?,?,?,?,?,?,?)")
            .bind(crypto::hash(&secret))
            .bind(host)
            .bind(&id.subject)
            .bind(username)
            .bind(csrf)
            .bind(now)
            .bind(now)
            .bind(now + duration)
            .bind(id.auth_time.unwrap_or(0))
            .bind(token(&d, "access_token")?)
            .bind(token(&d, "refresh_token")?)
            .bind(nonce)
            .execute(&mut *tx)
            .await?;
        tx.commit().await?;
        Ok((
            field(&row, "retour")?,
            session_cookie(&secret, duration),
            set_cookie(
                if proper.is_some() {
                    &name
                } else {
                    "__Host-mrj_oidc"
                },
                "",
                0,
            ),
        ))
    }
    pub async fn logout(&self, host: &str, cookies: Option<&str>) -> Result<String> {
        let client = self.client(host)?;
        let _lock = self.rotation.lock().await;
        if let Some(secret) = cookie(cookies, "__Host-mrj_session")? {
            let refresh: Option<String> = sqlx::query_scalar(
                "DELETE FROM log_sessions WHERE digest=? AND host=? RETURNING refresh",
            )
            .bind(crypto::hash(&secret))
            .bind(host)
            .fetch_optional(&self.db)
            .await?;
            if let Some(refresh) = refresh {
                // Local deletion commits even when the IdP is unavailable.
                let _ = self
                    .transport
                    .exchange(
                        client,
                        "/oauth2/token/revoke",
                        Some(&[("token", &refresh), ("token_type_hint", "refresh_token")]),
                    )
                    .await;
            }
        }
        Ok(session_cookie("", 0))
    }
    pub async fn revoke_others(&self, session: &Session) -> Result<()> {
        let _lock = self.rotation.lock().await;
        sqlx::query("DELETE FROM log_sessions WHERE username=? AND digest<>?")
            .bind(&session.username)
            .bind(&session.digest)
            .execute(&self.db)
            .await?;
        Ok(())
    }
    pub async fn session_document(&self, session: &Session) -> Result<Value> {
        Ok(
            json!({"username":session.username,"csrf":session.csrf,"expiresAt":session.expires,
            "administrateur":session.administrator,"verificationRenforcee":self.elevated(session).await?}),
        )
    }
}
pub fn csrf(session: &Session, host: &str, origin: Option<&str>, csrf: Option<&str>) -> Result<()> {
    require(
        origin == Some(format!("https://{host}").as_str())
            && csrf.is_some_and(|s| crypto::same(s, &session.csrf)),
        403,
    )
}
pub fn return_path(value: &str) -> bool {
    if !crypto::text(value, 1, 4096) || value.contains('\\') {
        return false;
    }
    matches!(
        value,
        "/" | "/auth/mcp"
            | "/#administration"
            | "/#compte"
            | "/#enseignant"
            | "/#preparer"
            | "/#suivre"
            | "/#eleve"
            | "/#aide"
    ) || value.starts_with("/oauth/authorize?")
        || ["/#seance/", "/#activite/", "/#cours/", "/#affectation/"]
            .iter()
            .any(|p| {
                value
                    .strip_prefix(p)
                    .is_some_and(|id| config::identifier(id, 64))
            })
}

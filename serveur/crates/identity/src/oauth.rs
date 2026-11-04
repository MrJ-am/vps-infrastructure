use crate::{
    crypto,
    error::{Error, Result, require},
    oidc::form,
    state::{Broker, Session, field, now, number},
};
use serde_json::{Value, json};
use sqlx::{Row, Sqlite, Transaction};
use std::collections::BTreeMap;

pub type Parameters = BTreeMap<String, String>;
pub fn get<'a>(parameters: &'a Parameters, key: &str) -> Result<&'a str> {
    parameters.get(key).map(String::as_str).ok_or(Error(400))
}
pub fn audience(host: &str) -> Result<(&'static str, &'static str)> {
    match host {
        "vision.mrj.am" => Ok(("https://vision.mrj.am/mcp", "vision:mcp")),
        "audition.mrj.am" => Ok(("https://audition.mrj.am/mcp", "audition:mcp")),
        _ => Err(Error(403)),
    }
}
pub fn metadata(host: &str, resource: bool) -> Result<Value> {
    let (resource_url, scope) = audience(host)?;
    let origin = format!("https://{host}");
    Ok(if resource {
        json!({"resource":resource_url,"authorization_servers":[origin],"scopes_supported":[scope],"bearer_methods_supported":["header"]})
    } else {
        json!({"issuer":origin,"authorization_endpoint":format!("{origin}/oauth/authorize"),"token_endpoint":format!("{origin}/oauth/token"),
        "registration_endpoint":format!("{origin}/oauth/register"),"revocation_endpoint":format!("{origin}/oauth/revoke"),
        "response_types_supported":["code"],"grant_types_supported":["authorization_code","refresh_token"],"code_challenge_methods_supported":["S256"],
        "token_endpoint_auth_methods_supported":["none"],"scopes_supported":[scope]})
    })
}
fn redirect(value: &str) -> bool {
    if !(9..=1024).contains(&value.len())
        || !value.starts_with("https://")
        || !value.bytes().all(|b| (33..=126).contains(&b))
        || value.contains(['#', '\\'])
    {
        return false;
    }
    let authority = value[8..].split(['/', '?']).next().unwrap_or("");
    !authority.is_empty()
        && authority
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b".-:".contains(&b))
        && url::Url::parse(value).is_ok_and(|url| {
            url.scheme() == "https"
                && url.host_str().is_some()
                && url.username().is_empty()
                && url.password().is_none()
        })
}
fn resource(host: &str, parameters: &Parameters) -> Result<()> {
    let (url, _) = audience(host)?;
    require(parameters.get("resource").is_none_or(|v| v == url), 400)
}
async fn parent(
    tx: &mut Transaction<'_, Sqlite>,
    host: &str,
    digest: &str,
    now: i64,
) -> Result<i64> {
    sqlx::query_scalar("SELECT expires FROM log_sessions WHERE digest=? AND host=? AND expires>?")
        .bind(digest)
        .bind(host)
        .bind(now)
        .fetch_optional(&mut **tx)
        .await?
        .ok_or(Error(400))
}
async fn pair(
    tx: &mut Transaction<'_, Sqlite>,
    host: &str,
    client: &str,
    session: &str,
    family: &str,
    now: i64,
) -> Result<Value> {
    let expires = parent(tx, host, session, now).await?;
    let duration = (expires - now).min(3600);
    let access = crypto::random()?;
    let refresh = crypto::random()?;
    for (secret, kind, lifetime) in [
        (&access, "access", duration),
        (&refresh, "refresh", (expires - now).min(30 * 86400)),
    ] {
        sqlx::query("INSERT INTO log_oauth_tokens VALUES(?,?,?,?,?,NULL,?)")
            .bind(crypto::hash(secret))
            .bind(client)
            .bind(session)
            .bind(kind)
            .bind(now + lifetime)
            .bind(family)
            .execute(&mut **tx)
            .await?;
    }
    Ok(
        json!({"access_token":access,"refresh_token":refresh,"token_type":"Bearer","expires_in":duration,"scope":audience(host)?.1}),
    )
}
impl Broker {
    pub async fn register(&self, document: &Value) -> Result<Value> {
        let redirects = document
            .get("redirect_uris")
            .and_then(Value::as_array)
            .ok_or(Error(400))?;
        require(
            (1..=5).contains(&redirects.len())
                && redirects.iter().all(|v| v.as_str().is_some_and(redirect)),
            400,
        )?;
        let name = match document.get("client_name") {
            None | Some(Value::Null) => "Client MCP",
            Some(v) => v.as_str().ok_or(Error(400))?,
        };
        require(
            crypto::text(name, 1, 80)
                && document
                    .get("token_endpoint_auth_method")
                    .is_none_or(|v| v.is_null() || v == "none"),
            400,
        )?;
        let id = crypto::random()?;
        let mut tx = self.db.begin().await?;
        let count: i64 = sqlx::query_scalar("SELECT count(*) FROM log_oauth_clients")
            .fetch_one(&mut *tx)
            .await?;
        require(count < 2048, 429)?;
        sqlx::query("INSERT INTO log_oauth_clients VALUES(?,?,?,?)")
            .bind(&id)
            .bind(name)
            .bind(serde_json::to_string(redirects).map_err(|_| Error(400))?)
            .bind(now()?)
            .execute(&mut *tx)
            .await?;
        tx.commit().await?;
        Ok(
            json!({"client_id":id,"client_name":name,"redirect_uris":redirects,"token_endpoint_auth_method":"none",
            "grant_types":["authorization_code","refresh_token"],"response_types":["code"]}),
        )
    }
    pub async fn request_mcp(
        &self,
        host: &str,
        session: &Session,
        p: &Parameters,
    ) -> Result<String> {
        let (_, scope) = audience(host)?;
        resource(host, p)?;
        let challenge = get(p, "code_challenge")?;
        let state = get(p, "state")?;
        let client = get(p, "client_id")?;
        let redirect = get(p, "redirect_uri")?;
        require(
            get(p, "response_type")? == "code"
                && get(p, "code_challenge_method")? == "S256"
                && crypto::secret(challenge)
                && crypto::text(state, 1, 1024)
                && p.get("scope").is_none_or(|v| v == scope),
            400,
        )?;
        let id = crypto::random()?;
        let now = now()?;
        let mut tx = self.db.begin().await?;
        parent(&mut tx, host, &session.digest, now).await?;
        let redirects: String =
            sqlx::query_scalar("SELECT redirects FROM log_oauth_clients WHERE id=?")
                .bind(client)
                .fetch_optional(&mut *tx)
                .await?
                .ok_or(Error(400))?;
        let allowed: Vec<String> = serde_json::from_str(&redirects).map_err(|_| Error(503))?;
        require(allowed.iter().any(|v| v == redirect), 400)?;
        sqlx::query("DELETE FROM log_oauth_requests WHERE expires<=?")
            .bind(now)
            .execute(&mut *tx)
            .await?;
        let count: i64 = sqlx::query_scalar("SELECT count(*) FROM log_oauth_requests")
            .fetch_one(&mut *tx)
            .await?;
        require(count < 4096, 429)?;
        sqlx::query("INSERT INTO log_oauth_requests VALUES(?,?,?,?,?,?,?)")
            .bind(&id)
            .bind(client)
            .bind(&session.digest)
            .bind(redirect)
            .bind(state)
            .bind(challenge)
            .bind(now + 600)
            .execute(&mut *tx)
            .await?;
        tx.commit().await?;
        Ok(id)
    }
    pub async fn read_request(&self, host: &str, session: &Session, id: &str) -> Result<Value> {
        require(crypto::secret(id), 400)?;
        let (resource, scope) = audience(host)?;
        let row=sqlx::query("SELECT r.*,c.name FROM log_oauth_requests r JOIN log_oauth_clients c ON c.id=r.client WHERE r.id=? AND r.session=? AND r.expires>?")
            .bind(id).bind(&session.digest).bind(now()?).fetch_optional(&self.db).await?.ok_or(Error(404))?;
        let redirect = field(&row, "redirect")?;
        let reprise = format!(
            "/oauth/authorize?{}",
            form(&[
                ("client_id", &field(&row, "client")?),
                ("redirect_uri", &redirect),
                ("response_type", "code"),
                ("code_challenge_method", "S256"),
                ("code_challenge", &field(&row, "challenge")?),
                ("state", &field(&row, "state")?),
                ("scope", scope),
                ("resource", resource)
            ])
        );
        Ok(
            json!({"id":id,"client":field(&row,"name")?,"redirect_uri":redirect,"reprise":reprise,"scope":scope}),
        )
    }
    pub async fn consent(
        &self,
        host: &str,
        session: &Session,
        id: &str,
        accept: bool,
    ) -> Result<String> {
        require(crypto::secret(id), 400)?;
        let now = now()?;
        let mut tx = self.db.begin().await?;
        parent(&mut tx, host, &session.digest, now).await?;
        let row = sqlx::query(
            "DELETE FROM log_oauth_requests WHERE id=? AND session=? AND expires>? RETURNING *",
        )
        .bind(id)
        .bind(&session.digest)
        .bind(now)
        .fetch_optional(&mut *tx)
        .await?
        .ok_or(Error(400))?;
        let code = crypto::random()?;
        if accept {
            sqlx::query("INSERT INTO log_oauth_codes VALUES(?,?,?,?,?,?)")
                .bind(crypto::hash(&code))
                .bind(field(&row, "client")?)
                .bind(&session.digest)
                .bind(field(&row, "redirect")?)
                .bind(field(&row, "challenge")?)
                .bind(now + 300)
                .execute(&mut *tx)
                .await?;
        }
        let redirect = field(&row, "redirect")?;
        let parameters = form(&[
            ("state", &field(&row, "state")?),
            if accept {
                ("code", &code)
            } else {
                ("error", "access_denied")
            },
        ]);
        tx.commit().await?;
        Ok(format!(
            "{redirect}{}{parameters}",
            if redirect.contains('?') { "&" } else { "?" }
        ))
    }
    pub async fn mcp_tokens(&self, host: &str, p: &Parameters) -> Result<Value> {
        resource(host, p)?;
        let client = get(p, "client_id")?;
        let grant = get(p, "grant_type")?;
        require(matches!(grant, "authorization_code" | "refresh_token"), 400)?;
        let code = grant == "authorization_code";
        let secret = get(p, if code { "code" } else { "refresh_token" })?;
        require(crypto::secret(secret), 400)?;
        let digest = crypto::hash(secret);
        let query = if code {
            "SELECT * FROM log_oauth_codes WHERE digest=? AND client=?"
        } else {
            "SELECT * FROM log_oauth_tokens WHERE digest=? AND client=?"
        };
        let row = sqlx::query(query)
            .bind(&digest)
            .bind(client)
            .fetch_optional(&self.db)
            .await?
            .ok_or(Error(400))?;
        require(
            number(&row, "expires")? > now()? && (code || field(&row, "kind")? == "refresh"),
            400,
        )?;
        let session = field(&row, "session")?;
        require(self.session_digest(host, &session).await?.is_some(), 400)?;
        if code {
            let verifier = get(p, "code_verifier")?;
            require(
                crypto::text(verifier, 43, 128)
                    && verifier
                        .bytes()
                        .all(|b| b.is_ascii_alphanumeric() || b"._~-".contains(&b))
                    && get(p, "redirect_uri")? == field(&row, "redirect")?
                    && crypto::same(&field(&row, "challenge")?, &crypto::challenge(verifier)),
                400,
            )?;
        }
        let now = now()?;
        let mut tx = self.db.begin().await?;
        let current = sqlx::query(query)
            .bind(&digest)
            .bind(client)
            .fetch_optional(&mut *tx)
            .await?
            .ok_or(Error(400))?;
        require(
            number(&current, "expires")? > now
                && field(&current, "session")? == session
                && (code || field(&current, "kind")? == "refresh"),
            400,
        )?;
        parent(&mut tx, host, &session, now).await?;
        if !code && current.try_get::<Option<i64>, _>("revoked")?.is_some() {
            sqlx::query("UPDATE log_oauth_tokens SET revoked=? WHERE family=?")
                .bind(now)
                .bind(field(&current, "family")?)
                .execute(&mut *tx)
                .await?;
            tx.commit().await?;
            return Err(Error(400));
        }
        let family = if code {
            crypto::random()?
        } else {
            field(&current, "family")?
        };
        if code {
            sqlx::query("DELETE FROM log_oauth_codes WHERE digest=?")
                .bind(&digest)
                .execute(&mut *tx)
                .await?;
        } else {
            sqlx::query("UPDATE log_oauth_tokens SET revoked=? WHERE digest=?")
                .bind(now)
                .bind(&digest)
                .execute(&mut *tx)
                .await?;
        }
        let result = pair(&mut tx, host, client, &session, &family, now).await?;
        tx.commit().await?;
        Ok(result)
    }
    pub async fn mcp_session(
        &self,
        host: &str,
        authorization: Option<&str>,
    ) -> Result<Option<Session>> {
        audience(host)?;
        let Some(authorization) = authorization else {
            return Ok(None);
        };
        let Some((scheme, secret)) = authorization.split_once(' ') else {
            return Ok(None);
        };
        if !scheme.eq_ignore_ascii_case("Bearer") || !crypto::secret(secret) {
            return Ok(None);
        }
        let digest = crypto::hash(secret);
        let query = "SELECT session FROM log_oauth_tokens WHERE digest=? AND kind='access' AND revoked IS NULL AND expires>?";
        let parent: Option<String> = sqlx::query_scalar(query)
            .bind(&digest)
            .bind(now()?)
            .fetch_optional(&self.db)
            .await?;
        let Some(parent) = parent else {
            return Ok(None);
        };
        let session = self.session_digest(host, &parent).await?;
        // Recheck revocation after network validation; never accept a concurrently revoked token.
        let current: Option<String> = sqlx::query_scalar(query)
            .bind(&digest)
            .bind(now()?)
            .fetch_optional(&self.db)
            .await?;
        if current.as_deref() != Some(&parent) {
            return Ok(None);
        }
        Ok(session)
    }
    pub async fn revoke_mcp(&self, host: &str, client: &str, secret: &str) -> Result<()> {
        audience(host)?;
        require(crypto::secret(secret), 400)?;
        sqlx::query("UPDATE log_oauth_tokens SET revoked=? WHERE client=? AND family IN (SELECT t.family FROM log_oauth_tokens t JOIN log_sessions s ON s.digest=t.session WHERE t.digest=? AND t.client=? AND s.host=?)")
            .bind(now()?).bind(client).bind(crypto::hash(secret)).bind(client).bind(host).execute(&self.db).await?;
        Ok(())
    }
}

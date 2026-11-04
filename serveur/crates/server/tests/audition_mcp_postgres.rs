//! MCP SDK + real PostgreSQL: a proposal cannot become a web prescription.
use axum::{
    Router,
    body::{Body, to_bytes},
    http::{HeaderMap, Request, StatusCode},
    routing::get,
};
use mrjam_audition::{
    Timestamp, WriteChannel,
    service::{PgAudition, VerifiedActor},
};
use mrjam_server::{runtime_config::RuntimeConfiguration, runtime_files::digest};
use serde_json::{Value, json};
use sqlx::{
    PgPool,
    postgres::{PgConnectOptions, PgPoolOptions},
};
use std::{
    os::unix::fs::PermissionsExt,
    path::PathBuf,
    str::FromStr,
    sync::{
        Arc,
        atomic::{AtomicBool, Ordering},
    },
    time::{SystemTime, UNIX_EPOCH},
};
use tower::ServiceExt;

const URL: &str =
    "postgresql://mrjam_synthetic:mrjam_synthetic_only@127.0.0.1:55432/mrjam_synthetic";
type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;

struct Files(PathBuf);
impl Drop for Files {
    fn drop(&mut self) {
        let _ = std::fs::remove_dir_all(&self.0);
    }
}

async fn request(
    router: &Router,
    path: &str,
    token: &str,
    document: Value,
) -> Result<(StatusCode, Value)> {
    let mut request = Request::builder()
        .method("POST")
        .uri(path)
        .header("host", "audition.mrj.am")
        .header("content-type", "application/json")
        .header("x-mrj-user", "forged.admin")
        .header("accept", "application/json, text/event-stream")
        .header("mcp-protocol-version", "2025-06-18");
    request = if path == "/mcp" {
        request.header("authorization", format!("Bearer {token}"))
    } else {
        request
            .header("cookie", token)
            .header("origin", "https://audition.mrj.am")
            .header("x-csrf-token", "synthetic-csrf")
    };
    let response = router
        .clone()
        .oneshot(request.body(Body::from(document.to_string()))?)
        .await?;
    Ok((
        response.status(),
        serde_json::from_slice(&to_bytes(response.into_body(), 524_288).await?)?,
    ))
}

async fn mcp(router: &Router, token: &str, operation: &str, arguments: Value) -> Result<Value> {
    let (status,result) = request(router,"/mcp",token,json!({"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":operation,"arguments":arguments}})).await?;
    assert_eq!(status, StatusCode::OK);
    Ok(result["result"]["structuredContent"].clone())
}

#[tokio::test]
async fn mcp_proposals_require_web_validation_and_current_group_authority() -> Result<()> {
    assert_eq!(
        std::env::var("MRJAM_SYNTHETIC_DATABASE_URL")
            .ok()
            .as_deref(),
        Some(URL),
        "literal synthetic fixture required"
    );
    let suffix = SystemTime::now().duration_since(UNIX_EPOCH)?.as_nanos();
    let name = format!("runtime_mcp_{suffix}");
    let files = Files(std::env::temp_dir().join(&name));
    std::fs::create_dir(&files.0)?;
    let admin = PgPoolOptions::new().max_connections(2).connect(URL).await?;
    // Names consist only of this fixed prefix and clock digits. Existing
    // fixtures are never reused or removed; CREATE collision fails closed.
    sqlx::raw_sql(sqlx::AssertSqlSafe(format!("CREATE ROLE {name} LOGIN PASSWORD 'synthetic_mcp_only' NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS"))).execute(&admin).await?;
    let creation = sqlx::raw_sql(sqlx::AssertSqlSafe(format!("CREATE DATABASE {name}")))
        .execute(&admin)
        .await;
    if let Err(error) = creation {
        sqlx::raw_sql(sqlx::AssertSqlSafe(format!("DROP ROLE {name}")))
            .execute(&admin)
            .await?;
        return Err(error.into());
    }
    let result = exercise(&name, &files).await;
    sqlx::raw_sql(sqlx::AssertSqlSafe(format!(
        "DROP DATABASE {name} WITH (FORCE)"
    )))
    .execute(&admin)
    .await?;
    sqlx::raw_sql(sqlx::AssertSqlSafe(format!("DROP ROLE {name}")))
        .execute(&admin)
        .await?;
    admin.close().await;
    result
}

async fn exercise(name: &str, files: &Files) -> Result<()> {
    let options = PgConnectOptions::from_str(URL)?.database(name);
    let admin = PgPoolOptions::new()
        .max_connections(2)
        .connect_with(options.clone())
        .await?;
    sqlx::raw_sql(include_str!("../../audition/migrations/001-schema.sql"))
        .execute(&admin)
        .await?;
    sqlx::raw_sql(include_str!(
        "../../audition/migrations/002-version-scope.sql"
    ))
    .execute(&admin)
    .await?;
    sqlx::raw_sql(sqlx::AssertSqlSafe(format!("GRANT USAGE ON SCHEMA audition TO {name}; GRANT SELECT ON audition.schema_migrations,audition.administrateurs TO {name}; GRANT SELECT,INSERT,DELETE ON audition.groupes TO {name}; GRANT SELECT,INSERT,UPDATE,DELETE ON audition.membres TO {name}; GRANT SELECT,INSERT,UPDATE ON audition.objets TO {name}; GRANT SELECT,INSERT ON audition.versions,audition.requetes,audition.audit TO {name}; GRANT USAGE,SELECT ON SEQUENCE audition.audit_id_seq TO {name}; GRANT EXECUTE ON FUNCTION audition.est_admin(),audition.role_groupe(text) TO {name}; INSERT INTO audition.administrateurs VALUES('invented.admin',true);"))).execute(&admin).await?;
    let pool = PgPoolOptions::new()
        .max_connections(2)
        .connect_with(options.username(name).password("synthetic_mcp_only"))
        .await?;
    let service = PgAudition::new(pool.clone());
    let now = i64::try_from(SystemTime::now().duration_since(UNIX_EPOCH)?.as_secs())?;
    let manager = VerifiedActor::from_authenticated_identity("invented.admin", Some(now))?;
    let group = service
        .execute(
            &manager,
            WriteChannel::Web,
            "creer_groupe",
            br#"{"nom":"Invented MCP class","cle":"synthetic-create-group"}"#,
            Timestamp::new(now)?,
        )
        .await?["id"]
        .clone();
    for (actor, role) in [
        ("invented.teacher", "enseignant"),
        ("invented.student", "eleve"),
    ] {
        service.execute(&manager,WriteChannel::Web,"habiliter",json!({"groupe":group,"acteur":actor,"role":role,"cle":format!("synthetic-habiliter-{role}")}).to_string().as_bytes(),Timestamp::new(now)?).await?;
    }
    let revoked = Arc::new(AtomicBool::new(false));
    let broker = Router::new()
        .route("/verify", get(verify))
        .route(
            "/verify-gestion",
            get(|| async { StatusCode::UNAUTHORIZED }),
        )
        .route(
            "/verify-mcp",
            get({
                let revoked = revoked.clone();
                move |headers: HeaderMap| {
                    let revoked = revoked.clone();
                    async move {
                        assert_eq!(headers["x-forwarded-host"], "audition.mrj.am");
                        assert!(!headers.contains_key("x-mrj-user"));
                        let token = headers.get("authorization").and_then(|v| v.to_str().ok());
                        let owner = match token {
                            Some("Bearer synthetic-teacher") => Some("invented.teacher"),
                            Some("Bearer synthetic-student") if !revoked.load(Ordering::SeqCst) => {
                                Some("invented.student")
                            }
                            _ => None,
                        };
                        match owner {
                            Some(owner) => (StatusCode::NO_CONTENT, [("x-mrj-user", owner)]),
                            None => (StatusCode::UNAUTHORIZED, [("cache-control", "no-store")]),
                        }
                    }
                }
            }),
        );
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await?;
    let endpoint = listener.local_addr()?;
    let broker_task = tokio::spawn(async move {
        let _ = axum::serve(listener, broker).await;
    });
    let html = b"<!doctype html><title>Invented MCP fixture</title>";
    std::fs::write(files.0.join("index.html"), html)?;
    let manifest = json!({"schema_version":1,"artifact":"synthetic","source_commits":{"synthetic":"0".repeat(40)},"style_revision":"0".repeat(40),"input_manifest_sha256":"0".repeat(64),"toolchains_lock_sha256":"0".repeat(64),"payload_sha256":{"index.html":digest(html)},"deployment_authorized":false,"runtime_qualification":"synthetic-only"});
    let bytes = serde_json::to_vec(&manifest)?;
    std::fs::write(files.0.join("artifact.json"), &bytes)?;
    let password = files.0.join("password");
    std::fs::write(&password, "synthetic_mcp_only")?;
    std::fs::set_permissions(&password, std::fs::Permissions::from_mode(0o600))?;
    let configuration = json!({"schema_version":1,"public_hosts":["audition.mrj.am"],"required_capabilities":["audition-mcp"],"assets":[{"host":"audition.mrj.am","directory":files.0,"manifest_sha256":digest(&bytes),"payload_prefix":"","mount":"/"}],"identity":{"endpoint":endpoint.to_string(),"protocol":"mrj-auth-v1"},"audition":{"transport":{"kind":"tcp","port":55432},"database":name,"username":name,"password_file":password,"schema":"audition","maximum_connections":2}});
    let router = mrjam_server::runtime::assemble(RuntimeConfiguration::from_bytes(
        &serde_json::to_vec(&configuration)?,
    )?)
    .await?;
    let result = scenario(&router, &admin, &group, &revoked).await;
    drop(router);
    broker_task.abort();
    pool.close().await;
    admin.close().await;
    result
}

async fn verify(headers: HeaderMap) -> (StatusCode, [(&'static str, &'static str); 1]) {
    assert_eq!(headers["x-forwarded-host"], "audition.mrj.am");
    if headers
        .get("cookie")
        .is_some_and(|v| v == "synthetic-teacher")
    {
        assert_eq!(headers["origin"], "https://audition.mrj.am");
        assert_eq!(headers["x-csrf-token"], "synthetic-csrf");
        (StatusCode::NO_CONTENT, [("x-mrj-user", "invented.teacher")])
    } else {
        (StatusCode::UNAUTHORIZED, [("cache-control", "no-store")])
    }
}

async fn scenario(
    router: &Router,
    admin: &PgPool,
    group: &Value,
    revoked: &AtomicBool,
) -> Result<()> {
    let initialize = json!({"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"synthetic-pg","version":"1"}}});
    let (status, result) = request(router, "/mcp", "synthetic-teacher", initialize).await?;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(result["result"]["protocolVersion"], "2025-06-18");
    let context = mcp(router, "synthetic-teacher", "contexte", json!({})).await?;
    assert_eq!(context["acteur"], "invented.teacher");
    let document = json!({"titre":"Invented open problem","consigne":"Discuss the square sign","attendus":[{"id":"sign","texte":"Explain sign"}],"criteres":[{"id":"reason","attendu":"sign","texte":"Justify","maximum":2}],"type":"ouverte","corrige":"SYNTHETIC_PRIVATE_CORRECTION"});
    let proposal = json!({"groupe":group,"document":document,"cle":"synthetic-mcp-proposal"});
    let activity = mcp(router, "synthetic-teacher", "activite", proposal.clone()).await?;
    assert_eq!(activity["document"]["validee"], false);
    assert_eq!(activity["document"]["version_prescrite"], 0);
    let repeated = mcp(router, "synthetic-teacher", "activite", proposal.clone()).await?;
    assert_eq!(activity, repeated);
    let (status, error) = request(
        router,
        "/api/audition/activite",
        "synthetic-teacher",
        proposal,
    )
    .await?;
    assert_eq!(status, StatusCode::CONFLICT);
    assert_eq!(error["erreur"], "cle_reutilisee_avec_autre_operation");
    let prescription = json!({"groupe":group,"activite":activity["id"],"eleves":["invented.student"],"echeance":0,"cle":"synthetic-prescription"});
    let blocked = mcp(
        router,
        "synthetic-teacher",
        "affecter",
        prescription.clone(),
    )
    .await?;
    assert_eq!(blocked["statut"], 409);
    assert_eq!(blocked["erreur"], "proposition_non_validee");
    let(status,official)=request(router,"/api/audition/activite","synthetic-teacher",json!({"groupe":group,"document":document,"id":activity["id"],"revision":activity["revision"],"cle":"synthetic-web-validation"})).await?;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(official["document"]["validee"], true);
    let assigned = mcp(router, "synthetic-teacher", "affecter", prescription).await?;
    assert!(assigned["id"].is_string());
    let session = mcp(
        router,
        "synthetic-student",
        "ouvrir_seance",
        json!({"groupe":group,"affectation":assigned["id"],"cle":"synthetic-open-session"}),
    )
    .await?;
    assert!(session["seance"]["id"].is_string());
    assert!(!session.to_string().contains("SYNTHETIC_PRIVATE_CORRECTION"));
    let before: i64 = sqlx::query_scalar("SELECT count(*) FROM audition.versions")
        .fetch_one(admin)
        .await?;
    let(status,_)=request(router,"/mcp","synthetic-teacher",json!({"jsonrpc":"2.0","method":"tools/call","params":{"name":"activite","arguments":{"groupe":group,"document":document,"cle":"synthetic-notification"}}})).await?;
    assert_eq!(status, StatusCode::BAD_REQUEST);
    let after: i64 = sqlx::query_scalar("SELECT count(*) FROM audition.versions")
        .fetch_one(admin)
        .await?;
    assert_eq!(before, after);
    let denied = mcp(router, "synthetic-teacher", "diagnostic", json!({})).await?;
    assert_eq!(denied["statut"], 403);
    revoked.store(true, Ordering::SeqCst);
    let(status,_)=request(router,"/mcp","synthetic-student",json!({"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"contexte","arguments":{}}})).await?;
    assert_eq!(status, StatusCode::UNAUTHORIZED);
    sqlx::query("DELETE FROM audition.membres WHERE groupe=$1 AND acteur='invented.teacher'")
        .bind(group.as_str().ok_or("missing group")?)
        .execute(admin)
        .await?;
    let denied = mcp(
        router,
        "synthetic-teacher",
        "activite",
        json!({"groupe":group,"document":document,"cle":"synthetic-mcp-proposal"}),
    )
    .await?;
    assert_eq!(denied["statut"], 403);
    Ok(())
}

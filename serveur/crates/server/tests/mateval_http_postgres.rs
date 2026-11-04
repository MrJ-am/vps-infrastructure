//! Explicitly selected HTTP + PostgreSQL test. Only the named synthetic cluster
//! is accepted before a socket is opened; it never falls back to a real database.
use axum::{
    Router,
    body::{Body, to_bytes},
    http::{Method, Request, StatusCode},
};
use mrjam_server::{application_with_mateval, mateval::MatevalState};
use serde_json::{Value, json};
use sqlx::{
    postgres::{PgConnectOptions, PgPoolOptions},
    types::Json,
};
use std::{
    str::FromStr,
    time::{SystemTime, UNIX_EPOCH},
};
use tower::ServiceExt;

type TestResult<T> = Result<T, Box<dyn std::error::Error>>;

const SYNTHETIC_DATABASE_URL: &str =
    "postgresql://mrjam_synthetic:mrjam_synthetic_only@127.0.0.1:55432/mrjam_synthetic";

fn synthetic_options(url: &str) -> Result<PgConnectOptions, &'static str> {
    // Compare raw bytes before invoking the SQLx parser: query parameters can
    // select a Unix socket, and unknown options may be logged by that parser.
    if url != SYNTHETIC_DATABASE_URL {
        return Err("only the exact declared synthetic fixture URL is accepted");
    }
    PgConnectOptions::from_str(SYNTHETIC_DATABASE_URL)
        .map_err(|_| "invalid declared synthetic database fixture")
}

async fn request(
    router: &Router,
    method: Method,
    path: &str,
    secret: Option<&str>,
    body: Option<&Value>,
) -> TestResult<(StatusCode, Value)> {
    let mut request = Request::builder().method(method).uri(path);
    if let Some(secret) = secret {
        request = request.header("x-session-token", secret);
    }
    let bytes = match body {
        Some(body) => {
            request = request
                .header("origin", mrjam_mateval::WRITE_ORIGIN)
                .header("x-matheval-request", "1")
                .header("content-type", "application/json");
            serde_json::to_vec(body)?
        }
        None => Vec::new(),
    };
    let response = router
        .clone()
        .oneshot(request.body(Body::from(bytes))?)
        .await?;
    let status = response.status();
    assert_eq!(response.headers()["cache-control"], "no-store");
    let value = serde_json::from_slice(&to_bytes(response.into_body(), 65_536).await?)?;
    Ok((status, value))
}

#[test]
fn synthetic_cluster_guard_rejects_other_targets_without_connecting() {
    for url in [
        "postgresql://mrjam_synthetic:synthetic@203.0.113.10:55432/mrjam_synthetic",
        "postgresql://mrjam_synthetic:synthetic@127.0.0.1:55432/production",
        "postgresql://mrjam_synthetic:synthetic@127.0.0.1:5432/mrjam_synthetic",
        "postgresql://postgres:synthetic@127.0.0.1:55432/mrjam_synthetic",
        "postgresql://mrjam_synthetic:synthetic@localhost:55432/mrjam_synthetic",
        "postgresql://mrjam_synthetic:mrjam_synthetic_only@127.0.0.1:55432/mrjam_synthetic?host=%2Fsynthetic-socket",
        "postgresql://mrjam_synthetic:mrjam_synthetic_only@127.0.0.1:55432/mrjam_synthetic?unknown=SYNTHETIC_PRIVATE_MARKER",
    ] {
        assert!(synthetic_options(url).is_err());
    }
    assert!(synthetic_options(SYNTHETIC_DATABASE_URL).is_ok());
}

#[tokio::test]
async fn http_creates_reads_saves_and_rejects_other_participation_secrets() -> TestResult<()> {
    let url = std::env::var("MRJAM_SYNTHETIC_DATABASE_URL")
        .map_err(|_| "explicit synthetic PostgreSQL is required for this selected test")?;
    let options = synthetic_options(&url)?;
    let admin = PgPoolOptions::new()
        .max_connections(2)
        .connect_with(options.clone())
        .await?;
    let schema = format!(
        "mateval_http_synthetic_{}",
        SystemTime::now().duration_since(UNIX_EPOCH)?.as_nanos()
    );
    sqlx::query(sqlx::AssertSqlSafe(format!("CREATE SCHEMA {schema}")))
        .execute(&admin)
        .await?;
    sqlx::query("DO $block$ BEGIN IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='mateval_synthetic_app') THEN CREATE ROLE mateval_synthetic_app LOGIN PASSWORD 'mateval_synthetic_only' NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS; END IF; END $block$").execute(&admin).await?;
    let setup = PgPoolOptions::new()
        .max_connections(1)
        .connect_with(options.clone().options([("search_path", schema.as_str())]))
        .await?;
    sqlx::raw_sql(include_str!(
        "../../../components/mateval/migrations/001-collecte.sql"
    ))
    .execute(&setup)
    .await?;
    for grant in [
        format!("GRANT USAGE ON SCHEMA {schema} TO mateval_synthetic_app"),
        format!("GRANT SELECT ON {schema}.corpus TO mateval_synthetic_app"),
        format!("GRANT SELECT,INSERT,UPDATE ON {schema}.participations TO mateval_synthetic_app"),
        format!("GRANT SELECT,INSERT,DELETE ON {schema}.answers TO mateval_synthetic_app"),
        format!("GRANT SELECT,INSERT ON {schema}.interaction_events TO mateval_synthetic_app"),
    ] {
        // The only interpolation is a locally constructed numeric schema suffix.
        sqlx::query(sqlx::AssertSqlSafe(grant))
            .execute(&admin)
            .await?;
    }
    let corpus = json!({"version":"1.0.0","questions":[
        {"id":"R01","family":"f1","level":"synthetic","domain":"fixture","statement":"Entirely invented HTTP question","productions":[{"id":"R01-1","content":"Entirely invented HTTP production"}]}
    ]});
    sqlx::query("INSERT INTO corpus(version,digest,bank,codebook) VALUES('1.0.0','synthetic-http-only',$1,'{}')")
        .bind(Json(corpus)).execute(&setup).await?;
    let app = PgPoolOptions::new()
        .max_connections(2)
        .connect_with(
            options
                .username("mateval_synthetic_app")
                .password("mateval_synthetic_only")
                .options([("search_path", schema.as_str())]),
        )
        .await?;
    let privileged: bool = sqlx::query_scalar("SELECT rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls FROM pg_roles WHERE rolname=current_user").fetch_one(&app).await?;
    assert!(!privileged);
    let router = application_with_mateval(MatevalState::with_service(mrjam_mateval::Service::new(
        app.clone(),
    )));
    let id = "00000000-0000-4000-8000-000000000002";
    let secret = "a".repeat(64);
    let create =
        json!({"id":id,"secret":secret,"bankVersion":"1.0.0","levels":["synthetic"],"seed":1});
    let (status, session) = request(
        &router,
        Method::POST,
        "/matheval/api/sessions",
        None,
        Some(&create),
    )
    .await?;
    assert_eq!(status, StatusCode::CREATED);
    assert_eq!(session["id"], id);
    assert!(session.get("secret").is_none());
    assert!(session.get("token_hash").is_none());
    let path = format!("/matheval/api/sessions/{id}");
    let (status, _) = request(&router, Method::GET, &path, Some(&"b".repeat(64)), None).await?;
    assert_eq!(status, StatusCode::UNAUTHORIZED);
    let (status, read) = request(&router, Method::GET, &path, Some(&secret), None).await?;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(read["id"], id);
    let checkpoint = json!({"revision":1,"final":false,"snapshot":{"answers":{"R01-1":{"note":0,"initialNote":null,"coordinates":{"x":0,"y":0,"z":0},"evaluatedAxes":[]}},"skippedQuestions":[],"progress":{"mode":"running","index":0,"selected":"R01-1","exposed":{"R01":1},"reader":false,"tour":-1}},"events":[{"event":"grade","questionId":"R01","productionId":"R01-1","at":"2024-02-29T12:00:00Z","elapsedMs":100,"value":0}]});
    let (status, saved) = request(
        &router,
        Method::PUT,
        &path,
        Some(&secret),
        Some(&checkpoint),
    )
    .await?;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(saved["revision"], 1);
    let (status, repeated) = request(
        &router,
        Method::PUT,
        &path,
        Some(&secret),
        Some(&checkpoint),
    )
    .await?;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(saved, repeated);
    let (status, events) = request(
        &router,
        Method::GET,
        &format!("{path}/events"),
        Some(&secret),
        None,
    )
    .await?;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(
        events
            .as_array()
            .ok_or("synthetic events response missing")?
            .len(),
        1
    );
    drop(router);
    app.close().await;
    setup.close().await;
    sqlx::query(sqlx::AssertSqlSafe(format!("DROP SCHEMA {schema} CASCADE")))
        .execute(&admin)
        .await?;
    admin.close().await;
    Ok(())
}

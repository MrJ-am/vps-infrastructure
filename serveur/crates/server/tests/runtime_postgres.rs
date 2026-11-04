//! Real runtime assembly against a disposable, explicitly named local fixture.
use axum::{
    Router,
    body::{Body, to_bytes},
    http::{HeaderMap, Request, StatusCode},
};
use mrjam_server::{runtime_config::RuntimeConfiguration, runtime_files::digest};
use serde_json::{Value, json};
use sqlx::{
    PgPool,
    postgres::{PgConnectOptions, PgPoolOptions},
    types::Json,
};
use std::{
    os::unix::fs::PermissionsExt,
    path::PathBuf,
    str::FromStr,
    time::{SystemTime, UNIX_EPOCH},
};
use tower::ServiceExt;

const URL: &str =
    "postgresql://mrjam_synthetic:mrjam_synthetic_only@127.0.0.1:55432/mrjam_synthetic";
type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;
fn public_bank() -> Value {
    json!({"version":"1.0.0","questions":[{"id":"R01","family":"f1","level":"synthetic","domain":"fixture","statement":"Invented runtime question","productions":[{"id":"R01-1","content":"Invented runtime production"}]}]})
}
struct Files(PathBuf);
impl Drop for Files {
    fn drop(&mut self) {
        let _ = std::fs::remove_dir_all(&self.0);
    }
}

async fn request(
    router: &Router,
    method: &str,
    path: &str,
    cookie: Option<&str>,
    body: Option<Value>,
) -> Result<(StatusCode, HeaderMap, Value)> {
    let mut request = Request::builder()
        .method(method)
        .uri(path)
        .header("host", "principiipetit.io");
    if let Some(cookie) = cookie {
        request = request.header("cookie", cookie);
    }
    let bytes = if let Some(body) = body {
        request = request
            .header("origin", "https://principiipetit.io")
            .header("x-matheval-request", "1")
            .header("content-type", "application/json");
        serde_json::to_vec(&body)?
    } else {
        vec![]
    };
    let response = router
        .clone()
        .oneshot(request.body(Body::from(bytes))?)
        .await?;
    let status = response.status();
    let headers = response.headers().clone();
    let body: Value = serde_json::from_slice(&to_bytes(response.into_body(), 1_048_576).await?)?;
    Ok((status, headers, body))
}

async fn exercise(
    admin: &PgPool,
    schema: &str,
    role: &str,
    admin_role: &str,
    files: &Files,
) -> Result<()> {
    let root = &files.0;
    let pass = root.join("password");
    std::fs::write(&pass, "synthetic-runtime-only")?;
    std::fs::set_permissions(&pass, std::fs::Permissions::from_mode(0o600))?;
    let activation = root.join("activation");
    std::fs::write(&activation, digest("c".repeat(64).as_bytes()))?;
    std::fs::set_permissions(&activation, std::fs::Permissions::from_mode(0o600))?;
    let html = b"<!doctype html><title>Synthetic runtime integration</title>";
    std::fs::create_dir(root.join("admin"))?;
    let mut payload = serde_json::Map::new();
    for name in [
        "index.html",
        "survey.js",
        "enquete.js",
        "admin/index.html",
        "admin/administration.js",
        "admin/admin.js",
    ] {
        std::fs::write(root.join(name), html)?;
        payload.insert(name.into(), json!(digest(html)));
    }
    std::fs::create_dir(root.join("data"))?;
    let bank = serde_json::to_vec(&public_bank())?;
    std::fs::write(root.join("data/bank.json"), &bank)?;
    payload.insert("data/bank.json".into(), json!(digest(&bank)));
    let manifest = json!({"schema_version":1,"artifact":"synthetic","source_commits":{"synthetic":"0".repeat(40)},"style_revision":"0".repeat(40),"input_manifest_sha256":"0".repeat(64),"toolchains_lock_sha256":"0".repeat(64),"payload_sha256":payload,"deployment_authorized":false,"runtime_qualification":"synthetic-only"});
    let bytes = serde_json::to_vec(&manifest)?;
    std::fs::write(root.join("artifact.json"), &bytes)?;
    let database = |username: &str| json!({"transport":{"kind":"tcp","port":55432},"database":"mrjam_synthetic","username":username,"password_file":pass,"schema":schema,"maximum_connections":2});
    let configuration = json!({"schema_version":1,"public_hosts":["principiipetit.io"],"required_capabilities":["static-assets","mateval-collection","mateval-administration"],"assets":[{"host":"principiipetit.io","directory":root,"manifest_sha256":digest(&bytes),"payload_prefix":"","mount":"/matheval/"}],"mateval":{"database":database(role),"administration_database":database(admin_role),"activation_sha256_file":activation},"identity":null,"vision":null,"audition":null});
    let mut historical = public_bank();
    historical["private_fixture_metadata"] = json!({"origin":"invented"});
    historical["questions"][0]["private_fixture_metadata"] = json!("invented question metadata");
    historical["questions"][0]["productions"][0]["private_fixture_metadata"] =
        json!("invented production metadata");
    sqlx::query(sqlx::AssertSqlSafe(format!(
        "UPDATE {schema}.corpus SET bank=$1"
    )))
    .bind(Json(&historical))
    .execute(admin)
    .await?;
    let formerly_aligned: bool = sqlx::query_scalar(sqlx::AssertSqlSafe(format!(
        "SELECT EXISTS(SELECT 1 FROM {schema}.corpus WHERE version='1.0.0' AND bank=$1)"
    )))
    .bind(Json(public_bank()))
    .fetch_one(admin)
    .await?;
    assert!(!formerly_aligned);
    let corpus_before: Json<Value> = sqlx::query_scalar(sqlx::AssertSqlSafe(format!(
        "SELECT to_jsonb(c) FROM {schema}.corpus c WHERE version='1.0.0'"
    )))
    .fetch_one(admin)
    .await?;
    let router = mrjam_server::runtime::assemble(RuntimeConfiguration::from_bytes(
        &serde_json::to_vec(&configuration)?,
    )?)
    .await?;
    let (status, _, ready) = request(&router, "GET", "/readyz", None, None).await?;
    assert_eq!(status, StatusCode::OK);
    let corpus_after: Json<Value> = sqlx::query_scalar(sqlx::AssertSqlSafe(format!(
        "SELECT to_jsonb(c) FROM {schema}.corpus c WHERE version='1.0.0'"
    )))
    .fetch_one(admin)
    .await?;
    assert_eq!(corpus_after.0, corpus_before.0);
    // No participation exists yet: exercise a missing version without deleting
    // the historical row or weakening its later foreign-key references.
    sqlx::query(sqlx::AssertSqlSafe(format!(
        "UPDATE {schema}.corpus SET version='1.0.1' WHERE version='1.0.0'"
    )))
    .execute(admin)
    .await?;
    assert_eq!(
        request(&router, "GET", "/readyz", None, None).await?.0,
        StatusCode::SERVICE_UNAVAILABLE
    );
    sqlx::query(sqlx::AssertSqlSafe(format!(
        "UPDATE {schema}.corpus SET version='1.0.0' WHERE version='1.0.1'"
    )))
    .execute(admin)
    .await?;
    assert_eq!(
        request(&router, "GET", "/readyz", None, None).await?.0,
        StatusCode::OK
    );
    assert_eq!(
        ready["capabilities"],
        configuration["required_capabilities"]
    );
    let (status,_,session)=request(&router,"POST","/matheval/api/sessions",None,Some(json!({"id":"00000000-0000-4000-8000-000000000034","secret":"a".repeat(64),"bankVersion":"1.0.0","levels":["synthetic"],"seed":1}))).await?;
    assert_eq!(status, StatusCode::CREATED);
    assert!(session.get("token_hash").is_none());
    let participation_before: Json<Value> = sqlx::query_scalar(sqlx::AssertSqlSafe(format!("SELECT to_jsonb(p) FROM {schema}.participations p WHERE id='00000000-0000-4000-8000-000000000034'"))).fetch_one(admin).await?;
    for path in [
        "/version",
        "/questions/0/id",
        "/questions/0/family",
        "/questions/0/level",
        "/questions/0/domain",
        "/questions/0/statement",
        "/questions/0/productions/0/id",
        "/questions/0/productions/0/content",
    ] {
        let mut changed = historical.clone();
        if let Some(value) = changed.pointer_mut(path) {
            *value = json!("invented mismatch");
        }
        sqlx::query(sqlx::AssertSqlSafe(format!(
            "UPDATE {schema}.corpus SET bank=$1"
        )))
        .bind(Json(changed))
        .execute(admin)
        .await?;
        assert_eq!(
            request(&router, "GET", "/readyz", None, None).await?.0,
            StatusCode::SERVICE_UNAVAILABLE
        );
    }
    let mut oversized = historical.clone();
    oversized["private_fixture_metadata"] = json!("x".repeat(5 * 1024 * 1024));
    sqlx::query(sqlx::AssertSqlSafe(format!(
        "UPDATE {schema}.corpus SET bank=$1"
    )))
    .bind(Json(oversized))
    .execute(admin)
    .await?;
    assert_eq!(
        request(&router, "GET", "/readyz", None, None).await?.0,
        StatusCode::SERVICE_UNAVAILABLE
    );
    sqlx::query(sqlx::AssertSqlSafe(format!(
        "UPDATE {schema}.corpus SET bank=$1"
    )))
    .bind(Json(&historical))
    .execute(admin)
    .await?;
    assert_eq!(
        request(&router, "GET", "/readyz", None, None).await?.0,
        StatusCode::OK
    );
    let participation_after: Json<Value> = sqlx::query_scalar(sqlx::AssertSqlSafe(format!("SELECT to_jsonb(p) FROM {schema}.participations p WHERE id='00000000-0000-4000-8000-000000000034'"))).fetch_one(admin).await?;
    assert_eq!(participation_after.0, participation_before.0);
    let corpus_after: Json<Value> = sqlx::query_scalar(sqlx::AssertSqlSafe(format!(
        "SELECT to_jsonb(c) FROM {schema}.corpus c WHERE version='1.0.0'"
    )))
    .fetch_one(admin)
    .await?;
    assert_eq!(corpus_after.0, corpus_before.0);
    let (status, _, _) = request(&router, "GET", "/matheval/api/admin/me", None, None).await?;
    assert_eq!(status, StatusCode::UNAUTHORIZED);
    sqlx::query(sqlx::AssertSqlSafe(format!(
        "UPDATE {schema}.corpus SET bank='{{\"version\":\"1.0.0\",\"questions\":[]}}'::jsonb"
    )))
    .execute(admin)
    .await?;
    let (status, _, _) = request(&router, "GET", "/readyz", None, None).await?;
    assert_eq!(status, StatusCode::SERVICE_UNAVAILABLE);
    sqlx::query(sqlx::AssertSqlSafe(format!(
        "UPDATE {schema}.corpus SET bank=$1"
    )))
    .bind(Json(public_bank()))
    .execute(admin)
    .await?;
    for extra in [
        "DELETE ON participations",
        "UPDATE(note) ON answers",
        "SELECT(password_hash) ON administrators",
    ] {
        let (privilege, table) = extra.split_once(" ON ").ok_or("invalid synthetic grant")?;
        sqlx::query(sqlx::AssertSqlSafe(format!(
            "GRANT {privilege} ON {schema}.{table} TO {role}"
        )))
        .execute(admin)
        .await?;
        let (status, _, _) = request(&router, "GET", "/readyz", None, None).await?;
        assert_eq!(status, StatusCode::SERVICE_UNAVAILABLE);
        sqlx::query(sqlx::AssertSqlSafe(format!(
            "REVOKE {privilege} ON {schema}.{table} FROM {role}"
        )))
        .execute(admin)
        .await?;
        let (status, _, _) = request(&router, "GET", "/readyz", None, None).await?;
        assert_eq!(status, StatusCode::OK);
    }
    let (status,headers,account)=request(&router,"POST","/matheval/api/admin/setup",None,Some(json!({"username":"synthetic_admin","password":"Entirely synthetic password 2026!","token":"c".repeat(64)}))).await?;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(account, json!({"username":"synthetic_admin"}));
    let cookie_header = headers
        .get("set-cookie")
        .ok_or("missing synthetic admin cookie")?
        .to_str()?;
    for attribute in [
        "Secure",
        "HttpOnly",
        "SameSite=Strict",
        "Path=/matheval/api/admin",
        "Max-Age=28800",
    ] {
        assert!(cookie_header.contains(attribute));
    }
    let cookie = cookie_header
        .split(';')
        .next()
        .ok_or("invalid synthetic cookie")?;
    let (status, _, account) =
        request(&router, "GET", "/matheval/api/admin/me", Some(cookie), None).await?;
    assert_eq!(status, StatusCode::OK);
    assert_eq!(account["username"], "synthetic_admin");
    let (status, _, _) = request(
        &router,
        "GET",
        "/matheval/api/admin/participations?page=1&page=2",
        Some(cookie),
        None,
    )
    .await?;
    assert_eq!(status, StatusCode::BAD_REQUEST);
    let (status, headers, _) = request(
        &router,
        "POST",
        "/matheval/api/admin/logout",
        Some(cookie),
        Some(json!({})),
    )
    .await?;
    assert_eq!(status, StatusCode::OK);
    assert!(headers["set-cookie"].to_str()?.contains("Max-Age=0"));
    let (status, _, _) =
        request(&router, "GET", "/matheval/api/admin/me", Some(cookie), None).await?;
    assert_eq!(status, StatusCode::UNAUTHORIZED);
    sqlx::query(sqlx::AssertSqlSafe(format!(
        "ALTER TABLE {schema}.answers RENAME TO answers_unavailable"
    )))
    .execute(admin)
    .await?;
    let (status, _, body) = request(&router, "GET", "/readyz", None, None).await?;
    assert_eq!(status, StatusCode::SERVICE_UNAVAILABLE);
    assert_eq!(body, json!({"error":{"code":"NOT_READY"}}));
    drop(router);
    Ok(())
}

#[tokio::test]
async fn configured_runtime_serves_collection_admin_and_tracks_real_schema_availability()
-> Result<()> {
    if std::env::var("MRJAM_SYNTHETIC_DATABASE_URL").as_deref() != Ok(URL)
        || std::env::vars_os().any(|(key, _)| key.to_string_lossy().starts_with("PG"))
    {
        return Err("explicit local synthetic fixture required".into());
    }
    let options = PgConnectOptions::from_str(URL)?;
    let admin = PgPoolOptions::new()
        .max_connections(2)
        .connect_with(options.clone())
        .await?;
    let id = SystemTime::now().duration_since(UNIX_EPOCH)?.as_nanos();
    let schema = format!("runtime_synthetic_{id}");
    let role = format!("runtime_c_{id}");
    let admin_role = format!("runtime_a_{id}");
    let files = Files(std::env::temp_dir().join(&schema));
    std::fs::create_dir(&files.0)?;
    sqlx::query(sqlx::AssertSqlSafe(format!("CREATE SCHEMA {schema}")))
        .execute(&admin)
        .await?;
    for name in [&role, &admin_role] {
        sqlx::query(sqlx::AssertSqlSafe(format!("CREATE ROLE {name} LOGIN PASSWORD 'synthetic-runtime-only' NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS"))).execute(&admin).await?;
        sqlx::query(sqlx::AssertSqlSafe(format!(
            "GRANT USAGE ON SCHEMA {schema} TO {name}"
        )))
        .execute(&admin)
        .await?;
    }
    let setup = PgPoolOptions::new()
        .max_connections(1)
        .connect_with(options.options([("search_path", schema.as_str())]))
        .await?;
    sqlx::raw_sql(include_str!(
        "../../../components/mateval/migrations/001-collecte.sql"
    ))
    .execute(&setup)
    .await?;
    sqlx::raw_sql(include_str!(
        "../../../components/mateval/migrations/002-sessions-administrateur.sql"
    ))
    .execute(&setup)
    .await?;
    for sql in [
        format!("GRANT SELECT ON {schema}.corpus TO {role}"),
        format!("GRANT SELECT,INSERT,UPDATE ON {schema}.participations TO {role}"),
        format!("GRANT SELECT,INSERT,DELETE ON {schema}.answers TO {role}"),
        format!("GRANT SELECT,INSERT ON {schema}.interaction_events TO {role}"),
        format!("GRANT SELECT ON ALL TABLES IN SCHEMA {schema} TO {admin_role}"),
        format!("GRANT INSERT,UPDATE(id) ON {schema}.administrators TO {admin_role}"),
        format!("GRANT INSERT,UPDATE,DELETE ON {schema}.administrator_sessions TO {admin_role}"),
        format!("GRANT USAGE ON SEQUENCE {schema}.administrators_id_seq TO {admin_role}"),
    ] {
        sqlx::query(sqlx::AssertSqlSafe(sql))
            .execute(&admin)
            .await?;
    }
    let bank = public_bank();
    sqlx::query(
        "INSERT INTO corpus(version,digest,bank,codebook) VALUES('1.0.0','synthetic-only',$1,'{}')",
    )
    .bind(Json(bank))
    .execute(&setup)
    .await?;
    let result = exercise(&admin, &schema, &role, &admin_role, &files).await;
    setup.close().await;
    sqlx::query(sqlx::AssertSqlSafe(format!("DROP SCHEMA {schema} CASCADE")))
        .execute(&admin)
        .await?;
    for name in [&role, &admin_role] {
        sqlx::query(sqlx::AssertSqlSafe(format!("DROP ROLE {name}")))
            .execute(&admin)
            .await?;
    }
    admin.close().await;
    result
}

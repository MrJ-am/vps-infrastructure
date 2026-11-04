//! Entirely invented files and loopback identity servers; no production fixtures.
use axum::{
    Router,
    body::{Body, to_bytes},
    http::{Method, Request, StatusCode, header},
    routing::get,
};
use mrjam_server::{
    identity::{IdentityClient, IdentityError},
    runtime_config::{IdentityConfiguration, RuntimeConfiguration},
    runtime_files,
};
use serde_json::{Value, json};
use std::{
    os::unix::fs::{PermissionsExt, symlink},
    path::{Path, PathBuf},
    time::{SystemTime, UNIX_EPOCH},
};
use tower::ServiceExt;

type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;
struct Fixture(PathBuf);
impl Fixture {
    fn new() -> Result<Self> {
        let path = std::env::temp_dir().join(format!(
            "mrjam_runtime_synthetic_{}_{}",
            std::process::id(),
            SystemTime::now().duration_since(UNIX_EPOCH)?.as_nanos()
        ));
        std::fs::create_dir(&path)?;
        Ok(Self(path))
    }
    fn root(&self) -> &Path {
        &self.0
    }
    fn config(&self) -> Result<Value> {
        let document = b"<!doctype html><title>Entirely invented runtime page</title>";
        std::fs::write(self.root().join("index.html"), document)?;
        let license = b"# Synthetic package documentation\n<script>not executed</script>";
        std::fs::write(self.root().join("README.md"), license)?;
        let manifest = json!({"schema_version":1,"artifact":"synthetic-elm","source_commits":{"synthetic":"0".repeat(40)},"style_revision":"0".repeat(40),"input_manifest_sha256":"1".repeat(64),"toolchains_lock_sha256":"2".repeat(64),"payload_sha256":{"index.html":runtime_files::digest(document),"README.md":runtime_files::digest(license)},"deployment_authorized":false,"runtime_qualification":"synthetic"});
        let bytes = serde_json::to_vec(&manifest)?;
        std::fs::write(self.root().join("artifact.json"), &bytes)?;
        Ok(
            json!({"schema_version":1,"public_hosts":["synthetic.invalid"],"required_capabilities":["static-assets"],"assets":[{"host":"synthetic.invalid","directory":self.root(),"manifest_sha256":runtime_files::digest(&bytes),"payload_prefix":"","mount":"/"}],"mateval":null,"identity":null,"vision":null,"audition":null}),
        )
    }
}
impl Drop for Fixture {
    fn drop(&mut self) {
        let _ = std::fs::remove_dir_all(&self.0);
    }
}

#[test]
fn check_config_validates_public_references_without_opening_runtime_dependencies() -> Result<()> {
    let fixture = Fixture::new()?;
    let mut config = fixture.config()?;
    config["public_hosts"] = json!(["principiipetit.io"]);
    config["assets"][0]["host"] = json!("principiipetit.io");
    config["assets"][0]["mount"] = json!("/matheval/");
    config["assets"][0]["directory"] = json!("/synthetic-unavailable/assets");
    config["mateval"] = json!({"database":{"transport":{"kind":"tcp","port":9},"database":"synthetic","username":"synthetic","password_file":"/synthetic-unavailable/credential","schema":"synthetic","maximum_connections":1}});
    config["identity"] = json!({"endpoint":"127.0.0.1:9","protocol":"mrj-auth-v1"});
    let file = fixture.root().join("runtime.json");
    std::fs::write(&file, serde_json::to_vec(&config)?)?;
    let output = std::process::Command::new(env!("CARGO_BIN_EXE_mrjam-server"))
        .args(["check-config"])
        .arg(&file)
        .env("PGHOST", "synthetic-selector-that-check-config-must-ignore")
        .output()?;
    assert!(output.status.success());
    assert_eq!(output.stdout, b"{\"code\":\"CONFIGURATION_VALID\"}\n");
    assert!(output.stderr.is_empty());
    config["unknown"] = json!("SYNTHETIC_UNECHOED_MARKER");
    std::fs::write(&file, serde_json::to_vec(&config)?)?;
    let output = std::process::Command::new(env!("CARGO_BIN_EXE_mrjam-server"))
        .args(["check-config"])
        .arg(&file)
        .output()?;
    assert_eq!(output.status.code(), Some(2));
    assert!(output.stdout.is_empty());
    assert_eq!(
        output.stderr,
        b"{\"code\":\"INVALID_RUNTIME_CONFIGURATION\"}\n"
    );
    Ok(())
}

#[tokio::test]
async fn vision_entry_routes_serve_only_the_fixed_manifested_shell() -> Result<()> {
    let fixture = Fixture::new()?;
    let mut config = fixture.config()?;
    config["public_hosts"] = json!(["vision.mrj.am"]);
    config["assets"][0]["host"] = json!("vision.mrj.am");
    let router = mrjam_server::runtime::assemble(RuntimeConfiguration::from_bytes(
        &serde_json::to_vec(&config)?,
    )?)
    .await?;
    let expected = std::fs::read(fixture.root().join("index.html"))?;
    for path in [
        "/connexion",
        "/docs",
        "/docs/",
        "/privacy",
        "/admission",
        "/invitation",
    ] {
        for method in [Method::GET, Method::HEAD, Method::POST] {
            let response = router
                .clone()
                .oneshot(
                    Request::builder()
                        .method(method.clone())
                        .uri(path)
                        .header("host", "vision.mrj.am")
                        .body(Body::empty())?,
                )
                .await?;
            if method == Method::POST {
                assert_eq!(response.status(), StatusCode::METHOD_NOT_ALLOWED);
            } else {
                assert_eq!(response.status(), StatusCode::OK);
                assert_eq!(
                    response.headers()[header::CONTENT_TYPE],
                    "text/html; charset=utf-8"
                );
                let body = to_bytes(response.into_body(), 4096).await?;
                assert_eq!(
                    body.as_ref(),
                    if method == Method::HEAD {
                        b""
                    } else {
                        expected.as_slice()
                    }
                );
            }
        }
    }
    for path in [
        "/unknown",
        "/connexion/",
        "/%63onnexion",
        "/docs/../connexion",
        "/api/unknown",
    ] {
        let response = router
            .clone()
            .oneshot(
                Request::builder()
                    .uri(path)
                    .header("host", "vision.mrj.am")
                    .body(Body::empty())?,
            )
            .await?;
        assert_eq!(
            response.status(),
            if path == "/api/unknown" {
                StatusCode::UNAUTHORIZED
            } else {
                StatusCode::NOT_FOUND
            }
        );
        assert_eq!(response.headers()[header::CONTENT_TYPE], "application/json");
    }
    config["public_hosts"] = json!(["synthetic.invalid"]);
    config["assets"][0]["host"] = json!("synthetic.invalid");
    let other = mrjam_server::runtime::assemble(RuntimeConfiguration::from_bytes(
        &serde_json::to_vec(&config)?,
    )?)
    .await?;
    let response = other
        .oneshot(
            Request::builder()
                .uri("/connexion")
                .header("host", "synthetic.invalid")
                .body(Body::empty())?,
        )
        .await?;
    assert_eq!(response.status(), StatusCode::NOT_FOUND);
    Ok(())
}

#[tokio::test]
async fn manifested_assets_are_exact_and_readiness_names_only_selected_capabilities() -> Result<()>
{
    let fixture = Fixture::new()?;
    let config = fixture.config()?;
    let router = mrjam_server::runtime::assemble(RuntimeConfiguration::from_bytes(
        &serde_json::to_vec(&config)?,
    )?)
    .await?;
    std::fs::write(fixture.root().join("index.html"), "REPLACED_SYNTHETIC_FILE")?;
    let response = router
        .clone()
        .oneshot(
            Request::builder()
                .uri("/")
                .header("host", "synthetic.invalid")
                .body(Body::empty())?,
        )
        .await?;
    assert_eq!(response.status(), StatusCode::OK);
    assert_eq!(
        response.headers()[header::CONTENT_TYPE],
        "text/html; charset=utf-8"
    );
    let body = to_bytes(response.into_body(), 4096).await?;
    assert!(String::from_utf8(body.to_vec())?.contains("Entirely invented runtime page"));
    let license = router
        .clone()
        .oneshot(
            Request::builder()
                .uri("/README.md")
                .header("host", "synthetic.invalid")
                .body(Body::empty())?,
        )
        .await?;
    assert_eq!(license.status(), StatusCode::OK);
    assert_eq!(
        license.headers()[header::CONTENT_TYPE],
        "text/plain; charset=utf-8"
    );
    for path in [
        "/.env",
        "/artifact.json",
        "/../index.html",
        "/%2e%2e/index.html",
        "/not-in-manifest",
    ] {
        let response = router
            .clone()
            .oneshot(
                Request::builder()
                    .uri(path)
                    .header("host", "synthetic.invalid")
                    .body(Body::empty())?,
            )
            .await?;
        assert_eq!(response.status(), StatusCode::NOT_FOUND);
    }
    let wrong = router
        .clone()
        .oneshot(
            Request::builder()
                .uri("/")
                .header("host", "not-declared.invalid")
                .body(Body::empty())?,
        )
        .await?;
    assert_eq!(wrong.status(), StatusCode::MISDIRECTED_REQUEST);
    let ready = router
        .oneshot(Request::builder().uri("/readyz").body(Body::empty())?)
        .await?;
    assert_eq!(ready.status(), StatusCode::OK);
    let status: Value = serde_json::from_slice(&to_bytes(ready.into_body(), 4096).await?)?;
    assert_eq!(
        status,
        json!({"status":"ready","scope":"configured-capabilities-only","capabilities":["static-assets"]})
    );
    Ok(())
}

#[tokio::test]
async fn public_license_and_static_host_marker_keep_exact_plaintext_bytes() -> Result<()> {
    let fixture = Fixture::new()?;
    let mut config = fixture.config()?;
    let manifest_path = fixture.root().join("artifact.json");
    let mut manifest: Value = serde_json::from_slice(&std::fs::read(&manifest_path)?)?;
    let license = b"Invented distribution license\n<script>plain text only</script>";
    std::fs::create_dir(fixture.root().join("katex"))?;
    for (name, bytes) in [
        ("katex/LICENSE", license.as_slice()),
        (".nojekyll", b"".as_slice()),
    ] {
        std::fs::write(fixture.root().join(name), bytes)?;
        manifest["payload_sha256"][name] = json!(runtime_files::digest(bytes));
    }
    let bytes = serde_json::to_vec(&manifest)?;
    std::fs::write(&manifest_path, &bytes)?;
    config["assets"][0]["manifest_sha256"] = json!(runtime_files::digest(&bytes));
    let router = mrjam_server::runtime::assemble(RuntimeConfiguration::from_bytes(
        &serde_json::to_vec(&config)?,
    )?)
    .await?;
    for (path, expected) in [
        ("/katex/LICENSE", license.as_slice()),
        ("/.nojekyll", b"".as_slice()),
    ] {
        let response = router
            .clone()
            .oneshot(
                Request::builder()
                    .uri(path)
                    .header("host", "synthetic.invalid")
                    .body(Body::empty())?,
            )
            .await?;
        assert_eq!(response.status(), StatusCode::OK);
        assert_eq!(
            response.headers()[header::CONTENT_TYPE],
            "text/plain; charset=utf-8"
        );
        assert_eq!(response.headers()["x-content-type-options"], "nosniff");
        assert_eq!(
            to_bytes(response.into_body(), 4096).await?.as_ref(),
            expected
        );
    }
    // Recognition of two public names must not expose arbitrary dotfiles,
    // licenses outside the manifest or other extensionless files.
    for path in ["/.env", "/LICENSE", "/katex/OTHER"] {
        let response = router
            .clone()
            .oneshot(
                Request::builder()
                    .uri(path)
                    .header("host", "synthetic.invalid")
                    .body(Body::empty())?,
            )
            .await?;
        assert_eq!(response.status(), StatusCode::NOT_FOUND);
    }
    std::fs::write(fixture.root().join(".env"), b"INVENTED_NO_SECRET")?;
    manifest["payload_sha256"][".env"] = json!(runtime_files::digest(b"INVENTED_NO_SECRET"));
    let bytes = serde_json::to_vec(&manifest)?;
    std::fs::write(manifest_path, &bytes)?;
    config["assets"][0]["manifest_sha256"] = json!(runtime_files::digest(&bytes));
    assert!(
        mrjam_server::runtime::assemble(RuntimeConfiguration::from_bytes(&serde_json::to_vec(
            &config
        )?,)?)
        .await
        .is_err()
    );
    Ok(())
}

#[tokio::test]
async fn startup_refuses_tampered_assets_and_unimplemented_required_capabilities() -> Result<()> {
    let fixture = Fixture::new()?;
    let mut config = fixture.config()?;
    std::fs::write(fixture.root().join("index.html"), "tampered-synthetic")?;
    assert!(
        mrjam_server::runtime::assemble(RuntimeConfiguration::from_bytes(&serde_json::to_vec(
            &config
        )?)?)
        .await
        .is_err()
    );
    config["required_capabilities"] = json!(["mateval-collection"]);
    assert!(RuntimeConfiguration::from_bytes(&serde_json::to_vec(&config)?).is_err());
    config["required_capabilities"] = json!(["static-assets", "static-assets"]);
    assert!(RuntimeConfiguration::from_bytes(&serde_json::to_vec(&config)?).is_err());
    Ok(())
}

#[test]
fn credentials_and_parent_links_are_refused_without_following_them() -> Result<()> {
    let fixture = Fixture::new()?;
    let private = fixture.root().join("credential");
    std::fs::write(&private, "synthetic-only\n")?;
    std::fs::set_permissions(&private, std::fs::Permissions::from_mode(0o644))?;
    assert!(runtime_files::credential(&private).is_err());
    std::fs::set_permissions(&private, std::fs::Permissions::from_mode(0o600))?;
    assert_eq!(runtime_files::credential(&private)?, "synthetic-only");
    std::fs::set_permissions(&private, std::fs::Permissions::from_mode(0o440))?;
    assert!(runtime_files::credential(&private).is_err());
    std::fs::set_permissions(&private, std::fs::Permissions::from_mode(0o600))?;
    symlink(fixture.root(), fixture.root().join("parent"))?;
    assert!(runtime_files::credential(&fixture.root().join("parent/credential")).is_err());
    symlink(&private, fixture.root().join("linked"))?;
    assert!(runtime_files::credential(&fixture.root().join("linked")).is_err());
    assert!(runtime_files::read_regular(fixture.root(), 65_536, false).is_err());
    Ok(())
}

async fn identity_fixture(
    status: StatusCode,
    user: Option<&'static str>,
) -> Result<(IdentityClient, tokio::task::JoinHandle<()>)> {
    let app = Router::new().route(
        "/verify",
        get(move |headers: axum::http::HeaderMap| async move {
            assert_eq!(headers["x-forwarded-host"], "synthetic.invalid");
            assert_eq!(headers["x-forwarded-proto"], "https");
            assert!(!headers.contains_key("x-mrj-user"));
            let mut response = axum::response::Response::builder().status(status);
            if let Some(value) = user {
                response = response.header("x-mrj-user", value);
            }
            response.body(Body::empty()).unwrap_or_default()
        }),
    );
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await?;
    let client = IdentityClient::new(&IdentityConfiguration {
        endpoint: listener.local_addr()?,
        protocol: "mrj-auth-v1".into(),
    })?;
    let task = tokio::spawn(async move {
        let _ = axum::serve(listener, app).await;
    });
    Ok((client, task))
}

#[tokio::test]
async fn identity_comes_from_verified_response_not_request_headers() -> Result<()> {
    let (client, task) =
        identity_fixture(StatusCode::NO_CONTENT, Some("synthetic_verified_user")).await?;
    let mut headers = axum::http::HeaderMap::new();
    headers.insert(
        "cookie",
        header::HeaderValue::from_static("__Secure-mrj_session=synthetic-session"),
    );
    headers.insert(
        "x-mrj-user",
        header::HeaderValue::from_static("forged_other_user"),
    );
    let identity = client
        .verify_browser("synthetic.invalid", &Method::GET, &headers, false)
        .await
        .map_err(|_| "identity fixture failed")?;
    assert_eq!(identity.owner(), "synthetic_verified_user");
    assert!(!identity.elevated());
    assert!(matches!(
        client
            .verify_browser("synthetic.invalid", &Method::POST, &headers, false)
            .await,
        Err(IdentityError::Forbidden)
    ));
    task.abort();
    Ok(())
}

#[tokio::test]
async fn identity_failures_redirects_and_missing_principals_stay_closed() -> Result<()> {
    for (status, user) in [
        (StatusCode::UNAUTHORIZED, None),
        (StatusCode::FORBIDDEN, None),
        (StatusCode::OK, Some("synthetic")),
        (StatusCode::FOUND, Some("synthetic")),
        (StatusCode::NO_CONTENT, None),
        (StatusCode::NO_CONTENT, Some("invalid identity")),
    ] {
        let (client, task) = identity_fixture(status, user).await?;
        let mut headers = axum::http::HeaderMap::new();
        headers.insert(
            "cookie",
            header::HeaderValue::from_static("synthetic=credential"),
        );
        assert!(
            client
                .verify_browser("synthetic.invalid", &Method::GET, &headers, false)
                .await
                .is_err()
        );
        task.abort();
    }
    Ok(())
}

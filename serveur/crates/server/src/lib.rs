//! Serveur d'assemblage local. L'identité non qualifiée reste refusée.
//!
//! La disponibilité HTTP ne prouve ni la disponibilité des domaines, ni une
//! autorisation d'exploiter des données. Aucun contenu de requête n'est journalisé.

mod admission;
pub mod config;
mod database;
mod embeddings;
pub mod identity;
pub mod mateval;
mod mateval_admin;
mod mcp;
mod mcp_audition;
pub mod runtime;
pub mod runtime_config;
pub mod runtime_files;
pub mod static_assets;
mod strict_json;
mod vision_admission;

use axum::{
    Json, Router,
    extract::Request,
    http::{StatusCode, header},
    middleware::{self, Next},
    response::{IntoResponse, Response},
    routing::{any, get},
};
use serde::Serialize;
use std::{future::Future, time::Duration};
use tokio::net::TcpListener;

pub const REQUEST_TIMEOUT: Duration = Duration::from_secs(10);

#[derive(Serialize)]
struct ErrorEnvelope {
    error: SafeError,
}

#[derive(Serialize)]
struct SafeError {
    code: &'static str,
}

fn error_response(status: StatusCode, code: &'static str) -> Response {
    (
        status,
        Json(ErrorEnvelope {
            error: SafeError { code },
        }),
    )
        .into_response()
}

async fn health() -> impl IntoResponse {
    Json(serde_json::json!({"status": "ok"}))
}

async fn not_ready() -> Response {
    error_response(StatusCode::SERVICE_UNAVAILABLE, "NOT_READY")
}

async fn unauthenticated() -> Response {
    // Ni un header X-Mrj-User ni un jeton fourni par l'appelant ne constitue
    // une identité vérifiée. Aucun parseur métier ou accès SQL n'est appelé.
    error_response(StatusCode::UNAUTHORIZED, "UNAUTHENTICATED")
}

async fn not_found() -> Response {
    error_response(StatusCode::NOT_FOUND, "NOT_FOUND")
}

async fn method_not_allowed() -> Response {
    error_response(StatusCode::METHOD_NOT_ALLOWED, "METHOD_NOT_ALLOWED")
}

async fn deadline(request: Request, next: Next) -> Response {
    match tokio::time::timeout(REQUEST_TIMEOUT, next.run(request)).await {
        Ok(response) => response,
        Err(_) => error_response(StatusCode::GATEWAY_TIMEOUT, "REQUEST_TIMEOUT"),
    }
}

async fn response_policy(request: Request, next: Next) -> Response {
    let mut response = next.run(request).await;
    response.headers_mut().insert(
        "x-mrjam-source",
        header::HeaderValue::from_static("vps-infrastructure"),
    );
    response.headers_mut().insert(
        header::CACHE_CONTROL,
        header::HeaderValue::from_static("no-store"),
    );
    response.headers_mut().insert(
        header::X_CONTENT_TYPE_OPTIONS,
        header::HeaderValue::from_static("nosniff"),
    );
    response
}

/// Assemble les routes d'amorçage sans aucune capacité de données.
pub fn application() -> Router {
    application_with_mateval(mateval::MatevalState::default())
}

/// Le service injecté reste distinct du mode CLI d'amorçage sans capacité SQL.
pub fn application_with_mateval(mateval: mateval::MatevalState) -> Router {
    transport_policy(
        Router::new()
            .route("/healthz", get(health))
            .route("/readyz", get(not_ready))
            .route("/mcp", any(unauthenticated))
            .route("/api", any(unauthenticated))
            .route("/api/{*path}", any(unauthenticated))
            .merge(mateval::routes(mateval))
            .fallback(not_found)
            .method_not_allowed_fallback(method_not_allowed),
    )
}

pub(crate) fn transport_policy(router: Router) -> Router {
    router
        .layer(middleware::from_fn_with_state(
            admission::Admission::new(),
            admission::admit,
        ))
        .layer(middleware::from_fn(deadline))
        .layer(middleware::from_fn(response_policy))
}

/// Catalogue déclaratif uniquement, validé aussi par les types du SDK MCP.
/// Aucun transport MCP ni aucune opération métier n'est exécuté par cette API.
pub fn vision_catalogue() -> Result<serde_json::Value, &'static str> {
    let catalogue = mrjam_vision::Catalogue::officiel().map_err(|_| "INVALID_VISION_CATALOGUE")?;
    let value = serde_json::Value::Array(catalogue.outils().to_vec());
    let _: Vec<rmcp::model::Tool> =
        serde_json::from_value(value.clone()).map_err(|_| "INVALID_MCP_TOOL_DECLARATIONS")?;
    Ok(value)
}

/// La fermeture attend les requêtes en cours, sans délai de destruction forcée.
pub async fn serve<F>(listener: TcpListener, router: Router, shutdown: F) -> std::io::Result<()>
where
    F: Future<Output = ()> + Send + 'static,
{
    axum::serve(listener, router)
        .with_graceful_shutdown(shutdown)
        .await
}

#[cfg(test)]
mod tests {
    use super::application;
    use axum::{
        body::{Body, to_bytes},
        http::{Request, StatusCode},
    };
    use tower::ServiceExt;

    #[tokio::test]
    async fn health_is_not_readiness() -> Result<(), Box<dyn std::error::Error>> {
        let health = application()
            .oneshot(Request::builder().uri("/healthz").body(Body::empty())?)
            .await?;
        assert_eq!(health.status(), StatusCode::OK);
        assert_eq!(health.headers()["cache-control"], "no-store");
        assert_eq!(
            to_bytes(health.into_body(), 1024).await?.as_ref(),
            br#"{"status":"ok"}"#
        );
        let ready = application()
            .oneshot(Request::builder().uri("/readyz").body(Body::empty())?)
            .await?;
        assert_eq!(ready.status(), StatusCode::SERVICE_UNAVAILABLE);
        Ok(())
    }

    #[tokio::test]
    async fn unverified_headers_never_authorize_or_echo_payloads()
    -> Result<(), Box<dyn std::error::Error>> {
        for path in [
            "/mcp",
            "/api",
            "/api/web/lire",
            "/api/v1/health",
            "/api/v1/SYNTHETIC_PRIVATE_MARKER",
        ] {
            let response = application()
                .oneshot(
                    Request::builder()
                        .method("POST")
                        .uri(path)
                        .header("x-mrj-user", "SYNTHETIC_PRIVATE_MARKER")
                        .header("x-vision-authenticated", "1")
                        .header("authorization", "Bearer SYNTHETIC_PRIVATE_MARKER")
                        .body(Body::from("{SYNTHETIC_PRIVATE_MARKER invalid-json"))?,
                )
                .await?;
            assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
            assert_eq!(
                to_bytes(response.into_body(), 1024).await?.as_ref(),
                br#"{"error":{"code":"UNAUTHENTICATED"}}"#
            );
        }
        Ok(())
    }
}

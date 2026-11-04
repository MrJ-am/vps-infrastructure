use axum::{
    body::{Body, to_bytes},
    http::{Request, StatusCode},
};
use mrjam_server::application;
use tower::ServiceExt;

#[tokio::test]
async fn head_preserves_health_and_readiness_without_a_body()
-> Result<(), Box<dyn std::error::Error>> {
    for (path, expected) in [
        ("/healthz", StatusCode::OK),
        ("/readyz", StatusCode::SERVICE_UNAVAILABLE),
    ] {
        let response = application()
            .oneshot(
                Request::builder()
                    .method("HEAD")
                    .uri(path)
                    .body(Body::empty())?,
            )
            .await?;
        assert_eq!(response.status(), expected);
        assert_eq!(response.headers()["cache-control"], "no-store");
        assert_eq!(response.headers()["x-content-type-options"], "nosniff");
        assert_eq!(response.headers()["x-mrjam-source"], "vps-infrastructure");
        assert!(to_bytes(response.into_body(), 1024).await?.is_empty());
    }
    Ok(())
}

#[tokio::test]
async fn post_cannot_turn_a_readiness_probe_into_an_operation()
-> Result<(), Box<dyn std::error::Error>> {
    let response = application()
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/readyz")
                .body(Body::empty())?,
        )
        .await?;
    assert_eq!(response.status(), StatusCode::METHOD_NOT_ALLOWED);
    assert_eq!(response.headers()["cache-control"], "no-store");
    assert_eq!(response.headers()["x-content-type-options"], "nosniff");
    assert_eq!(response.headers()["x-mrjam-source"], "vps-infrastructure");
    Ok(())
}

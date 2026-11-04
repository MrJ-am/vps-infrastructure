//! Invented bodies and a closed lazy pool. No SQL connection or actual user data.
use axum::{
    Router,
    body::{Body, Bytes, to_bytes},
    http::{Request, StatusCode},
    response::Response,
};
use http_body_util::{BodyExt, Full};
use mrjam_server::{
    application_with_mateval,
    mateval::{MAX_BODY_BYTES, MatevalState},
};
use std::{
    sync::{
        Arc,
        atomic::{AtomicUsize, Ordering},
    },
    time::Duration,
};
use tokio::{sync::oneshot, time::timeout};
use tower::ServiceExt;
type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;

async fn router() -> Result<Router> {
    let pool = sqlx::postgres::PgPoolOptions::new().connect_lazy(
        "postgresql://mrjam_synthetic:mrjam_synthetic_only@127.0.0.1:55432/mrjam_synthetic",
    )?;
    pool.close().await;
    Ok(application_with_mateval(MatevalState::with_service(
        mrjam_mateval::Service::new(pool),
    )))
}
fn request(body: Body) -> Result<Request<Body>> {
    Ok(Request::builder()
        .method("POST")
        .uri("/matheval/api/sessions")
        .header("origin", mrjam_mateval::WRITE_ORIGIN)
        .header("x-matheval-request", "1")
        .header("content-type", "application/json")
        .body(body)?)
}
fn rejected_body(bytes: Bytes, polled: Arc<AtomicUsize>) -> Body {
    Body::new(Full::new(bytes).map_frame(move |frame| {
        polled.fetch_add(1, Ordering::SeqCst);
        frame
    }))
}
async fn health(router: &Router) -> Result<Response> {
    Ok(router
        .clone()
        .oneshot(Request::builder().uri("/healthz").body(Body::empty())?)
        .await?)
}

#[tokio::test]
async fn weighted_budget_remains_held_through_headers_and_releases_when_response_drops()
-> Result<()> {
    let router = router().await?;
    let bytes = Bytes::from(vec![b'x'; MAX_BODY_BYTES]);
    let response = router
        .clone()
        .oneshot(request(Body::from(bytes.clone()))?)
        .await?;
    assert_eq!(response.status(), StatusCode::BAD_REQUEST);
    let observed = Arc::new(AtomicUsize::new(0));
    let refused = router
        .clone()
        .oneshot(request(rejected_body(bytes.clone(), observed.clone()))?)
        .await?;
    assert_eq!(refused.status(), StatusCode::SERVICE_UNAVAILABLE);
    assert_eq!(observed.load(Ordering::SeqCst), 0);
    assert_eq!(health(&router).await?.status(), StatusCode::OK);
    drop(response);
    assert_eq!(
        router.oneshot(request(Body::from(bytes))?).await?.status(),
        StatusCode::BAD_REQUEST
    );
    Ok(())
}

#[tokio::test]
async fn cancelling_a_large_body_releases_weighted_capacity_without_reading_other_bodies()
-> Result<()> {
    let router = router().await?;
    let bytes = Bytes::from(vec![b'x'; MAX_BODY_BYTES]);
    let (entered, ready) = oneshot::channel();
    let (_finish, pending) = oneshot::channel::<()>();
    let body = Body::new(Full::new(bytes.clone()).with_trailers(async move {
        let _ = entered.send(());
        let _ = pending.await;
        None
    }));
    let task = tokio::spawn(router.clone().oneshot(request(body)?));
    timeout(Duration::from_secs(1), ready).await??;
    let observed = Arc::new(AtomicUsize::new(0));
    for _ in 0..64 {
        assert_eq!(
            router
                .clone()
                .oneshot(request(rejected_body(bytes.clone(), observed.clone()))?)
                .await?
                .status(),
            StatusCode::SERVICE_UNAVAILABLE
        );
    }
    assert_eq!(observed.load(Ordering::SeqCst), 0);
    assert_eq!(health(&router).await?.status(), StatusCode::OK);
    task.abort();
    assert!(task.await.is_err_and(|error| error.is_cancelled()));
    assert_eq!(
        router.oneshot(request(Body::from(bytes))?).await?.status(),
        StatusCode::BAD_REQUEST
    );
    Ok(())
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
#[ignore = "Explicit release memory measurement; run separately from other tests"]
async fn measured_dense_json_and_sixty_four_competing_maximum_bodies() -> Result<()> {
    let router = router().await?;
    let mut dense = Vec::with_capacity(MAX_BODY_BYTES);
    dense.push(b'[');
    while dense.len() + 3 < MAX_BODY_BYTES {
        dense.extend_from_slice(b"0,");
    }
    dense.extend_from_slice(b"0]");
    dense.resize(MAX_BODY_BYTES, b' ');
    let bytes = Bytes::from(dense);
    let (entered, ready) = oneshot::channel();
    let (finish, pending) = oneshot::channel::<()>();
    let body = Body::new(Full::new(bytes.clone()).with_trailers(async move {
        let _ = entered.send(());
        let _ = pending.await;
        None
    }));
    let task = tokio::spawn(router.clone().oneshot(request(body)?));
    timeout(Duration::from_secs(1), ready).await??;
    let observed = Arc::new(AtomicUsize::new(0));
    let mut competing = Vec::new();
    for _ in 0..64 {
        competing.push(tokio::spawn(
            router
                .clone()
                .oneshot(request(rejected_body(bytes.clone(), observed.clone()))?),
        ));
    }
    for task in competing {
        assert_eq!(task.await??.status(), StatusCode::SERVICE_UNAVAILABLE);
    }
    assert_eq!(observed.load(Ordering::SeqCst), 0);
    finish.send(()).map_err(|_| "synthetic body unavailable")?;
    let response = timeout(Duration::from_secs(10), task).await???;
    assert_eq!(response.status(), StatusCode::BAD_REQUEST);
    let _ = to_bytes(response.into_body(), 4096).await?;
    let status = std::fs::read_to_string("/proc/self/status")?;
    let peak = status
        .lines()
        .find_map(|line| line.strip_prefix("VmHWM:"))
        .and_then(|value| value.split_whitespace().next())
        .ok_or("resource metric missing")?
        .parse::<u64>()?;
    assert!(
        peak <= 220 * 1024,
        "synthetic parser memory exceeds the reviewed envelope"
    );
    println!(
        "{}",
        serde_json::json!({"scope":"release-transport-and-json-parser-only","maximum_body_bytes":MAX_BODY_BYTES,"concurrent_competitors":64,"rejected_before_body_poll":64,"peak_rss_kib":peak,"real_sql":false,"assets_included":false,"scrypt_included":false})
    );
    Ok(())
}

//! Admission of real application routes, with entirely invented request bodies.
//! The injected lazy pool is closed before use: no SQL connection is possible.
use axum::{
    Router,
    body::{Body, Bytes, to_bytes},
    http::{Method, Request, StatusCode},
    response::Response,
};
use http_body_util::{BodyExt, Full};
use mrjam_server::{application, application_with_mateval, mateval::MatevalState};
use sqlx::postgres::PgPoolOptions;
use std::{
    convert::Infallible,
    sync::{
        Arc,
        atomic::{AtomicBool, Ordering},
    },
    time::{Duration, Instant},
};
use tokio::{sync::oneshot, task::JoinHandle, time::timeout};
use tower::ServiceExt;

type TestResult<T> = Result<T, Box<dyn std::error::Error>>;

const QUICK: Duration = Duration::from_secs(1);
const PARTICIPATION: &str = "/matheval/api/sessions/00000000-0000-4000-8000-000000000008";

async fn fixture() -> TestResult<Router> {
    let pool = PgPoolOptions::new().max_connections(1).connect_lazy(
        "postgresql://mrjam_synthetic:mrjam_synthetic_only@127.0.0.1:55432/mrjam_synthetic",
    )?;
    pool.close().await;
    Ok(application_with_mateval(MatevalState::with_service(
        mrjam_mateval::Service::new(pool),
    )))
}

fn write(method: Method, path: &str, body: Body) -> TestResult<Request<Body>> {
    Ok(Request::builder()
        .method(method)
        .uri(path)
        .header("origin", mrjam_mateval::WRITE_ORIGIN)
        .header("x-matheval-request", "1")
        .header("content-type", "application/json")
        .header("x-session-token", "SYNTHETIC_PRIVATE_MARKER")
        .body(body)?)
}

struct HeldRequest {
    finish: Option<oneshot::Sender<()>>,
    task: JoinHandle<Result<Response, Infallible>>,
}

impl HeldRequest {
    async fn finish(mut self) -> TestResult<Response> {
        self.finish
            .take()
            .ok_or("missing synthetic body sender")?
            .send(())
            .map_err(|_| "synthetic body receiver ended too soon")?;
        Ok(timeout(QUICK, &mut self.task).await???)
    }

    async fn cancel(mut self) -> TestResult<()> {
        self.task.abort();
        let result = timeout(QUICK, &mut self.task).await?;
        assert!(result.is_err_and(|error| error.is_cancelled()));
        Ok(())
    }
}

impl Drop for HeldRequest {
    fn drop(&mut self) {
        self.task.abort();
    }
}

async fn hold(router: &Router, index: usize) -> TestResult<HeldRequest> {
    let (entered, receive_entered) = oneshot::channel();
    let (finish, receive_finish) = oneshot::channel();
    let body = Body::new(
        Full::new(Bytes::from_static(b"{")).with_trailers(async move {
            let _ = entered.send(());
            let _ = receive_finish.await;
            None
        }),
    );
    let (method, path) = if index.is_multiple_of(2) {
        (Method::POST, "/matheval/api/sessions")
    } else {
        (Method::PUT, PARTICIPATION)
    };
    let request = write(method, path, body)?;
    let held = HeldRequest {
        finish: Some(finish),
        task: tokio::spawn(router.clone().oneshot(request)),
    };
    // The real handler has started to read the body. No sleep or guessed order
    // is needed to know this request occupies application capacity.
    timeout(QUICK, receive_entered).await??;
    Ok(held)
}

async fn fill(router: &Router) -> TestResult<Vec<HeldRequest>> {
    let mut requests = Vec::new();
    for index in 0..64 {
        requests.push(hold(router, index).await?);
    }
    Ok(requests)
}

async fn get(router: &Router, path: &str) -> TestResult<Response> {
    Ok(timeout(
        QUICK,
        router
            .clone()
            .oneshot(Request::builder().uri(path).body(Body::empty())?),
    )
    .await??)
}

async fn assert_error(response: Response, status: StatusCode, expected: &str) -> TestResult<()> {
    assert_eq!(response.status(), status);
    assert_eq!(response.headers()["cache-control"], "no-store");
    assert_eq!(response.headers()["x-content-type-options"], "nosniff");
    assert_eq!(response.headers()["content-type"], "application/json");
    assert_eq!(
        to_bytes(response.into_body(), 1024).await?.as_ref(),
        expected.as_bytes()
    );
    Ok(())
}

#[tokio::test]
async fn capacity_is_shared_by_routes_clones_and_fallbacks_without_reading_rejected_bodies()
-> TestResult<()> {
    let router = fixture().await?;
    let mut held = fill(&router).await?;
    for path in [
        "/healthz",
        "/readyz",
        "/mcp",
        "/api/SYNTHETIC_PRIVATE_MARKER",
        "/SYNTHETIC_PRIVATE_MARKER?secret=SYNTHETIC_PRIVATE_MARKER",
        "/matheval/apix",
    ] {
        assert_error(
            get(&router, path).await?,
            StatusCode::SERVICE_UNAVAILABLE,
            r#"{"error":{"code":"OVERLOADED"}}"#,
        )
        .await?;
    }
    let polled = Arc::new(AtomicBool::new(false));
    let observed = Arc::clone(&polled);
    let body = Body::new(
        Full::new(Bytes::from_static(b"SYNTHETIC_PRIVATE_MARKER")).map_frame(move |frame| {
            observed.store(true, Ordering::SeqCst);
            frame
        }),
    );
    let rejected = timeout(
        QUICK,
        router
            .clone()
            .oneshot(write(Method::POST, "/matheval/api/sessions", body)?),
    )
    .await??;
    assert_error(
        rejected,
        StatusCode::SERVICE_UNAVAILABLE,
        r#"{"error":"Enregistrement temporairement indisponible. Vos réponses sont conservées sur cet appareil."}"#,
    )
    .await?;
    assert!(!polled.load(Ordering::SeqCst));

    // A separately constructed application has a separate admission budget.
    assert_eq!(
        get(&application(), "/healthz").await?.status(),
        StatusCode::OK
    );
    assert_eq!(
        held.remove(0).finish().await?.status(),
        StatusCode::BAD_REQUEST
    );
    assert_eq!(get(&router, "/healthz").await?.status(), StatusCode::OK);
    held.push(hold(&router, 0).await?);
    assert_error(
        get(&router, "/healthz").await?,
        StatusCode::SERVICE_UNAVAILABLE,
        r#"{"error":{"code":"OVERLOADED"}}"#,
    )
    .await?;
    Ok(())
}

#[tokio::test]
async fn cancelling_an_admitted_request_releases_exactly_one_slot() -> TestResult<()> {
    let router = fixture().await?;
    let mut held = fill(&router).await?;
    held.remove(0).cancel().await?;
    assert_error(
        get(&router, "/readyz").await?,
        StatusCode::SERVICE_UNAVAILABLE,
        r#"{"error":{"code":"NOT_READY"}}"#,
    )
    .await?;
    assert_error(
        get(&router, "/mcp").await?,
        StatusCode::UNAUTHORIZED,
        r#"{"error":{"code":"UNAUTHENTICATED"}}"#,
    )
    .await?;
    held.push(hold(&router, 1).await?);
    assert_error(
        get(&router, "/healthz").await?,
        StatusCode::SERVICE_UNAVAILABLE,
        r#"{"error":{"code":"OVERLOADED"}}"#,
    )
    .await?;
    Ok(())
}

#[tokio::test]
async fn the_ten_second_deadline_releases_all_admission_slots() -> TestResult<()> {
    let router = fixture().await?;
    let started = Instant::now();
    let mut held = fill(&router).await?;
    for request in &mut held {
        let response = timeout(Duration::from_secs(12), &mut request.task).await???;
        assert_error(
            response,
            StatusCode::GATEWAY_TIMEOUT,
            r#"{"error":{"code":"REQUEST_TIMEOUT"}}"#,
        )
        .await?;
    }
    assert!(started.elapsed() >= Duration::from_secs(10));
    let _refilled = fill(&router).await?;
    assert_error(
        get(&router, "/healthz").await?,
        StatusCode::SERVICE_UNAVAILABLE,
        r#"{"error":{"code":"OVERLOADED"}}"#,
    )
    .await?;
    Ok(())
}

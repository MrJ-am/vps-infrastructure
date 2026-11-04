//! Shared request and weighted memory budgets, held through response consumption.
use axum::{
    body::{Body, HttpBody},
    extract::{Request, State},
    http::StatusCode,
    middleware::Next,
    response::Response,
};
use http_body_util::Limited;
use std::{
    pin::Pin,
    sync::Arc,
    task::{Context, Poll},
};
use tokio::sync::{OwnedSemaphorePermit, Semaphore};

const UNIT: usize = 65_536;
const WEIGHTED_UNITS: usize = 80; // Five MiB of weighted body reservations.

#[derive(Clone)]
pub(crate) struct Admission {
    requests: Arc<Semaphore>,
    memory: Arc<Semaphore>,
}

impl Admission {
    pub(crate) fn new() -> Self {
        Self {
            requests: Arc::new(Semaphore::new(64)),
            memory: Arc::new(Semaphore::new(WEIGHTED_UNITS)),
        }
    }
}

fn overload(request: &Request) -> Response {
    if request.uri().path() == "/matheval/api" || request.uri().path().starts_with("/matheval/api/")
    {
        use axum::response::IntoResponse;
        return (
            StatusCode::SERVICE_UNAVAILABLE,
            axum::Json(
                serde_json::json!({"error":mrjam_mateval::Error::StorageUnavailable.message()}),
            ),
        )
            .into_response();
    }
    crate::error_response(StatusCode::SERVICE_UNAVAILABLE, "OVERLOADED")
}

fn reservation(request: &Request) -> (usize, usize) {
    let path = request.uri().path();
    let write = !matches!(
        *request.method(),
        axum::http::Method::GET | axum::http::Method::HEAD
    );
    if path.starts_with("/matheval/api/") {
        if !write {
            return (
                0,
                if path.ends_with("/exports/responses.csv") {
                    WEIGHTED_UNITS
                } else {
                    16
                },
            );
        }
        let maximum = if path.starts_with("/matheval/api/admin/") {
            16_384
        } else {
            crate::mateval::MAX_BODY_BYTES
        };
        let known = request
            .body()
            .size_hint()
            .upper()
            .and_then(|value| usize::try_from(value).ok())
            .unwrap_or(maximum);
        let units = known.min(maximum).div_ceil(UNIT).max(1);
        return ((units * UNIT).min(maximum), units);
    }
    if path == "/mcp" || path.starts_with("/api/") || path == "/presentation/api" {
        // Small request bodies can produce larger domain responses: reserve one
        // MiB per operation, keeping at most five such operations resident.
        return (if write { UNIT } else { 0 }, 16);
    }
    (0, 0)
}

pub(crate) async fn admit(
    State(state): State<Admission>,
    request: Request,
    next: Next,
) -> Response {
    let Ok(request_permit) = state.requests.try_acquire_owned() else {
        return overload(&request);
    };
    let (limit, units) = reservation(&request);
    let Ok(memory_permit) = state.memory.try_acquire_many_owned(units as u32) else {
        return overload(&request);
    };
    let (parts, body) = request.into_parts();
    // The advertised size can never authorize a larger actual body. A lying
    // size hint is bounded by this wrapper before any application's parser.
    let request = Request::from_parts(parts, Body::new(Limited::new(body, limit)));
    let response = next.run(request).await;
    let (parts, body) = response.into_parts();
    Response::from_parts(
        parts,
        Body::new(GuardedBody {
            body,
            permits: Some((request_permit, memory_permit)),
        }),
    )
}

struct GuardedBody {
    body: Body,
    permits: Option<(OwnedSemaphorePermit, OwnedSemaphorePermit)>,
}

impl HttpBody for GuardedBody {
    type Data = axum::body::Bytes;
    type Error = axum::Error;
    fn poll_frame(
        self: Pin<&mut Self>,
        cx: &mut Context<'_>,
    ) -> Poll<Option<Result<hyper::body::Frame<Self::Data>, Self::Error>>> {
        let this = self.get_mut();
        let result = Pin::new(&mut this.body).poll_frame(cx);
        if matches!(result, Poll::Ready(None) | Poll::Ready(Some(Err(_)))) {
            this.permits.take();
        }
        result
    }
    fn is_end_stream(&self) -> bool {
        self.body.is_end_stream()
    }
    fn size_hint(&self) -> hyper::body::SizeHint {
        self.body.size_hint()
    }
}

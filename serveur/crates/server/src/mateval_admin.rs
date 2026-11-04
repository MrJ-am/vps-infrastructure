//! Scientific administration retains its independent session protocol.
use axum::{
    Json, Router,
    body::to_bytes,
    extract::{Request, State},
    http::{Method, StatusCode, header},
    response::{IntoResponse, Response},
    routing::any,
};
use mrjam_mateval::AdminService;
use serde_json::{Map, Value};
use std::{
    sync::{Arc, Mutex},
    time::Instant,
};

const COOKIE: &str = "matheval_admin";

struct AttemptBudget {
    tokens: u32,
    updated: Instant,
}
impl AttemptBudget {
    fn new(now: Instant) -> Self {
        Self {
            tokens: 20,
            updated: now,
        }
    }
    fn allow(&mut self, now: Instant) -> bool {
        let intervals = now
            .checked_duration_since(self.updated)
            .unwrap_or_default()
            .as_secs()
            / 30;
        if intervals > 0 {
            self.tokens = (u64::from(self.tokens) + intervals).min(20) as u32;
            self.updated = now;
        }
        if self.tokens == 0 {
            false
        } else {
            self.tokens -= 1;
            true
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::body::{Body, Bytes};
    use http_body_util::{BodyExt, Full};
    use std::{
        sync::atomic::{AtomicBool, Ordering},
        time::Duration,
    };
    use tower::ServiceExt;

    #[test]
    fn attempt_budget_is_bounded_and_refills_with_monotonic_time() {
        let now = Instant::now();
        let mut budget = AttemptBudget::new(now);
        for _ in 0..20 {
            assert!(budget.allow(now));
        }
        assert!(!budget.allow(now));
        assert!(!budget.allow(now + Duration::from_secs(29)));
        assert!(budget.allow(now + Duration::from_secs(30)));
        assert!(!budget.allow(now + Duration::from_secs(30)));
    }

    #[tokio::test]
    async fn login_rate_limit_precedes_body_kdf_and_database()
    -> Result<(), Box<dyn std::error::Error>> {
        let pool = sqlx::postgres::PgPoolOptions::new().connect_lazy(
            "postgresql://mrjam_synthetic:mrjam_synthetic_only@127.0.0.1:55432/mrjam_synthetic",
        )?;
        pool.close().await;
        let router = routes(Arc::new(AdminService::new(pool, None)?));
        let request = |body| {
            axum::http::Request::builder()
                .method("POST")
                .uri("/matheval/api/admin/login")
                .header("origin", mrjam_mateval::WRITE_ORIGIN)
                .header("x-matheval-request", "1")
                .header("content-type", "application/json")
                .body(body)
        };
        for _ in 0..20 {
            assert_eq!(
                router
                    .clone()
                    .oneshot(request(Body::from("{}"))?)
                    .await?
                    .status(),
                StatusCode::BAD_REQUEST
            );
        }
        let polled = Arc::new(AtomicBool::new(false));
        let seen = polled.clone();
        let body = Body::new(
            Full::new(Bytes::from_static(b"SYNTHETIC_UNREAD_BODY")).map_frame(move |frame| {
                seen.store(true, Ordering::SeqCst);
                frame
            }),
        );
        let response = router.oneshot(request(body)?).await?;
        assert_eq!(response.status(), StatusCode::TOO_MANY_REQUESTS);
        assert_eq!(response.headers()[header::RETRY_AFTER], "30");
        assert!(!polled.load(Ordering::SeqCst));
        Ok(())
    }
}

#[derive(Clone)]
struct Administration {
    service: Arc<AdminService>,
    attempts: Arc<Mutex<AttemptBudget>>,
}

fn failure(error: mrjam_mateval::Error) -> Response {
    (
        StatusCode::from_u16(error.status()).unwrap_or(StatusCode::INTERNAL_SERVER_ERROR),
        Json(serde_json::json!({"error":error.message()})),
    )
        .into_response()
}

fn token(headers: &axum::http::HeaderMap) -> Option<&str> {
    let cookie = crate::identity::unique_header(headers, "cookie")?;
    if cookie.len() > 4096 {
        return None;
    }
    let mut matches = cookie
        .split(';')
        .filter_map(|part| part.trim().split_once('='))
        .filter(|(name, _)| *name == COOKIE);
    let (_, value) = matches.next()?;
    if matches.next().is_some()
        || value.is_empty()
        || value.len() > 128
        || !value
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b"_-".contains(&b))
    {
        return None;
    }
    Some(value)
}

fn query(query: Option<&str>) -> Result<Value, mrjam_mateval::Error> {
    let Some(query) = query else {
        return Ok(Value::Object(Map::new()));
    };
    if query.len() > 2048 {
        return Err(mrjam_mateval::Error::InvalidInput);
    }
    let mut output = Map::new();
    // Historical filters contain only version/status/level/date/page ASCII.
    // Percent encoded syntax is decoded strictly, duplicate keys are refused.
    for part in query.split('&') {
        let (name, value) = part
            .split_once('=')
            .ok_or(mrjam_mateval::Error::InvalidInput)?;
        let name = decode(name)?;
        let value = decode(value)?;
        if output.insert(name, Value::String(value)).is_some() {
            return Err(mrjam_mateval::Error::InvalidInput);
        }
    }
    Ok(Value::Object(output))
}

fn decode(value: &str) -> Result<String, mrjam_mateval::Error> {
    let mut output = Vec::new();
    let mut input = value.bytes();
    while let Some(byte) = input.next() {
        match byte {
            b'%' => {
                let a = input
                    .next()
                    .and_then(|b| (b as char).to_digit(16))
                    .ok_or(mrjam_mateval::Error::InvalidInput)?;
                let b = input
                    .next()
                    .and_then(|b| (b as char).to_digit(16))
                    .ok_or(mrjam_mateval::Error::InvalidInput)?;
                output.push((a * 16 + b) as u8);
            }
            b'+' => output.push(b' '),
            other => output.push(other),
        }
    }
    let output = String::from_utf8(output).map_err(|_| mrjam_mateval::Error::InvalidInput)?;
    if output.chars().any(char::is_control) {
        return Err(mrjam_mateval::Error::InvalidInput);
    }
    Ok(output)
}

pub fn routes(service: Arc<AdminService>) -> Router {
    Router::new()
        .route("/matheval/api/admin", any(handle))
        .route("/matheval/api/admin/{*path}", any(handle))
        .with_state(Administration {
            service,
            attempts: Arc::new(Mutex::new(AttemptBudget::new(Instant::now()))),
        })
}

async fn handle(State(state): State<Administration>, request: Request) -> Response {
    let service = state.service;
    let path = request
        .uri()
        .path()
        .strip_prefix("/matheval/api/admin/")
        .unwrap_or("")
        .to_owned();
    let secret = token(request.headers()).map(str::to_owned);
    let is_write = matches!(path.as_str(), "setup" | "login" | "logout");
    if (is_write && request.method() != Method::POST)
        || (!is_write && request.method() != Method::GET)
    {
        return crate::error_response(StatusCode::METHOD_NOT_ALLOWED, "METHOD_NOT_ALLOWED");
    }
    if is_write {
        if crate::identity::unique_header(request.headers(), "origin")
            != Some(mrjam_mateval::WRITE_ORIGIN)
            || crate::identity::unique_header(request.headers(), "x-matheval-request") != Some("1")
            || !crate::identity::unique_header(request.headers(), "content-type").is_some_and(|v| {
                v.split(';')
                    .next()
                    .is_some_and(|s| s.trim().eq_ignore_ascii_case("application/json"))
            })
            || request.uri().query().is_some()
        {
            return failure(mrjam_mateval::Error::ActivationForbidden);
        }
        if path != "logout"
            && !state
                .attempts
                .lock()
                .is_ok_and(|mut budget| budget.allow(Instant::now()))
        {
            let mut response = (
                StatusCode::TOO_MANY_REQUESTS,
                Json(serde_json::json!({"error":"Trop de tentatives. Réessayez plus tard."})),
            )
                .into_response();
            response
                .headers_mut()
                .insert(header::RETRY_AFTER, header::HeaderValue::from_static("30"));
            return response;
        }
        let body = match to_bytes(request.into_body(), 16_384).await {
            Ok(bytes) => bytes,
            Err(_) => return failure(mrjam_mateval::Error::InvalidInput),
        };
        let unique: crate::strict_json::SansDoublons = match serde_json::from_slice(&body) {
            Ok(value) => value,
            Err(_) => return failure(mrjam_mateval::Error::InvalidInput),
        };
        if path == "logout" {
            if unique.0 != serde_json::json!({}) {
                return failure(mrjam_mateval::Error::InvalidInput);
            }
            let Some(token) = secret else {
                return failure(mrjam_mateval::Error::AdminUnauthorized);
            };
            return match service.logout(&token).await {
                Ok(value) => {
                    let mut response = Json(value).into_response();
                    response.headers_mut().insert(header::SET_COOKIE,header::HeaderValue::from_static("matheval_admin=; Secure; HttpOnly; SameSite=Strict; Path=/matheval/api/admin; Max-Age=0"));
                    response
                }
                Err(error) => failure(error),
            };
        }
        let result = if path == "setup" {
            service.setup(unique.0, secret.as_deref()).await
        } else {
            service.login(unique.0, secret.as_deref()).await
        };
        return match result {
            Ok(session) => {
                let cookie = format!(
                    "matheval_admin={}; Secure; HttpOnly; SameSite=Strict; Path=/matheval/api/admin; Max-Age=28800",
                    session.token()
                );
                let mut response = Json(session.account()).into_response();
                match header::HeaderValue::from_str(&cookie) {
                    Ok(value) => {
                        response.headers_mut().insert(header::SET_COOKIE, value);
                        response
                    }
                    Err(_) => failure(mrjam_mateval::Error::StorageUnavailable),
                }
            }
            Err(error) => failure(error),
        };
    }
    let Some(token) = secret else {
        return failure(mrjam_mateval::Error::AdminUnauthorized);
    };
    let query = match query(request.uri().query()) {
        Ok(value) => value,
        Err(error) => return failure(error),
    };
    let result = match path.as_str() {
        "me" if query == serde_json::json!({}) => service.current(&token).await,
        "corpora" if query == serde_json::json!({}) => service.corpora(&token).await,
        "statistics" => service.statistics(&token, query).await,
        "participations" => service.participations(&token, query).await,
        "exports/responses.csv" => {
            return match service.export_csv(&token, query).await {
                Ok(csv) => (
                    [
                        (header::CONTENT_TYPE, "text/csv; charset=utf-8"),
                        (
                            header::CONTENT_DISPOSITION,
                            "attachment; filename=responses.csv",
                        ),
                    ],
                    csv,
                )
                    .into_response(),
                Err(error) => failure(error),
            };
        }
        _ if path.starts_with("corpus/") && query == serde_json::json!({}) => {
            service.corpus(&token, &path[7..]).await
        }
        _ if path.starts_with("participations/") && query == serde_json::json!({}) => {
            service.participation(&token, &path[15..]).await
        }
        _ if path.starts_with("productions/") && path.ends_with("/answers") => {
            service
                .answers(&token, query, &path[12..path.len() - 8])
                .await
        }
        _ => return crate::error_response(StatusCode::NOT_FOUND, "NOT_FOUND"),
    };
    match result {
        Ok(value) => Json(value).into_response(),
        Err(error) => failure(error),
    }
}

//! Adaptateur HTTP de Mateval. Le secret de participation reste distinct du SSO.
use axum::{
    Json, Router,
    body::to_bytes,
    extract::{Path, Request, State, rejection::PathRejection},
    http::{HeaderMap, StatusCode, header},
    response::{IntoResponse, Response},
    routing::{get, post},
};
use mrjam_mateval::Service;
use serde::Serialize;
use serde_json::Value;
use std::{error::Error as _, sync::Arc};

pub const MAX_BODY_BYTES: usize = 5 * 1024 * 1024;

#[derive(Clone, Default)]
pub struct MatevalState {
    service: Option<Arc<Service>>,
}

impl MatevalState {
    /// Le constructeur ne crée ni connexion ni schéma ; le pool est injecté
    /// par une configuration d'exploitation ou un harnais synthétique séparé.
    pub fn with_service(service: Service) -> Self {
        Self {
            service: Some(Arc::new(service)),
        }
    }
}

#[derive(Serialize)]
struct LegacyError {
    error: &'static str,
}

fn failure(status: StatusCode, message: &'static str) -> Response {
    (status, Json(LegacyError { error: message })).into_response()
}

fn unavailable() -> Response {
    failure(
        StatusCode::SERVICE_UNAVAILABLE,
        "Enregistrement temporairement indisponible. Vos réponses sont conservées sur cet appareil.",
    )
}

#[derive(Clone, Copy, Debug)]
enum RequestError {
    Forbidden,
    Unauthenticated,
    InvalidBody,
    OversizedBody,
    InvalidParticipation,
}

impl IntoResponse for RequestError {
    fn into_response(self) -> Response {
        let (status, message) = match self {
            Self::Forbidden => (StatusCode::FORBIDDEN, "Origine de la requête refusée."),
            Self::Unauthenticated => (
                StatusCode::UNAUTHORIZED,
                "Accès à cette participation refusé.",
            ),
            Self::InvalidBody => (
                StatusCode::BAD_REQUEST,
                "Données invalides. Vérifiez les champs et réessayez.",
            ),
            Self::OversizedBody => (
                StatusCode::PAYLOAD_TOO_LARGE,
                "La requête dépasse la taille autorisée.",
            ),
            Self::InvalidParticipation => (StatusCode::NOT_FOUND, "Participation introuvable."),
        };
        failure(status, message)
    }
}

fn unique_header<'a>(headers: &'a HeaderMap, name: &str) -> Option<&'a str> {
    let mut values = headers.get_all(name).iter();
    let value = values.next()?.to_str().ok()?;
    if values.next().is_some() {
        return None;
    }
    Some(value)
}

fn write_allowed(headers: &HeaderMap) -> Result<(), RequestError> {
    if unique_header(headers, "origin") != Some(mrjam_mateval::WRITE_ORIGIN)
        || unique_header(headers, "x-matheval-request") != Some("1")
    {
        return Err(RequestError::Forbidden);
    }
    let content_type = unique_header(headers, header::CONTENT_TYPE.as_str())
        .and_then(|value| value.split(';').next());
    if !content_type.is_some_and(|value| value.trim().eq_ignore_ascii_case("application/json")) {
        return Err(RequestError::Forbidden);
    }
    if let Some(length) = unique_header(headers, header::CONTENT_LENGTH.as_str()) {
        match length.parse::<u64>() {
            Ok(length) if length > MAX_BODY_BYTES as u64 => {
                return Err(RequestError::OversizedBody);
            }
            Ok(_) => {}
            Err(_) => return Err(RequestError::InvalidBody),
        }
    }
    Ok(())
}

fn secret(headers: &HeaderMap) -> Result<&str, RequestError> {
    unique_header(headers, "x-session-token")
        .filter(|value| !value.is_empty())
        .ok_or(RequestError::Unauthenticated)
}

async fn payload(request: Request) -> Result<Value, RequestError> {
    let bytes = to_bytes(request.into_body(), MAX_BODY_BYTES)
        .await
        .map_err(|error| {
            if error
                .source()
                .is_some_and(|source| source.is::<http_body_util::LengthLimitError>())
            {
                RequestError::OversizedBody
            } else {
                RequestError::InvalidBody
            }
        })?;
    serde_json::from_slice(&bytes).map_err(|_| RequestError::InvalidBody)
}

fn result(response: Result<Value, mrjam_mateval::Error>, success: StatusCode) -> Response {
    match response {
        Ok(value) => (success, Json(value)).into_response(),
        Err(error) => failure(
            StatusCode::from_u16(error.status()).unwrap_or(StatusCode::INTERNAL_SERVER_ERROR),
            error.message(),
        ),
    }
}

async fn create_session(
    State(state): State<MatevalState>,
    headers: HeaderMap,
    request: Request,
) -> Response {
    if let Err(response) = write_allowed(&headers) {
        return response.into_response();
    }
    let Some(service) = state.service else {
        return unavailable();
    };
    let body = match payload(request).await {
        Ok(value) => value,
        Err(response) => return response.into_response(),
    };
    result(service.create_session(body).await, StatusCode::CREATED)
}

async fn read_session(
    State(state): State<MatevalState>,
    path: Result<Path<String>, PathRejection>,
    headers: HeaderMap,
) -> Response {
    let token = match secret(&headers) {
        Ok(value) => value,
        Err(response) => return response.into_response(),
    };
    let id = match participation_path(path) {
        Ok(value) => value,
        Err(response) => return response.into_response(),
    };
    let Some(service) = state.service else {
        return unavailable();
    };
    result(service.read_session(&id, token).await, StatusCode::OK)
}

async fn read_events(
    State(state): State<MatevalState>,
    path: Result<Path<String>, PathRejection>,
    headers: HeaderMap,
) -> Response {
    let token = match secret(&headers) {
        Ok(value) => value,
        Err(response) => return response.into_response(),
    };
    let id = match participation_path(path) {
        Ok(value) => value,
        Err(response) => return response.into_response(),
    };
    let Some(service) = state.service else {
        return unavailable();
    };
    result(service.read_events(&id, token).await, StatusCode::OK)
}

async fn save_session(
    State(state): State<MatevalState>,
    path: Result<Path<String>, PathRejection>,
    headers: HeaderMap,
    request: Request,
) -> Response {
    if let Err(response) = write_allowed(&headers) {
        return response.into_response();
    }
    let token = match secret(&headers) {
        Ok(value) => value,
        Err(response) => return response.into_response(),
    };
    let id = match participation_path(path) {
        Ok(value) => value,
        Err(response) => return response.into_response(),
    };
    let Some(service) = state.service else {
        return unavailable();
    };
    let body = match payload(request).await {
        Ok(value) => value,
        Err(response) => return response.into_response(),
    };
    result(service.save_session(&id, token, body).await, StatusCode::OK)
}

async fn resource_not_found() -> Response {
    failure(StatusCode::NOT_FOUND, "Ressource inconnue.")
}

fn participation_path(path: Result<Path<String>, PathRejection>) -> Result<String, RequestError> {
    match path {
        Ok(Path(value)) if mrjam_mateval::types::uuid_syntax(&value) => Ok(value),
        _ => Err(RequestError::InvalidParticipation),
    }
}

async fn method_not_allowed() -> Response {
    failure(StatusCode::METHOD_NOT_ALLOWED, "Méthode non autorisée.")
}

async fn unqualified_administration() -> Response {
    // Les exportations scientifiques ne sont pas ouvertes avec un secret de
    // participation. Leur autorité distincte doit être portée et qualifiée.
    unavailable()
}

pub fn routes(state: MatevalState) -> Router {
    collection_routes(state)
        .route(
            "/matheval/api/admin",
            axum::routing::any(unqualified_administration),
        )
        .route(
            "/matheval/api/admin/{*path}",
            axum::routing::any(unqualified_administration),
        )
}

pub(crate) fn collection_routes(state: MatevalState) -> Router {
    Router::new()
        .route("/matheval/api/sessions", post(create_session))
        .route(
            "/matheval/api/sessions/{id}",
            get(read_session).put(save_session),
        )
        .route("/matheval/api/sessions/{id}/events", get(read_events))
        .route(
            "/matheval/api/{*path}",
            axum::routing::any(resource_not_found),
        )
        .method_not_allowed_fallback(method_not_allowed)
        .with_state(state)
}

#[cfg(test)]
mod tests {
    use super::{MAX_BODY_BYTES, MatevalState, payload, routes};
    use axum::{
        body::{Body, to_bytes},
        http::{Request, StatusCode},
        response::IntoResponse,
    };
    use tower::ServiceExt;

    #[tokio::test]
    async fn no_origin_or_token_is_ever_interpreted_as_a_verified_identity()
    -> Result<(), Box<dyn std::error::Error>> {
        let router = routes(MatevalState::default());
        let create = router
            .clone()
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/matheval/api/sessions")
                    .header("x-mrj-user", "SYNTHETIC_PRIVATE_MARKER")
                    .body(Body::from("SYNTHETIC_PRIVATE_MARKER"))?,
            )
            .await?;
        assert_eq!(create.status(), StatusCode::FORBIDDEN);
        assert!(
            !String::from_utf8(to_bytes(create.into_body(), 1024).await?.to_vec())?
                .contains("SYNTHETIC_PRIVATE_MARKER")
        );
        let read = router
            .oneshot(
                Request::builder()
                    .uri("/matheval/api/sessions/not-an-identity")
                    .header("authorization", "Bearer SYNTHETIC_PRIVATE_MARKER")
                    .body(Body::empty())?,
            )
            .await?;
        assert_eq!(read.status(), StatusCode::UNAUTHORIZED);
        Ok(())
    }

    #[tokio::test]
    async fn writes_without_a_service_are_explicitly_unavailable_and_never_accepted()
    -> Result<(), Box<dyn std::error::Error>> {
        let response = routes(MatevalState::default())
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/matheval/api/sessions")
                    .header("origin", mrjam_mateval::WRITE_ORIGIN)
                    .header("x-matheval-request", "1")
                    .header("content-type", "application/json; charset=utf-8")
                    .body(Body::from("{}"))?,
            )
            .await?;
        assert_eq!(response.status(), StatusCode::SERVICE_UNAVAILABLE);
        Ok(())
    }

    #[tokio::test]
    async fn duplicate_origins_and_oversized_declared_bodies_are_rejected()
    -> Result<(), Box<dyn std::error::Error>> {
        let duplicate = routes(MatevalState::default())
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/matheval/api/sessions")
                    .header("origin", mrjam_mateval::WRITE_ORIGIN)
                    .header("origin", "https://synthetic.invalid")
                    .header("x-matheval-request", "1")
                    .header("content-type", "application/json")
                    .body(Body::from("{}"))?,
            )
            .await?;
        assert_eq!(duplicate.status(), StatusCode::FORBIDDEN);
        let large = routes(MatevalState::default())
            .oneshot(
                Request::builder()
                    .method("POST")
                    .uri("/matheval/api/sessions")
                    .header("origin", mrjam_mateval::WRITE_ORIGIN)
                    .header("x-matheval-request", "1")
                    .header("content-type", "application/json")
                    .header("content-length", (MAX_BODY_BYTES + 1).to_string())
                    .body(Body::empty())?,
            )
            .await?;
        assert_eq!(large.status(), StatusCode::PAYLOAD_TOO_LARGE);
        Ok(())
    }

    #[tokio::test]
    async fn invalid_path_encoding_is_closed_and_never_echoed()
    -> Result<(), Box<dyn std::error::Error>> {
        let response = routes(MatevalState::default())
            .oneshot(
                Request::builder()
                    .uri("/matheval/api/sessions/%FF-SYNTHETIC_PRIVATE_MARKER")
                    .header("x-session-token", "SYNTHETIC_PRIVATE_MARKER")
                    .body(Body::empty())?,
            )
            .await?;
        assert_eq!(response.status(), StatusCode::NOT_FOUND);
        let value: serde_json::Value =
            serde_json::from_slice(&to_bytes(response.into_body(), 1024).await?)?;
        assert!(value.as_object().is_some_and(|object| {
            object.len() == 1
                && object
                    .get("error")
                    .is_some_and(serde_json::Value::is_string)
        }));
        assert!(!value.to_string().contains("SYNTHETIC_PRIVATE_MARKER"));
        Ok(())
    }

    #[tokio::test]
    async fn undeclared_body_length_cannot_bypass_streaming_limit()
    -> Result<(), Box<dyn std::error::Error>> {
        let request = Request::builder().body(Body::from(vec![b'x'; MAX_BODY_BYTES + 1]))?;
        let response = match payload(request).await {
            Ok(_) => return Err("an oversized synthetic body was accepted".into()),
            Err(response) => response.into_response(),
        };
        assert_eq!(response.status(), StatusCode::PAYLOAD_TOO_LARGE);
        Ok(())
    }
}

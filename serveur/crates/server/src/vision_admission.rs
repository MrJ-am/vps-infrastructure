//! Fixed local admission approval bridge. The browser cannot select identity,
//! URL, method, credential or arbitrary worker operation.
use crate::identity::{IdentityClient, IdentityError, VerifiedIdentity, unique_header};
use axum::{
    Json, Router,
    body::{Bytes, to_bytes},
    extract::{Request, State},
    http::{Method, StatusCode, header},
    response::{IntoResponse, Response},
    routing::post,
};
use http_body_util::{BodyExt, Full, Limited};
use hyper_util::rt::TokioIo;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    net::{Ipv4Addr, SocketAddr},
    path::Path,
    sync::Arc,
    time::Duration,
};
use tokio::{net::TcpStream, sync::Semaphore};

#[derive(Clone)]
pub(crate) struct ApprovalClient {
    endpoint: SocketAddr,
    credential: Arc<str>,
    active: Arc<Semaphore>,
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct Parameters {
    id: String,
    methode: String,
    reference: String,
    source_pays: String,
}

#[derive(Clone, Copy)]
enum Failure {
    Invalid,
    Forbidden,
    Unavailable,
}

impl Failure {
    fn response(self) -> Response {
        let (status, code) = match self {
            Self::Invalid => (StatusCode::BAD_REQUEST, "parametres_invalides"),
            Self::Forbidden => (StatusCode::FORBIDDEN, "acces_interdit"),
            Self::Unavailable => (
                StatusCode::SERVICE_UNAVAILABLE,
                "approbation_admission_indisponible",
            ),
        };
        (status, Json(json!({"erreur":code}))).into_response()
    }
}

impl Parameters {
    fn parse(bytes: &[u8]) -> Result<Self, Failure> {
        if bytes.len() > 4096 {
            return Err(Failure::Invalid);
        }
        let unique: crate::strict_json::SansDoublons =
            serde_json::from_slice(bytes).map_err(|_| Failure::Invalid)?;
        let value: Self = serde_json::from_value(unique.0).map_err(|_| Failure::Invalid)?;
        if value.id.len() != 36
            || !value.id.bytes().enumerate().all(|(i, b)| {
                if [8, 13, 18, 23].contains(&i) {
                    b == b'-'
                } else {
                    b.is_ascii_digit() || (b'a'..=b'f').contains(&b)
                }
            })
            || !matches!(
                value.methode.as_str(),
                "entretien" | "verification_relation" | "controle_pays"
            )
            || value.reference.is_empty()
            || value.reference.chars().count() > 160
            || value.reference.chars().any(char::is_control)
            || value.source_pays.len() > 500
            || value.source_pays.chars().any(char::is_control)
        {
            return Err(Failure::Invalid);
        }
        // The worker performs the canonical HTTPS URL and business checks.
        // source_pays remains data; it is never used as a request destination.
        Ok(value)
    }
}

impl ApprovalClient {
    pub(crate) fn load(path: &Path) -> Result<Self, &'static str> {
        let credential = crate::runtime_files::credential(path)?;
        if !(32..=512).contains(&credential.len())
            || !credential
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'-' | b'_'))
        {
            return Err("INVALID_ADMISSION_APPROVAL_CREDENTIAL");
        }
        Ok(Self {
            endpoint: SocketAddr::from((Ipv4Addr::LOCALHOST, 3027)),
            credential: credential.into(),
            active: Arc::new(Semaphore::new(2)),
        })
    }

    async fn exchange(
        &self,
        method: Method,
        path: &'static str,
        body: Vec<u8>,
    ) -> Result<Value, Failure> {
        let _permit = self
            .active
            .try_acquire()
            .map_err(|_| Failure::Unavailable)?;
        if body.len() > 4096 {
            return Err(Failure::Invalid);
        }
        let request = axum::http::Request::builder()
            .method(method)
            .uri(path)
            .header(header::HOST, "mrjam-admission.internal")
            .header(header::CONTENT_TYPE, "application/json")
            .header(header::AUTHORIZATION, format!("Bearer {}", self.credential))
            .body(Full::new(Bytes::from(body)))
            .map_err(|_| Failure::Unavailable)?;
        tokio::time::timeout(Duration::from_secs(3), async {
            let stream = TcpStream::connect(self.endpoint)
                .await
                .map_err(|_| Failure::Unavailable)?;
            let (mut sender, connection) = hyper::client::conn::http1::Builder::new()
                .max_headers(32)
                .max_buf_size(8192)
                .handshake(TokioIo::new(stream))
                .await
                .map_err(|_| Failure::Unavailable)?;
            struct Abort(tokio::task::JoinHandle<()>);
            impl Drop for Abort {
                fn drop(&mut self) {
                    self.0.abort();
                }
            }
            let _guard = Abort(tokio::spawn(async move {
                let _ = connection.await;
            }));
            let response = sender
                .send_request(request)
                .await
                .map_err(|_| Failure::Unavailable)?;
            let status = response.status();
            if response.headers().contains_key(header::LOCATION)
                || response.headers().contains_key(header::SET_COOKIE)
                || !unique_header(response.headers(), "content-type").is_some_and(|value| {
                    value
                        .split(';')
                        .next()
                        .is_some_and(|mime| mime.trim().eq_ignore_ascii_case("application/json"))
                })
            {
                return Err(Failure::Unavailable);
            }
            let bytes = Limited::new(response.into_body(), 4096)
                .collect()
                .await
                .map_err(|_| Failure::Unavailable)?
                .to_bytes();
            if status != StatusCode::OK {
                return Err(match status {
                    StatusCode::BAD_REQUEST => Failure::Invalid,
                    StatusCode::FORBIDDEN => Failure::Forbidden,
                    _ => Failure::Unavailable,
                });
            }
            let unique: crate::strict_json::SansDoublons =
                serde_json::from_slice(&bytes).map_err(|_| Failure::Unavailable)?;
            Ok(unique.0)
        })
        .await
        .map_err(|_| Failure::Unavailable)?
    }

    pub(crate) async fn ready(&self) -> Result<(), &'static str> {
        let reply = self
            .exchange(Method::GET, "/interne/disponibilite", vec![])
            .await
            .map_err(|_| "ADMISSION_APPROVAL_UNAVAILABLE")?;
        if reply != json!({"disponible":true}) {
            return Err("ADMISSION_APPROVAL_UNAVAILABLE");
        }
        Ok(())
    }

    async fn approve(
        &self,
        identity: &VerifiedIdentity,
        parameters: Parameters,
    ) -> Result<Value, Failure> {
        if !identity.elevated() {
            return Err(Failure::Forbidden);
        }
        let body=serde_json::to_vec(&json!({"acteur":identity.owner(),"id":parameters.id,"methode":parameters.methode,"reference":parameters.reference,"source_pays":parameters.source_pays})).map_err(|_|Failure::Invalid)?;
        let value = self
            .exchange(Method::POST, "/interne/approuver", body)
            .await?;
        if value != json!({"controle_enregistre":true}) {
            return Err(Failure::Unavailable);
        }
        Ok(value)
    }
}

#[derive(Clone)]
struct ApprovalState {
    identity: Option<IdentityClient>,
    client: Option<ApprovalClient>,
}

pub(crate) fn routes(identity: Option<IdentityClient>, client: Option<ApprovalClient>) -> Router {
    Router::new()
        .route("/api/gestion/approuver_admission", post(approve))
        .with_state(ApprovalState { identity, client })
}

async fn approve(State(state): State<ApprovalState>, request: Request) -> Response {
    if unique_header(request.headers(), "host") != Some("vision.mrj.am") {
        return crate::error_response(StatusCode::MISDIRECTED_REQUEST, "HOST_REFUSED");
    }
    let Some(identity) = state.identity else {
        return crate::unauthenticated().await;
    };
    let actor = match identity
        .verify_browser("vision.mrj.am", request.method(), request.headers(), true)
        .await
    {
        Ok(actor) => actor,
        Err(IdentityError::Unauthenticated) => return crate::unauthenticated().await,
        Err(IdentityError::Forbidden) => return Failure::Forbidden.response(),
        Err(IdentityError::Unavailable) => return Failure::Unavailable.response(),
    };
    if request.uri().query().is_some()
        || !unique_header(request.headers(), "content-type").is_some_and(|value| {
            value
                .split(';')
                .next()
                .is_some_and(|mime| mime.trim().eq_ignore_ascii_case("application/json"))
        })
    {
        return Failure::Invalid.response();
    }
    let bytes = match to_bytes(request.into_body(), 4096).await {
        Ok(bytes) => bytes,
        Err(_) => return crate::error_response(StatusCode::PAYLOAD_TOO_LARGE, "REQUEST_TOO_LARGE"),
    };
    let parameters = match Parameters::parse(&bytes) {
        Ok(parameters) => parameters,
        Err(error) => return error.response(),
    };
    let Some(client) = state.client else {
        return Failure::Unavailable.response();
    };
    match client.approve(&actor, parameters).await {
        Ok(value) => Json(value).into_response(),
        Err(error) => error.response(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::{body::Body, routing::get};
    use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
    use tower::ServiceExt;

    #[tokio::test]
    async fn approval_requires_verified_mfa_rejects_caller_actor_and_closes_rpc_errors()
    -> Result<(), Box<dyn std::error::Error>> {
        let permitted = Arc::new(AtomicBool::new(false));
        let worker_calls = Arc::new(AtomicUsize::new(0));
        let malformed = Arc::new(AtomicBool::new(false));
        let auth = Router::new().route(
            "/verify-gestion",
            get({
                let permitted = permitted.clone();
                move |headers: axum::http::HeaderMap| {
                    let permitted = permitted.clone();
                    async move {
                        assert_eq!(headers["x-forwarded-host"], "vision.mrj.am");
                        assert_eq!(headers["x-original-method"], "POST");
                        assert!(!headers.contains_key("x-mrj-user"));
                        if permitted.load(Ordering::SeqCst) {
                            (StatusCode::NO_CONTENT, [("x-mrj-user", "invented.manager")])
                        } else {
                            (StatusCode::FORBIDDEN, [("cache-control", "no-store")])
                        }
                    }
                }
            }),
        );
        let auth_listener = tokio::net::TcpListener::bind("127.0.0.1:0").await?;
        let identity = IdentityClient::new(&crate::runtime_config::IdentityConfiguration {
            endpoint: auth_listener.local_addr()?,
            protocol: "mrj-auth-v1".into(),
        })?;
        let auth_task = tokio::spawn(async move {
            let _ = axum::serve(auth_listener, auth).await;
        });
        let worker = Router::new().route(
            "/interne/approuver",
            post({
                let calls = worker_calls.clone();
                let malformed = malformed.clone();
                move |request: Request| {
                    let calls = calls.clone();
                    let malformed = malformed.clone();
                    async move {
                        calls.fetch_add(1, Ordering::SeqCst);
                        assert_eq!(
                            request.headers()["authorization"],
                            "Bearer invented-approval-credential-00001"
                        );
                        assert!(!request.headers().contains_key("cookie"));
                        assert!(!request.headers().contains_key("origin"));
                        let body = to_bytes(request.into_body(), 4096)
                            .await
                            .unwrap_or_default();
                        let value: Value = serde_json::from_slice(&body).unwrap_or_default();
                        assert_eq!(value["acteur"], "invented.manager");
                        Json(if malformed.load(Ordering::SeqCst) {
                            json!({"controle_enregistre":true,"secret":"SYNTHETIC_LEAK_MARKER"})
                        } else {
                            json!({"controle_enregistre":true})
                        })
                    }
                }
            }),
        );
        let worker_listener = tokio::net::TcpListener::bind("127.0.0.1:0").await?;
        let client = ApprovalClient {
            endpoint: worker_listener.local_addr()?,
            credential: "invented-approval-credential-00001".into(),
            active: Arc::new(Semaphore::new(2)),
        };
        let worker_task = tokio::spawn(async move {
            let _ = axum::serve(worker_listener, worker).await;
        });
        let router = routes(Some(identity), Some(client));
        let document = json!({"id":"00000000-0000-4000-8000-000000000001","methode":"controle_pays","reference":"Invented case","source_pays":"https://synthetic.invalid/rules"});
        let request = |document: Value| {
            Request::builder()
                .method("POST")
                .uri("/api/gestion/approuver_admission")
                .header("host", "vision.mrj.am")
                .header("cookie", "invented-session")
                .header("origin", "https://vision.mrj.am")
                .header("x-csrf-token", "invented-csrf")
                .header("content-type", "application/json")
                .header("x-mrj-user", "forged.admin")
                .body(Body::from(document.to_string()))
        };
        assert_eq!(
            router
                .clone()
                .oneshot(request(document.clone())?)
                .await?
                .status(),
            StatusCode::FORBIDDEN
        );
        assert_eq!(worker_calls.load(Ordering::SeqCst), 0);
        permitted.store(true, Ordering::SeqCst);
        let mut spoofed = document.clone();
        spoofed["acteur"] = json!("forged.admin");
        assert_eq!(
            router.clone().oneshot(request(spoofed)?).await?.status(),
            StatusCode::BAD_REQUEST
        );
        assert_eq!(worker_calls.load(Ordering::SeqCst), 0);
        assert_eq!(
            router
                .clone()
                .oneshot(request(document.clone())?)
                .await?
                .status(),
            StatusCode::OK
        );
        assert_eq!(worker_calls.load(Ordering::SeqCst), 1);
        malformed.store(true, Ordering::SeqCst);
        let failed = router.clone().oneshot(request(document.clone())?).await?;
        assert_eq!(failed.status(), StatusCode::SERVICE_UNAVAILABLE);
        assert!(
            !String::from_utf8(to_bytes(failed.into_body(), 4096).await?.to_vec())?
                .contains("SYNTHETIC_LEAK_MARKER")
        );
        worker_task.abort();
        let _ = worker_task.await;
        assert_eq!(
            router.oneshot(request(document)?).await?.status(),
            StatusCode::SERVICE_UNAVAILABLE
        );
        auth_task.abort();
        Ok(())
    }
}

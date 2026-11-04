//! Bounded verification against the dedicated identity service, never headers
//! claimed by the caller. The service owns OIDC/session/revocation/MFA policy.
use crate::runtime_config::IdentityConfiguration;
use axum::{
    body::Bytes,
    http::{HeaderMap, Method, Request, StatusCode, header},
};
use http_body_util::Empty;
use hyper_util::rt::TokioIo;
use mrjam_vision::{AutoriserVision, ErreurVision, FuturVision, Justificatif, Proprietaire};
use std::{net::SocketAddr, time::Duration};
use tokio::net::TcpStream;

#[derive(Clone)]
pub struct IdentityClient {
    endpoint: SocketAddr,
}

/// Closed host/audience binding. The dedicated broker validates each grant
/// against this resource; an identity or token from another host is not proof.
#[derive(Clone, Copy)]
pub(crate) enum McpResource {
    Vision,
    Audition,
}

impl McpResource {
    pub(crate) const fn host(self) -> &'static str {
        match self {
            Self::Vision => "vision.mrj.am",
            Self::Audition => "audition.mrj.am",
        }
    }

    pub(crate) const fn origin(self) -> &'static str {
        match self {
            Self::Vision => "https://vision.mrj.am",
            Self::Audition => "https://audition.mrj.am",
        }
    }

    pub(crate) const fn challenge(self) -> &'static str {
        match self {
            Self::Vision => {
                "Bearer realm=\"Vision MCP\", resource_metadata=\"https://vision.mrj.am/.well-known/oauth-protected-resource/mcp\""
            }
            Self::Audition => {
                "Bearer realm=\"Audition MCP\", resource_metadata=\"https://audition.mrj.am/.well-known/oauth-protected-resource/mcp\""
            }
        }
    }
}

struct Verification<'a> {
    host: &'a str,
    path: &'static str,
    method: &'a Method,
    credential_name: &'static str,
    credential: &'a str,
    csrf: Option<&'a str>,
    origin: Option<&'a str>,
    elevated: bool,
}

#[derive(Clone)]
pub struct VerifiedIdentity {
    owner: String,
    elevated: bool,
}

impl VerifiedIdentity {
    pub fn owner(&self) -> &str {
        &self.owner
    }
    pub fn elevated(&self) -> bool {
        self.elevated
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum IdentityError {
    Unauthenticated,
    Forbidden,
    Unavailable,
}

pub(crate) fn unique_header<'a>(headers: &'a HeaderMap, name: &str) -> Option<&'a str> {
    let mut values = headers.get_all(name).iter();
    let value = values.next()?.to_str().ok()?;
    if values.next().is_some() {
        return None;
    }
    Some(value)
}

impl IdentityClient {
    pub fn new(config: &IdentityConfiguration) -> Result<Self, &'static str> {
        if !config.endpoint.ip().is_loopback()
            || config.endpoint.port() == 0
            || config.protocol != "mrj-auth-v1"
        {
            return Err("INVALID_IDENTITY_CONFIGURATION");
        }
        Ok(Self {
            endpoint: config.endpoint,
        })
    }

    async fn verify(
        &self,
        verification: Verification<'_>,
    ) -> Result<VerifiedIdentity, IdentityError> {
        let Verification {
            host,
            path,
            method,
            credential_name,
            credential,
            csrf,
            origin,
            elevated,
        } = verification;
        if !crate::runtime_config::host(host)
            || credential.is_empty()
            || credential.len() > 8192
            || credential.bytes().any(|byte| !(32..=126).contains(&byte))
        {
            return Err(IdentityError::Unauthenticated);
        }
        let mut request = Request::builder()
            .method("GET")
            .uri(path)
            .header(header::HOST, "mrj-auth.internal")
            .header("x-forwarded-host", host)
            .header("x-forwarded-proto", "https")
            .header("x-original-method", method.as_str())
            .header(credential_name, credential);
        if let Some(value) = csrf {
            request = request.header("x-csrf-token", value);
        }
        if let Some(value) = origin {
            request = request.header(header::ORIGIN, value);
        }
        let request = request
            .body(Empty::<Bytes>::new())
            .map_err(|_| IdentityError::Unauthenticated)?;
        let response = self.exchange(request).await?;
        match response.status() {
            StatusCode::NO_CONTENT => {
                let owner = unique_header(response.headers(), "x-mrj-user")
                    .ok_or(IdentityError::Unavailable)?;
                let owner = Proprietaire::valider(owner).map_err(|_| IdentityError::Unavailable)?;
                if response.headers().contains_key(header::LOCATION)
                    || response.headers().contains_key(header::SET_COOKIE)
                {
                    return Err(IdentityError::Unavailable);
                }
                Ok(VerifiedIdentity {
                    owner: owner.valeur().to_owned(),
                    elevated,
                })
            }
            StatusCode::UNAUTHORIZED => Err(IdentityError::Unauthenticated),
            StatusCode::FORBIDDEN => Err(IdentityError::Forbidden),
            _ => Err(IdentityError::Unavailable),
        }
    }

    async fn exchange(
        &self,
        request: Request<Empty<Bytes>>,
    ) -> Result<hyper::Response<hyper::body::Incoming>, IdentityError> {
        tokio::time::timeout(Duration::from_secs(2), async {
            let stream = TcpStream::connect(self.endpoint)
                .await
                .map_err(|_| IdentityError::Unavailable)?;
            let (mut sender, connection) = hyper::client::conn::http1::Builder::new()
                .max_headers(32)
                .max_buf_size(32_768)
                .handshake(TokioIo::new(stream))
                .await
                .map_err(|_| IdentityError::Unavailable)?;
            // An abort guard also closes the connection if the outer request is
            // cancelled by a deadline, avoiding detached credential-bearing work.
            struct AbortConnection(tokio::task::JoinHandle<()>);
            impl Drop for AbortConnection {
                fn drop(&mut self) {
                    self.0.abort();
                }
            }
            let _guard = AbortConnection(tokio::spawn(async move {
                let _ = connection.await;
            }));
            sender
                .send_request(request)
                .await
                .map_err(|_| IdentityError::Unavailable)
        })
        .await
        .map_err(|_| IdentityError::Unavailable)?
    }

    pub async fn verify_browser(
        &self,
        host: &str,
        method: &Method,
        headers: &HeaderMap,
        elevated: bool,
    ) -> Result<VerifiedIdentity, IdentityError> {
        let cookie = unique_header(headers, header::COOKIE.as_str())
            .ok_or(IdentityError::Unauthenticated)?;
        let (csrf, origin) = if *method != Method::GET && *method != Method::HEAD {
            let csrf = unique_header(headers, "x-csrf-token")
                .filter(|value| !value.is_empty() && value.len() <= 256)
                .ok_or(IdentityError::Forbidden)?;
            let origin =
                unique_header(headers, header::ORIGIN.as_str()).ok_or(IdentityError::Forbidden)?;
            if origin != format!("https://{host}") {
                return Err(IdentityError::Forbidden);
            }
            (Some(csrf), Some(origin))
        } else {
            (None, None)
        };
        self.verify(Verification {
            host,
            path: if elevated {
                "/verify-gestion"
            } else {
                "/verify"
            },
            method,
            credential_name: "cookie",
            credential: cookie,
            csrf,
            origin,
            elevated,
        })
        .await
    }

    pub async fn verify_bearer(
        &self,
        credential: &Justificatif,
    ) -> Result<VerifiedIdentity, IdentityError> {
        self.verify_mcp(McpResource::Vision, credential).await
    }

    pub(crate) async fn verify_mcp(
        &self,
        resource: McpResource,
        credential: &Justificatif,
    ) -> Result<VerifiedIdentity, IdentityError> {
        self.verify(Verification {
            host: resource.host(),
            path: "/verify-mcp",
            method: &Method::GET,
            credential_name: "authorization",
            credential: &format!("Bearer {}", credential.secret()),
            csrf: None,
            origin: None,
            elevated: false,
        })
        .await
    }

    pub async fn negative_probe(&self, host: &str) -> Result<(), IdentityError> {
        self.negative_endpoint(host, "/verify").await
    }

    pub async fn negative_probe_management(&self, host: &str) -> Result<(), IdentityError> {
        self.negative_endpoint(host, "/verify-gestion").await
    }

    pub(crate) async fn negative_probe_mcp(
        &self,
        resource: McpResource,
    ) -> Result<(), IdentityError> {
        self.negative_endpoint(resource.host(), "/verify-mcp").await
    }

    async fn negative_endpoint(&self, host: &str, path: &'static str) -> Result<(), IdentityError> {
        // A 401 with no credentials proves only this verification endpoint is
        // reachable and closed. It is not an end-to-end IdP/SSO/MFA qualification.
        let request = Request::builder()
            .method("GET")
            .uri(path)
            .header(header::HOST, "mrj-auth.internal")
            .header("x-forwarded-host", host)
            .header("x-forwarded-proto", "https")
            .header("x-original-method", "GET")
            .body(Empty::<Bytes>::new())
            .map_err(|_| IdentityError::Unavailable)?;
        let response = self.exchange(request).await?;
        if response.status() != StatusCode::UNAUTHORIZED
            || response.headers().contains_key("x-mrj-user")
        {
            return Err(IdentityError::Unavailable);
        }
        Ok(())
    }
}

impl AutoriserVision for IdentityClient {
    fn autoriser<'a>(&'a self, justificatif: &'a Justificatif) -> FuturVision<'a, Proprietaire> {
        Box::pin(async move {
            let identity = self
                .verify_bearer(justificatif)
                .await
                .map_err(|error| match error {
                    IdentityError::Unauthenticated => ErreurVision::IdentiteRequise,
                    IdentityError::Forbidden => ErreurVision::AccesInterdit,
                    IdentityError::Unavailable => ErreurVision::IdentiteRequise,
                })?;
            Proprietaire::valider(identity.owner)
        })
    }
}

pub(crate) struct RequestIdentity(pub VerifiedIdentity);
impl AutoriserVision for RequestIdentity {
    fn autoriser<'a>(&'a self, _: &'a Justificatif) -> FuturVision<'a, Proprietaire> {
        Box::pin(async move { Proprietaire::valider(self.0.owner.clone()) })
    }
}

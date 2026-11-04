use crate::{
    error::{Error, Result, require},
    json,
    oauth::{self, Parameters, get},
    oidc::form,
    state::{self, Broker},
};
use axum::{
    Router,
    body::{Body, to_bytes},
    extract::{Request, State},
    http::{HeaderMap, HeaderName, HeaderValue, StatusCode},
    response::Response,
};
use serde_json::{Value, json};
use std::{sync::Arc, time::Duration};
use tokio::sync::Semaphore;

struct Web {
    broker: Arc<Broker>,
    requests: Semaphore,
}
pub fn router(broker: Arc<Broker>) -> Router {
    Router::new().fallback(handle).with_state(Arc::new(Web {
        broker,
        requests: Semaphore::new(32),
    }))
}
struct Reply {
    status: u16,
    body: Value,
    headers: Vec<(&'static str, String)>,
}
impl Reply {
    fn json(status: u16, body: Value) -> Self {
        Self {
            status,
            body,
            headers: Vec::new(),
        }
    }
    fn header(mut self, name: &'static str, value: String) -> Self {
        self.headers.push((name, value));
        self
    }
    fn redirect(url: String) -> Self {
        Self::json(302, json!({})).header("location", url)
    }
    fn response(self) -> Result<Response> {
        let body = if self.status == 204 {
            String::new()
        } else {
            serde_json::to_string(&self.body).map_err(|_| Error(503))?
        };
        let mut response = Response::new(Body::from(body));
        *response.status_mut() = StatusCode::from_u16(self.status).map_err(|_| Error(503))?;
        for (name, value) in self.headers {
            response.headers_mut().append(
                HeaderName::from_static(name),
                HeaderValue::from_str(&value).map_err(|_| Error(503))?,
            );
        }
        for (name, value) in [
            ("content-type", "application/json"),
            ("cache-control", "no-store"),
            ("referrer-policy", "no-referrer"),
            ("x-content-type-options", "nosniff"),
        ] {
            response.headers_mut().insert(
                HeaderName::from_static(name),
                HeaderValue::from_static(value),
            );
        }
        Ok(response)
    }
}
fn failure(error: Error) -> Response {
    let mut reply = Reply::json(
        error.0,
        if error.0 == 503 {
            json!({"error":"temporarily_unavailable"})
        } else {
            json!({"error":"request_refused"})
        },
    );
    if error.0 == 503 {
        reply = reply.header("retry-after", "5".into());
    }
    match reply.response() {
        Ok(response) => response,
        Err(_) => {
            let mut response = Response::new(Body::empty());
            *response.status_mut() = StatusCode::SERVICE_UNAVAILABLE;
            response
        }
    }
}
async fn handle(State(web): State<Arc<Web>>, request: Request) -> Response {
    let Ok(_permit) = web.requests.try_acquire() else {
        return failure(Error(503));
    };
    match tokio::time::timeout(Duration::from_secs(45), route(&web.broker, request)).await {
        Ok(Ok(reply)) => match reply.response() {
            Ok(response) => response,
            Err(error) => failure(error),
        },
        Ok(Err(error)) => failure(error),
        Err(_) => failure(Error(503)),
    }
}
fn header<'a>(headers: &'a HeaderMap, name: &str) -> Result<Option<&'a str>> {
    let mut values = headers.get_all(name).iter();
    let value = values.next();
    require(values.next().is_none(), 400)?;
    value
        .map(|v| v.to_str().map_err(|_| Error(400)))
        .transpose()
}
fn hex(b: u8) -> Result<u8> {
    match b {
        b'0'..=b'9' => Ok(b - b'0'),
        b'a'..=b'f' => Ok(b - b'a' + 10),
        b'A'..=b'F' => Ok(b - b'A' + 10),
        _ => Err(Error(400)),
    }
}
fn decode(value: &str) -> Result<String> {
    let mut bytes = Vec::with_capacity(value.len());
    let mut iter = value.bytes();
    while let Some(b) = iter.next() {
        match b {
            b'+' => bytes.push(b' '),
            b'%' => {
                let a = hex(iter.next().ok_or(Error(400))?)?;
                let b = hex(iter.next().ok_or(Error(400))?)?;
                bytes.push((a << 4) | b);
            }
            _ => bytes.push(b),
        }
    }
    let result = String::from_utf8(bytes).map_err(|_| Error(400))?;
    require(!result.chars().any(char::is_control), 400)?;
    Ok(result)
}
pub fn parameters(value: &str) -> Result<Parameters> {
    require(value.len() <= 8192, 400)?;
    let mut p = Parameters::new();
    if value.is_empty() {
        return Ok(p);
    }
    for pair in value.split('&') {
        let (key, value) = pair.split_once('=').unwrap_or((pair, ""));
        let key = decode(key)?;
        let value = decode(value)?;
        require(!key.is_empty() && key.len() <= 128 && p.len() < 64, 400)?;
        require(p.insert(key, value).is_none(), 400)?;
    }
    Ok(p)
}
fn body<'a>(headers: &HeaderMap, body: &'a [u8], kind: &str) -> Result<&'a [u8]> {
    require(
        !body.is_empty()
            && body.len() <= 8192
            && header(headers, "content-type")?.is_some_and(|s| s.split(';').next() == Some(kind)),
        415,
    )?;
    Ok(body)
}
fn form_body(headers: &HeaderMap, bytes: &[u8]) -> Result<Parameters> {
    parameters(
        std::str::from_utf8(body(headers, bytes, "application/x-www-form-urlencoded")?)
            .map_err(|_| Error(400))?,
    )
}
fn json_body(headers: &HeaderMap, bytes: &[u8]) -> Result<Value> {
    json::object(body(headers, bytes, "application/json")?, 8192)
}
fn string<'a>(v: &'a Value, key: &str) -> Result<&'a str> {
    v.get(key).and_then(Value::as_str).ok_or(Error(400))
}

async fn route(b: &Broker, request: Request) -> Result<Reply> {
    let (parts, body_bytes) = request.into_parts();
    let headers = &parts.headers;
    let method = parts.method.as_str();
    let path = parts.uri.path();
    require(
        headers.len() <= 64
            && headers
                .iter()
                .map(|(k, v)| k.as_str().len() + v.as_bytes().len())
                .sum::<usize>()
                <= 16384,
        400,
    )?;
    for name in [
        "host",
        "x-forwarded-host",
        "x-forwarded-proto",
        "cookie",
        "authorization",
        "origin",
        "x-csrf-token",
        "x-original-method",
        "content-type",
        "content-length",
        "transfer-encoding",
    ] {
        header(headers, name)?;
    }
    let bytes = to_bytes(body_bytes, 8192).await.map_err(|_| Error(413))?;
    if method == "GET" {
        require(bytes.is_empty(), 400)?;
    }
    if method == "GET" && path == "/healthz" {
        return Ok(Reply::json(200, json!({"status":"ok"})));
    }
    if method == "GET" && path == "/readyz" {
        b.ready().await?;
        return Ok(Reply::json(200, json!({"status":"ready"})));
    }
    require(header(headers, "x-forwarded-proto")? == Some("https"), 503)?;
    let host = header(headers, "x-forwarded-host")?.ok_or(Error(403))?;
    b.client(host)?;
    let cookies = header(headers, "cookie")?;
    let p = parameters(parts.uri.query().unwrap_or(""))?;
    if path.starts_with("/oauth/")
        || path.starts_with("/.well-known/oauth-")
        || path == "/verify-mcp"
    {
        oauth::audience(host)?;
    }
    match (method, path) {
        (
            "GET",
            "/.well-known/oauth-authorization-server"
            | "/.well-known/oauth-protected-resource"
            | "/.well-known/oauth-protected-resource/mcp",
        ) => {
            return Ok(Reply::json(
                200,
                oauth::metadata(host, path != "/.well-known/oauth-authorization-server")?,
            ));
        }
        ("POST", "/oauth/register") => {
            return Ok(Reply::json(
                201,
                b.register(&json_body(headers, &bytes)?).await?,
            ));
        }
        ("POST", "/oauth/token") => {
            let parameters = form_body(headers, &bytes)?;
            return match b.mcp_tokens(host, &parameters).await {
                Ok(document) => Ok(Reply::json(200, document)),
                Err(Error(400 | 401 | 403)) => {
                    Ok(Reply::json(400, json!({"error":"invalid_grant"})))
                }
                Err(error) => Err(error),
            };
        }
        ("POST", "/oauth/revoke") => {
            let p = form_body(headers, &bytes)?;
            b.revoke_mcp(host, get(&p, "client_id")?, get(&p, "token")?)
                .await?;
            return Ok(Reply::json(200, json!({})));
        }
        ("GET", "/verify-mcp") => {
            let session = b
                .mcp_session(host, header(headers, "authorization")?)
                .await?
                .ok_or(Error(401))?;
            return Ok(Reply::json(204, json!({})).header("x-mrj-user", session.username));
        }
        ("GET", "/oauth/authorize") => {
            let session = match b.session(host, cookies).await {
                Ok(session) => session,
                Err(Error(401)) => None,
                Err(e) => return Err(e),
            };
            let Some(session) = session else {
                return Ok(Reply::redirect(format!(
                    "/auth/connexion?{}",
                    form(&[("retour", &parts.uri.to_string())])
                )));
            };
            return Ok(Reply::redirect(format!(
                "/#autorisation-mcp={}",
                b.request_mcp(host, &session, &p).await?
            )));
        }
        ("GET", "/auth/connexion") => {
            let (url, cookie) = b
                .begin(
                    host,
                    p.get("retour").map(String::as_str).unwrap_or("/"),
                    p.get("verification").is_some_and(|v| v == "renforcee"),
                )
                .await?;
            return Ok(Reply::redirect(url).header("set-cookie", cookie));
        }
        ("GET", "/auth/retour") => {
            let (url, cookie, clear) = b
                .callback(host, get(&p, "state")?, get(&p, "code")?, cookies)
                .await?;
            return Ok(Reply::redirect(url)
                .header("set-cookie", cookie)
                .header("set-cookie", clear));
        }
        ("GET", "/auth/configuration") => {
            return Ok(Reply::json(
                200,
                json!({"mode":"oidc","connexion":"/auth/connexion","compte":"https://log.mrj.am/ui/profile"}),
            ));
        }
        _ => {}
    }
    let session = b.session(host, cookies).await?.ok_or(Error(401))?;
    let csrf = || {
        state::csrf(
            &session,
            host,
            header(headers, "origin")?,
            header(headers, "x-csrf-token")?,
        )
    };
    match (method, path) {
        ("GET", "/auth/oauth-demande") => {
            oauth::audience(host)?;
            Ok(Reply::json(
                200,
                b.read_request(host, &session, get(&p, "id")?).await?,
            ))
        }
        ("POST", "/auth/oauth-consentement") => {
            oauth::audience(host)?;
            csrf()?;
            let d = json_body(headers, &bytes)?;
            let decision = string(&d, "decision")?;
            require(matches!(decision, "autoriser" | "refuser"), 400)?;
            Ok(Reply::json(
                200,
                json!({"redirection":b.consent(host,&session,string(&d,"id")?,decision=="autoriser").await?}),
            ))
        }
        ("GET", "/verify" | "/verify-gestion") => {
            if !matches!(header(headers, "x-original-method")?, Some("GET" | "HEAD")) {
                csrf()?;
            }
            if path == "/verify-gestion" {
                require(session.administrator && b.elevated(&session).await?, 403)?;
            }
            Ok(Reply::json(204, json!({})).header("x-mrj-user", session.username))
        }
        ("GET", "/auth/session") => Ok(Reply::json(200, b.session_document(&session).await?)),
        ("POST", "/auth/logout") => {
            csrf()?;
            Ok(Reply::json(200, json!({"signedOut":true}))
                .header("set-cookie", b.logout(host, cookies).await?))
        }
        ("POST", "/auth/revoquer-autres") => {
            csrf()?;
            b.revoke_others(&session).await?;
            Ok(Reply::json(
                200,
                json!({"sessionsApplicativesRevoquees":true}),
            ))
        }
        _ => Err(Error(404)),
    }
}

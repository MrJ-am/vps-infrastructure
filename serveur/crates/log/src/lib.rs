//! Bounded bridge to the official Kanidm user API. No identity provider or
//! authentication policy is reimplemented here. No listener, database or logger.
#![forbid(unsafe_code)]
mod aliases;
mod json;
mod tls;
pub use aliases::SqliteLoginAliases;
use serde::Deserialize;
use serde_json::{Value, json};
use std::{fmt, future::Future, net::IpAddr, pin::Pin, sync::Arc};
pub use tls::KanidmClient;

type Result<T> = std::result::Result<T, LogError>;
pub type NativeFuture<'a, T> = Pin<Box<dyn Future<Output = Result<T>> + Send + 'a>>;
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct LogError {
    code: &'static str,
    status: u16,
}
impl LogError {
    pub const fn new(code: &'static str, status: u16) -> Self {
        Self { code, status }
    }
    pub const fn code(self) -> &'static str {
        self.code
    }
    pub const fn status(self) -> u16 {
        self.status
    }
}
impl fmt::Display for LogError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.code)
    }
}
impl std::error::Error for LogError {}
fn require(ok: bool, code: &'static str, status: u16) -> Result<()> {
    if ok {
        Ok(())
    } else {
        Err(LogError::new(code, status))
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum NativeMethod {
    Get,
    Post,
    Delete,
}
pub struct NativeRequest {
    path: String,
    method: NativeMethod,
    document: Option<Value>,
    cookie: Option<String>,
    bearer: Option<String>,
    source_ip: Option<IpAddr>,
}
impl NativeRequest {
    pub fn path(&self) -> &str {
        &self.path
    }
    pub const fn method(&self) -> NativeMethod {
        self.method
    }
    pub fn document(&self) -> Option<&Value> {
        self.document.as_ref()
    }
    pub fn cookie(&self) -> Option<&str> {
        self.cookie.as_deref()
    }
    pub fn bearer(&self) -> Option<&str> {
        self.bearer.as_deref()
    }
    pub const fn source_ip(&self) -> Option<IpAddr> {
        self.source_ip
    }
}
pub struct NativeResponse {
    pub status: u16,
    pub body: Vec<u8>,
    pub set_cookies: Vec<String>,
    pub location: Option<String>,
}
pub trait NativeClient: Send + Sync {
    fn exchange(&self, request: NativeRequest) -> NativeFuture<'_, NativeResponse>;
}
/// Reads an existing, reviewed alias mapping. Resolving a login alias MUST NOT
/// create, merge or rebind a business identity. Email is never an identity claim.
pub trait LoginAliases: Send + Sync {
    fn resolve<'a>(&'a self, email: &'a str) -> NativeFuture<'a, Option<String>>;
}
pub struct UnconfiguredAliases;
impl LoginAliases for UnconfiguredAliases {
    fn resolve<'a>(&'a self, _: &'a str) -> NativeFuture<'a, Option<String>> {
        Box::pin(async { Err(LogError::new("alias_non_raccordes", 503)) })
    }
}
pub struct PresentationContext<'a> {
    pub host: &'a str,
    pub origin: &'a str,
    pub cookie: Option<&'a str>,
    pub source_ip: Option<IpAddr>,
}
pub struct PresentationResponse {
    pub status: u16,
    pub document: Value,
    pub set_cookies: Vec<String>,
}
#[derive(Clone)]
pub struct LogService {
    native: Arc<dyn NativeClient>,
    aliases: Arc<dyn LoginAliases>,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Request {
    action: String,
    #[serde(default)]
    document: Value,
    #[serde(default)]
    parametre: Option<String>,
}
impl LogService {
    pub fn new(native: Arc<dyn NativeClient>, aliases: Arc<dyn LoginAliases>) -> Self {
        Self { native, aliases }
    }
    pub async fn presentation(
        &self,
        context: PresentationContext<'_>,
        body: &[u8],
    ) -> Result<PresentationResponse> {
        require(
            context.host == "log.mrj.am" && context.origin == "https://log.mrj.am",
            "origine_interdite",
            403,
        )?;
        require(
            !body.is_empty() && body.len() <= 65_536,
            "requete_trop_large",
            413,
        )?;
        if let Some(cookie) = context.cookie {
            require(
                cookie.len() < 16384 && cookie.bytes().all(|v| (32..=126).contains(&v)),
                "cookie_invalide",
                400,
            )?;
        }
        let mut p: Request = serde_json::from_value(json::parse(body)?)
            .map_err(|_| LogError::new("champs_invalides", 400))?;
        let fixed = match p.action.as_str() {
            "auth" => Some("/v1/auth"),
            "reauth" => Some("/v1/reauth"),
            "profil" => Some("/v1/self/_uat"),
            "applications" => Some("/v1/self/_applinks"),
            "deconnexion" => Some("/v1/logout"),
            "oauth" => Some("/oauth2/authorise"),
            "consentir" => Some("/oauth2/authorise/permit"),
            "refuser" => Some("/oauth2/authorise/reject"),
            "recuperer" => Some("/v1/credential/_exchange_intent"),
            "statut" => Some("/v1/credential/_status"),
            "modifier" => Some("/v1/credential/_update"),
            "enregistrer" => Some("/v1/credential/_commit"),
            "annuler" => Some("/v1/credential/_cancel"),
            "ouvrir" | "sessions" | "revoquer" => None,
            _ => return Err(LogError::new("operation_inconnue", 400)),
        };
        if p.action != "revoquer" {
            require(p.parametre.is_none(), "champs_invalides", 400)?;
        }
        let path = if let Some(path) = fixed {
            path.to_owned()
        } else {
            // Subject is resolved from the authenticated upstream session, never
            // accepted from a request parameter, JWT payload or email address.
            let response = self
                .native
                .exchange(NativeRequest {
                    path: "/v1/self".into(),
                    method: NativeMethod::Get,
                    document: None,
                    cookie: context.cookie.map(str::to_owned),
                    bearer: None,
                    source_ip: context.source_ip,
                })
                .await?;
            require(response.status == 200, "identite_requise", 401)?;
            require(
                response.body.len() <= 524288,
                "reponse_native_invalide",
                502,
            )?;
            let document: Value = json::parse(&response.body)
                .map_err(|_| LogError::new("reponse_native_invalide", 502))?;
            let values = document["youare"]["attrs"]["uuid"]
                .as_array()
                .ok_or(LogError::new("reponse_native_invalide", 502))?;
            require(values.len() == 1, "reponse_native_invalide", 502)?;
            let subject = values
                .first()
                .and_then(Value::as_str)
                .filter(|s| uuid(s))
                .ok_or(LogError::new("reponse_native_invalide", 502))?;
            match p.action.as_str() {
                "ouvrir" => format!("/v1/person/{subject}/_credential/_update"),
                "sessions" => format!("/v1/account/{subject}/_user_auth_token"),
                _ => {
                    let session = p
                        .parametre
                        .as_deref()
                        .filter(|s| uuid(s))
                        .ok_or(LogError::new("session_invalide", 400))?;
                    format!("/v1/account/{subject}/_user_auth_token/{session}")
                }
            }
        };
        if p.action == "auth" {
            let doc = p
                .document
                .as_object()
                .ok_or(LogError::new("champs_invalides", 400))?;
            require(doc.len() == 1, "champs_invalides", 400)?;
            let step = doc
                .get("step")
                .and_then(Value::as_object)
                .ok_or(LogError::new("champs_invalides", 400))?;
            require(step.len() == 1, "champs_invalides", 400)?;
            if let Some(init) = step.get("init2") {
                let username = init
                    .get("username")
                    .and_then(Value::as_str)
                    .filter(|s| {
                        !s.is_empty()
                            && s.len() <= 320
                            && s.chars().all(|c| c >= ' ' && !c.is_control())
                    })
                    .ok_or(LogError::new("identifiant_invalide", 400))?;
                let login = if username.contains('@') {
                    self.aliases
                        .resolve(&username.to_lowercase())
                        .await?
                        .unwrap_or_else(|| "mrjam-compte-inconnu".into())
                } else {
                    username.to_owned()
                };
                require(
                    !login.is_empty() && login.len() <= 320 && !login.chars().any(char::is_control),
                    "alias_invalide",
                    502,
                )?;
                p.document = json!({"step":{"init2":{"username":login,"issue":"cookie","privileged":false}}});
            } else {
                require(
                    step.contains_key("begin") || step.contains_key("cred"),
                    "champs_invalides",
                    400,
                )?;
            }
        }
        if p.action == "reauth" {
            p.document = json!("cookie");
        }
        let method = match p.action.as_str() {
            "profil" | "applications" | "deconnexion" | "ouvrir" | "sessions" => NativeMethod::Get,
            "revoquer" => NativeMethod::Delete,
            _ => NativeMethod::Post,
        };
        let oauth = matches!(p.action.as_str(), "oauth" | "consentir" | "refuser");
        let bearer = if oauth {
            Some(cookie_bearer(context.cookie)?)
        } else {
            None
        };
        let response = self
            .native
            .exchange(NativeRequest {
                path,
                method,
                document: if method == NativeMethod::Post {
                    Some(p.document)
                } else {
                    None
                },
                cookie: context.cookie.map(str::to_owned),
                bearer,
                source_ip: context.source_ip,
            })
            .await?;
        require(
            response.body.len() <= 524288 && (200..=599).contains(&response.status),
            "reponse_native_invalide",
            502,
        )?;
        let mut result =
            if oauth && (200..400).contains(&response.status) && response.location.is_some() {
                let location = response
                    .location
                    .as_deref()
                    .ok_or(LogError::new("reponse_native_invalide", 502))?;
                let url = url::Url::parse(location)
                    .map_err(|_| LogError::new("redirection_invalide", 502))?;
                require(
                    url.scheme() == "https"
                        && url.host_str().is_some()
                        && url.username().is_empty()
                        && url.password().is_none(),
                    "redirection_invalide",
                    502,
                )?;
                json!({"redirection":location})
            } else if response.body.is_empty() {
                Value::Null
            } else {
                json::parse(&response.body)
                    .map_err(|_| LogError::new("reponse_native_invalide", 502))?
            };
        let connected = matches!(p.action.as_str(), "auth" | "reauth")
            && response.status == 200
            && result.get("state").and_then(|s| s.get("success")).is_some();
        if connected {
            result = json!({"state":{"success":""}});
        }
        let cookies = response
            .set_cookies
            .iter()
            .map(|s| bounded_cookie(s, connected))
            .collect::<Result<Vec<_>>>()?;
        let status = if (300..400).contains(&response.status) {
            require(
                oauth && response.location.is_some(),
                "redirection_native_inattendue",
                502,
            )?;
            200
        } else {
            response.status
        };
        Ok(PresentationResponse {
            status,
            document: result,
            set_cookies: cookies,
        })
    }
}
fn uuid(s: &str) -> bool {
    s.len() == 36
        && s.bytes().enumerate().all(|(n, b)| {
            if [8, 13, 18, 23].contains(&n) {
                b == b'-'
            } else {
                b.is_ascii_hexdigit()
            }
        })
}
fn cookie_bearer(cookie: Option<&str>) -> Result<String> {
    let values = cookie
        .unwrap_or("")
        .split(';')
        .map(str::trim)
        .filter_map(|s| s.strip_prefix("bearer="))
        .collect::<Vec<_>>();
    require(
        values.len() == 1 && !values[0].is_empty(),
        "identite_requise",
        401,
    )?;
    Ok(values[0].to_owned())
}
fn bounded_cookie(cookie: &str, connected: bool) -> Result<String> {
    require(
        cookie.len() <= 16384 && cookie.bytes().all(|b| (32..=126).contains(&b)),
        "cookie_natif_invalide",
        502,
    )?;
    let parts = cookie.split(';').map(str::trim).collect::<Vec<_>>();
    require(
        parts.first().is_some_and(|s| s.contains('=')),
        "cookie_natif_invalide",
        502,
    )?;
    let mut http_only = false;
    let mut secure = false;
    let mut same_site = false;
    let mut path = false;
    let mut max_age = false;
    let mut attributes = std::collections::BTreeSet::new();
    for attribute in parts.iter().skip(1) {
        let (key, value) = attribute
            .split_once('=')
            .map_or((*attribute, None), |(k, v)| (k, Some(v.trim())));
        let key = key.trim().to_ascii_lowercase();
        require(
            attributes.insert(key.clone()),
            "cookie_attribut_ambigu",
            502,
        )?;
        require(key != "domain", "cookie_domaine_interdit", 502)?;
        match key.as_str() {
            "path" => {
                require(value == Some("/"), "cookie_chemin_invalide", 502)?;
                path = true;
            }
            "samesite" => {
                require(
                    value.is_some_and(|v| {
                        v.eq_ignore_ascii_case("lax") || v.eq_ignore_ascii_case("strict")
                    }),
                    "cookie_samesite_invalide",
                    502,
                )?;
                same_site = true;
            }
            "httponly" => {
                require(value.is_none(), "cookie_natif_invalide", 502)?;
                http_only = true;
            }
            "secure" => {
                require(value.is_none(), "cookie_natif_invalide", 502)?;
                secure = true;
            }
            "max-age" => {
                require(
                    value.is_some_and(|v| v.parse::<i64>().is_ok()),
                    "cookie_natif_invalide",
                    502,
                )?;
                max_age = true;
            }
            _ => {}
        }
    }
    let mut result = cookie.to_owned();
    // Retain the existing browser persistence ceiling. Kanidm expiry/revocation
    // remains authoritative and may be much shorter than this cookie lifetime.
    if connected && cookie.starts_with("bearer=") && !max_age {
        result.push_str("; Max-Age=7776000");
    }
    if !path {
        result.push_str("; Path=/");
    }
    if !http_only {
        result.push_str("; HttpOnly");
    }
    if !secure {
        result.push_str("; Secure");
    }
    if !same_site {
        result.push_str("; SameSite=Lax");
    }
    Ok(result)
}

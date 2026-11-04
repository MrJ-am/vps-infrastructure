use crate::{
    crypto,
    error::{Error, Result, require},
    json,
};
use base64::{Engine, engine::general_purpose::STANDARD};
use http_body_util::{BodyExt, Full};
use hyper::{Request, body::Bytes};
use hyper_util::rt::TokioIo;
use rustls::{
    ClientConfig, RootCertStore,
    pki_types::{CertificateDer, ServerName, pem::PemObject},
};
use serde_json::Value;
use std::{net::SocketAddr, sync::Arc, time::Duration};
use tokio::{net::TcpStream, task::JoinHandle};
use tokio_rustls::TlsConnector;

pub struct Client {
    pub id: String,
    secret: String,
}
impl Client {
    pub fn new(id: String, secret: String) -> Self {
        Self { id, secret }
    }
}
#[derive(Clone)]
pub struct Transport {
    endpoint: SocketAddr,
    connector: TlsConnector,
}
struct Connection(JoinHandle<()>);
impl Drop for Connection {
    fn drop(&mut self) {
        self.0.abort();
    }
}
pub struct Response {
    pub status: u16,
    pub document: Value,
}
pub fn form(pairs: &[(&str, &str)]) -> String {
    url::form_urlencoded::Serializer::new(String::new())
        .extend_pairs(pairs.iter().copied())
        .finish()
}

impl Transport {
    pub fn new(endpoint: SocketAddr, ca: &[u8]) -> Result<Self> {
        require(
            endpoint.ip().is_loopback()
                && endpoint.port() != 0
                && !ca.is_empty()
                && ca.len() <= 1_048_576,
            503,
        )?;
        let mut roots = RootCertStore::empty();
        for cert in CertificateDer::pem_slice_iter(ca) {
            roots
                .add(cert.map_err(|_| Error(503))?)
                .map_err(|_| Error(503))?;
        }
        require(!roots.is_empty(), 503)?;
        let tls =
            ClientConfig::builder_with_provider(Arc::new(rustls::crypto::ring::default_provider()))
                .with_safe_default_protocol_versions()
                .map_err(|_| Error(503))?
                .with_root_certificates(roots)
                .with_no_client_auth();
        Ok(Self {
            endpoint,
            connector: TlsConnector::from(Arc::new(tls)),
        })
    }
    async fn exchange_inner(
        &self,
        client: &Client,
        path: &str,
        pairs: Option<&[(&str, &str)]>,
    ) -> Result<Response> {
        let tcp = TcpStream::connect(self.endpoint)
            .await
            .map_err(|_| Error(503))?;
        let tls = self
            .connector
            .connect(
                ServerName::try_from("log.mrj.am").map_err(|_| Error(503))?,
                tcp,
            )
            .await
            .map_err(|_| Error(503))?;
        let (mut sender, connection) = hyper::client::conn::http1::Builder::new()
            .max_headers(32)
            .max_buf_size(16384)
            .handshake(TokioIo::new(tls))
            .await
            .map_err(|_| Error(503))?;
        let _task = Connection(tokio::spawn(async move {
            let _ = connection.await;
        }));
        let mut builder = Request::builder()
            .method(if pairs.is_some() { "POST" } else { "GET" })
            .uri(path)
            .header("Host", "log.mrj.am")
            .header("Accept", "application/json");
        let body = if let Some(pairs) = pairs {
            builder = builder.header("Content-Type", "application/x-www-form-urlencoded");
            if path == "/oauth2/token" {
                let encoded_id = form(&[("", &client.id)]);
                let encoded_secret = form(&[("", &client.secret)]);
                let basic = format!(
                    "{}:{}",
                    encoded_id.trim_start_matches('='),
                    encoded_secret.trim_start_matches('=')
                );
                builder =
                    builder.header("Authorization", format!("Basic {}", STANDARD.encode(basic)));
            }
            let body = form(pairs);
            require(body.len() <= 32768, 400)?;
            body
        } else {
            String::new()
        };
        let request = builder
            .body(Full::new(Bytes::from(body)))
            .map_err(|_| Error(503))?;
        let response = sender.send_request(request).await.map_err(|_| Error(503))?;
        let status = response.status().as_u16();
        require(
            (200..=599).contains(&status) && !(300..=399).contains(&status),
            503,
        )?;
        let mut body = response.into_body();
        let mut bytes = Vec::new();
        while let Some(frame) = body.frame().await {
            let frame = frame.map_err(|_| Error(503))?;
            if let Some(data) = frame.data_ref() {
                require(bytes.len() + data.len() <= 65536, 503)?;
                bytes.extend_from_slice(data);
            }
        }
        let document = if bytes.is_empty() {
            Value::Null
        } else {
            json::object(&bytes, 65536).map_err(|_| Error(503))?
        };
        Ok(Response { status, document })
    }
    pub async fn exchange(
        &self,
        client: &Client,
        path: &str,
        pairs: Option<&[(&str, &str)]>,
    ) -> Result<Response> {
        require(
            matches!(
                path,
                "/oauth2/token" | "/oauth2/token/introspect" | "/oauth2/token/revoke"
            ) || path == format!("/oauth2/openid/{}/public_key.jwk", client.id)
                || path
                    == format!(
                        "/oauth2/openid/{}/.well-known/openid-configuration",
                        client.id
                    ),
            503,
        )?;
        tokio::time::timeout(
            Duration::from_secs(10),
            self.exchange_inner(client, path, pairs),
        )
        .await
        .map_err(|_| Error(503))?
    }
    pub async fn jwks(&self, client: &Client) -> Result<Value> {
        let response = self
            .exchange(
                client,
                &format!("/oauth2/openid/{}/public_key.jwk", client.id),
                None,
            )
            .await?;
        require(response.status == 200 && response.document.is_object(), 503)?;
        Ok(response.document)
    }
    pub async fn discovery(&self, client: &Client) -> Result<()> {
        let response = self
            .exchange(
                client,
                &format!(
                    "/oauth2/openid/{}/.well-known/openid-configuration",
                    client.id
                ),
                None,
            )
            .await?;
        require(response.status == 200, 503)?;
        let d = response.document;
        require(
            d["issuer"] == crypto::issuer(&client.id)
                && d["authorization_endpoint"] == "https://log.mrj.am/ui/oauth2"
                && d["token_endpoint"] == "https://log.mrj.am/oauth2/token"
                && d["jwks_uri"] == format!("{}/public_key.jwk", crypto::issuer(&client.id)),
            503,
        )?;
        for (key, value) in [
            ("response_types_supported", "code"),
            ("id_token_signing_alg_values_supported", "ES256"),
            ("code_challenge_methods_supported", "S256"),
            (
                "token_endpoint_auth_methods_supported",
                "client_secret_basic",
            ),
        ] {
            let a = d
                .get(key)
                .and_then(Value::as_array)
                .filter(|a| !a.is_empty() && a.len() <= 32)
                .ok_or(Error(503))?;
            require(
                a.iter().all(Value::is_string) && a.iter().any(|v| v == value),
                503,
            )?;
        }
        Ok(())
    }
    pub async fn introspect(&self, client: &Client, token: &str) -> Result<Value> {
        require(crypto::text(token, 1, 16384), 503)?;
        let response = self
            .exchange(
                client,
                "/oauth2/token/introspect",
                Some(&[("token", token), ("token_type_hint", "access_token")]),
            )
            .await?;
        require(
            response.status == 200
                && response
                    .document
                    .get("active")
                    .and_then(Value::as_bool)
                    .is_some(),
            503,
        )?;
        Ok(response.document)
    }
}

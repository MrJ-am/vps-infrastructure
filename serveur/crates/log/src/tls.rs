use crate::{
    LogError, NativeClient, NativeFuture, NativeMethod, NativeRequest, NativeResponse, Result,
    require,
};
use http_body_util::{BodyExt, Full};
use hyper::{Request, body::Bytes};
use hyper_util::rt::TokioIo;
use rustls::{
    ClientConfig, RootCertStore,
    pki_types::{CertificateDer, ServerName, pem::PemObject},
};
use std::{net::SocketAddr, sync::Arc, time::Duration};
use tokio::{net::TcpStream, task::JoinHandle};
use tokio_rustls::TlsConnector;

#[derive(Clone)]
pub struct KanidmClient {
    address: SocketAddr,
    connector: TlsConnector,
}
struct ConnectionTask(JoinHandle<()>);
impl Drop for ConnectionTask {
    fn drop(&mut self) {
        self.0.abort();
    }
}
impl KanidmClient {
    /// Public CA certificates only. TLS authenticates log.mrj.am while the
    /// transport is fixed to an explicitly configured loopback socket.
    pub fn from_ca_pem(address: SocketAddr, public_ca_pem: &[u8]) -> Result<Self> {
        require(
            address.ip().is_loopback() && address.port() != 0,
            "adresse_idp_interdite",
            400,
        )?;
        require(
            !public_ca_pem.is_empty() && public_ca_pem.len() <= 262144,
            "ca_invalide",
            400,
        )?;
        let mut roots = RootCertStore::empty();
        for certificate in CertificateDer::pem_slice_iter(public_ca_pem) {
            roots
                .add(certificate.map_err(|_| LogError::new("ca_invalide", 400))?)
                .map_err(|_| LogError::new("ca_invalide", 400))?;
        }
        require(!roots.is_empty(), "ca_invalide", 400)?;
        let provider = Arc::new(rustls::crypto::ring::default_provider());
        let config = ClientConfig::builder_with_provider(provider)
            .with_safe_default_protocol_versions()
            .map_err(|_| LogError::new("tls_indisponible", 503))?
            .with_root_certificates(roots)
            .with_no_client_auth();
        Ok(Self {
            address,
            connector: TlsConnector::from(Arc::new(config)),
        })
    }
    /// Transport health only. No profile, session, alias or application data is
    /// read. A successful TLS handshake is not a qualification of SSO flows.
    pub async fn ready(&self) -> Result<()> {
        tokio::time::timeout(Duration::from_secs(10), async {
            let tcp = TcpStream::connect(self.address)
                .await
                .map_err(|_| LogError::new("identite_indisponible", 503))?;
            let name = ServerName::try_from("log.mrj.am")
                .map_err(|_| LogError::new("tls_indisponible", 503))?;
            let _tls = self
                .connector
                .connect(name, tcp)
                .await
                .map_err(|_| LogError::new("identite_indisponible", 503))?;
            Ok(())
        })
        .await
        .map_err(|_| LogError::new("identite_indisponible", 503))?
    }
    async fn send(&self, input: NativeRequest) -> Result<NativeResponse> {
        let tcp = TcpStream::connect(self.address)
            .await
            .map_err(|_| LogError::new("identite_indisponible", 503))?;
        let name = ServerName::try_from("log.mrj.am")
            .map_err(|_| LogError::new("tls_indisponible", 503))?;
        let tls = self
            .connector
            .connect(name, tcp)
            .await
            .map_err(|_| LogError::new("identite_indisponible", 503))?;
        let (mut client, connection) = hyper::client::conn::http1::Builder::new()
            .max_buf_size(16384)
            .handshake(TokioIo::new(tls))
            .await
            .map_err(|_| LogError::new("identite_indisponible", 503))?;
        let _task = ConnectionTask(tokio::spawn(async move {
            let _ = connection.await;
        }));
        let method = match input.method() {
            NativeMethod::Get => "GET",
            NativeMethod::Post => "POST",
            NativeMethod::Delete => "DELETE",
        };
        let mut builder = Request::builder()
            .method(method)
            .uri(input.path())
            .header("Host", "log.mrj.am")
            .header("Origin", "https://log.mrj.am")
            .header("Accept", "application/json");
        if let Some(cookie) = input.cookie() {
            builder = builder.header("Cookie", cookie);
        }
        if let Some(bearer) = input.bearer() {
            builder = builder.header("Authorization", format!("Bearer {bearer}"));
        }
        if let Some(ip) = input.source_ip() {
            builder = builder.header("X-Forwarded-For", ip.to_string());
        }
        let bytes = match input.document() {
            Some(doc) => {
                builder = builder.header("Content-Type", "application/json");
                doc.to_string().into_bytes()
            }
            None => Vec::new(),
        };
        let request = builder
            .body(Full::new(Bytes::from(bytes)))
            .map_err(|_| LogError::new("requete_native_invalide", 400))?;
        let response = client
            .send_request(request)
            .await
            .map_err(|_| LogError::new("identite_indisponible", 503))?;
        let status = response.status().as_u16();
        let set_cookies = response
            .headers()
            .get_all("set-cookie")
            .iter()
            .map(|v| {
                v.to_str()
                    .map(str::to_owned)
                    .map_err(|_| LogError::new("reponse_native_invalide", 502))
            })
            .collect::<Result<Vec<_>>>()?;
        require(set_cookies.len() <= 16, "reponse_native_invalide", 502)?;
        let locations = response
            .headers()
            .get_all("location")
            .iter()
            .collect::<Vec<_>>();
        require(locations.len() <= 1, "reponse_native_invalide", 502)?;
        let location = locations
            .first()
            .map(|v| {
                v.to_str()
                    .map(str::to_owned)
                    .map_err(|_| LogError::new("reponse_native_invalide", 502))
            })
            .transpose()?;
        let mut body = response.into_body();
        let mut bytes = Vec::new();
        while let Some(frame) = body.frame().await {
            let frame = frame.map_err(|_| LogError::new("reponse_native_invalide", 502))?;
            if let Some(data) = frame.data_ref() {
                require(
                    bytes.len() + data.len() <= 524288,
                    "reponse_native_trop_large",
                    502,
                )?;
                bytes.extend_from_slice(data);
            }
        }
        Ok(NativeResponse {
            status,
            body: bytes,
            set_cookies,
            location,
        })
    }
}
impl NativeClient for KanidmClient {
    fn exchange(&self, request: NativeRequest) -> NativeFuture<'_, NativeResponse> {
        Box::pin(async move {
            tokio::time::timeout(Duration::from_secs(10), self.send(request))
                .await
                .map_err(|_| LogError::new("identite_indisponible", 503))?
        })
    }
}

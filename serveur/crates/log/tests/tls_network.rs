//! Explicit local TLS qualification. Synthetic one-day certificate/key are
//! generated in a private temporary directory; never copied to a repository.
use mrjam_log::{KanidmClient, LogService, PresentationContext, UnconfiguredAliases};
use rustls::{
    ServerConfig,
    pki_types::{CertificateDer, PrivateKeyDer, pem::PemObject},
};
use std::{
    path::PathBuf,
    process::{Command, Stdio},
    sync::Arc,
    time::{Duration, SystemTime, UNIX_EPOCH},
};
use tokio::{
    io::{AsyncReadExt, AsyncWriteExt},
    net::TcpListener,
};
use tokio_rustls::TlsAcceptor;
type Error = Box<dyn std::error::Error + Send + Sync>;
struct Fixture(PathBuf);
impl Drop for Fixture {
    fn drop(&mut self) {
        let _ = std::fs::remove_dir_all(&self.0);
    }
}
fn certificate() -> Result<(Fixture, Vec<u8>, Arc<ServerConfig>), Error> {
    let path = std::env::temp_dir().join(format!(
        "mrjam-log-synthetic-{}-{}",
        std::process::id(),
        SystemTime::now().duration_since(UNIX_EPOCH)?.as_nanos()
    ));
    std::fs::create_dir(&path)?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o700))?;
    }
    let fixture = Fixture(path);
    let key = fixture.0.join("synthetic-key.pem");
    let cert = fixture.0.join("synthetic-cert.pem");
    let status = Command::new("openssl")
        .args([
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "1",
            "-subj",
            "/CN=log.mrj.am",
            "-addext",
            "subjectAltName=DNS:log.mrj.am",
            "-addext",
            "basicConstraints=critical,CA:FALSE",
            "-keyout",
        ])
        .arg(&key)
        .arg("-out")
        .arg(&cert)
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()?;
    if !status.success() {
        return Err("synthetic certificate generation failed".into());
    }
    let pem = std::fs::read(cert)?;
    let certs = CertificateDer::pem_slice_iter(&pem).collect::<Result<Vec<_>, _>>()?;
    let key = PrivateKeyDer::from_pem_slice(&std::fs::read(key)?)?;
    let config =
        ServerConfig::builder_with_provider(Arc::new(rustls::crypto::ring::default_provider()))
            .with_safe_default_protocol_versions()?
            .with_no_client_auth()
            .with_single_cert(certs, key)?;
    Ok((fixture, pem, Arc::new(config)))
}
#[tokio::test]
async fn real_tls_preserves_fixed_host_cookie_and_bounds_response() -> Result<(), Error> {
    let (_fixture, pem, config) = certificate()?;
    for oversized in [false, true] {
        let listener = TcpListener::bind("127.0.0.1:0").await?;
        let address = listener.local_addr()?;
        let acceptor = TlsAcceptor::from(config.clone());
        let task = tokio::spawn(async move {
            let (socket, _) = listener.accept().await?;
            let mut stream = acceptor.accept(socket).await?;
            let mut request = Vec::new();
            let mut byte = [0u8; 1];
            while !request.ends_with(b"\r\n\r\n") && request.len() < 16384 {
                stream.read_exact(&mut byte).await?;
                request.push(byte[0]);
            }
            let text = String::from_utf8(request)?;
            if !text.starts_with("GET /v1/self/_uat HTTP/1.1\r\n")
                || !text.to_ascii_lowercase().contains("host: log.mrj.am")
                || !text.contains("synthetic-cookie")
            {
                return Err::<(), Error>("unexpected request to synthetic TLS endpoint".into());
            }
            let body = if oversized {
                vec![b'x'; 524289]
            } else {
                br#"{"synthetic":true}"#.to_vec()
            };
            let head = format!(
                "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
                body.len()
            );
            stream.write_all(head.as_bytes()).await?;
            // The bounded client may close as soon as the excess is observed.
            let _ = stream.write_all(&body).await;
            let _ = stream.shutdown().await;
            Ok(())
        });
        let client = KanidmClient::from_ca_pem(address, &pem)?;
        let service = LogService::new(Arc::new(client), Arc::new(UnconfiguredAliases));
        let response = service
            .presentation(
                PresentationContext {
                    host: "log.mrj.am",
                    origin: "https://log.mrj.am",
                    cookie: Some("bearer=synthetic-cookie"),
                    source_ip: None,
                },
                br#"{"action":"profil"}"#,
            )
            .await;
        if oversized {
            if response
                .err()
                .is_none_or(|e| e.code() != "reponse_native_trop_large")
            {
                return Err("oversized response not rejected".into());
            }
        } else if response?.document["synthetic"] != true {
            return Err("TLS response not received".into());
        }
        tokio::time::timeout(Duration::from_secs(15), task).await???;
    }
    Ok(())
}
#[tokio::test]
async fn untrusted_certificate_fails_without_disabling_tls() -> Result<(), Error> {
    let (_trusted, pem, _) = certificate()?;
    let (_server, _other_pem, config) = certificate()?;
    let listener = TcpListener::bind("127.0.0.1:0").await?;
    let address = listener.local_addr()?;
    let task = tokio::spawn(async move {
        let (socket, _) = listener.accept().await?;
        let _ = TlsAcceptor::from(config).accept(socket).await;
        Ok::<(), Error>(())
    });
    let service = LogService::new(
        Arc::new(KanidmClient::from_ca_pem(address, &pem)?),
        Arc::new(UnconfiguredAliases),
    );
    let result = service
        .presentation(
            PresentationContext {
                host: "log.mrj.am",
                origin: "https://log.mrj.am",
                cookie: None,
                source_ip: None,
            },
            br#"{"action":"profil"}"#,
        )
        .await;
    if result.is_ok() {
        return Err("untrusted TLS peer accepted".into());
    }
    tokio::time::timeout(Duration::from_secs(15), task).await???;
    Ok(())
}

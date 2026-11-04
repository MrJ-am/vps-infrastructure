//! A fixed Unix capability for deleting a native Kanidm person.
//! The replay worker never receives the upstream administrative API token.
use http_body_util::{BodyExt, Empty};
use hyper::{Request, body::Bytes};
use hyper_util::rt::TokioIo;
use rustls::{
    ClientConfig, RootCertStore,
    pki_types::{CertificateDer, ServerName, pem::PemObject},
};
use serde::Deserialize;
use std::{
    fs::{self, File},
    io::Read,
    os::unix::fs::{FileTypeExt, MetadataExt, PermissionsExt},
    path::{Component, Path},
    sync::Arc,
    time::Duration,
};
use tokio::{
    io::{AsyncReadExt, AsyncWriteExt},
    net::{TcpStream, UnixListener, UnixStream},
    task::{JoinHandle, JoinSet},
};
use tokio_rustls::TlsConnector;

const SOCKET: &str = "/run/mrjam-identity-deletion/delete.sock";
const CREDENTIAL: &str = "/run/credentials/mrjam-identity-deletion.service/kanidm";
const ISSUER: &str = "https://log.mrj.am/oauth2/openid/mrjam-vision";
const SERVICE_UID: u32 = 948;
const REPLAY_UID: u32 = 944;
const REPLAY_GID: u32 = 944;

#[derive(Debug, Clone, Copy, PartialEq)]
enum Failure {
    Refused,
    Unavailable,
}
type Result<T> = std::result::Result<T, Failure>;
fn require(value: bool) -> Result<()> {
    if value { Ok(()) } else { Err(Failure::Refused) }
}
fn unavailable<T>(_: T) -> Failure {
    Failure::Unavailable
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Configuration {
    schema_version: u8,
    kanidm_ca_file: String,
    kanidm_ca_sha256: String,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Deletion {
    issuer: String,
    subject: String,
}

fn uuid(value: &str) -> bool {
    value.len() == 36
        && value != "00000000-0000-0000-0000-000000000000"
        && value.bytes().enumerate().all(|(i, b)| {
            if [8, 13, 18, 23].contains(&i) {
                b == b'-'
            } else {
                b.is_ascii_digit() || (b'a'..=b'f').contains(&b)
            }
        })
}
fn document(raw: &[u8]) -> Result<Deletion> {
    require((2..=256).contains(&raw.len()) && raw.last() == Some(&b'\n'))?;
    let value: Deletion = serde_json::from_slice(raw).map_err(|_| Failure::Refused)?;
    require(value.issuer == ISSUER && uuid(&value.subject))?;
    Ok(value)
}

/// Every path component is opened without following symbolic links.
fn open_regular(path: &Path, maximum: usize, private: bool) -> Result<Vec<u8>> {
    use rustix::fs::{Mode, OFlags, open, openat};
    require(path.is_absolute())?;
    let names: Vec<_> = path.components().collect();
    require(
        names.len() > 1
            && names
                .iter()
                .skip(1)
                .all(|p| matches!(p, Component::Normal(_))),
    )?;
    let mut parent = open(
        "/",
        OFlags::RDONLY | OFlags::DIRECTORY | OFlags::NOFOLLOW | OFlags::CLOEXEC,
        Mode::empty(),
    )
    .map_err(unavailable)?;
    for name in &names[1..names.len() - 1] {
        parent = openat(
            &parent,
            name.as_os_str(),
            OFlags::RDONLY | OFlags::DIRECTORY | OFlags::NOFOLLOW | OFlags::CLOEXEC,
            Mode::empty(),
        )
        .map_err(unavailable)?;
    }
    let last = names.last().ok_or(Failure::Refused)?;
    let fd = openat(
        &parent,
        last.as_os_str(),
        OFlags::RDONLY | OFlags::NOFOLLOW | OFlags::NONBLOCK | OFlags::CLOEXEC,
        Mode::empty(),
    )
    .map_err(unavailable)?;
    let mut file = File::from(fd);
    let before = file.metadata().map_err(unavailable)?;
    require(
        before.is_file()
            && before.nlink() == 1
            && before.len() > 0
            && before.len() <= maximum as u64,
    )?;
    if private {
        let parent_meta = File::from(parent).metadata().map_err(unavailable)?;
        require(
            path == Path::new(CREDENTIAL)
                && before.uid() == 0
                && before.gid() == 0
                && before.mode() & 0o7777 == 0o440
                && parent_meta.uid() == 0
                && parent_meta.gid() == 0
                && parent_meta.mode() & 0o7777 == 0o550
                && rustix::fs::fstatvfs(&file)
                    .map_err(unavailable)?
                    .f_flag
                    .contains(rustix::fs::StatVfsMountFlags::RDONLY),
        )?;
    } else {
        require(before.uid() == 0 && before.mode() & 0o022 == 0)?;
    }
    let mut raw = Vec::new();
    (&mut file)
        .take(maximum as u64 + 1)
        .read_to_end(&mut raw)
        .map_err(unavailable)?;
    let after = file.metadata().map_err(unavailable)?;
    require(
        raw.len() == before.len() as usize
            && before.len() == after.len()
            && before.mtime_nsec() == after.mtime_nsec()
            && before.ctime_nsec() == after.ctime_nsec(),
    )?;
    Ok(raw)
}
fn secret(raw: &[u8]) -> Result<String> {
    let text = std::str::from_utf8(raw).map_err(|_| Failure::Refused)?;
    let text = text.strip_suffix('\n').unwrap_or(text);
    require(
        (32..=4095).contains(&text.len())
            && text
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || b"._-".contains(&b)),
    )?;
    Ok(text.to_string())
}
fn sha256(raw: &[u8]) -> String {
    ring::digest::digest(&ring::digest::SHA256, raw)
        .as_ref()
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect()
}

struct Connection(JoinHandle<()>);
impl Drop for Connection {
    fn drop(&mut self) {
        self.0.abort();
    }
}
struct Provider {
    connector: TlsConnector,
    token: String,
}
#[derive(Clone, Copy)]
enum Outcome {
    Deleted,
    Absent,
}
impl Provider {
    fn new(ca: &[u8], token: String) -> Result<Self> {
        let mut roots = RootCertStore::empty();
        for cert in CertificateDer::pem_slice_iter(ca) {
            roots.add(cert.map_err(unavailable)?).map_err(unavailable)?;
        }
        require(!roots.is_empty())?;
        let tls =
            ClientConfig::builder_with_provider(Arc::new(rustls::crypto::ring::default_provider()))
                .with_safe_default_protocol_versions()
                .map_err(unavailable)?
                .with_root_certificates(roots)
                .with_no_client_auth();
        Ok(Self {
            connector: TlsConnector::from(Arc::new(tls)),
            token,
        })
    }
    async fn delete(&self, value: &Deletion) -> Result<Outcome> {
        require(value.issuer == ISSUER && uuid(&value.subject))?;
        let tcp = TcpStream::connect((std::net::Ipv4Addr::LOCALHOST, 8443))
            .await
            .map_err(unavailable)?;
        let tls = self
            .connector
            .connect(
                ServerName::try_from("log.mrj.am").map_err(unavailable)?,
                tcp,
            )
            .await
            .map_err(unavailable)?;
        let (mut sender, connection) = hyper::client::conn::http1::Builder::new()
            .max_headers(24)
            .max_buf_size(16384)
            .handshake(TokioIo::new(tls))
            .await
            .map_err(unavailable)?;
        let _guard = Connection(tokio::spawn(async move {
            let _ = connection.await;
        }));
        let request = Request::builder()
            .method("DELETE")
            .uri(format!("/v1/person/{}", value.subject))
            .header("Host", "log.mrj.am")
            .header("Accept", "application/json")
            .header("Authorization", format!("Bearer {}", self.token))
            .header("Connection", "close")
            .body(Empty::<Bytes>::new())
            .map_err(unavailable)?;
        let response = sender.send_request(request).await.map_err(unavailable)?;
        let status = response.status().as_u16();
        if response.headers().contains_key("location") {
            return Err(Failure::Unavailable);
        }
        let mut body = response.into_body();
        let mut size = 0usize;
        while let Some(frame) = body.frame().await {
            let frame = frame.map_err(unavailable)?;
            if let Some(data) = frame.data_ref() {
                size = size.checked_add(data.len()).ok_or(Failure::Unavailable)?;
                if size > 4096 {
                    return Err(Failure::Unavailable);
                }
            }
        }
        match status {
            200 | 204 => Ok(Outcome::Deleted),
            404 => Ok(Outcome::Absent),
            400 | 401 | 403 => Err(Failure::Refused),
            _ => Err(Failure::Unavailable),
        }
    }
}
fn reply(result: Result<Outcome>) -> &'static [u8] {
    match result {
        Ok(Outcome::Deleted) => b"{\"status\":\"deleted\"}\n",
        Ok(Outcome::Absent) => b"{\"status\":\"absent\"}\n",
        Err(Failure::Refused) => b"{\"error\":\"refused\"}\n",
        Err(Failure::Unavailable) => b"{\"error\":\"unavailable\"}\n",
    }
}
async fn receive(stream: &mut UnixStream, peer_allowed: bool) -> Result<Option<Deletion>> {
    let raw = tokio::time::timeout(Duration::from_secs(2), async {
        let mut prefix = Vec::with_capacity(257);
        let mut total = 0usize;
        let mut buffer = [0u8; 1024];
        loop {
            // Drain rejected finite frames before closing, so a readable JSON
            // refusal is followed by EOF instead of ECONNRESET from unread Unix
            // input. Neither oversized bytes nor an unauthorised peer can
            // become an upstream request. Excessive input is aborted outright.
            if total == 65536 {
                return Ok(None);
            }
            let maximum = buffer.len().min(65536 - total);
            let count = stream
                .read(&mut buffer[..maximum])
                .await
                .map_err(|_| Failure::Refused)?;
            if count == 0 {
                return Ok(Some(prefix));
            }
            total += count;
            let retained = count.min(257 - prefix.len());
            prefix.extend_from_slice(&buffer[..retained]);
        }
    })
    .await
    .map_err(|_| Failure::Refused)??;
    let Some(raw) = raw else {
        return Ok(None);
    };
    require(peer_allowed)?;
    document(&raw).map(Some)
}

async fn handle(mut stream: UnixStream, provider: Arc<Provider>) {
    let peer_allowed = stream
        .peer_cred()
        .is_ok_and(|peer| peer.uid() == REPLAY_UID);
    let result = tokio::time::timeout(Duration::from_secs(12), async {
        let Some(value) = receive(&mut stream, peer_allowed).await? else {
            return Ok(None);
        };
        provider.delete(&value).await.map(Some)
    })
    .await
    .unwrap_or(Err(Failure::Unavailable));
    let result = match result {
        Ok(None) => return,
        Ok(Some(outcome)) => Ok(outcome),
        Err(error) => Err(error),
    };
    let _ = tokio::time::timeout(Duration::from_secs(1), stream.write_all(reply(result))).await;
}
struct Socket {
    listener: UnixListener,
    inode: u64,
}
impl Socket {
    async fn bind() -> Result<Self> {
        let parent = fs::symlink_metadata("/run/mrjam-identity-deletion").map_err(unavailable)?;
        require(
            parent.is_dir()
                && parent.uid() == SERVICE_UID
                && parent.gid() == REPLAY_GID
                && parent.mode() & 0o7777 == 0o750,
        )?;
        match fs::symlink_metadata(SOCKET) {
            Ok(old) => {
                require(
                    old.file_type().is_socket()
                        && old.uid() == SERVICE_UID
                        && old.gid() == REPLAY_GID,
                )?;
                match UnixStream::connect(SOCKET).await {
                    Err(e) if e.kind() == std::io::ErrorKind::ConnectionRefused => {
                        require(
                            fs::symlink_metadata(SOCKET).map_err(unavailable)?.ino() == old.ino(),
                        )?;
                        fs::remove_file(SOCKET).map_err(unavailable)?;
                    }
                    _ => return Err(Failure::Refused),
                }
            }
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => (),
            Err(_) => return Err(Failure::Unavailable),
        }
        let listener = UnixListener::bind(SOCKET).map_err(unavailable)?;
        fs::set_permissions(SOCKET, fs::Permissions::from_mode(0o660)).map_err(unavailable)?;
        let current = fs::symlink_metadata(SOCKET).map_err(unavailable)?;
        require(current.uid() == SERVICE_UID && current.gid() == REPLAY_GID)?;
        Ok(Self {
            listener,
            inode: current.ino(),
        })
    }
}
impl Drop for Socket {
    fn drop(&mut self) {
        if fs::symlink_metadata(SOCKET)
            .is_ok_and(|m| m.file_type().is_socket() && m.ino() == self.inode)
        {
            let _ = fs::remove_file(SOCKET);
        }
    }
}
async fn run() -> Result<()> {
    require(
        rustix::process::geteuid().as_raw() == SERVICE_UID
            && rustix::process::getegid().as_raw() == REPLAY_GID,
    )?;
    let args: Vec<_> = std::env::args_os().collect();
    require(args.len() == 3 && args[1] == "--config")?;
    let raw = open_regular(Path::new(&args[2]), 8192, false)?;
    let config: Configuration = serde_json::from_slice(&raw).map_err(unavailable)?;
    require(config.schema_version == 1 && config.kanidm_ca_sha256.len() == 64)?;
    let ca = open_regular(Path::new(&config.kanidm_ca_file), 65536, false)?;
    require(sha256(&ca) == config.kanidm_ca_sha256)?;
    let provider = Arc::new(Provider::new(
        &ca,
        secret(&open_regular(Path::new(CREDENTIAL), 4096, true)?)?,
    )?);
    let socket = Socket::bind().await?;
    let mut jobs = JoinSet::new();
    let mut termination = tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())
        .map_err(unavailable)?;
    loop {
        tokio::select! {
            accepted=socket.listener.accept()=>{
                let (stream,_) = accepted.map_err(unavailable)?;
                if jobs.len() < 4 { jobs.spawn(handle(stream,Arc::clone(&provider))); }
            }
            _=jobs.join_next(),if !jobs.is_empty()=>{},
            _=termination.recv()=>{jobs.abort_all();break;},
            _=tokio::signal::ctrl_c()=>{jobs.abort_all();break;},
        }
    }
    Ok(())
}
#[tokio::main(flavor = "current_thread")]
async fn main() {
    if run().await.is_err() {
        eprintln!("IDENTITY_DELETION_REFUSED");
        std::process::exit(1);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    const SUBJECT: &str = "3f559b41-543f-414f-9ea9-374db5003db1";
    #[test]
    fn fixed_deletion_contract() {
        let raw = format!("{{\"issuer\":\"{ISSUER}\",\"subject\":\"{SUBJECT}\"}}\n");
        assert!(document(raw.as_bytes()).is_ok());
        assert!(document(raw.trim_end().as_bytes()).is_err());
        assert!(document(format!("{raw}{raw}").as_bytes()).is_err());
        assert!(document(&vec![b' '; 257]).is_err());
    }
    #[test]
    fn extra_operations_and_ambiguous_fields_are_refused() {
        for extra in [
            "\"method\":\"GET\"",
            "\"path\":\"/v1/person\"",
            "\"token\":\"x\"",
            "\"subject\":\"another\"",
            "\"issuer\":\"another\"",
        ] {
            let raw = format!("{{\"issuer\":\"{ISSUER}\",\"subject\":\"{SUBJECT}\",{extra}}}\n");
            assert!(document(raw.as_bytes()).is_err());
        }
        for subject in [
            "admin",
            "../group",
            "3F559B41-543f-414f-9ea9-374db5003db1",
            "00000000-0000-0000-0000-000000000000",
        ] {
            assert!(!uuid(subject));
        }
        assert!(
            document(
                format!(
                    "{{\"issuer\":\"https://log.mrj.am/realms/mrjam\",\"subject\":\"{SUBJECT}\"}}\n"
                )
                .as_bytes()
            )
            .is_err()
        );
    }
    #[test]
    fn bearer_is_bounded_and_cannot_inject_headers() {
        assert!(secret(&[b'a'; 32]).is_ok());
        assert!(secret(&[b'a'; 4096]).is_err());
        assert!(secret(b"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\r\nX: yes").is_err());
    }
    #[test]
    fn responses_never_contain_subject_or_credential() {
        for result in [
            Ok(Outcome::Deleted),
            Ok(Outcome::Absent),
            Err(Failure::Refused),
            Err(Failure::Unavailable),
        ] {
            let raw = reply(result);
            assert!(raw.len() < 32 && raw.last() == Some(&b'\n'));
            assert!(serde_json::from_slice::<serde_json::Value>(raw).is_ok());
        }
    }

    #[tokio::test]
    async fn denied_peer_and_oversized_frame_receive_refusal_then_eof()
    -> std::result::Result<(), Box<dyn std::error::Error>> {
        let valid = format!("{{\"issuer\":\"{ISSUER}\",\"subject\":\"{SUBJECT}\"}}\n").into_bytes();
        for (allowed, raw) in [(false, valid), (true, vec![b'x'; 258])] {
            let (mut client, mut server) = UnixStream::pair()?;
            let response = tokio::spawn(async move {
                assert!(matches!(
                    receive(&mut server, allowed).await,
                    Err(Failure::Refused)
                ));
                server.write_all(reply(Err(Failure::Refused))).await
            });
            client.write_all(&raw).await?;
            client.shutdown().await?;
            let mut received = Vec::new();
            client.read_to_end(&mut received).await?;
            assert_eq!(received, reply(Err(Failure::Refused)));
            response.await??;
        }
        Ok(())
    }

    #[tokio::test]
    async fn incomplete_input_has_one_global_deadline_and_is_refused()
    -> std::result::Result<(), Box<dyn std::error::Error>> {
        let (mut client, mut server) = UnixStream::pair()?;
        client.write_all(b"{").await?;
        let response = tokio::spawn(async move {
            assert!(matches!(
                receive(&mut server, true).await,
                Err(Failure::Refused)
            ));
            server.write_all(reply(Err(Failure::Refused))).await
        });
        let mut received = Vec::new();
        tokio::time::timeout(Duration::from_secs(5), client.read_to_end(&mut received)).await??;
        assert_eq!(received, reply(Err(Failure::Refused)));
        response.await??;
        Ok(())
    }

    #[tokio::test]
    async fn excessive_transport_is_aborted_without_an_upstream_document()
    -> std::result::Result<(), Box<dyn std::error::Error>> {
        let (mut client, mut server) = UnixStream::pair()?;
        let response = tokio::spawn(async move {
            assert!(matches!(receive(&mut server, true).await, Ok(None)));
        });
        client.write_all(&vec![b'x'; 65536]).await?;
        response.await?;
        Ok(())
    }
}

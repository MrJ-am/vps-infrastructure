use crate::error::{Error, Result, require};
use serde::Deserialize;
use std::{
    collections::BTreeSet,
    fs::{self, OpenOptions},
    io::Read,
    net::SocketAddr,
    os::unix::{
        ffi::OsStrExt,
        fs::{MetadataExt, OpenOptionsExt},
    },
    path::{Component, Path, PathBuf},
};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Configuration {
    pub schema_version: u8,
    pub listen: SocketAddr,
    pub state_database: PathBuf,
    pub kanidm_endpoint: SocketAddr,
    pub kanidm_ca_file: PathBuf,
    pub clients: Vec<Client>,
    pub principal_database: PrincipalDatabase,
    pub principal_registration: Option<PrincipalRegistration>,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PrincipalRegistration {
    pub socket: PathBuf,
    pub uid: u32,
    pub gid: u32,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Client {
    pub host: String,
    pub client_id: String,
    pub secret_file: PathBuf,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PrincipalDatabase {
    pub host: PathBuf,
    pub port: u16,
    pub database: String,
    pub user: String,
}
pub fn identifier(value: &str, maximum: usize) -> bool {
    !value.is_empty()
        && value.len() <= maximum
        && value
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b == b'_' || b == b'-')
}
pub fn host(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 253
        && !value.starts_with('.')
        && !value.contains("..")
        && (value.ends_with(".mrj.am")
            || matches!(value, "principiipetit.io" | "www.principiipetit.io"))
        && value
            .bytes()
            .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'.' || b == b'-')
}
pub fn path(value: &Path) -> bool {
    value.is_absolute()
        && value.as_os_str().as_bytes().len() <= 4096
        && value
            .components()
            .all(|c| matches!(c, Component::RootDir | Component::Normal(_)))
        && !value
            .as_os_str()
            .as_bytes()
            .iter()
            .any(|b| *b < 32 || *b == 127)
}
pub fn read_regular(pathname: &Path, maximum: usize, private: bool) -> Result<Vec<u8>> {
    require(path(pathname), 503)?;
    let mut file = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK | libc::O_CLOEXEC)
        .open(pathname)
        .map_err(|_| Error(503))?;
    let meta = file.metadata().map_err(|_| Error(503))?;
    require(
        meta.is_file() && meta.len() > 0 && meta.len() <= maximum as u64,
        503,
    )?;
    if private {
        let owner_private = meta.mode() & 0o077 == 0;
        require(
            owner_private || systemd_credential(pathname, &file, &meta),
            503,
        )?;
    }
    let mut data = Vec::new();
    (&mut file)
        .take(maximum as u64 + 1)
        .read_to_end(&mut data)
        .map_err(|_| Error(503))?;
    require(data.len() == meta.len() as usize, 503)?;
    Ok(data)
}
fn systemd_credential(pathname: &Path, file: &std::fs::File, meta: &fs::Metadata) -> bool {
    // systemd 260 gives the service an ACL on root:root 0440 credentials.
    // The group mode is the ACL mask, not an authorization for the root group.
    // Accept that representation only inside its protected read-only mount.
    let Some(directory) = std::env::var_os("CREDENTIALS_DIRECTORY").map(PathBuf::from) else {
        return false;
    };
    if !path(&directory)
        || pathname.parent() != Some(directory.as_path())
        || directory.parent() != Some(Path::new("/run/credentials"))
        || meta.uid() != 0
        || meta.gid() != 0
        || meta.mode() & 0o7777 != 0o440
        || meta.nlink() != 1
    {
        return false;
    }
    let Ok(parent) = fs::symlink_metadata(&directory) else {
        return false;
    };
    parent.is_dir()
        && parent.uid() == 0
        && parent.gid() == 0
        && parent.mode() & 0o027 == 0
        && rustix::fs::fstatvfs(file)
            .is_ok_and(|stat| stat.f_flag.contains(rustix::fs::StatVfsMountFlags::RDONLY))
}
impl Configuration {
    pub fn load(pathname: &Path) -> Result<Self> {
        let bytes = read_regular(pathname, 65536, false)?;
        let config: Self = serde_json::from_slice(&bytes).map_err(|_| Error(503))?;
        require(
            config.schema_version == 1
                && config.listen.ip().is_loopback()
                && config.listen.port() != 0
                && config.kanidm_endpoint.ip().is_loopback()
                && config.kanidm_endpoint.port() != 0
                && config.listen != config.kanidm_endpoint
                && (1..=8).contains(&config.clients.len()),
            503,
        )?;
        require(
            path(&config.state_database)
                && path(&config.kanidm_ca_file)
                && path(&config.principal_database.host)
                && config.principal_database.port != 0
                && identifier(&config.principal_database.database, 63)
                && identifier(&config.principal_database.user, 63),
            503,
        )?;
        let mut hosts = BTreeSet::new();
        for client in &config.clients {
            require(
                host(&client.host)
                    && identifier(&client.client_id, 128)
                    && path(&client.secret_file)
                    && hosts.insert(client.host.clone()),
                503,
            )?;
        }
        let meta = fs::symlink_metadata(&config.state_database).map_err(|_| Error(503))?;
        if let Some(registration) = &config.principal_registration {
            require(
                path(&registration.socket)
                    && registration.socket.as_os_str().as_bytes().len() < 104
                    && registration.uid > 0
                    && registration.gid > 0
                    && config.clients.iter().any(|c| c.client_id == "mrjam-vision"),
                503,
            )?;
        }
        require(
            meta.is_file() && meta.len() > 0 && meta.mode() & 0o077 == 0,
            503,
        )?;
        // Reject hidden libpq selectors before SQLx constructs its options.
        require(
            !std::env::vars_os().any(|(name, _)| name.as_bytes().starts_with(b"PG")),
            503,
        )?;
        Ok(config)
    }
}

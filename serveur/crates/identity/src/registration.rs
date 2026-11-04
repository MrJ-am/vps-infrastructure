//! Admission capability: Unix peer credentials, explicit subject, no token access.
use crate::{
    config::PrincipalRegistration,
    crypto,
    error::{Error, Result, require},
    state::{Broker, now},
};
use serde::Deserialize;
use sqlx::{Row, SqlitePool};
use std::{
    fs,
    os::unix::fs::{FileTypeExt, MetadataExt, PermissionsExt},
    path::PathBuf,
    sync::Arc,
    time::Duration,
};
use tokio::{
    io::{AsyncBufReadExt, AsyncReadExt, AsyncWriteExt, BufReader},
    net::{UnixListener, UnixStream},
    task::JoinSet,
};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Registration {
    issuer: String,
    subject: String,
    mail: String,
}
pub(crate) fn document(bytes: &[u8]) -> Result<Registration> {
    require(
        (2..=2048).contains(&bytes.len()) && bytes.last() == Some(&b'\n'),
        400,
    )?;
    let value: Registration = serde_json::from_slice(bytes).map_err(|_| Error(400))?;
    require(
        value.issuer == crypto::issuer("mrjam-vision")
            && value.subject.len() == 36
            && value.subject.bytes().enumerate().all(|(i, b)| {
                if [8, 13, 18, 23].contains(&i) {
                    b == b'-'
                } else {
                    b.is_ascii_digit() || (b'a'..=b'f').contains(&b)
                }
            })
            && crypto::text(&value.mail, 3, 320)
            && value.mail == value.mail.to_lowercase()
            && value.mail.bytes().all(|b| (33..=126).contains(&b))
            && value.mail.matches('@').count() == 1
            && !value.mail.starts_with('@')
            && !value.mail.ends_with('@'),
        400,
    )?;
    Ok(value)
}
pub(crate) fn peer(stream: &UnixStream, uid: u32) -> Result<()> {
    require(
        stream.peer_cred().map_err(|_| Error(503))?.uid() == uid,
        403,
    )
}
pub(crate) async fn insert(db: &SqlitePool, registration: &Registration) -> Result<()> {
    let mut tx = db.begin().await?;
    let rows = sqlx::query("SELECT subject,mail FROM log_principaux WHERE subject=? OR mail=?")
        .bind(&registration.subject)
        .bind(&registration.mail)
        .fetch_all(&mut *tx)
        .await?;
    if !rows.is_empty() {
        require(
            rows.len() == 1
                && rows[0].try_get::<String, _>("subject")? == registration.subject
                && rows[0].try_get::<String, _>("mail")? == registration.mail,
            409,
        )?;
        tx.commit().await?;
        return Ok(());
    }
    sqlx::query("INSERT INTO log_principaux(subject,mail,duration,minimum,qualified_after) VALUES(?,?,604800,'any',?)")
        .bind(&registration.subject).bind(&registration.mail).bind(now()?).execute(&mut *tx).await?;
    tx.commit().await?;
    Ok(())
}
pub struct Socket {
    listener: UnixListener,
    path: PathBuf,
    inode: u64,
    uid: u32,
}
impl Drop for Socket {
    fn drop(&mut self) {
        if fs::symlink_metadata(&self.path)
            .is_ok_and(|m| m.file_type().is_socket() && m.ino() == self.inode)
        {
            let _ = fs::remove_file(&self.path);
        }
    }
}
impl Socket {
    pub async fn bind(config: &PrincipalRegistration) -> Result<Self> {
        let parent = config.socket.parent().ok_or(Error(503))?;
        let directory = fs::symlink_metadata(parent).map_err(|_| Error(503))?;
        require(directory.is_dir() && directory.mode() & 0o026 == 0, 503)?;
        match fs::symlink_metadata(&config.socket) {
            Ok(metadata) => {
                require(
                    metadata.file_type().is_socket() && metadata.uid() == directory.uid(),
                    503,
                )?;
                match UnixStream::connect(&config.socket).await {
                    Err(error) if error.kind() == std::io::ErrorKind::ConnectionRefused => {
                        let current =
                            fs::symlink_metadata(&config.socket).map_err(|_| Error(503))?;
                        require(current.ino() == metadata.ino(), 503)?;
                        fs::remove_file(&config.socket).map_err(|_| Error(503))?;
                    }
                    _ => return Err(Error(503)),
                }
            }
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
            Err(_) => return Err(Error(503)),
        }
        let listener = UnixListener::bind(&config.socket).map_err(|_| Error(503))?;
        let inode = fs::symlink_metadata(&config.socket)
            .map_err(|_| Error(503))?
            .ino();
        let socket = Self {
            listener,
            path: config.socket.clone(),
            inode,
            uid: config.uid,
        };
        std::os::unix::fs::chown(&config.socket, None, Some(config.gid)).map_err(|_| Error(503))?;
        fs::set_permissions(&config.socket, fs::Permissions::from_mode(0o660))
            .map_err(|_| Error(503))?;
        Ok(socket)
    }
    pub async fn serve(self, broker: Arc<Broker>) -> Result<()> {
        let mut tasks = JoinSet::new();
        loop {
            tokio::select! {
                accepted=self.listener.accept()=>{
                    let (stream,_)=accepted.map_err(|_|Error(503))?;
                    if tasks.len()>=8{drop(stream);continue;}
                    let broker=Arc::clone(&broker);let uid=self.uid;
                    tasks.spawn(async move {
                        let mut stream=BufReader::new(stream);
                        let result=tokio::time::timeout(Duration::from_secs(5),async {
                            peer(stream.get_ref(),uid)?;
                            let mut bytes=Vec::new();(&mut stream).take(2049).read_until(b'\n',&mut bytes).await.map_err(|_|Error(400))?;
                            let registration=document(&bytes)?;
                            broker.principal(&registration.issuer,&registration.subject).await?;
                            insert(&broker.db,&registration).await
                        }).await.unwrap_or(Err(Error(503)));
                        let response=match result{Ok(())=>b"{\"status\":\"registered\"}\n".as_slice(),Err(Error(503))=>b"{\"error\":\"temporarily_unavailable\"}\n",Err(_)=>b"{\"error\":\"registration_refused\"}\n"};
                        let _=tokio::time::timeout(Duration::from_secs(1),stream.get_mut().write_all(response)).await;
                    });
                }
                _=tasks.join_next(),if !tasks.is_empty()=>{},
            }
        }
    }
}

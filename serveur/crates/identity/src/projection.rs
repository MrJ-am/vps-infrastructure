//! Explicit, unprivileged projection. The source is always opened read-only.
//! Readers keep SQLite handles open, so subsequent updates preserve the inode.
use crate::{
    config, crypto,
    error::{Error, Result, require},
};
use sqlx::{
    ConnectOptions, Connection, SqliteConnection,
    sqlite::{SqliteConnectOptions, SqliteJournalMode},
};
use std::{
    fs::{self, File, OpenOptions},
    os::unix::fs::{MetadataExt, OpenOptionsExt, PermissionsExt},
    path::{Path, PathBuf},
    time::Duration,
};

struct Temporary(PathBuf);
impl Drop for Temporary {
    fn drop(&mut self) {
        let _ = fs::remove_file(&self.0);
    }
}
fn options(path: &Path, readonly: bool) -> SqliteConnectOptions {
    let options = SqliteConnectOptions::new()
        .filename(path)
        .read_only(readonly)
        .create_if_missing(false)
        .busy_timeout(Duration::from_secs(2))
        .disable_statement_logging();
    if readonly {
        options
    } else {
        options.journal_mode(SqliteJournalMode::Delete)
    }
}
async fn refresh(path: &Path, rows: &[(String, String)], initialize: bool) -> Result<()> {
    let mut db = SqliteConnection::connect_with(&options(path, false)).await?;
    let mut tx = db.begin().await?;
    if initialize {
        sqlx::query(
            "CREATE TABLE log_principaux(subject TEXT PRIMARY KEY,mail TEXT UNIQUE NOT NULL)",
        )
        .execute(&mut *tx)
        .await?;
    }
    let tables: Vec<String> =
        sqlx::query_scalar("SELECT name FROM sqlite_master WHERE type='table'")
            .fetch_all(&mut *tx)
            .await?;
    require(tables == ["log_principaux"], 503)?;
    let columns: Vec<String> =
        sqlx::query_scalar("SELECT name FROM pragma_table_info('log_principaux') ORDER BY cid")
            .fetch_all(&mut *tx)
            .await?;
    require(columns == ["subject", "mail"], 503)?;
    let triggers: i64 = sqlx::query_scalar(
        "SELECT count(*) FROM sqlite_master WHERE type='trigger' OR type='view'",
    )
    .fetch_one(&mut *tx)
    .await?;
    require(triggers == 0, 503)?;
    sqlx::query("DELETE FROM log_principaux")
        .execute(&mut *tx)
        .await?;
    for (subject, mail) in rows {
        sqlx::query("INSERT INTO log_principaux(subject,mail) VALUES(?,?)")
            .bind(subject)
            .bind(mail)
            .execute(&mut *tx)
            .await?;
    }
    tx.commit().await?;
    db.close().await?;
    File::open(path)
        .map_err(|_| Error(503))?
        .sync_all()
        .map_err(|_| Error(503))?;
    Ok(())
}
pub async fn project(source: &Path, destination: &Path) -> Result<()> {
    require(
        config::path(source) && config::path(destination) && source != destination,
        503,
    )?;
    let source_meta = fs::symlink_metadata(source).map_err(|_| Error(503))?;
    require(
        source_meta.is_file() && source_meta.len() > 0 && source_meta.mode() & 0o077 == 0,
        503,
    )?;
    let directory = destination.parent().ok_or(Error(503))?;
    let directory_meta = fs::symlink_metadata(directory).map_err(|_| Error(503))?;
    require(
        directory_meta.is_dir() && directory_meta.mode() & 0o026 == 0,
        503,
    )?;
    let mut db = SqliteConnection::connect_with(&options(source, true)).await?;
    let mut tx = db.begin().await?;
    let rows: Vec<(String, String)> =
        sqlx::query_as("SELECT subject,mail FROM log_principaux ORDER BY subject LIMIT 100001")
            .fetch_all(&mut *tx)
            .await?;
    require(
        rows.len() <= 100000
            && rows
                .iter()
                .all(|(subject, mail)| crypto::text(subject, 1, 128) && crypto::text(mail, 1, 320)),
        503,
    )?;
    tx.commit().await?;
    db.close().await?;
    match fs::symlink_metadata(destination) {
        Ok(meta) => {
            require(
                meta.is_file()
                    && meta.nlink() == 1
                    && meta.uid() == directory_meta.uid()
                    && meta.mode() & 0o777 == 0o640,
                503,
            )?;
            refresh(destination, &rows, false).await
        }
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
            let temporary =
                Temporary(directory.join(format!(".aliases-{}.sqlite", crypto::random()?)));
            let file = OpenOptions::new()
                .write(true)
                .create_new(true)
                .mode(0o600)
                .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
                .open(&temporary.0)
                .map_err(|_| Error(503))?;
            drop(file);
            refresh(&temporary.0, &rows, true).await?;
            fs::set_permissions(&temporary.0, fs::Permissions::from_mode(0o640))
                .map_err(|_| Error(503))?;
            // link is an atomic, no-replace publication of the completed database.
            fs::hard_link(&temporary.0, destination).map_err(|_| Error(503))?;
            fs::remove_file(&temporary.0).map_err(|_| Error(503))?;
            File::open(directory)
                .map_err(|_| Error(503))?
                .sync_all()
                .map_err(|_| Error(503))?;
            Ok(())
        }
        Err(_) => Err(Error(503)),
    }
}

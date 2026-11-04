use crate::{LogError, LoginAliases, NativeFuture, Result, require};
use sqlx::{
    ConnectOptions, SqlitePool,
    sqlite::{SqliteConnectOptions, SqlitePoolOptions},
};
use std::{path::Path, time::Duration};

/// The existing identity broker owns this database. This adapter only reads
/// its explicit alias table; it never creates users, links emails or migrates.
#[derive(Clone)]
pub struct SqliteLoginAliases {
    pool: SqlitePool,
}
impl SqliteLoginAliases {
    pub async fn open_read_only(path: &Path) -> Result<Self> {
        require(path.is_absolute(), "reference_alias_invalide", 400)?;
        let options = SqliteConnectOptions::new()
            .filename(path)
            .read_only(true)
            .create_if_missing(false)
            .busy_timeout(Duration::from_secs(2))
            .disable_statement_logging();
        let pool = SqlitePoolOptions::new()
            .max_connections(2)
            .acquire_timeout(Duration::from_secs(2))
            .connect_with(options)
            .await
            .map_err(|_| LogError::new("alias_indisponibles", 503))?;
        // Validate schema readability without inspecting any alias row.
        sqlx::query("SELECT mail,subject FROM log_principaux LIMIT 0")
            .execute(&pool)
            .await
            .map_err(|_| LogError::new("alias_schema_incompatible", 503))?;
        Ok(Self { pool })
    }
    pub async fn ready(&self) -> Result<()> {
        sqlx::query("SELECT mail,subject FROM log_principaux LIMIT 0")
            .execute(&self.pool)
            .await
            .map_err(|_| LogError::new("alias_schema_incompatible", 503))?;
        Ok(())
    }
}
impl LoginAliases for SqliteLoginAliases {
    fn resolve<'a>(&'a self, email: &'a str) -> NativeFuture<'a, Option<String>> {
        Box::pin(async move {
            require(
                !email.is_empty()
                    && email.len() <= 320
                    && email.contains('@')
                    && !email.chars().any(char::is_control),
                "identifiant_invalide",
                400,
            )?;
            let rows: Vec<(String,)> =
                sqlx::query_as("SELECT subject FROM log_principaux WHERE mail=? LIMIT 2")
                    .bind(email.to_lowercase())
                    .fetch_all(&self.pool)
                    .await
                    .map_err(|_| LogError::new("alias_indisponibles", 503))?;
            require(rows.len() <= 1, "alias_ambigu", 503)?;
            Ok(rows.into_iter().next().map(|(subject,)| subject))
        })
    }
}

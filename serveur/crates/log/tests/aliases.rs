use mrjam_log::{LoginAliases, SqliteLoginAliases};
use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};
use std::{
    path::PathBuf,
    time::{SystemTime, UNIX_EPOCH},
};
type Error = Box<dyn std::error::Error + Send + Sync>;
struct Fixture(PathBuf);
impl Drop for Fixture {
    fn drop(&mut self) {
        let _ = std::fs::remove_dir_all(&self.0);
    }
}
#[tokio::test]
async fn existing_aliases_are_read_without_creation_linking_or_database_changes()
-> Result<(), Error> {
    let directory = std::env::temp_dir().join(format!(
        "mrjam-log-alias-fixture-{}-{}",
        std::process::id(),
        SystemTime::now().duration_since(UNIX_EPOCH)?.as_nanos()
    ));
    std::fs::create_dir(&directory)?;
    let fixture = Fixture(directory);
    let database = fixture.0.join("synthetic.sqlite");
    let pool = SqlitePoolOptions::new()
        .max_connections(1)
        .connect_with(
            SqliteConnectOptions::new()
                .filename(&database)
                .create_if_missing(true),
        )
        .await?;
    sqlx::raw_sql("CREATE TABLE log_principaux(mail TEXT,subject TEXT NOT NULL);INSERT INTO log_principaux VALUES('invented@example.invalid','existing-synthetic-subject');").execute(&pool).await?;
    pool.close().await;
    let before = std::fs::read(&database)?;
    let aliases = SqliteLoginAliases::open_read_only(&database).await?;
    assert_eq!(
        aliases.resolve("Invented@example.invalid").await?,
        Some("existing-synthetic-subject".into())
    );
    assert_eq!(aliases.resolve("unknown@example.invalid").await?, None);
    assert!(aliases.resolve("malformed").await.is_err());
    assert_eq!(std::fs::read(&database)?, before);
    let missing = fixture.0.join("must-not-create.sqlite");
    assert!(SqliteLoginAliases::open_read_only(&missing).await.is_err());
    assert!(!missing.exists());
    Ok(())
}

use crate::{
    crypto,
    error::{Error, Result},
    http, json, projection, registration,
};
use base64::{Engine, engine::general_purpose::URL_SAFE_NO_PAD};
use ring::{
    rand::SystemRandom,
    signature::{self, KeyPair},
};
use serde_json::{Value, json};
use sqlx::{
    Connection, SqliteConnection,
    sqlite::{SqliteConnectOptions, SqliteJournalMode},
};
use std::{
    fs,
    os::unix::fs::{DirBuilderExt, MetadataExt, PermissionsExt},
    path::PathBuf,
};

#[test]
fn pkce_rfc7636_vector() {
    assert_eq!(
        crypto::challenge("dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"),
        "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
    );
}

#[test]
fn admission_document_is_closed() {
    let valid = json!({"issuer":crypto::issuer("mrjam-vision"),"subject":"12345678-1234-4234-8234-123456789abc","mail":"invented@example.invalid"});
    assert!(registration::document(format!("{valid}\n").as_bytes()).is_ok());
    for (field, value) in [
        ("issuer", json!("https://log.mrj.am/realms/mrjam")),
        ("subject", json!("not-a-native-subject")),
        ("mail", json!("other@example.invalid\n")),
        ("minimum", json!("mfa")),
        ("duration", json!(7776000)),
    ] {
        let mut changed = valid.clone();
        changed[field] = value;
        assert!(registration::document(format!("{changed}\n").as_bytes()).is_err());
    }
    assert!(registration::document(valid.to_string().as_bytes()).is_err());
    assert!(registration::document(format!("{}\n", " ".repeat(2048)).as_bytes()).is_err());
    let duplicate = format!(
        "{{\"issuer\":\"{}\",\"issuer\":\"{}\",\"subject\":\"12345678-1234-4234-8234-123456789abc\",\"mail\":\"invented@example.invalid\"}}\n",
        crypto::issuer("mrjam-vision"),
        crypto::issuer("mrjam-vision")
    );
    assert!(registration::document(duplicate.as_bytes()).is_err());
}
#[tokio::test]
async fn admission_peer_is_the_kernel_uid() -> std::result::Result<(), Box<dyn std::error::Error>> {
    let directory = Directory::temporary()?;
    let owner = fs::metadata(&directory.0)?.uid();
    let (stream, _other) = tokio::net::UnixStream::pair()?;
    assert!(registration::peer(&stream, owner).is_ok());
    assert!(registration::peer(&stream, owner ^ 1).is_err());
    Ok(())
}

#[test]
fn ordinary_secrets_still_reject_group_access_and_links()
-> std::result::Result<(), Box<dyn std::error::Error>> {
    let directory = Directory::temporary()?;
    let file = directory.0.join("synthetic-secret");
    fs::write(&file, b"invented-secret-no-real-credential")?;
    for mode in [0o400, 0o600] {
        fs::set_permissions(&file, fs::Permissions::from_mode(mode))?;
        assert!(crate::config::read_regular(&file, 512, true).is_ok());
    }
    for mode in [0o440, 0o640, 0o444, 0o644] {
        fs::set_permissions(&file, fs::Permissions::from_mode(mode))?;
        assert!(crate::config::read_regular(&file, 512, true).is_err());
    }
    fs::set_permissions(&file, fs::Permissions::from_mode(0o600))?;
    let link = directory.0.join("linked-secret");
    std::os::unix::fs::symlink(&file, &link)?;
    assert!(crate::config::read_regular(&link, 512, true).is_err());
    Ok(())
}
#[tokio::test]
async fn admission_replay_preserves_policy_and_rejects_conflicts()
-> std::result::Result<(), Box<dyn std::error::Error>> {
    let db = sqlx::sqlite::SqlitePoolOptions::new()
        .max_connections(1)
        .connect("sqlite::memory:")
        .await?;
    sqlx::query("CREATE TABLE log_principaux(subject TEXT PRIMARY KEY,mail TEXT UNIQUE NOT NULL,duration INTEGER NOT NULL,minimum TEXT NOT NULL,qualified_after INTEGER NOT NULL)").execute(&db).await?;
    let make = |subject: &str, mail: &str| {
        registration::document(
            format!(
                "{}\n",
                json!({"issuer":crypto::issuer("mrjam-vision"),"subject":subject,"mail":mail})
            )
            .as_bytes(),
        )
    };
    let first = make(
        "12345678-1234-4234-8234-123456789abc",
        "one@example.invalid",
    )?;
    registration::insert(&db, &first).await?;
    let inserted: (i64, String, i64) =
        sqlx::query_as("SELECT duration,minimum,qualified_after FROM log_principaux")
            .fetch_one(&db)
            .await?;
    assert_eq!(inserted.0, 604800);
    assert_eq!(inserted.1, "any");
    assert!(inserted.2 > 0);
    sqlx::query("UPDATE log_principaux SET duration=7776000,minimum='mfa',qualified_after=12345")
        .execute(&db)
        .await?;
    registration::insert(&db, &first).await?;
    let unchanged: (i64, String, i64) =
        sqlx::query_as("SELECT duration,minimum,qualified_after FROM log_principaux")
            .fetch_one(&db)
            .await?;
    assert_eq!(unchanged, (7776000, "mfa".into(), 12345));
    for conflict in [
        make(
            "12345678-1234-4234-8234-123456789abc",
            "two@example.invalid",
        )?,
        make(
            "23456789-1234-4234-8234-123456789abc",
            "one@example.invalid",
        )?,
    ] {
        assert!(registration::insert(&db, &conflict).await.is_err());
    }
    let count: i64 = sqlx::query_scalar("SELECT count(*) FROM log_principaux")
        .fetch_one(&db)
        .await?;
    assert_eq!(count, 1);
    db.close().await;
    Ok(())
}
#[test]
fn ambiguous_input_is_rejected() {
    for input in [
        r#"{"nonce":"a","nonce":"b"}"#,
        r#"{"a":{"b":1,"b":2}}"#,
        r#"{"a":1} {}"#,
    ] {
        assert!(json::object(input.as_bytes(), 8192).is_err());
    }
    for input in [
        "state=a&state=b",
        "state=a&st%61te=b",
        "x=%FF",
        "x=%",
        "x=%0A",
        "=value",
    ] {
        assert!(http::parameters(input).is_err());
    }
    let nested = format!("{}0{}", "{\"x\":".repeat(17), "}".repeat(17));
    assert!(json::object(nested.as_bytes(), 8192).is_err());
}
#[test]
fn signed_oidc_boundaries() -> Result<()> {
    let random = SystemRandom::new();
    let encoded = signature::EcdsaKeyPair::generate_pkcs8(
        &signature::ECDSA_P256_SHA256_FIXED_SIGNING,
        &random,
    )
    .map_err(|_| Error(503))?;
    let key = signature::EcdsaKeyPair::from_pkcs8(
        &signature::ECDSA_P256_SHA256_FIXED_SIGNING,
        encoded.as_ref(),
        &random,
    )
    .map_err(|_| Error(503))?;
    let public = key.public_key().as_ref();
    let jwks = json!({"keys":[{"kid":"synthetic","kty":"EC","crv":"P-256","x":URL_SAFE_NO_PAD.encode(&public[1..33]),"y":URL_SAFE_NO_PAD.encode(&public[33..65])}]});
    let nonce = "invented-nonce-for-signed-unit-test";
    let claims = json!({"iss":crypto::issuer("synthetic-client"),"sub":"invented-subject","aud":"synthetic-client","nonce":nonce,"iat":1000,"exp":1100,"auth_time":990});
    let sign = |claims: &Value, header: &Value| -> Result<String> {
        let input = format!(
            "{}.{}",
            URL_SAFE_NO_PAD.encode(header.to_string()),
            URL_SAFE_NO_PAD.encode(claims.to_string())
        );
        let signature = key
            .sign(&random, input.as_bytes())
            .map_err(|_| Error(503))?;
        Ok(format!(
            "{input}.{}",
            URL_SAFE_NO_PAD.encode(signature.as_ref())
        ))
    };
    let header = json!({"alg":"ES256","kid":"synthetic","typ":"JWT"});
    let token = sign(&claims, &header)?;
    assert_eq!(
        crypto::verify(
            &token,
            &jwks,
            "synthetic-client",
            nonce,
            "invented-access",
            1000
        )?
        .subject,
        "invented-subject"
    );
    for (field, value) in [
        ("iss", json!("https://evil.invalid")),
        ("aud", json!("another-client")),
        ("nonce", json!("a-different-invented-nonce")),
        ("exp", json!(970)),
        ("iat", json!(1031)),
        ("nbf", json!(1031)),
        ("auth_time", json!(1031)),
        ("at_hash", json!("incorrect")),
        ("aud", json!(["synthetic-client", "another-client"])),
    ] {
        let mut changed = claims.clone();
        changed[field] = value;
        assert!(
            crypto::verify(
                &sign(&changed, &header)?,
                &jwks,
                "synthetic-client",
                nonce,
                "invented-access",
                1000
            )
            .is_err(),
            "{field}"
        );
    }
    let mut injected = header.clone();
    injected["jku"] = json!("https://evil.invalid/keys");
    assert!(
        crypto::verify(
            &sign(&claims, &injected)?,
            &jwks,
            "synthetic-client",
            nonce,
            "invented-access",
            1000
        )
        .is_err()
    );
    let duplicate = json!({"keys":[jwks["keys"][0].clone(),jwks["keys"][0].clone()]});
    assert!(
        crypto::verify(
            &token,
            &duplicate,
            "synthetic-client",
            nonce,
            "invented-access",
            1000
        )
        .is_err()
    );
    Ok(())
}
struct Directory(PathBuf);
impl Directory {
    fn temporary() -> std::result::Result<Self, Box<dyn std::error::Error>> {
        let root = fs::canonicalize(std::env::temp_dir())?;
        let path = root.join(format!("mrjam-identity-tests-{}", crypto::random()?));
        fs::DirBuilder::new().mode(0o700).create(&path)?;
        Ok(Self(path))
    }
}
impl Drop for Directory {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}
#[tokio::test]
async fn projection_is_minimal_and_refreshes_open_readers()
-> std::result::Result<(), Box<dyn std::error::Error>> {
    let directory = Directory::temporary()?;
    let source = directory.0.join("source.sqlite");
    let destination = directory.0.join("aliases.sqlite");
    let mut db = SqliteConnection::connect_with(
        &SqliteConnectOptions::new()
            .filename(&source)
            .create_if_missing(true)
            .journal_mode(SqliteJournalMode::Wal),
    )
    .await?;
    fs::set_permissions(&source, fs::Permissions::from_mode(0o600))?;
    sqlx::query("CREATE TABLE log_principaux(subject TEXT PRIMARY KEY,mail TEXT UNIQUE NOT NULL,duration INTEGER,minimum TEXT,qualified_after INTEGER)").execute(&mut db).await?;
    sqlx::query("CREATE TABLE log_sessions(access TEXT)")
        .execute(&mut db)
        .await?;
    sqlx::query("INSERT INTO log_sessions VALUES('synthetic-secret-must-never-be-projected')")
        .execute(&mut db)
        .await?;
    sqlx::query("INSERT INTO log_principaux VALUES('invented-subject','one@example.invalid',604800,'any',0)").execute(&mut db).await?;
    projection::project(&source, &destination)
        .await
        .map_err(|_| "initial projection")?;
    let inode = fs::metadata(&destination)?.ino();
    assert_eq!(fs::metadata(&destination)?.mode() & 0o777, 0o640);
    let mut reader = SqliteConnection::connect_with(
        &SqliteConnectOptions::new()
            .filename(&destination)
            .read_only(true),
    )
    .await?;
    let tables: Vec<String> =
        sqlx::query_scalar("SELECT name FROM sqlite_master WHERE type='table'")
            .fetch_all(&mut reader)
            .await?;
    assert_eq!(tables, ["log_principaux"]);
    let before: String =
        sqlx::query_scalar("SELECT mail FROM log_principaux WHERE subject='invented-subject'")
            .fetch_one(&mut reader)
            .await?;
    assert_eq!(before, "one@example.invalid");
    sqlx::query("UPDATE log_principaux SET mail='two@example.invalid'")
        .execute(&mut db)
        .await?;
    projection::project(&source, &destination)
        .await
        .map_err(|_| "projection refresh")?;
    assert_eq!(fs::metadata(&destination)?.ino(), inode);
    let after: String =
        sqlx::query_scalar("SELECT mail FROM log_principaux WHERE subject='invented-subject'")
            .fetch_one(&mut reader)
            .await?;
    assert_eq!(after, "two@example.invalid");
    let mode: String = sqlx::query_scalar("PRAGMA journal_mode")
        .fetch_one(&mut db)
        .await?;
    assert_eq!(mode, "wal");
    let untouched: String = sqlx::query_scalar("SELECT access FROM log_sessions")
        .fetch_one(&mut db)
        .await?;
    assert_eq!(untouched, "synthetic-secret-must-never-be-projected");
    let marker = b"synthetic-secret-must-never-be-projected";
    assert!(
        !fs::read(&destination)?
            .windows(marker.len())
            .any(|bytes| bytes == marker)
    );
    reader.close().await?;
    db.close().await?;
    Ok(())
}

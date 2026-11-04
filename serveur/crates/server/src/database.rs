//! Explicit local PostgreSQL capabilities; no URL, ambient libpq options or DDL.
use crate::runtime_config::{DatabaseConfiguration, DatabaseTransport};
use sqlx::{
    ConnectOptions, PgPool,
    postgres::{PgConnectOptions, PgPoolOptions, PgSslMode},
};
use std::time::Duration;

pub async fn connect(config: &DatabaseConfiguration) -> Result<PgPool, &'static str> {
    // SQLx defaults otherwise consult PGHOST/PGOPTIONS/PGSSLKEY and .pgpass.
    // Reject selectors before constructing its options, without printing them.
    if std::env::vars_os().any(|(name, _)| name.to_string_lossy().starts_with("PG")) {
        return Err("AMBIENT_DATABASE_CONFIGURATION_REFUSED");
    }
    let password = config
        .password_file
        .as_ref()
        .map(|path| crate::runtime_files::credential(path))
        .transpose()?;
    let search_path = format!("{},pg_catalog", config.schema);
    let mut options = PgConnectOptions::new_without_pgpass()
        .host("127.0.0.1")
        .port(5432)
        .database(&config.database)
        .username(&config.username)
        .ssl_mode(PgSslMode::Disable)
        .application_name("mrjam-rust")
        .options([
            ("search_path", search_path.as_str()),
            ("statement_timeout", "10000"),
            ("lock_timeout", "2000"),
        ])
        .disable_statement_logging();
    if let Some(password) = password {
        options = options.password(&password);
    }
    match &config.transport {
        DatabaseTransport::Tcp { port } => options = options.port(*port),
        DatabaseTransport::Unix { directory } => options = options.socket(directory),
    }
    let pool = tokio::time::timeout(
        Duration::from_secs(5),
        PgPoolOptions::new()
            .max_connections(config.maximum_connections)
            .acquire_timeout(Duration::from_secs(3))
            .connect_with(options),
    )
    .await
    .map_err(|_| "DATABASE_UNAVAILABLE")?
    .map_err(|_| "DATABASE_UNAVAILABLE")?;
    verify_role(&pool, &config.schema).await?;
    Ok(pool)
}

pub async fn verify_role(pool: &PgPool, schema: &str) -> Result<(), &'static str> {
    let safe:bool=sqlx::query_scalar("SELECT NOT (rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls)
        AND NOT EXISTS(SELECT 1 FROM pg_auth_members WHERE member=r.oid)
        AND EXISTS(SELECT 1 FROM pg_namespace n WHERE n.nspname=$1 AND n.nspowner<>r.oid)
        AND has_schema_privilege(current_user,$1,'USAGE')
        AND NOT has_schema_privilege(current_user,$1,'CREATE')
        AND NOT EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=$1 AND c.relowner=r.oid)
        FROM pg_roles r WHERE rolname=current_user")
        .bind(schema).fetch_one(pool).await.map_err(|_|"DATABASE_POLICY_UNAVAILABLE")?;
    if !safe {
        return Err("DATABASE_ROLE_REFUSED");
    }
    Ok(())
}

pub async fn mateval_ready(
    pool: &PgPool,
    schema: &str,
    bank: Option<&serde_json::Value>,
) -> Result<(), &'static str> {
    verify_role(pool, schema).await?;
    // Resolve the exact columns required by collection without reading rows.
    for sql in [
        "SELECT version,digest,bank,codebook FROM corpus LIMIT 0",
        "SELECT id,token_hash,bank_version,levels,seed,question_order,production_order,started_at,updated_at,completed_at,revision,payload_hash,snapshot FROM participations LIMIT 0",
        "SELECT participation_id,question_id,production_id,note,initial_note,x,y,z,evaluated_axes FROM answers LIMIT 0",
        "SELECT participation_id,sequence,event,occurred_at,elapsed_ms,payload FROM interaction_events LIMIT 0",
    ] {
        sqlx::query(sql)
            .execute(pool)
            .await
            .map_err(|_| "MATEVAL_SCHEMA_UNAVAILABLE")?;
    }
    let privileges:bool=sqlx::query_scalar("SELECT has_table_privilege('corpus','SELECT')
        AND NOT has_table_privilege('corpus','INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER,MAINTAIN')
        AND NOT has_any_column_privilege('corpus','INSERT,UPDATE,REFERENCES')
        AND has_table_privilege('participations','SELECT') AND has_table_privilege('participations','INSERT') AND has_table_privilege('participations','UPDATE')
        AND NOT has_table_privilege('participations','DELETE,TRUNCATE,REFERENCES,TRIGGER,MAINTAIN')
        AND NOT has_any_column_privilege('participations','REFERENCES')
        AND has_table_privilege('answers','SELECT') AND has_table_privilege('answers','INSERT') AND has_table_privilege('answers','DELETE')
        AND NOT has_table_privilege('answers','UPDATE,TRUNCATE,REFERENCES,TRIGGER,MAINTAIN')
        AND NOT has_any_column_privilege('answers','UPDATE,REFERENCES')
        AND has_table_privilege('interaction_events','SELECT') AND has_table_privilege('interaction_events','INSERT')
        AND NOT has_table_privilege('interaction_events','UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER,MAINTAIN')
        AND NOT has_any_column_privilege('interaction_events','UPDATE,REFERENCES')
        AND NOT has_table_privilege('administrators','SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER,MAINTAIN')
        AND NOT has_any_column_privilege('administrators','SELECT,INSERT,UPDATE,REFERENCES')
        AND NOT has_table_privilege('administrator_sessions','SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER,MAINTAIN')
        AND NOT has_any_column_privilege('administrator_sessions','SELECT,INSERT,UPDATE,REFERENCES')")
        .fetch_one(pool).await.map_err(|_|"MATEVAL_PRIVILEGES_UNAVAILABLE")?;
    if !privileges {
        return Err("MATEVAL_PRIVILEGES_REFUSED");
    }
    if let Some(bank) = bank {
        let version = bank
            .get("version")
            .and_then(serde_json::Value::as_str)
            .ok_or("INVALID_PUBLIC_CORPUS")?;
        // Collection and resumed sessions consume Bank, retaining every known
        // field and array order while ignoring historical private metadata.
        // Compare that exact contract without rewriting the stored JSON,
        // digest, codebook, version or existing participation references.
        let stored = sqlx::query_scalar::<_, Option<sqlx::types::Json<serde_json::Value>>>(
            "SELECT CASE WHEN octet_length(bank::text)<=5242880 THEN bank ELSE NULL END FROM corpus WHERE version=$1",
        )
        .bind(version)
        .fetch_optional(pool)
        .await
        .map_err(|_| "MATEVAL_CORPUS_UNAVAILABLE")?
        .flatten()
        .ok_or("MATEVAL_CORPUS_MISMATCH")?
        .0;
        if !same_mateval_bank(bank, &stored) {
            return Err("MATEVAL_CORPUS_MISMATCH");
        }
    }
    Ok(())
}

fn same_mateval_bank(public: &serde_json::Value, stored: &serde_json::Value) -> bool {
    let typed = |value: &serde_json::Value| -> Option<serde_json::Value> {
        let bank: mrjam_mateval::Bank = serde_json::from_value(value.clone()).ok()?;
        bank.validate().ok()?;
        serde_json::to_value(bank).ok()
    };
    let Some(expected) = typed(public) else {
        return false;
    };
    // A future public field cannot be silently ignored by this runtime.
    expected == *public && typed(stored).as_ref() == Some(&expected)
}

#[cfg(test)]
mod bank_tests {
    use super::same_mateval_bank;
    use serde_json::{Value, json};

    fn bank() -> Value {
        json!({"version":"0.3.0","questions":[{"id":"R01","family":"f1","level":"level","domain":"domain","statement":"invented question","productions":[{"id":"R01-1","content":"invented one"},{"id":"R01-2","content":"invented two"}]}]})
    }

    #[test]
    fn historical_metadata_is_retained_but_not_a_collection_field() {
        let expected = bank();
        let mut stored = expected.clone();
        stored["historical"] = json!({"invented":"root"});
        stored["questions"][0]["historical"] = json!({"invented":"question"});
        stored["questions"][0]["productions"][0]["historical"] = json!({"invented":"production"});
        let before = stored.clone();
        assert_ne!(expected, stored);
        assert!(same_mateval_bank(&expected, &stored));
        assert_eq!(stored, before);
        assert!(!same_mateval_bank(&stored, &expected));
    }

    #[test]
    fn every_known_field_and_order_remains_exact() {
        let expected = bank();
        for path in [
            "/version",
            "/questions/0/id",
            "/questions/0/family",
            "/questions/0/level",
            "/questions/0/domain",
            "/questions/0/statement",
            "/questions/0/productions/0/id",
            "/questions/0/productions/0/content",
        ] {
            let mut stored = expected.clone();
            if let Some(value) = stored.pointer_mut(path) {
                *value = json!("invented difference");
            }
            assert!(!same_mateval_bank(&expected, &stored));
        }
        let mut stored = expected.clone();
        if let Some(productions) = stored["questions"][0]["productions"].as_array_mut() {
            productions.reverse();
        }
        assert!(!same_mateval_bank(&expected, &stored));
    }

    #[test]
    fn missing_fields_invalid_types_and_invalid_identifiers_are_refused() {
        let expected = bank();
        for stored in [
            Value::Null,
            json!({"version":"0.3.0"}),
            json!({"version":3,"questions":[]}),
        ] {
            assert!(!same_mateval_bank(&expected, &stored));
        }
        let mut invalid = expected.clone();
        invalid["questions"][0]["id"] = json!("invalid");
        assert!(!same_mateval_bank(&invalid, &invalid));
        let mut duplicate = expected.clone();
        duplicate["questions"][0]["productions"][1]["id"] = json!("R01-1");
        assert!(!same_mateval_bank(&duplicate, &duplicate));
    }

    #[test]
    fn two_question_order_is_not_canonicalized() {
        let mut expected = bank();
        let second = json!({"id":"R02","family":"f2","level":"level","domain":"domain","statement":"invented second question","productions":[{"id":"R02-1","content":"invented second production"}]});
        if let Some(questions) = expected["questions"].as_array_mut() {
            questions.push(second);
        }
        assert_eq!(expected["questions"].as_array().map(Vec::len), Some(2));
        let mut stored = expected.clone();
        if let Some(questions) = stored["questions"].as_array_mut() {
            questions.reverse();
        }
        assert!(!same_mateval_bank(&expected, &stored));
    }
}

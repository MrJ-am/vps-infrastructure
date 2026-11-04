//! Browser qualification only. This is never a deployment entrypoint.
//! It accepts one literal local fixture, creates its own schema/role, and removes
//! only those objects after shutdown. All returned diagnostics are fixed codes.
use mrjam_server::{application_with_mateval, mateval::MatevalState, serve};
use serde_json::{Value, json};
use sqlx::{
    PgPool,
    postgres::{PgConnectOptions, PgPoolOptions},
    types::Json,
};
use std::{
    io::{self, Write},
    process::ExitCode,
    str::FromStr,
    time::{Duration, SystemTime, UNIX_EPOCH},
};
use tokio::{
    net::TcpListener,
    signal::unix::{SignalKind, signal},
};

const FIXTURE_URL: &str =
    "postgresql://mrjam_synthetic:mrjam_synthetic_only@127.0.0.1:55432/mrjam_synthetic";

fn synthetic_options(url: &str) -> Result<PgConnectOptions, &'static str> {
    // Reject sockets, alternate hosts, query options and unknown options before
    // calling SQLx's parser, which might otherwise emit their values in a log.
    if url != FIXTURE_URL {
        return Err("SYNTHETIC_DATABASE_REQUIRED");
    }
    // SQLx also consults PGOPTIONS/PGSSL* and other libpq-style variables when
    // parsing a URL. A correct literal URL alone must not authorize these
    // inherited selectors. Never print their names or values.
    if std::env::vars_os().any(|(name, _)| name.to_string_lossy().starts_with("PG")) {
        return Err("SYNTHETIC_DATABASE_ENVIRONMENT_REFUSED");
    }
    PgConnectOptions::from_str(FIXTURE_URL).map_err(|_| "FIXTURE_CONFIGURATION_INVALID")
}

async fn local_ddl(pool: &PgPool, sql: String) -> Result<(), &'static str> {
    // Identifiers originate solely from numeric clock/PID values below. There
    // is no command, schema, role, password or SQL parameter exposed to callers.
    sqlx::query(sqlx::AssertSqlSafe(sql))
        .execute(pool)
        .await
        .map_err(|_| "SYNTHETIC_DDL_FAILED")?;
    Ok(())
}

async fn run() -> Result<(), &'static str> {
    if std::env::args_os().len() != 1 {
        return Err("INVALID_INVOCATION");
    }
    let url =
        std::env::var("MRJAM_SYNTHETIC_DATABASE_URL").map_err(|_| "SYNTHETIC_DATABASE_REQUIRED")?;
    let options = synthetic_options(&url)?;
    let mut terminate = signal(SignalKind::terminate()).map_err(|_| "SIGNAL_UNAVAILABLE")?;
    let mut interrupt = signal(SignalKind::interrupt()).map_err(|_| "SIGNAL_UNAVAILABLE")?;
    let suffix = format!(
        "{}_{}",
        std::process::id(),
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map_err(|_| "CLOCK_UNAVAILABLE")?
            .as_nanos()
    );
    let schema = format!("mateval_browser_{suffix}");
    let role = format!("mateval_browser_role_{suffix}");
    let admin = PgPoolOptions::new()
        .max_connections(2)
        .connect_with(options.clone())
        .await
        .map_err(|_| "SYNTHETIC_DATABASE_UNAVAILABLE")?;
    // A collision fails before cleanup; preexisting objects are never removed.
    local_ddl(&admin, format!("CREATE SCHEMA {schema}")).await?;
    let mut role_created = false;
    let mut setup_pool = None;
    let mut application_pool = None;
    let result = async {
        local_ddl(&admin, format!("CREATE ROLE {role} LOGIN PASSWORD 'mateval_browser_synthetic_only' NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS")).await?;
        role_created = true;
        let setup = PgPoolOptions::new()
            .max_connections(1)
            .connect_with(options.clone().options([("search_path", schema.as_str())]))
            .await
            .map_err(|_| "SYNTHETIC_SETUP_UNAVAILABLE")?;
        setup_pool = Some(setup.clone());
        sqlx::raw_sql(include_str!("../../../components/mateval/migrations/001-collecte.sql"))
            .execute(&setup).await.map_err(|_| "SYNTHETIC_SCHEMA_FAILED")?;
        for grant in [
            format!("GRANT USAGE ON SCHEMA {schema} TO {role}"),
            format!("GRANT SELECT ON {schema}.corpus TO {role}"),
            format!("GRANT SELECT,INSERT,UPDATE ON {schema}.participations TO {role}"),
            format!("GRANT SELECT,INSERT,DELETE ON {schema}.answers TO {role}"),
            format!("GRANT SELECT,INSERT ON {schema}.interaction_events TO {role}"),
        ] {
            local_ddl(&admin, grant).await?;
        }
        let bank: Value = serde_json::from_str(include_str!("../../../tools/mateval-browser-synthetic/bank.json"))
            .map_err(|_| "SYNTHETIC_BANK_INVALID")?;
        let version = bank.get("version").and_then(Value::as_str).ok_or("SYNTHETIC_BANK_INVALID")?.to_owned();
        sqlx::query("INSERT INTO corpus(version,digest,bank,codebook) VALUES($1,'synthetic-browser-only',$2,'{}')")
            .bind(version).bind(Json(bank)).execute(&setup).await.map_err(|_| "SYNTHETIC_BANK_FAILED")?;
        let app = PgPoolOptions::new()
            .max_connections(4)
            .connect_with(options.username(&role).password("mateval_browser_synthetic_only").options([("search_path", schema.as_str())]))
            .await.map_err(|_| "SYNTHETIC_ROLE_UNAVAILABLE")?;
        application_pool = Some(app.clone());
        let privileged: bool = sqlx::query_scalar("SELECT rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls FROM pg_roles WHERE rolname=current_user")
            .fetch_one(&app).await.map_err(|_| "SYNTHETIC_ROLE_CHECK_FAILED")?;
        if privileged { return Err("SYNTHETIC_PRIVILEGED_ROLE_REFUSED"); }
        let listener = TcpListener::bind((std::net::Ipv4Addr::LOCALHOST, 0))
            .await.map_err(|_| "SYNTHETIC_LISTEN_FAILED")?;
        let port = listener.local_addr().map_err(|_| "SYNTHETIC_LISTEN_FAILED")?.port();
        let router = application_with_mateval(MatevalState::with_service(mrjam_mateval::Service::new(app)));
        {
            let mut output = io::stdout().lock();
            serde_json::to_writer(&mut output, &json!({"status":"ready","port":port}))
                .map_err(|_| "SYNTHETIC_REPORT_FAILED")?;
            output.write_all(b"\n").map_err(|_| "SYNTHETIC_REPORT_FAILED")?;
            output.flush().map_err(|_| "SYNTHETIC_REPORT_FAILED")?;
        }
        serve(listener, router, async move {
            tokio::select! {
                _ = terminate.recv() => {},
                _ = interrupt.recv() => {},
                _ = tokio::time::sleep(Duration::from_secs(600)) => {},
            }
        }).await.map_err(|_| "SYNTHETIC_SERVE_FAILED")
    }.await;
    if let Some(pool) = application_pool {
        pool.close().await;
    }
    if let Some(pool) = setup_pool {
        pool.close().await;
    }
    let schema_cleanup = local_ddl(&admin, format!("DROP SCHEMA {schema} CASCADE")).await;
    let role_cleanup = if role_created {
        local_ddl(&admin, format!("DROP ROLE {role}")).await
    } else {
        Ok(())
    };
    admin.close().await;
    result.and(schema_cleanup).and(role_cleanup)
}

#[tokio::main(flavor = "multi_thread", worker_threads = 2)]
async fn main() -> ExitCode {
    match run().await {
        Ok(()) => ExitCode::SUCCESS,
        Err(code) => {
            let _ = writeln!(io::stderr().lock(), "{{\"code\":\"{code}\"}}");
            ExitCode::from(2)
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn guard_refuses_nonliteral_targets_before_sqlx_parsing() {
        for url in [
            "",
            "postgresql://mrjam_synthetic:mrjam_synthetic_only@localhost:55432/mrjam_synthetic",
            "postgresql://mrjam_synthetic:mrjam_synthetic_only@127.0.0.1:55432/production",
            "postgresql://mrjam_synthetic:mrjam_synthetic_only@127.0.0.1:55432/mrjam_synthetic?host=%2Fsynthetic-socket",
            "postgresql://mrjam_synthetic:mrjam_synthetic_only@127.0.0.1:55432/mrjam_synthetic?unknown=SYNTHETIC_MARKER",
        ] {
            assert!(synthetic_options(url).is_err());
        }
        assert!(synthetic_options(FIXTURE_URL).is_ok());
    }
}

use mrjam_audition::service::{PgAudition, ServiceError, VerifiedActor};
use mrjam_audition::{Timestamp, WriteChannel};
use serde_json::{Value, json};
use sqlx::{
    PgPool,
    postgres::{PgConnectOptions, PgPoolOptions},
};
use std::str::FromStr;
type Error = Box<dyn std::error::Error + Send + Sync>;
const URL: &str =
    "postgresql://mrjam_synthetic:mrjam_synthetic_only@127.0.0.1:55432/mrjam_synthetic";
const NOW: i64 = 1_800_000_000;
fn check(ok: bool, message: &'static str) -> Result<(), Error> {
    if ok { Ok(()) } else { Err(message.into()) }
}
async fn call(
    service: &PgAudition,
    actor: &VerifiedActor,
    operation: &str,
    params: Value,
) -> Result<Value, ServiceError> {
    service
        .execute(
            actor,
            WriteChannel::Web,
            operation,
            params.to_string().as_bytes(),
            Timestamp::new(NOW).map_err(|_| ServiceError::new("date_invalide", 400))?,
        )
        .await
}
fn key(n: u32) -> String {
    format!("synthetic-audition-key-{n:04}")
}
#[tokio::test]
async fn real_postgres_permissions_transactions_versions_and_replays() -> Result<(), Error> {
    check(
        std::env::var("MRJAM_SYNTHETIC_DATABASE_URL")
            .ok()
            .as_deref()
            == Some(URL),
        "literal synthetic opt-in required",
    )?;
    let admin = PgPoolOptions::new().max_connections(2).connect(URL).await?;
    let present:bool=sqlx::query_scalar("SELECT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname='audition') OR EXISTS(SELECT 1 FROM pg_roles WHERE rolname='audition_synthetic_app')").fetch_one(&admin).await?;
    check(
        !present,
        "synthetic Audition fixture collision; no existing schema/role is removed",
    )?;
    sqlx::raw_sql(include_str!("../migrations/001-schema.sql"))
        .execute(&admin)
        .await?;
    let result = fixture(&admin).await;
    sqlx::raw_sql("DROP SCHEMA audition CASCADE; DROP ROLE IF EXISTS audition_synthetic_app;")
        .execute(&admin)
        .await?;
    result
}
async fn fixture(admin: &PgPool) -> Result<(), Error> {
    sqlx::raw_sql(include_str!("../migrations/002-version-scope.sql"))
        .execute(admin)
        .await?;
    sqlx::raw_sql("CREATE ROLE audition_synthetic_app LOGIN PASSWORD 'synthetic_only' NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS; GRANT USAGE ON SCHEMA audition TO audition_synthetic_app; GRANT SELECT ON audition.schema_migrations,audition.administrateurs TO audition_synthetic_app; GRANT SELECT,INSERT,DELETE ON audition.groupes TO audition_synthetic_app; GRANT SELECT,INSERT,UPDATE,DELETE ON audition.membres TO audition_synthetic_app; GRANT SELECT,INSERT,UPDATE ON audition.objets TO audition_synthetic_app; GRANT SELECT,INSERT ON audition.versions,audition.requetes,audition.audit TO audition_synthetic_app; GRANT USAGE,SELECT ON SEQUENCE audition.audit_id_seq TO audition_synthetic_app; GRANT EXECUTE ON FUNCTION audition.est_admin(),audition.role_groupe(text) TO audition_synthetic_app; INSERT INTO audition.administrateurs VALUES('invented.admin',true);").execute(admin).await?;
    let options = PgConnectOptions::from_str(URL)?
        .username("audition_synthetic_app")
        .password("synthetic_only");
    let pool = PgPoolOptions::new()
        .max_connections(4)
        .connect_with(options)
        .await?;
    let service = PgAudition::new(pool.clone());
    let result = scenario(&service, &pool, admin).await;
    pool.close().await;
    result
}
async fn scenario(service: &PgAudition, pool: &PgPool, admin: &PgPool) -> Result<(), Error> {
    service.ready().await?;
    sqlx::query("GRANT mrjam_synthetic TO audition_synthetic_app")
        .execute(admin)
        .await?;
    let inherited_rejected = service.ready().await.is_err();
    sqlx::query("REVOKE mrjam_synthetic FROM audition_synthetic_app")
        .execute(admin)
        .await?;
    check(
        inherited_rejected,
        "runtime role inherited schema owner authority",
    )?;
    check(
        PgAudition::new(admin.clone()).ready().await.is_err(),
        "privileged runtime pool must be rejected",
    )?;
    let manager = VerifiedActor::from_authenticated_identity("invented.admin", Some(NOW))?;
    let stale = VerifiedActor::from_authenticated_identity("invented.admin", Some(NOW - 901))?;
    let teacher = VerifiedActor::from_authenticated_identity("invented.teacher", None)?;
    let student = VerifiedActor::from_authenticated_identity("invented.student", None)?;
    let other = VerifiedActor::from_authenticated_identity("invented.other", None)?;
    check(
        call(
            service,
            &stale,
            "creer_groupe",
            json!({"nom":"Synthetic class","cle":key(1)}),
        )
        .await
        .err()
        .is_some_and(|e| e.code() == "verification_renforcee_requise"),
        "stale MFA accepted",
    )?;
    let group = call(
        service,
        &manager,
        "creer_groupe",
        json!({"nom":"Synthetic class","cle":key(1)}),
    )
    .await?["id"]
        .clone();
    for (n, actor, role) in [
        (2, "invented.teacher", "enseignant"),
        (3, "invented.student", "eleve"),
        (4, "invented.other", "eleve"),
    ] {
        call(
            service,
            &manager,
            "habiliter",
            json!({"groupe":group,"acteur":actor,"role":role,"cle":key(n)}),
        )
        .await?;
    }
    let activity_doc = json!({"titre":"Invented square","consigne":"Discuss square sign","attendus":[{"id":"sign","texte":"Explain sign"}],"criteres":[{"id":"reason","attendu":"sign","texte":"Justification","maximum":2}],"type":"ouverte","corrige":"Synthetic private correction"});
    let activity = call(
        service,
        &teacher,
        "activite",
        json!({"groupe":group,"document":activity_doc,"cle":key(5)}),
    )
    .await?;
    check(
        activity["url"].as_str()
            == Some(
                format!(
                    "https://audition.mrj.am/#activite/{}",
                    activity["id"].as_str().ok_or("missing id")?
                )
                .as_str(),
            ),
        "canonical URL differs from Elm router",
    )?;
    let assignment=call(service,&teacher,"affecter",json!({"groupe":group,"activite":activity["id"],"eleves":["invented.student"],"echeance":NOW+86400,"cle":key(6)})).await?;
    check(
        call(
            service,
            &other,
            "ouvrir_seance",
            json!({"groupe":group,"affectation":assignment["id"],"cle":key(7)}),
        )
        .await
        .is_err(),
        "unassigned student opened session",
    )?;
    let open = json!({"groupe":group,"affectation":assignment["id"],"cle":key(8)});
    let session = call(service, &student, "ouvrir_seance", open.clone()).await?;
    check(
        session["activite"]["document"].get("corrige").is_none(),
        "private correction leaked",
    )?;
    check(
        call(service, &student, "ouvrir_seance", open.clone()).await? == session,
        "exact replay changed",
    )?;
    let sid = session["seance"]["id"].clone();
    check(
        call(
            service,
            &manager,
            "consulter_seance",
            json!({"groupe":group,"id":sid}),
        )
        .await
        .is_err(),
        "technical admin read pedagogy",
    )?;
    let sample = json!({"groupe":group,"id":sid,"revision":1,"activite_version":1,"politique_version":1,"production":"Invented answer","activite_a":NOW,"aides":[],"observations":[{"critere":"reason","etat":"difficulte","points":0,"justification":"Invented explanation"}],"cle":key(9)});
    let (first, concurrent) = tokio::join!(
        call(service, &student, "consigner", sample.clone()),
        call(service, &student, "consigner", sample.clone())
    );
    let recorded = first?;
    check(
        concurrent? == recorded,
        "concurrent duplicate did not commit one result",
    )?;
    check(
        recorded["seance"]["revision"] == 2,
        "revision did not advance",
    )?;
    check(
        call(service, &student, "consigner", sample.clone()).await? == recorded,
        "committed replay did not return receipt",
    )?;
    let mut changed = sample.clone();
    changed["production"] = json!("Different invented answer");
    check(
        call(service, &student, "consigner", changed)
            .await
            .err()
            .is_some_and(|e| e.code() == "cle_reutilisee_avec_autre_operation"),
        "changed payload replay accepted",
    )?;
    let attempt = recorded["seance"]["document"]["tentatives"][0]["id"].clone();
    let corrected=call(service,&teacher,"rectifier",json!({"groupe":group,"id":sid,"revision":2,"tentative":attempt,"observation":"reason","justification":"Teacher rechecked invented answer","etat":"reussite_autonome","points":2,"cle":key(10)})).await?;
    check(
        corrected["seance"]["document"]["tentatives"][0]["observations"][0]["points"] == 0,
        "correction overwrote original",
    )?;
    let report = call(service, &teacher, "rapport", json!({"groupe":group})).await?;
    check(
        report["elements"][0]["observations"][0]["points"] == 2,
        "corrected score absent from report",
    )?;
    check(
        !report.to_string().contains("Invented answer"),
        "report loaded production",
    )?;
    // Raw RLS is tested separately from application permissions.
    let mut tx = pool.begin().await?;
    sqlx::query("SELECT set_config('audition.acteur','invented.other',true)")
        .execute(&mut *tx)
        .await?;
    let visible: i64 = sqlx::query_scalar("SELECT count(*) FROM audition.versions WHERE objet=$1")
        .bind(sid.as_str())
        .fetch_one(&mut *tx)
        .await?;
    check(
        visible == 0,
        "other student could read session history through RLS",
    )?;
    tx.rollback().await?;
    // New official activity must be explicitly adopted; old traces survive.
    let mut revised = activity_doc.clone();
    revised["criteres"][0]["maximum"] = json!(3);
    call(
        service,
        &teacher,
        "activite",
        json!({"groupe":group,"id":activity["id"],"revision":1,"document":revised,"cle":key(11)}),
    )
    .await?;
    check(
        call(
            service,
            &student,
            "transition",
            json!({"groupe":group,"id":sid,"revision":3,"action":"terminer","cle":key(12)}),
        )
        .await
        .err()
        .is_some_and(|e| e.code() == "contexte_modifie"),
        "stale context finished",
    )?;
    let adopted = call(
        service,
        &student,
        "adopter_contexte",
        json!({"groupe":group,"id":sid,"revision":3,"activite_version":2,"cle":key(13)}),
    )
    .await?;
    check(
        adopted["seance"]["document"]["tentatives"]
            .as_array()
            .is_some_and(|v| v.len() == 1),
        "adoption lost old traces",
    )?;
    check(
        call(
            service,
            &student,
            "transition",
            json!({"groupe":group,"id":sid,"revision":4,"action":"terminer","cle":key(14)}),
        )
        .await
        .err()
        .is_some_and(|e| e.code() == "criteres_non_observes"),
        "old observations satisfied new rubric",
    )?;
    // Assignment revocation blocks even the previously successful open receipt.
    call(service,&teacher,"affecter",json!({"groupe":group,"id":assignment["id"],"revision":1,"activite":activity["id"],"eleves":["invented.other"],"echeance":NOW+86400,"cle":key(15)})).await?;
    check(
        call(service, &student, "ouvrir_seance", open)
            .await
            .is_err(),
        "revoked assignment replay disclosed session",
    )?;
    call(
        service,
        &manager,
        "habiliter",
        json!({"groupe":group,"acteur":"invented.student","role":"retirer","cle":key(16)}),
    )
    .await?;
    check(
        call(service, &student, "consigner", sample).await.is_err(),
        "revoked membership replay disclosed receipt",
    )?;
    let deleted = call(
        service,
        &manager,
        "supprimer_groupe",
        json!({"groupe":group,"confirmation":group,"cle":key(17)}),
    )
    .await?;
    check(deleted["supprime"] == true, "delete failed")?;
    let count:i64=sqlx::query_scalar("SELECT (SELECT count(*) FROM audition.objets)+(SELECT count(*) FROM audition.versions)+(SELECT count(*) FROM audition.membres)").fetch_one(admin).await?;
    check(count == 0, "group deletion retained pedagogical rows")?;
    let audit: i64 = sqlx::query_scalar(
        "SELECT count(*) FROM audition.audit WHERE operation='supprimer_groupe'",
    )
    .fetch_one(admin)
    .await?;
    check(audit == 1, "deletion audit lost")?;
    Ok(())
}

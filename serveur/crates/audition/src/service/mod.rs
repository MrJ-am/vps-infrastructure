//! Transactional Audition service. Identity is supplied by the authenticated
//! adapter; no request field selects actor, role, channel or MFA status.
mod operations;
mod report;
mod store;
mod wire;

use crate::{ActorId, Timestamp, WriteChannel};
use serde_json::Value;
use sha2::{Digest, Sha256};
use sqlx::PgPool;
use std::fmt;
use store::Store;

pub struct VerifiedActor {
    id: ActorId,
    mfa_verified_at: Option<Timestamp>,
    maximum_auth_age_seconds: u16,
}
impl VerifiedActor {
    /// The caller MUST have authenticated this identity and MFA time. This
    /// constructor validates syntax only; it is not an authentication mechanism.
    pub fn from_authenticated_identity(id: &str, mfa_verified_at: Option<i64>) -> Result<Self> {
        Ok(Self {
            id: ActorId::new(id).map_err(|_| ServiceError::new("identite_requise", 401))?,
            mfa_verified_at: mfa_verified_at
                .map(Timestamp::new)
                .transpose()
                .map_err(ServiceError::domain)?,
            maximum_auth_age_seconds: 0,
        })
    }
    /// An authenticated verifier may attest an upper bound on the age of MFA
    /// without disclosing its exact auth_time. Keep that bound explicitly;
    /// `verification_time` is not represented as the authentication time.
    pub fn from_recent_mfa_verification(
        id: &str,
        verification_time: i64,
        maximum_auth_age_seconds: u16,
    ) -> Result<Self> {
        require(
            maximum_auth_age_seconds <= 900,
            "verification_renforcee_requise",
            403,
        )?;
        let mut actor = Self::from_authenticated_identity(id, Some(verification_time))?;
        actor.maximum_auth_age_seconds = maximum_auth_age_seconds;
        Ok(actor)
    }
    pub fn id(&self) -> &str {
        self.id.as_str()
    }
    fn recent_mfa(&self, now: Timestamp) -> bool {
        self.mfa_verified_at.is_some_and(|at| {
            at.seconds() <= now.seconds()
                && now.seconds() - at.seconds() + i64::from(self.maximum_auth_age_seconds) <= 900
        })
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct ServiceError {
    code: &'static str,
    status: u16,
}
impl ServiceError {
    pub const fn new(code: &'static str, status: u16) -> Self {
        Self { code, status }
    }
    pub const fn code(self) -> &'static str {
        self.code
    }
    pub const fn status(self) -> u16 {
        self.status
    }
    fn domain(e: crate::DomainError) -> Self {
        Self::new(e.code(), 400)
    }
}
impl fmt::Display for ServiceError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.code)
    }
}
impl std::error::Error for ServiceError {}
impl From<sqlx::Error> for ServiceError {
    fn from(_: sqlx::Error) -> Self {
        Self::new("stockage_indisponible", 503)
    }
}
type Result<T> = std::result::Result<T, ServiceError>;
fn require(ok: bool, code: &'static str, status: u16) -> Result<()> {
    if ok {
        Ok(())
    } else {
        Err(ServiceError::new(code, status))
    }
}

#[derive(Clone)]
pub struct PgAudition {
    pool: PgPool,
}
impl PgAudition {
    pub fn new(pool: PgPool) -> Self {
        Self { pool }
    }
    pub async fn ready(&self) -> Result<()> {
        let mut tx = self.pool.begin().await?;
        Store::check_connection(&mut tx).await?;
        tx.rollback().await?;
        Ok(())
    }
    pub async fn execute(
        &self,
        actor: &VerifiedActor,
        channel: WriteChannel,
        operation: &str,
        bytes: &[u8],
        now: Timestamp,
    ) -> Result<Value> {
        let params = wire::parse(bytes)?;
        let spec = wire::operation(operation)?;
        wire::fields(&params, spec.required, spec.optional)?;
        let group = params
            .get("groupe")
            .map(|v| wire::identifier(v, false))
            .transpose()?;
        let key = if spec.write {
            Some(wire::identifier(&params["cle"], false)?)
        } else {
            None
        };
        if let Some(key) = &key {
            require(key.len() >= 16, "cle_idempotence_requise", 400)?;
        }
        if spec.access == wire::Access::Admin {
            require(
                channel == WriteChannel::Web && actor.recent_mfa(now),
                "verification_renforcee_requise",
                403,
            )?;
        }
        let mut tx = self.pool.begin().await?;
        Store::check_connection(&mut tx).await?;
        sqlx::query("SELECT set_config('statement_timeout','5000',true),set_config('lock_timeout','2000',true),set_config('audition.acteur',$1,true)")
            .bind(actor.id()).execute(&mut *tx).await?;
        // Consistent lock order: actor first (global idempotency scope), then
        // group. All permissions and content are re-read after both locks.
        sqlx::query("SELECT pg_advisory_xact_lock(hashtextextended($1,0))")
            .bind(format!("audition:actor:{}", actor.id()))
            .execute(&mut *tx)
            .await?;
        sqlx::query("SELECT pg_advisory_xact_lock(hashtextextended($1,0))")
            .bind(format!(
                "audition:group:{}",
                group.as_deref().unwrap_or("__administration__")
            ))
            .execute(&mut *tx)
            .await?;
        let mut store = Store {
            tx: &mut tx,
            actor: actor.id(),
            now,
        };
        let role = store
            .authorize(
                spec.access,
                if operation == "supprimer_groupe" {
                    None
                } else {
                    group.as_deref()
                },
            )
            .await?;
        if operation == "ouvrir_seance" {
            let assignment = wire::identifier(&params["affectation"], false)?;
            let aff = store
                .read(&assignment, group.as_deref(), Some("affectation"))
                .await?;
            require(
                wire::array(&aff.document["eleves"], 500)?
                    .iter()
                    .any(|v| v.as_str() == Some(actor.id())),
                "affectation_interdite",
                403,
            )?;
        }
        // An exact replay cannot disclose a formerly accessible session.
        if matches!(
            operation,
            "consulter_seance" | "adopter_contexte" | "consigner" | "transition" | "rectifier"
        ) {
            store.own_session(&params, &role).await?;
        }
        let hash=key.as_ref().map(|_| {
            let envelope=serde_json::json!({"canal":if channel==WriteChannel::Web {"web"}else{"mcp"},"parametres":wire::canonical(&params)});
            format!("{:x}",Sha256::digest(wire::canonical(&envelope).to_string().as_bytes()))
        });
        if let Some(key) = &key
            && let Some((old_operation, old_hash, result)) = store.receipt(key).await?
        {
            require(
                old_operation == operation && Some(old_hash.as_str()) == hash.as_deref(),
                "cle_reutilisee_avec_autre_operation",
                409,
            )?;
            tx.commit().await?;
            return Ok(result);
        }
        let result = operations::perform(&mut store, operation, &params, &role, channel).await?;
        require(
            result.to_string().len() <= 262_144,
            "reponse_trop_large",
            409,
        )?;
        if let Some(key) = key {
            store
                .remember(
                    &key,
                    if operation == "supprimer_groupe" {
                        None
                    } else {
                        group.as_deref()
                    },
                    operation,
                    hash.as_deref()
                        .ok_or(ServiceError::new("etat_interne_invalide", 503))?,
                    &result,
                )
                .await?;
        }
        tx.commit().await?;
        Ok(result)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    #[test]
    fn ambiguous_and_oversized_json_are_rejected() {
        for value in [
            b"{\"groupe\":\"one\",\"groupe\":\"two\"}".as_slice(),
            b"{\"document\":{\"titre\":\"a\",\"titre\":\"b\"}}",
            b"{} {}",
            b"[]",
            b"{\"text\":\"\\u0000\"}",
        ] {
            assert!(wire::parse(value).is_err());
        }
        assert!(wire::parse(&vec![b' '; 65_537]).is_err());
        assert!(wire::parse(b"{\"points\":0,\"aides\":[]}").is_ok());
    }
    #[test]
    fn identity_and_channel_cannot_be_client_parameters() -> Result<()> {
        let spec = wire::operation("cours")?;
        let forged =
            json!({"groupe":"g","document":{},"cle":"synthetic-key-0001","acteur":"teacher"});
        assert!(wire::fields(&forged, spec.required, spec.optional).is_err());
        let actor = VerifiedActor::from_authenticated_identity("invented.admin", Some(1000))?;
        assert!(actor.recent_mfa(Timestamp::new(1900).map_err(ServiceError::domain)?));
        assert!(!actor.recent_mfa(Timestamp::new(1901).map_err(ServiceError::domain)?));
        assert!(!actor.recent_mfa(Timestamp::new(999).map_err(ServiceError::domain)?));
        let bounded = VerifiedActor::from_recent_mfa_verification("invented.admin", 1000, 300)?;
        assert!(bounded.recent_mfa(Timestamp::new(1600).map_err(ServiceError::domain)?));
        assert!(!bounded.recent_mfa(Timestamp::new(1601).map_err(ServiceError::domain)?));
        Ok(())
    }
    #[test]
    fn canonical_hash_input_preserves_zero_null_and_array_order() -> Result<()> {
        let a = wire::parse(br#"{"z":{"b":2,"a":1},"n":null,"v":[0,1]}"#)?;
        let b = wire::parse(br#"{"v":[0,1],"n":null,"z":{"a":1,"b":2}}"#)?;
        assert_eq!(
            wire::canonical(&a).to_string(),
            wire::canonical(&b).to_string()
        );
        assert_ne!(
            wire::canonical(&a),
            wire::canonical(&json!({"z":{"a":1,"b":2},"n":0,"v":[0,1]}))
        );
        Ok(())
    }
    #[test]
    fn reporting_keeps_absence_extremes_and_qcm_reference_separate() -> Result<()> {
        assert_eq!(report::indicator(0, 0, None)?["affichage"], "Non observé");
        assert_eq!(report::indicator(0, 1, None)?["extreme"], "moins_infini");
        assert_eq!(report::indicator(1, 1, None)?["extreme"], "plus_infini");
        assert_eq!(report::indicator(1, 2, None)?["affichage"], "0 dB");
        assert_eq!(report::indicator(1, 4, Some(4))?["affichage"], "0 dB");
        assert_eq!(
            report::indicator(1, 4, None)?["reference_hasard"],
            Value::Null
        );
        assert!(report::indicator(2, 1, None).is_err());
        Ok(())
    }
    #[test]
    fn correction_updates_interpretation_and_score_without_changing_original() -> Result<()> {
        let session = json!({"tentatives":[{"id":"attempt","activite_version":1,"observations":[{"critere":"reason","etat":"difficulte","points":0,"incertitude":"Invented uncertainty"}]}],"rectifications":[{"tentative":"attempt","critere":"reason","etat":"reussite_autonome","points":2,"auteur":"invented.teacher"}]});
        let latest = report::latest(&session)?;
        assert_eq!(latest[0]["points"], 2);
        assert_eq!(latest[0]["etat"], "reussite_autonome");
        assert!(latest[0].get("incertitude").is_none());
        assert_eq!(session["tentatives"][0]["observations"][0]["points"], 0);
        Ok(())
    }
}

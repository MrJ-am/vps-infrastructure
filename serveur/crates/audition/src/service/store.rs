use super::{Result, ServiceError, require, wire};
use crate::Timestamp;
use serde_json::{Value, json};
use sqlx::{Postgres, Transaction};

#[derive(Clone)]
pub(super) struct Record {
    pub id: String,
    pub group: String,
    pub nature: String,
    pub revision: i64,
    pub document: Value,
}
impl Record {
    pub fn present(&self) -> Value {
        self.present_document(self.document.clone())
    }
    pub fn present_document(&self, doc: Value) -> Value {
        json!({"id":self.id,"groupe":self.group,"nature":self.nature,"revision":self.revision,"document":doc,"url":format!("https://audition.mrj.am/#{}/{}",self.nature,self.id)})
    }
    pub fn official(&self) -> Result<i64> {
        wire::integer(&self.document["version_prescrite"], 0, 1_000_000_000)
    }
    pub fn check_revision(&self, p: &Value) -> Result<()> {
        require(
            p["revision"].as_i64() == Some(self.revision),
            "conflit_revision",
            409,
        )
    }
}
pub(super) struct Store<'a, 'c> {
    pub tx: &'a mut Transaction<'c, Postgres>,
    pub actor: &'a str,
    pub now: Timestamp,
}
impl Store<'_, '_> {
    pub async fn check_connection(tx: &mut Transaction<'_, Postgres>) -> Result<()> {
        let okay:bool=sqlx::query_scalar("SELECT NOT (rolsuper OR rolbypassrls OR rolcreaterole OR rolcreatedb) FROM pg_roles WHERE rolname=current_user").fetch_one(&mut **tx).await?;
        require(okay, "role_stockage_invalide", 503)?;
        let protected:bool=sqlx::query_scalar("SELECT count(*)=7 AND bool_and(NOT pg_has_role(current_user,c.relowner,'MEMBER')) AND bool_and(c.relrowsecurity) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='audition' AND c.relname IN ('administrateurs','groupes','membres','objets','versions','requetes','audit')").fetch_one(&mut **tx).await?;
        require(protected, "schema_stockage_invalide", 503)?;
        let version: Option<i32> =
            sqlx::query_scalar("SELECT max(version) FROM audition.schema_migrations")
                .fetch_one(&mut **tx)
                .await?;
        require(version == Some(2), "schema_incompatible", 503)
    }
    pub async fn admin(&mut self) -> Result<bool> {
        Ok(sqlx::query_scalar("SELECT audition.est_admin()")
            .fetch_one(&mut **self.tx)
            .await?)
    }
    pub async fn role(&mut self, group: &str) -> Result<String> {
        let r: Option<String> = sqlx::query_scalar("SELECT audition.role_groupe($1)")
            .bind(group)
            .fetch_one(&mut **self.tx)
            .await?;
        Ok(r.unwrap_or_default())
    }
    pub async fn authorize(&mut self, access: wire::Access, group: Option<&str>) -> Result<String> {
        let role = if let Some(group) = group {
            self.role(group).await?
        } else {
            String::new()
        };
        match access {
            wire::Access::Admin => {
                require(self.admin().await?, "administration_interdite", 403)?;
                if let Some(group) = group {
                    let exists: bool = sqlx::query_scalar(
                        "SELECT EXISTS(SELECT 1 FROM audition.groupes WHERE id=$1)",
                    )
                    .bind(group)
                    .fetch_one(&mut **self.tx)
                    .await?;
                    require(exists, "groupe_indisponible", 404)?;
                }
            }
            wire::Access::Teacher => require(role == "enseignant", "groupe_interdit", 403)?,
            wire::Access::Student => require(role == "eleve", "groupe_interdit", 403)?,
            wire::Access::Read if group.is_some() => require(
                role == "enseignant" || role == "eleve",
                "groupe_interdit",
                403,
            )?,
            _ => {}
        }
        Ok(role)
    }
    pub async fn receipt(&mut self, key: &str) -> Result<Option<(String, String, Value)>> {
        Ok(sqlx::query_as(
            "SELECT operation,empreinte,resultat FROM audition.requetes WHERE acteur=$1 AND cle=$2",
        )
        .bind(self.actor)
        .bind(key)
        .fetch_optional(&mut **self.tx)
        .await?)
    }
    pub async fn remember(
        &mut self,
        key: &str,
        group: Option<&str>,
        operation: &str,
        hash: &str,
        result: &Value,
    ) -> Result<()> {
        sqlx::query("INSERT INTO audition.requetes(acteur,cle,groupe,operation,empreinte,resultat,recu_a) VALUES($1,$2,$3,$4,$5,$6,to_timestamp($7::double precision))").bind(self.actor).bind(key).bind(group).bind(operation).bind(hash).bind(result).bind(self.now.seconds()).execute(&mut **self.tx).await?;
        Ok(())
    }
    pub async fn groups(&mut self) -> Result<Vec<Value>> {
        let rows: Vec<(String, String, Option<String>)> = sqlx::query_as(
            "SELECT id,nom,audition.role_groupe(id) FROM audition.groupes ORDER BY id LIMIT 501",
        )
        .fetch_all(&mut **self.tx)
        .await?;
        require(rows.len() <= 500, "capacite_groupes_atteinte", 409)?;
        Ok(rows
            .into_iter()
            .map(|(id, nom, role)| json!({"id":id,"nom":nom,"role":role}))
            .collect())
    }
    pub async fn members(&mut self, group: &str) -> Result<Vec<Value>> {
        let rows: Vec<(String, String)> = sqlx::query_as(
            "SELECT acteur,role FROM audition.membres WHERE groupe=$1 ORDER BY acteur LIMIT 501",
        )
        .bind(group)
        .fetch_all(&mut **self.tx)
        .await?;
        require(rows.len() <= 500, "capacite_groupe_atteinte", 409)?;
        Ok(rows
            .into_iter()
            .map(|(acteur, role)| json!({"acteur":acteur,"role":role}))
            .collect())
    }
    pub async fn target_students(&mut self, group: &str, list: &Value) -> Result<()> {
        let values = wire::array(list, 500)?;
        require(!values.is_empty(), "eleves_invalides", 400)?;
        let mut seen = std::collections::BTreeSet::new();
        for value in values {
            let student = wire::identifier(value, true)?;
            require(seen.insert(student.clone()), "eleves_invalides", 400)?;
            let exists:bool=sqlx::query_scalar("SELECT EXISTS(SELECT 1 FROM audition.membres WHERE groupe=$1 AND acteur=$2 AND role='eleve')").bind(group).bind(student).fetch_one(&mut **self.tx).await?;
            require(exists, "eleves_invalides", 400)?;
        }
        Ok(())
    }
    pub async fn id(&mut self) -> Result<String> {
        Ok(sqlx::query_scalar("SELECT gen_random_uuid()::text")
            .fetch_one(&mut **self.tx)
            .await?)
    }
    pub async fn read(
        &mut self,
        id: &str,
        group: Option<&str>,
        nature: Option<&str>,
    ) -> Result<Record> {
        wire::identifier(&Value::String(id.to_owned()), false)?;
        let row: Option<(String, String, String, i64, Value)> = sqlx::query_as(
            "SELECT id,groupe,nature,revision,document FROM audition.objets WHERE id=$1",
        )
        .bind(id)
        .fetch_optional(&mut **self.tx)
        .await?;
        let (id, g, n, r, d) = row.ok_or(ServiceError::new("objet_indisponible", 404))?;
        require(
            group.is_none_or(|v| v == g) && nature.is_none_or(|v| v == n),
            "objet_indisponible",
            404,
        )?;
        Ok(Record {
            id,
            group: g,
            nature: n,
            revision: r,
            document: d,
        })
    }
    pub async fn list(&mut self, group: &str, nature: &str) -> Result<Vec<Record>> {
        // A page/report never loads productions or full correction history.
        let rows:Vec<(String,String,String,i64,Value)>=sqlx::query_as("SELECT id,groupe,nature,revision,CASE WHEN nature='seance' THEN document-'tentatives'-'rectifications' ELSE document END FROM audition.objets WHERE groupe=$1 AND nature=$2 ORDER BY id LIMIT 2001").bind(group).bind(nature).fetch_all(&mut **self.tx).await?;
        require(rows.len() <= 2000, "capacite_groupe_atteinte", 409)?;
        Ok(rows
            .into_iter()
            .map(|(id, g, n, r, d)| Record {
                id,
                group: g,
                nature: n,
                revision: r,
                document: d,
            })
            .collect())
    }
    pub async fn version(&mut self, id: &str, version: i64) -> Result<Value> {
        require(
            (1..=1_000_000_000).contains(&version),
            "proposition_non_validee",
            409,
        )?;
        let result: Option<Value> = sqlx::query_scalar(
            "SELECT document FROM audition.versions WHERE objet=$1 AND revision=$2",
        )
        .bind(id)
        .bind(version)
        .fetch_optional(&mut **self.tx)
        .await?;
        result.ok_or(ServiceError::new("objet_indisponible", 404))
    }
    pub async fn write(&mut self, record: &Record, mut doc: Value, new: bool) -> Result<Record> {
        let revision = if new {
            1
        } else {
            record
                .revision
                .checked_add(1)
                .ok_or(ServiceError::new("limite_revisions_atteinte", 409))?
        };
        require(revision <= 1_000_000_000, "limite_revisions_atteinte", 409)?;
        if record.nature == "seance" {
            doc["synthese"] = Value::Array(super::report::latest(&doc)?);
            doc["total_tentatives"] = json!(wire::array(&doc["tentatives"], 128)?.len());
        }
        require(
            doc.is_object() && doc.to_string().len() <= 900_000,
            "limite_traces_atteinte",
            409,
        )?;
        if new {
            let count: i64 = sqlx::query_scalar(
                "SELECT count(*) FROM audition.objets WHERE groupe=$1 AND nature=$2",
            )
            .bind(&record.group)
            .bind(&record.nature)
            .fetch_one(&mut **self.tx)
            .await?;
            require(count < 2000, "capacite_groupe_atteinte", 409)?;
            sqlx::query("INSERT INTO audition.objets(id,groupe,nature,revision,document,modifie_a) VALUES($1,$2,$3,1,$4,to_timestamp($5::double precision))").bind(&record.id).bind(&record.group).bind(&record.nature).bind(&doc).bind(self.now.seconds()).execute(&mut **self.tx).await?;
        } else {
            let result=sqlx::query("UPDATE audition.objets SET revision=$3,document=$4,modifie_a=to_timestamp($5::double precision) WHERE id=$1 AND revision=$2").bind(&record.id).bind(record.revision).bind(revision).bind(&doc).bind(self.now.seconds()).execute(&mut **self.tx).await?;
            require(result.rows_affected() == 1, "conflit_revision", 409)?;
        }
        sqlx::query("INSERT INTO audition.versions(objet,groupe,revision,document,auteur,recu_a) VALUES($1,$2,$3,$4,$5,to_timestamp($6::double precision))").bind(&record.id).bind(&record.group).bind(revision).bind(&doc).bind(self.actor).bind(self.now.seconds()).execute(&mut **self.tx).await?;
        Ok(Record {
            revision,
            document: doc,
            ..record.clone()
        })
    }
    pub async fn create(&mut self, group: &str, nature: &str, doc: Value) -> Result<Record> {
        let record = Record {
            id: self.id().await?,
            group: group.to_owned(),
            nature: nature.to_owned(),
            revision: 0,
            document: Value::Null,
        };
        self.write(&record, doc, true).await
    }
    pub async fn audit(
        &mut self,
        group: Option<&str>,
        operation: &str,
        target: &str,
    ) -> Result<()> {
        sqlx::query("INSERT INTO audition.audit(groupe,auteur,operation,cible,recu_a) VALUES($1,$2,$3,$4,to_timestamp($5::double precision))").bind(group).bind(self.actor).bind(operation).bind(target).bind(self.now.seconds()).execute(&mut **self.tx).await?;
        Ok(())
    }
    pub async fn own_session(&mut self, p: &Value, role: &str) -> Result<Record> {
        let group = wire::identifier(&p["groupe"], false)?;
        let id = wire::identifier(&p["id"], false)?;
        let record = self.read(&id, Some(&group), Some("seance")).await?;
        require(
            role == "enseignant" || record.document["eleve"].as_str() == Some(self.actor),
            "seance_interdite",
            403,
        )?;
        if role == "eleve" {
            let assignment = wire::identifier(&record.document["affectation"], false)?;
            let aff = self
                .read(&assignment, Some(&group), Some("affectation"))
                .await?;
            require(
                wire::array(&aff.document["eleves"], 500)?
                    .iter()
                    .any(|v| v.as_str() == Some(self.actor)),
                "affectation_interdite",
                403,
            )?;
        }
        Ok(record)
    }
}

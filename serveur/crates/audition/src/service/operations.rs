use super::{
    Result, ServiceError, report, require,
    store::{Record, Store},
    wire,
};
use crate::{
    ActivityDefinition, ActivityKind, Criterion, CriterionId, ExpectedOutcome, ExpectedOutcomeId,
    Timestamp, WriteChannel,
};
use serde_json::{Value, json};
use std::collections::BTreeSet;

fn string<'a>(p: &'a Value, k: &str) -> Result<&'a str> {
    wire::text(&p[k], 64, false)
}
fn revision(p: &Value) -> Result<i64> {
    wire::integer(&p["revision"], 1, 1_000_000_000)
}
fn date(v: &Value) -> Result<i64> {
    wire::integer(v, 0, 4_102_444_800)
}
fn activity_time(v: &Value, now: Timestamp) -> Result<i64> {
    let t = date(v)?;
    require(
        t >= now.seconds() - 30 * 86400 && t <= now.seconds() + 300,
        "heure_activite_invalide",
        400,
    )?;
    Ok(t)
}
fn visible(mut doc: Value, teacher: bool, now: Timestamp) -> Value {
    if !teacher
        && !doc
            .get("publication_corrige")
            .and_then(Value::as_i64)
            .is_some_and(|v| v <= now.seconds())
        && let Some(o) = doc.as_object_mut()
    {
        o.remove("corrige");
        o.remove("publication_corrige");
    }
    doc
}
fn validate_activity(doc: &Value) -> Result<()> {
    wire::fields(
        doc,
        &["titre", "consigne", "attendus", "criteres"],
        &[
            "cours",
            "cours_version",
            "corrige",
            "publication_corrige",
            "type",
            "propositions",
        ],
    )?;
    let outcomes = wire::array(&doc["attendus"], 32)?
        .iter()
        .map(|a| {
            wire::fields(a, &["id", "texte"], &[])?;
            ExpectedOutcome::new(
                ExpectedOutcomeId::new(wire::identifier(&a["id"], false)?)
                    .map_err(ServiceError::domain)?,
                wire::text(&a["texte"], 2000, false)?,
            )
            .map_err(ServiceError::domain)
        })
        .collect::<Result<Vec<_>>>()?;
    let criteria = wire::array(&doc["criteres"], 64)?
        .iter()
        .map(|c| {
            wire::fields(c, &["id", "attendu", "texte", "maximum"], &[])?;
            Criterion::new(
                CriterionId::new(wire::identifier(&c["id"], false)?)
                    .map_err(ServiceError::domain)?,
                ExpectedOutcomeId::new(wire::identifier(&c["attendu"], false)?)
                    .map_err(ServiceError::domain)?,
                wire::text(&c["texte"], 2000, false)?,
                c["maximum"]
                    .as_f64()
                    .ok_or(ServiceError::new("critere_invalide", 400))?,
            )
            .map_err(ServiceError::domain)
        })
        .collect::<Result<Vec<_>>>()?;
    let kind = match doc.get("type").and_then(Value::as_str) {
        None | Some("ouverte") => ActivityKind::OpenResponse,
        Some("qcm") => ActivityKind::SingleCorrectChoice {
            alternatives: wire::integer(&doc["propositions"], 2, 100)? as u8,
        },
        _ => return Err(ServiceError::new("type_invalide", 400)),
    };
    let mut definition = ActivityDefinition::new(
        wire::text(&doc["titre"], 200, false)?,
        wire::text(&doc["consigne"], 16000, false)?,
        outcomes,
        criteria,
        kind,
    )
    .map_err(ServiceError::domain)?;
    if let Some(c) = doc.get("cours") {
        wire::identifier(c, false)?;
    }
    if let Some(v) = doc.get("cours_version") {
        wire::integer(v, 0, 1_000_000_000)?;
    }
    if let Some(p) = doc.get("publication_corrige") {
        date(p)?;
    }
    if let Some(c) = doc.get("corrige") {
        definition = definition
            .with_correction(
                wire::text(c, 16000, true)?,
                doc.get("publication_corrige")
                    .map(|v| date(v).and_then(|t| Timestamp::new(t).map_err(ServiceError::domain)))
                    .transpose()?,
            )
            .map_err(ServiceError::domain)?;
    }
    let _ = definition;
    Ok(())
}
fn observation(p: &Value, activity: &Value, has_help: bool, now: Timestamp) -> Result<Value> {
    wire::fields(
        p,
        &["critere", "etat", "justification"],
        &["points", "incertitude"],
    )?;
    let id = wire::identifier(&p["critere"], false)?;
    let criterion = wire::array(&activity["criteres"], 64)?
        .iter()
        .find(|c| c["id"].as_str() == Some(id.as_str()))
        .ok_or(ServiceError::new("observation_invalide", 400))?;
    let state = string(p, "etat")?;
    require(
        matches!(
            state,
            "non_observe" | "en_cours" | "difficulte" | "reussite_aidee" | "reussite_autonome"
        ),
        "observation_invalide",
        400,
    )?;
    wire::text(&p["justification"], 4000, false)?;
    let points = if p["points"].is_null() {
        None
    } else {
        Some(
            p["points"]
                .as_f64()
                .ok_or(ServiceError::new("points_invalides", 400))?,
        )
    };
    let max = criterion["maximum"]
        .as_f64()
        .ok_or(ServiceError::new("schema_incompatible", 503))?;
    require(
        points.is_none_or(|v| v >= 0.0 && v <= max),
        "points_invalides",
        400,
    )?;
    if let Some(u) = p.get("incertitude") {
        wire::text(u, 2000, false)?;
    }
    require(
        state != "reussite_autonome" || !has_help,
        "autonomie_incompatible_avec_aide",
        400,
    )?;
    if state == "reussite_autonome" || state == "reussite_aidee" {
        require(points == Some(max), "reussite_incomplete", 400)?;
        require(p.get("incertitude").is_none(), "reussite_incertaine", 400)?;
    }
    require(state != "reussite_aidee" || has_help, "aide_manquante", 400)?;
    let mut result = p.clone();
    result["recu_a"] = json!(now.seconds());
    result["fuseau"] = json!("UTC");
    Ok(result)
}
async fn session_context(
    store: &mut Store<'_, '_>,
    record: &Record,
    role: &str,
    p: &Value,
) -> Result<Value> {
    let s = &record.document;
    let activity = store
        .read(
            string(s, "activite")?,
            Some(&record.group),
            Some("activite"),
        )
        .await?;
    let adopted = wire::integer(&s["activite_version"], 1, 1_000_000_000)?;
    let current = activity.official()?;
    let doc = store.version(&activity.id, adopted).await?;
    let changed = adopted != current;
    let traces = wire::page(wire::array(&s["tentatives"], 128)?.clone(), p)?;
    let mut presented = s.clone();
    presented["tentatives"] = traces["elements"].clone();
    let course = if let Some(id) = doc.get("cours").and_then(Value::as_str) {
        let mut c = store.read(id, Some(&record.group), Some("cours")).await?;
        c.revision = wire::integer(&doc["cours_version"], 1, 1_000_000_000)?;
        c.present_document(store.version(id, c.revision).await?)
    } else {
        Value::Null
    };
    let next = if changed {
        let mut n = activity.clone();
        n.revision = current;
        n.present_document(visible(
            store.version(&activity.id, current).await?,
            role == "enseignant",
            store.now,
        ))
    } else {
        Value::Null
    };
    let mut actual = activity;
    actual.revision = adopted;
    let actions = match s["etat"].as_str() {
        Some("terminee") => vec!["consulter_seance"],
        Some("interrompue") => vec!["consulter_seance", "reprendre"],
        _ if changed => vec!["consulter_seance", "adopter_contexte", "interrompre"],
        _ => vec!["consigner", "interrompre", "terminer"],
    };
    Ok(
        json!({"seance":record.present_document(presented),"traces":traces,"cours":course,"activite":actual.present_document(visible(doc,role=="enseignant",store.now)),"nouvelle_activite":next,"activite_version":adopted,"version_actuelle":current,"politique":wire::policy(),"contexte_modifie":changed,"informations_manquantes":if s["tentatives"].as_array().is_some_and(|a|a.is_empty()){vec!["production et observations"]}else{vec![]},"actions_suivantes":actions}),
    )
}

pub(super) async fn perform(
    store: &mut Store<'_, '_>,
    op: &str,
    p: &Value,
    role: &str,
    channel: WriteChannel,
) -> Result<Value> {
    let group = p.get("groupe").and_then(Value::as_str).unwrap_or("");
    let now = store.now.seconds();
    match op {
        "contexte" => {
            let mut result = wire::page(store.groups().await?, p)?;
            result["acteur"] = json!(store.actor);
            result["administrateur"] = json!(store.admin().await?);
            result["politique"] = wire::policy();
            result["mcp"] = json!("https://audition.mrj.am/mcp");
            result["fuseau"] = json!("UTC");
            Ok(result)
        }
        "creer_groupe" => {
            let name = wire::text(&p["nom"], 200, false)?;
            require(
                store.groups().await?.len() < 500,
                "capacite_groupes_atteinte",
                409,
            )?;
            let id = store.id().await?;
            sqlx::query("INSERT INTO audition.groupes(id,nom) VALUES($1,$2)")
                .bind(&id)
                .bind(name)
                .execute(&mut **store.tx)
                .await?;
            store.audit(Some(&id), op, &id).await?;
            Ok(json!({"id":id,"nom":name}))
        }
        "habiliter" => {
            let member = wire::identifier(&p["acteur"], true)?;
            let target = string(p, "role")?;
            require(
                matches!(target, "enseignant" | "eleve" | "retirer"),
                "habilitation_invalide",
                400,
            )?;
            if target == "retirer" {
                sqlx::query("DELETE FROM audition.membres WHERE groupe=$1 AND acteur=$2")
                    .bind(group)
                    .bind(&member)
                    .execute(&mut **store.tx)
                    .await?;
            } else {
                let members = store.members(group).await?;
                require(
                    members.len() < 500
                        || members
                            .iter()
                            .any(|m| m["acteur"].as_str() == Some(member.as_str())),
                    "capacite_groupe_atteinte",
                    409,
                )?;
                sqlx::query("INSERT INTO audition.membres(groupe,acteur,role) VALUES($1,$2,$3) ON CONFLICT(groupe,acteur) DO UPDATE SET role=EXCLUDED.role").bind(group).bind(&member).bind(target).execute(&mut **store.tx).await?;
            }
            store.audit(Some(group), op, &member).await?;
            Ok(json!({"confirme":true}))
        }
        "membres" => wire::page(store.members(group).await?, p),
        "diagnostic" => Ok(json!({"base":"disponible","schema":2})),
        "supprimer_groupe" => {
            require(
                p["confirmation"].as_str() == Some(group),
                "confirmation_requise",
                400,
            )?;
            store.audit(Some(group), op, group).await?;
            let deleted = sqlx::query("DELETE FROM audition.groupes WHERE id=$1")
                .bind(group)
                .execute(&mut **store.tx)
                .await?;
            require(deleted.rows_affected() == 1, "groupe_indisponible", 404)?;
            Ok(json!({"supprime":true}))
        }
        "preparations" => {
            let mut result = wire::page(
                store
                    .list(group, "activite")
                    .await?
                    .iter()
                    .map(Record::present)
                    .collect(),
                p,
            )?;
            result["cours"] = wire::page(
                store
                    .list(group, "cours")
                    .await?
                    .iter()
                    .map(Record::present)
                    .collect(),
                p,
            )?["elements"]
                .clone();
            result["eleves"] = Value::Array(
                store
                    .members(group)
                    .await?
                    .into_iter()
                    .filter(|m| m["role"] == "eleve")
                    .collect(),
            );
            Ok(result)
        }
        "cours" | "activite" => {
            let mut doc = p["document"].clone();
            if op == "activite" {
                validate_activity(&doc)?;
            } else {
                wire::fields(&doc, &["titre", "contenu"], &[])?;
                wire::text(&doc["titre"], 200, false)?;
                wire::text(&doc["contenu"], 32000, false)?;
            }
            let old = if let Some(id) = p.get("id") {
                let o = store
                    .read(&wire::identifier(id, false)?, Some(group), Some(op))
                    .await?;
                o.check_revision(p)?;
                Some(o)
            } else {
                require(p.get("revision").is_none(), "champs_invalides", 400)?;
                None
            };
            if let Some(id) = doc.get("cours").and_then(Value::as_str) {
                let course = store.read(id, Some(group), Some("cours")).await?;
                let version = course.official()?;
                require(
                    channel != WriteChannel::Web || version > 0,
                    "proposition_non_validee",
                    409,
                )?;
                doc["cours_version"] = json!(version);
            }
            let official = channel == WriteChannel::Web;
            doc["origine"] = json!(if official {
                "prescription_enseignant"
            } else {
                "proposition_llm"
            });
            doc["validee"] = json!(official);
            doc["auteur"] = json!(store.actor);
            doc["recu_a"] = json!(now);
            doc["version_prescrite"] = json!(if official {
                old.as_ref().map_or(1, |o| o.revision + 1)
            } else {
                match &old {
                    Some(o) => o.official()?,
                    None => 0,
                }
            });
            Ok(match old {
                Some(o) => store.write(&o, doc, false).await?,
                None => store.create(group, op, doc).await?,
            }
            .present())
        }
        "affecter" | "remediation" => {
            let activity = store
                .read(
                    &wire::identifier(&p["activite"], false)?,
                    Some(group),
                    Some("activite"),
                )
                .await?;
            require(activity.official()? > 0, "proposition_non_validee", 409)?;
            store.target_students(group, &p["eleves"]).await?;
            let deadline = date(&p["echeance"])?;
            if op == "remediation" {
                wire::text(&p["consigne"], 8000, false)?;
            }
            if let Some(origin) = p.get("origine") {
                store
                    .read(
                        &wire::identifier(origin, false)?,
                        Some(group),
                        Some("seance"),
                    )
                    .await?;
            }
            let doc = json!({"activite":activity.id,"activite_version":activity.official()?,"eleves":p["eleves"],"echeance":deadline,"fuseau":"UTC","prescrit_par":store.actor,"prescrit_a":now,"remediation":op=="remediation","consigne_remediation":p["consigne"],"origine":p["origine"]});
            let saved = if let Some(id) = p.get("id") {
                let old = store
                    .read(
                        &wire::identifier(id, false)?,
                        Some(group),
                        Some("affectation"),
                    )
                    .await?;
                old.check_revision(p)?;
                require(
                    old.document["activite"] == p["activite"],
                    "activite_affectee_immuable",
                    409,
                )?;
                store.write(&old, doc, false).await?
            } else {
                store.create(group, "affectation", doc).await?
            };
            Ok(saved.present())
        }
        "travaux" => {
            let assignments = store.list(group, "affectation").await?;
            let sessions = store.list(group, "seance").await?;
            let mut rows = Vec::new();
            for aff in assignments {
                let mut doc = aff.document.clone();
                if role != "enseignant"
                    && !wire::array(&doc["eleves"], 500)?
                        .iter()
                        .any(|v| v.as_str() == Some(store.actor))
                {
                    continue;
                }
                let mut activity = store
                    .read(string(&doc, "activite")?, Some(group), Some("activite"))
                    .await?;
                activity.revision = activity.official()?;
                let activity_doc = visible(
                    store.version(&activity.id, activity.revision).await?,
                    role == "enseignant",
                    store.now,
                );
                let session = sessions.iter().find(|s| {
                    s.document["affectation"] == aff.id
                        && s.document["eleve"].as_str() == Some(store.actor)
                });
                if role != "enseignant" {
                    doc["eleves"] = json!([store.actor]);
                }
                rows.push(json!({"affectation":aff.present_document(doc),"activite":activity.present_document(activity_doc),"seance":session.map(Record::present)}));
            }
            wire::page(rows, p)
        }
        "ouvrir_seance" => {
            let aff = store
                .read(
                    &wire::identifier(&p["affectation"], false)?,
                    Some(group),
                    Some("affectation"),
                )
                .await?;
            require(
                wire::array(&aff.document["eleves"], 500)?
                    .iter()
                    .any(|v| v.as_str() == Some(store.actor)),
                "affectation_interdite",
                403,
            )?;
            let activity = store
                .read(
                    string(&aff.document, "activite")?,
                    Some(group),
                    Some("activite"),
                )
                .await?;
            let sessions = store.list(group, "seance").await?;
            let existing = sessions.iter().find(|s| {
                s.document["affectation"] == aff.id
                    && s.document["eleve"].as_str() == Some(store.actor)
            });
            let session = if let Some(s) = existing {
                store.read(&s.id, Some(group), Some("seance")).await?
            } else {
                require(activity.official()? > 0, "proposition_non_validee", 409)?;
                store.create(group,"seance",json!({"affectation":aff.id,"activite":activity.id,"activite_version":activity.official()?,"eleve":store.actor,"etat":"en_cours","ouverte_a":now,"reprise_a":now,"tentatives":[],"rectifications":[],"transitions":[]})).await?
            };
            session_context(store, &session, role, p).await
        }
        "consulter_seance" | "adopter_contexte" | "consigner" | "transition" | "rectifier" => {
            session_operation(store, op, p, role, channel).await
        }
        "retrouver" => {
            let mut obj = store
                .read(&wire::identifier(&p["id"], false)?, None, None)
                .await?;
            let current_role = store.role(&obj.group).await?;
            require(
                current_role == "enseignant" || current_role == "eleve",
                "objet_indisponible",
                404,
            )?;
            let mut doc = obj.document.clone();
            if obj.nature == "seance" {
                store
                    .own_session(&json!({"id":obj.id,"groupe":obj.group}), &current_role)
                    .await?;
                doc = json!({});
            }
            if current_role == "eleve" && (obj.nature == "activite" || obj.nature == "cours") {
                let assignments = store.list(&obj.group, "affectation").await?;
                let mut allowed = false;
                for aff in assignments {
                    let a = store
                        .read(
                            string(&aff.document, "activite")?,
                            Some(&obj.group),
                            Some("activite"),
                        )
                        .await?;
                    let d = store.version(&a.id, a.official()?).await?;
                    if obj.nature == "activite" && a.id == obj.id {
                        allowed = true;
                        obj.revision = a.official()?;
                        doc = d;
                        break;
                    }
                    if obj.nature == "cours" && d["cours"] == obj.id {
                        allowed = true;
                        obj.revision = wire::integer(&d["cours_version"], 1, 1_000_000_000)?;
                        doc = store.version(&obj.id, obj.revision).await?;
                        break;
                    }
                }
                require(allowed, "objet_indisponible", 404)?;
            }
            if obj.nature == "activite" {
                doc = visible(doc, current_role == "enseignant", store.now);
            }
            Ok(
                json!({"id":obj.id,"groupe":obj.group,"nature":obj.nature,"objet":obj.present_document(doc),"url":format!("https://audition.mrj.am/#{}/{}",obj.nature,obj.id)}),
            )
        }
        "rapport" => report::report(store, p).await,
        _ => Err(ServiceError::new("operation_inconnue", 404)),
    }
}

async fn session_operation(
    store: &mut Store<'_, '_>,
    op: &str,
    p: &Value,
    role: &str,
    channel: WriteChannel,
) -> Result<Value> {
    let record = store.own_session(p, role).await?;
    if op == "consulter_seance" {
        return session_context(store, &record, role, p).await;
    }
    record.check_revision(p)?;
    let _ = revision(p)?;
    let mut s = record.document.clone();
    let activity = store
        .read(
            string(&s, "activite")?,
            Some(&record.group),
            Some("activite"),
        )
        .await?;
    let current = activity.official()?;
    let adopted = wire::integer(&s["activite_version"], 1, 1_000_000_000)?;
    let now = store.now.seconds();
    match op {
        "adopter_contexte" => {
            require(s["etat"] == "en_cours", "transition_interdite", 409)?;
            require(
                p["activite_version"].as_i64() == Some(current),
                "contexte_modifie",
                409,
            )?;
            let mut transitions = wire::array(&s["transitions"], 256)?.clone();
            require(transitions.len() < 256, "limite_transitions_atteinte", 409)?;
            transitions.push(json!({"action":"adopter_contexte","ancienne_version":adopted,"version":current,"auteur":store.actor,"recu_a":now}));
            s["activite_version"] = json!(current);
            s["transitions"] = Value::Array(transitions);
        }
        "consigner" => {
            require(s["etat"] == "en_cours", "seance_non_ouverte", 409)?;
            require(
                p["activite_version"].as_i64() == Some(adopted) && adopted == current,
                "contexte_modifie",
                409,
            )?;
            require(
                p["politique_version"].as_i64() == Some(1),
                "politique_modifiee",
                409,
            )?;
            wire::text(&p["production"], 16000, false)?;
            activity_time(&p["activite_a"], store.now)?;
            let mut attempts = wire::array(&s["tentatives"], 128)?.clone();
            require(attempts.len() < 128, "limite_traces_atteinte", 409)?;
            let mut help = Vec::new();
            for item in wire::array(&p["aides"], 32)? {
                wire::fields(item, &["nature", "contenu", "activite_a"], &[])?;
                require(
                    matches!(
                        item["nature"].as_str(),
                        Some("indice" | "explication" | "correction" | "solution")
                    ),
                    "aide_invalide",
                    400,
                )?;
                wire::text(&item["contenu"], 8000, false)?;
                activity_time(&item["activite_a"], store.now)?;
                let mut h = item.clone();
                h["recu_a"] = json!(now);
                h["fuseau"] = json!("UTC");
                help.push(h);
            }
            let doc = store.version(&activity.id, current).await?;
            let observations = wire::array(&p["observations"], 64)?;
            require(!observations.is_empty(), "observation_invalide", 400)?;
            let mut observed = BTreeSet::new();
            let mut validated = Vec::new();
            for o in observations {
                require(
                    observed.insert(wire::identifier(&o["critere"], false)?),
                    "observations_dupliquees",
                    400,
                )?;
                validated.push(observation(o, &doc, !help.is_empty(), store.now)?);
            }
            attempts.push(json!({"id":store.id().await?,"production":p["production"],"production_origine":"eleve_rapportee","auteur_trace":store.actor,"canal":if channel==WriteChannel::Web{"web"}else{"mcp"},"interpretation_origine":if channel==WriteChannel::Web{"eleve"}else{"llm"},"activite_version":current,"politique_version":1,"activite_a":p["activite_a"],"recu_a":now,"fuseau":"UTC","aides":help,"observations":validated}));
            s["tentatives"] = Value::Array(attempts);
        }
        "transition" => {
            let action = string(p, "action")?;
            require(
                matches!(action, "reprendre" | "interrompre" | "terminer"),
                "action_invalide",
                400,
            )?;
            require(
                s["etat"]
                    == if action == "reprendre" {
                        "interrompue"
                    } else {
                        "en_cours"
                    },
                "transition_interdite",
                409,
            )?;
            if action == "terminer" {
                require(adopted == current, "contexte_modifie", 409)?;
                require(
                    !wire::array(&s["tentatives"], 128)?.is_empty(),
                    "seance_incomplete",
                    409,
                )?;
                let doc = store.version(&activity.id, current).await?;
                let latest = report::latest(&s)?;
                require(
                    wire::array(&doc["criteres"], 64)?.iter().all(|c| {
                        latest.iter().any(|o| {
                            o["critere"] == c["id"]
                                && o["activite_version"].as_i64() == Some(current)
                                && o["etat"] != "non_observe"
                        })
                    }),
                    "criteres_non_observes",
                    409,
                )?;
            }
            let mut transitions = wire::array(&s["transitions"], 256)?.clone();
            require(transitions.len() < 256, "limite_transitions_atteinte", 409)?;
            transitions
                .push(json!({"action":action,"auteur":store.actor,"recu_a":now,"fuseau":"UTC"}));
            s["transitions"] = Value::Array(transitions);
            s["etat"] = json!(match action {
                "reprendre" => "en_cours",
                "terminer" => "terminee",
                _ => "interrompue",
            });
            if action == "reprendre" {
                s["reprise_a"] = json!(now);
            }
        }
        "rectifier" => {
            let attempt = wire::array(&s["tentatives"], 128)?
                .iter()
                .find(|a| a["id"] == p["tentative"])
                .ok_or(ServiceError::new("rectification_invalide", 400))?;
            require(
                wire::array(&attempt["observations"], 64)?
                    .iter()
                    .any(|o| o["critere"] == p["observation"]),
                "rectification_invalide",
                400,
            )?;
            wire::text(&p["justification"], 4000, false)?;
            if let Some(a) = p.get("annotation") {
                wire::text(a, 4000, true)?;
            }
            if p.get("etat").is_some() {
                let doc = store
                    .version(
                        &activity.id,
                        wire::integer(&attempt["activite_version"], 1, 1_000_000_000)?,
                    )
                    .await?;
                observation(
                    &json!({"critere":p["observation"],"etat":p["etat"],"points":p["points"],"justification":p["justification"]}),
                    &doc,
                    !wire::array(&attempt["aides"], 32)?.is_empty(),
                    store.now,
                )?;
            } else {
                wire::text(&p["annotation"], 4000, false)?;
            }
            let mut corrections = wire::array(&s["rectifications"], 256)?.clone();
            require(
                corrections.len() < 256,
                "limite_rectifications_atteinte",
                409,
            )?;
            corrections.push(json!({"id":store.id().await?,"tentative":p["tentative"],"critere":p["observation"],"etat":p["etat"],"points":p["points"],"annotation":p["annotation"],"justification":p["justification"],"auteur":store.actor,"recu_a":now,"fuseau":"UTC"}));
            s["rectifications"] = Value::Array(corrections);
        }
        _ => return Err(ServiceError::new("operation_inconnue", 404)),
    }
    let saved = store.write(&record, s, false).await?;
    session_context(store, &saved, role, p).await
}

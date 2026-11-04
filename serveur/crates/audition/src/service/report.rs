use super::{Result, ServiceError, require, store::Store, wire};
use serde_json::{Value, json};
use std::collections::BTreeMap;

pub(super) fn latest(session: &Value) -> Result<Vec<Value>> {
    if session.get("tentatives").is_none() {
        return Ok(wire::array(&session["synthese"], 64)?.clone());
    }
    let mut observations = BTreeMap::<String, Value>::new();
    for attempt in wire::array(&session["tentatives"], 128)? {
        for observation in wire::array(&attempt["observations"], 64)? {
            let mut o = observation.clone();
            o["tentative"] = attempt["id"].clone();
            o["activite_version"] = attempt["activite_version"].clone();
            observations.insert(wire::identifier(&o["critere"], false)?, o);
        }
    }
    for correction in wire::array(&session["rectifications"], 256)? {
        if correction["etat"].is_null() {
            continue;
        }
        let criterion = wire::identifier(&correction["critere"], false)?;
        if let Some(o) = observations.get_mut(&criterion)
            && o["tentative"] == correction["tentative"]
        {
            o["etat"] = correction["etat"].clone();
            // Correct both interpretation and points. The old Lisp report
            // changed only the state, leaving a contradicted prior score.
            o["points"] = correction["points"].clone();
            if let Some(map) = o.as_object_mut() {
                map.remove("incertitude");
            }
            o["rectification"] = correction.clone();
        }
    }
    Ok(observations.into_values().collect())
}

/// Exact counts remain authoritative; no pseudo-observations or probability of
/// mastery is inferred. QCM reference is permitted only for a single answer.
pub fn indicator(successes: u32, count: u32, alternatives: Option<u8>) -> Result<Value> {
    require(
        count <= 1_000_000
            && successes <= count
            && alternatives.is_none_or(|m| (2..=100).contains(&m)),
        "effectif_invalide",
        400,
    )?;
    let p = if count == 0 {
        None
    } else {
        Some(f64::from(successes) / f64::from(count))
    };
    let p0 = alternatives.map(|m| 1.0 / f64::from(m));
    let (db, extreme, display) = match p {
        None => (None, None, "Non observé".to_owned()),
        Some(0.0) => (None, Some("moins_infini"), "−∞ dB".to_owned()),
        Some(1.0) => (None, Some("plus_infini"), "+∞ dB".to_owned()),
        Some(p) => {
            let reference = p0.map_or(0.0, |p| (p / (1.0 - p)).ln());
            let db = 10.0 / 10.0_f64.ln() * ((p / (1.0 - p)).ln() - reference);
            let integral = db.round_ties_even();
            let centinats = ((db - integral) * 10.0_f64.ln() / 10.0 * 100.0).round_ties_even();
            let display = if centinats == 0.0 {
                format!("{integral:.0} dB")
            } else {
                format!("{integral:.0}:{centinats:.0} dB")
            };
            (Some(db), None, display)
        }
    };
    Ok(
        json!({"reussites":successes,"effectif":count,"proportion":p,"reference_hasard":p0,"methode":"proportion brute, logit translaté, sans pseudo-observations","db":db,"extreme":extreme,"affichage":display,"pondération":"une production par observation ; aides séparées","precision":"Effectif affiché ; cet indicateur n'est pas une probabilité de maîtrise."}),
    )
}

pub(super) async fn report(store: &mut Store<'_, '_>, p: &Value) -> Result<Value> {
    let group = wire::identifier(&p["groupe"], false)?;
    let assignments = store.list(&group, "affectation").await?;
    let sessions = store.list(&group, "seance").await?;
    let students = store
        .members(&group)
        .await?
        .into_iter()
        .filter(|m| m["role"] == "eleve")
        .collect::<Vec<_>>();
    let assignments = assignments
        .into_iter()
        .filter(|a| {
            p.get("activite")
                .is_none_or(|v| a.document["activite"] == *v)
        })
        .collect::<Vec<_>>();
    require(
        assignments.len() * students.len() <= 10_000,
        "rapport_trop_large_preciser_activite",
        409,
    )?;
    let mut versions = BTreeMap::<(String, i64), Value>::new();
    let mut rows = Vec::new();
    for assignment in assignments {
        let activity = wire::identifier(&assignment.document["activite"], false)?;
        for student in &students {
            let id = wire::identifier(&student["acteur"], true)?;
            if p.get("eleve")
                .is_some_and(|v| v.as_str() != Some(id.as_str()))
            {
                continue;
            }
            if !wire::array(&assignment.document["eleves"], 500)?
                .iter()
                .any(|v| v.as_str() == Some(id.as_str()))
            {
                continue;
            }
            let session = sessions.iter().find(|s| {
                s.document["affectation"] == assignment.id
                    && s.document["eleve"].as_str() == Some(id.as_str())
            });
            let version = wire::integer(
                &session.map_or(&assignment.document, |s| &s.document)["activite_version"],
                1,
                1_000_000_000,
            )?;
            let key = (activity.clone(), version);
            if !versions.contains_key(&key) {
                versions.insert(key.clone(), store.version(&activity, version).await?);
            }
            let doc = versions
                .get(&key)
                .ok_or(ServiceError::new("schema_incompatible", 503))?;
            let observations = match session {
                Some(s) => latest(&s.document)?
                    .into_iter()
                    .filter(|o| o["activite_version"].as_i64() == Some(version))
                    .collect(),
                None => Vec::new(),
            };
            rows.push(json!({"eleve":id,"affectation":assignment.id,"activite":activity,"titre":doc["titre"],"activite_version":version,"echeance":assignment.document["echeance"],"seance":session.map(|s|s.present()),"attendus":doc["attendus"],"criteres":doc["criteres"],"observations":observations,"etat":session.map_or(json!("non_observe"),|s|s.document["etat"].clone()),"tentatives":session.map_or(json!(0),|s|s.document["total_tentatives"].clone())}));
        }
    }
    let mut groups = BTreeMap::<(String, i64, String), Vec<Option<Value>>>::new();
    for row in &rows {
        for criterion in wire::array(&row["criteres"], 64)? {
            let key = (
                wire::identifier(&row["activite"], false)?,
                wire::integer(&row["activite_version"], 1, 1_000_000_000)?,
                wire::identifier(&criterion["id"], false)?,
            );
            let found = wire::array(&row["observations"], 64)?
                .iter()
                .find(|o| o["critere"] == criterion["id"])
                .cloned();
            groups.entry(key).or_default().push(found);
        }
    }
    let mut indicators = Vec::new();
    for ((activity, version, criterion), observations) in groups {
        let defined = observations
            .iter()
            .filter_map(Option::as_ref)
            .filter(|o| {
                matches!(
                    o["etat"].as_str(),
                    Some("difficulte" | "reussite_aidee" | "reussite_autonome")
                ) && o.get("incertitude").is_none_or(Value::is_null)
            })
            .collect::<Vec<_>>();
        let assisted = defined
            .iter()
            .filter(|o| o["etat"] == "reussite_aidee")
            .count();
        let autonomous = defined
            .iter()
            .filter(|o| o["etat"] == "reussite_autonome")
            .count();
        let doc = versions
            .get(&(activity.clone(), version))
            .ok_or(ServiceError::new("schema_incompatible", 503))?;
        let alternatives = if doc["type"] == "qcm" {
            Some(wire::integer(&doc["propositions"], 2, 100)? as u8)
        } else {
            None
        };
        let mut item = indicator(
            (assisted + autonomous) as u32,
            defined.len() as u32,
            alternatives,
        )?;
        item["activite"] = json!(activity);
        item["activite_version"] = json!(version);
        item["critere"] = json!(criterion);
        item["prescrits"] = json!(observations.len());
        item["reussites_aidees"] = json!(assisted);
        item["reussites_autonomes"] = json!(autonomous);
        item["difficultes"] = json!(defined.iter().filter(|o| o["etat"] == "difficulte").count());
        item["non_observes_ou_incertains"] = json!(observations.len() - defined.len());
        item["couverture"] = json!(if observations.is_empty() {
            None
        } else {
            Some(defined.len() as f64 / observations.len() as f64)
        });
        indicators.push(item);
    }
    let mut result = wire::page(rows, p)?;
    result["methode"] = json!(
        "Dernière interprétation par séance et critère, rectifications attribuées. Versions et aides conservées ; aucune moyenne logarithmique."
    );
    result["difficultes"] = Value::Array(
        indicators
            .iter()
            .filter(|i| i["difficultes"].as_u64().is_some_and(|n| n > 0))
            .cloned()
            .collect(),
    );
    result["indicateurs"] = wire::page(indicators, p)?;
    Ok(result)
}

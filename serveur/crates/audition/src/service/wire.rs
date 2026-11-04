use super::{Result, ServiceError, require};
use serde::de::{DeserializeSeed, MapAccess, SeqAccess, Visitor};
use serde_json::{Map, Value, json};
use std::collections::BTreeMap;
use std::fmt;

pub(super) fn parse(bytes: &[u8]) -> Result<Value> {
    require(bytes.len() <= 65_536, "requete_trop_large", 413)?;
    let mut decoder = serde_json::Deserializer::from_slice(bytes);
    let value = Checked(0)
        .deserialize(&mut decoder)
        .map_err(|_| ServiceError::new("champs_invalides", 400))?;
    decoder
        .end()
        .map_err(|_| ServiceError::new("champs_invalides", 400))?;
    require(value.is_object(), "champs_invalides", 400)?;
    Ok(value)
}
struct Checked(u8);
impl<'de> DeserializeSeed<'de> for Checked {
    type Value = Value;
    fn deserialize<D: serde::Deserializer<'de>>(
        self,
        d: D,
    ) -> std::result::Result<Value, D::Error> {
        if self.0 > 32 {
            return Err(serde::de::Error::custom("depth"));
        }
        d.deserialize_any(self)
    }
}
impl<'de> Visitor<'de> for Checked {
    type Value = Value;
    fn expecting(&self, f: &mut fmt::Formatter) -> fmt::Result {
        f.write_str("bounded unambiguous JSON")
    }
    fn visit_bool<E: serde::de::Error>(self, v: bool) -> std::result::Result<Value, E> {
        Ok(Value::Bool(v))
    }
    fn visit_i64<E: serde::de::Error>(self, v: i64) -> std::result::Result<Value, E> {
        Ok(v.into())
    }
    fn visit_u64<E: serde::de::Error>(self, v: u64) -> std::result::Result<Value, E> {
        Ok(v.into())
    }
    fn visit_f64<E: serde::de::Error>(self, v: f64) -> std::result::Result<Value, E> {
        serde_json::Number::from_f64(v)
            .map(Value::Number)
            .ok_or_else(|| E::custom("number"))
    }
    fn visit_str<E: serde::de::Error>(self, v: &str) -> std::result::Result<Value, E> {
        if v.contains('\0') {
            Err(E::custom("nul"))
        } else {
            Ok(v.into())
        }
    }
    fn visit_string<E: serde::de::Error>(self, v: String) -> std::result::Result<Value, E> {
        self.visit_str(&v)
    }
    fn visit_unit<E: serde::de::Error>(self) -> std::result::Result<Value, E> {
        Ok(Value::Null)
    }
    fn visit_none<E: serde::de::Error>(self) -> std::result::Result<Value, E> {
        Ok(Value::Null)
    }
    fn visit_map<M: MapAccess<'de>>(self, mut access: M) -> std::result::Result<Value, M::Error> {
        let mut map = Map::new();
        while let Some(key) = access.next_key::<String>()? {
            if map.contains_key(&key) {
                return Err(serde::de::Error::custom("duplicate"));
            }
            map.insert(key, access.next_value_seed(Checked(self.0 + 1))?);
        }
        Ok(Value::Object(map))
    }
    fn visit_seq<S: SeqAccess<'de>>(self, mut access: S) -> std::result::Result<Value, S::Error> {
        let mut values = Vec::new();
        while let Some(value) = access.next_element_seed(Checked(self.0 + 1))? {
            values.push(value);
        }
        Ok(Value::Array(values))
    }
}
pub(super) fn fields(v: &Value, required: &[&str], optional: &[&str]) -> Result<()> {
    let map = v
        .as_object()
        .ok_or(ServiceError::new("champs_invalides", 400))?;
    require(
        required.iter().all(|k| map.contains_key(*k))
            && map
                .keys()
                .all(|k| required.contains(&k.as_str()) || optional.contains(&k.as_str())),
        "champs_invalides",
        400,
    )
}
pub(super) fn text(v: &Value, max: usize, empty: bool) -> Result<&str> {
    let s = v.as_str().ok_or(ServiceError::new("texte_invalide", 400))?;
    require(
        s.chars().count() <= max && !s.contains('\0') && (empty || !s.trim().is_empty()),
        "texte_invalide",
        400,
    )?;
    Ok(s)
}
pub(super) fn identifier(v: &Value, dot: bool) -> Result<String> {
    let s = text(v, 64, false)?;
    require(
        s.bytes()
            .all(|b| b.is_ascii_alphanumeric() || b == b'_' || b == b'-' || (dot && b == b'.')),
        "identifiant_invalide",
        400,
    )?;
    Ok(s.to_owned())
}
pub(super) fn integer(v: &Value, min: i64, max: i64) -> Result<i64> {
    v.as_i64()
        .filter(|n| *n >= min && *n <= max)
        .ok_or(ServiceError::new("entier_invalide", 400))
}
pub(super) fn array(v: &Value, max: usize) -> Result<&Vec<Value>> {
    let a = v
        .as_array()
        .ok_or(ServiceError::new("liste_invalide", 400))?;
    require(a.len() <= max, "limite_traces_atteinte", 409)?;
    Ok(a)
}
pub(super) fn canonical(v: &Value) -> Value {
    match v {
        Value::Object(m) => {
            let sorted: BTreeMap<_, _> = m.iter().map(|(k, v)| (k.clone(), canonical(v))).collect();
            Value::Object(sorted.into_iter().collect())
        }
        Value::Array(v) => Value::Array(v.iter().map(canonical).collect()),
        _ => v.clone(),
    }
}
#[derive(Clone, Copy, Eq, PartialEq)]
pub(super) enum Access {
    Read,
    Teacher,
    Student,
    Admin,
}
pub(super) struct Operation {
    pub access: Access,
    pub required: &'static [&'static str],
    pub optional: &'static [&'static str],
    pub write: bool,
}
pub(super) fn operation(name: &str) -> Result<Operation> {
    let (access, required, optional): (Access, &'static [&'static str], &'static [&'static str]) =
        match name {
            "contexte" => (Access::Read, &[], &["offset", "limite"]),
            "retrouver" => (Access::Read, &["id"], &[]),
            "creer_groupe" => (Access::Admin, &["nom", "cle"], &[]),
            "habiliter" => (Access::Admin, &["groupe", "acteur", "role", "cle"], &[]),
            "membres" => (Access::Admin, &["groupe"], &["offset", "limite"]),
            "diagnostic" => (Access::Admin, &[], &[]),
            "supprimer_groupe" => (Access::Admin, &["groupe", "confirmation", "cle"], &[]),
            "cours" | "activite" => (
                Access::Teacher,
                &["groupe", "document", "cle"],
                &["id", "revision"],
            ),
            "preparations" => (Access::Teacher, &["groupe"], &["offset", "limite"]),
            "affecter" => (
                Access::Teacher,
                &["groupe", "activite", "eleves", "echeance", "cle"],
                &["id", "revision"],
            ),
            "travaux" => (Access::Read, &["groupe"], &["offset", "limite"]),
            "ouvrir_seance" => (Access::Student, &["groupe", "affectation", "cle"], &[]),
            "consulter_seance" => (Access::Read, &["groupe", "id"], &["offset", "limite"]),
            "adopter_contexte" => (
                Access::Student,
                &["groupe", "id", "revision", "activite_version", "cle"],
                &[],
            ),
            "consigner" => (
                Access::Student,
                &[
                    "groupe",
                    "id",
                    "revision",
                    "activite_version",
                    "politique_version",
                    "production",
                    "activite_a",
                    "aides",
                    "observations",
                    "cle",
                ],
                &[],
            ),
            "transition" => (
                Access::Student,
                &["groupe", "id", "revision", "action", "cle"],
                &[],
            ),
            "rapport" => (
                Access::Teacher,
                &["groupe"],
                &["activite", "eleve", "offset", "limite"],
            ),
            "rectifier" => (
                Access::Teacher,
                &[
                    "groupe",
                    "id",
                    "revision",
                    "tentative",
                    "observation",
                    "justification",
                    "cle",
                ],
                &["points", "etat", "annotation"],
            ),
            "remediation" => (
                Access::Teacher,
                &["groupe", "activite", "eleves", "consigne", "cle"],
                &["origine", "echeance"],
            ),
            _ => return Err(ServiceError::new("operation_inconnue", 404)),
        };
    Ok(Operation {
        access,
        required,
        optional,
        write: required.contains(&"cle"),
    })
}
pub(super) fn page(values: Vec<Value>, p: &Value) -> Result<Value> {
    let offset = match p.get("offset") {
        Some(v) => integer(v, 0, 100_000)?,
        None => 0,
    } as usize;
    let limit = match p.get("limite") {
        Some(v) => integer(v, 1, 100)?,
        None => 50,
    } as usize;
    let total = values.len();
    let mut chosen = Vec::new();
    let mut bytes = 128;
    for value in values.into_iter().skip(offset).take(limit) {
        let size = value.to_string().len() + 1;
        if bytes + size > 262_000 {
            require(!chosen.is_empty(), "reponse_trop_large", 409)?;
            break;
        }
        bytes += size;
        chosen.push(value);
    }
    let end = offset + chosen.len();
    Ok(json!({"elements":chosen,"total":total,"suivant":if end<total {Some(end)}else{None}}))
}
pub(super) fn policy() -> Value {
    json!({"version":1,"attribution":"Les jugements du LLM sont rapportés, justifiés et révisables.","collecte":"Productions et aides utiles au travail affecté uniquement, jamais conversation privée ou raisonnement interne.","instructions":["Lire le contexte et les consignes prescrites avant de travailler.","Laisser répondre l'élève ; distinguer production, aides et interprétation.","Ne jamais annoncer un enregistrement sans confirmation du serveur.","Relire après conflit et réutiliser exactement la même clé après timeout."],"limites_ecriture":{"octets_requete":65536,"caracteres_production":16000,"aides_par_tentative":32,"observations_par_tentative":64,"tentatives_par_seance":128,"elements_par_page":100}})
}

use crate::Error;
use serde::{Deserialize, Deserializer, Serialize, Serializer, de, ser::SerializeMap};
use serde_json::Value;
use std::collections::{HashMap, HashSet};

/// Entier JSON exact ; accepte aussi 1.0 comme Zod/JavaScript.
#[derive(Clone, Copy, PartialEq, Eq)]
pub struct Entier<const MAX: u64>(u64);

impl<const MAX: u64> Entier<MAX> {
    pub fn value(self) -> u64 {
        self.0
    }
}

impl<'de, const MAX: u64> Deserialize<'de> for Entier<MAX> {
    fn deserialize<D: Deserializer<'de>>(d: D) -> Result<Self, D::Error> {
        let value = f64::deserialize(d)?;
        if value.is_finite() && value.fract() == 0.0 && value >= 0.0 && value <= MAX as f64 {
            Ok(Self(value as u64))
        } else {
            Err(de::Error::custom("invalid integer"))
        }
    }
}

impl<const MAX: u64> Serialize for Entier<MAX> {
    fn serialize<S: Serializer>(&self, s: S) -> Result<S::Ok, S::Error> {
        s.serialize_u64(self.0)
    }
}

#[derive(Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(try_from = "String", into = "String")]
pub struct ParticipationId(String);

impl ParticipationId {
    pub fn as_str(&self) -> &str {
        &self.0
    }
}
impl From<ParticipationId> for String {
    fn from(v: ParticipationId) -> Self {
        v.0
    }
}
impl TryFrom<String> for ParticipationId {
    type Error = &'static str;
    fn try_from(v: String) -> Result<Self, Self::Error> {
        if !uuid_syntax(&v) {
            return Err("invalid uuid");
        }
        let bytes = v.as_bytes();
        let ordinary = (b'1'..=b'8').contains(&bytes[14])
            && matches!(bytes[19].to_ascii_lowercase(), b'8' | b'9' | b'a' | b'b');
        let nil = bytes.iter().all(|b| matches!(b, b'0' | b'-'));
        let max = bytes
            .iter()
            .all(|b| matches!(b.to_ascii_lowercase(), b'f' | b'-'));
        if ordinary || nil || max {
            Ok(Self(v))
        } else {
            Err("invalid uuid")
        }
    }
}

pub fn uuid_syntax(value: &str) -> bool {
    value.len() == 36
        && value.bytes().enumerate().all(|(i, b)| {
            if matches!(i, 8 | 13 | 18 | 23) {
                b == b'-'
            } else {
                b.is_ascii_hexdigit()
            }
        })
}

/// Le secret ne possède pas Debug/Display ; il ne doit jamais devenir un log.
#[derive(Clone, Serialize, Deserialize)]
#[serde(try_from = "String", into = "String")]
pub struct ResumeSecret(String);
impl ResumeSecret {
    pub fn as_str(&self) -> &str {
        &self.0
    }
}
impl From<ResumeSecret> for String {
    fn from(v: ResumeSecret) -> Self {
        v.0
    }
}
impl TryFrom<String> for ResumeSecret {
    type Error = &'static str;
    fn try_from(v: String) -> Result<Self, Self::Error> {
        if v.len() == 64
            && v.bytes()
                .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
        {
            Ok(Self(v))
        } else {
            Err("invalid secret")
        }
    }
}

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields, rename_all = "camelCase")]
pub struct Creation {
    pub id: ParticipationId,
    pub secret: ResumeSecret,
    pub bank_version: String,
    pub levels: Vec<String>,
    pub seed: Entier<4294967295>,
}

pub fn parse_creation(value: Value) -> Result<Creation, Error> {
    let result: Creation = serde_json::from_value(value).map_err(|_| Error::InvalidInput)?;
    let parts: Vec<&str> = result.bank_version.split('.').collect();
    if parts.len() != 3
        || parts
            .iter()
            .any(|p| p.is_empty() || !p.bytes().all(|b| b.is_ascii_digit()))
        || !(1..=7).contains(&result.levels.len())
        || result.levels.iter().any(|s| s.chars().count() > 30)
    {
        return Err(Error::InvalidInput);
    }
    Ok(result)
}

#[derive(Clone, Copy, PartialEq, Serialize, Deserialize)]
#[serde(try_from = "f64", into = "f64")]
pub struct Grade(f64);
impl Grade {
    pub fn value(self) -> f64 {
        self.0
    }
}
impl From<Grade> for f64 {
    fn from(value: Grade) -> Self {
        value.0
    }
}
impl TryFrom<f64> for Grade {
    type Error = &'static str;
    fn try_from(v: f64) -> Result<Self, Self::Error> {
        if v.is_finite() && (0.0..=3.0).contains(&v) && (v * 4.0).fract() == 0.0 {
            Ok(Self(v))
        } else {
            Err("invalid grade")
        }
    }
}

#[derive(Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Coordinates {
    pub x: f64,
    pub y: f64,
    pub z: f64,
}
impl Coordinates {
    fn valid(&self) -> bool {
        [self.x, self.y, self.z]
            .into_iter()
            .all(|v| v.is_finite() && (-10.0..=10.0).contains(&v))
    }
}

#[derive(Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(try_from = "String", into = "String")]
pub enum Axis {
    X,
    Y,
    Z,
}
impl Axis {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::X => "x",
            Self::Y => "y",
            Self::Z => "z",
        }
    }
}
impl From<Axis> for String {
    fn from(v: Axis) -> Self {
        v.as_str().to_owned()
    }
}
impl TryFrom<String> for Axis {
    type Error = &'static str;
    fn try_from(v: String) -> Result<Self, Self::Error> {
        match v.as_str() {
            "x" => Ok(Self::X),
            "y" => Ok(Self::Y),
            "z" => Ok(Self::Z),
            _ => Err("invalid axis"),
        }
    }
}

fn required_grade<'de, D: Deserializer<'de>>(d: D) -> Result<Option<Grade>, D::Error> {
    Option::deserialize(d)
}
fn optional_grade<'de, D: Deserializer<'de>>(d: D) -> Result<Option<Option<Grade>>, D::Error> {
    Ok(Some(Option::deserialize(d)?))
}
fn optional_present<'de, D: Deserializer<'de>, T: Deserialize<'de>>(
    d: D,
) -> Result<Option<T>, D::Error> {
    Ok(Some(T::deserialize(d)?))
}

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields, rename_all = "camelCase")]
pub struct Answer {
    #[serde(deserialize_with = "required_grade")]
    pub note: Option<Grade>,
    #[serde(deserialize_with = "required_grade")]
    pub initial_note: Option<Grade>,
    pub coordinates: Coordinates,
    pub evaluated_axes: Vec<Axis>,
}

/// Ordre des propriétés conservé pour le hash JSON.stringify historique.
#[derive(Clone)]
pub struct OrderedMap<T>(pub Vec<(String, T)>);
impl<T: Serialize> Serialize for OrderedMap<T> {
    fn serialize<S: Serializer>(&self, s: S) -> Result<S::Ok, S::Error> {
        let mut map = s.serialize_map(Some(self.0.len()))?;
        for (key, value) in &self.0 {
            map.serialize_entry(key, value)?;
        }
        map.end()
    }
}
impl<'de, T: Deserialize<'de>> Deserialize<'de> for OrderedMap<T> {
    fn deserialize<D: Deserializer<'de>>(d: D) -> Result<Self, D::Error> {
        struct Visitor<T>(std::marker::PhantomData<T>);
        impl<'de, T: Deserialize<'de>> de::Visitor<'de> for Visitor<T> {
            type Value = OrderedMap<T>;
            fn expecting(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
                f.write_str("an object")
            }
            fn visit_map<M: de::MapAccess<'de>>(self, mut map: M) -> Result<Self::Value, M::Error> {
                let mut values = Vec::new();
                let mut keys = HashSet::new();
                while let Some((key, value)) = map.next_entry::<String, T>()? {
                    if !keys.insert(key.clone()) {
                        return Err(de::Error::custom("duplicate key"));
                    }
                    values.push((key, value));
                }
                Ok(OrderedMap(values))
            }
        }
        d.deserialize_map(Visitor(std::marker::PhantomData))
    }
}

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Progress {
    pub mode: String,
    pub index: Entier<19>,
    pub selected: String,
    pub exposed: OrderedMap<Entier<100>>,
    pub reader: bool,
    pub tour: f64,
}

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields, rename_all = "camelCase")]
pub struct Snapshot {
    pub answers: OrderedMap<Answer>,
    pub skipped_questions: Vec<String>,
    pub progress: Progress,
}

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields, rename_all = "camelCase")]
pub struct Event {
    pub event: String,
    pub question_id: String,
    pub production_id: String,
    pub at: String,
    pub elapsed_ms: Entier<31536000000>,
    #[serde(
        default,
        deserialize_with = "optional_grade",
        skip_serializing_if = "Option::is_none"
    )]
    pub value: Option<Option<Grade>>,
    #[serde(
        default,
        deserialize_with = "optional_present",
        skip_serializing_if = "Option::is_none"
    )]
    pub initial: Option<bool>,
    #[serde(
        default,
        deserialize_with = "optional_present",
        skip_serializing_if = "Option::is_none"
    )]
    pub axis: Option<Axis>,
    #[serde(
        default,
        deserialize_with = "optional_present",
        skip_serializing_if = "Option::is_none"
    )]
    pub coordinates: Option<Coordinates>,
    #[serde(
        default,
        deserialize_with = "optional_present",
        skip_serializing_if = "Option::is_none"
    )]
    pub source: Option<String>,
}

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Checkpoint {
    pub revision: Entier<2147483647>,
    #[serde(rename = "final")]
    pub is_final: bool,
    pub snapshot: Snapshot,
    pub events: Vec<Event>,
}

pub fn parse_checkpoint(value: Value) -> Result<Checkpoint, Error> {
    let result: Checkpoint = serde_json::from_value(value).map_err(|_| Error::InvalidInput)?;
    let p = &result.snapshot.progress;
    if result.revision.value() == 0
        || result.events.len() > 20_000
        || result.snapshot.skipped_questions.len() > 20
        || !matches!(p.mode.as_str(), "training" | "running" | "finished")
        || p.selected.chars().count() > 40
        || !p.tour.is_finite()
        || p.tour.fract() != 0.0
        || !(-1.0..=7.0).contains(&p.tour)
        || p.exposed
            .0
            .iter()
            .any(|(key, count)| key.chars().count() > 40 || count.value() == 0)
        || result
            .snapshot
            .skipped_questions
            .iter()
            .any(|id| !production_id(id))
    {
        return Err(Error::InvalidInput);
    }
    for (id, answer) in &result.snapshot.answers.0 {
        if !production_id(id)
            || !answer.coordinates.valid()
            || answer.evaluated_axes.len() > 3
            || answer.evaluated_axes.iter().collect::<HashSet<_>>().len()
                != answer.evaluated_axes.len()
        {
            return Err(Error::InvalidInput);
        }
    }
    for event in &result.events {
        if !matches!(
            event.event.as_str(),
            "grade"
                | "place"
                | "question"
                | "skip"
                | "finish"
                | "close"
                | "open"
                | "reveal"
                | "confirm-position"
                | "compare"
                | "orbit"
        ) || !production_id(&event.question_id)
            || !production_id(&event.production_id)
            || !utc_date(&event.at)
            || event.coordinates.as_ref().is_some_and(|c| !c.valid())
            || event
                .source
                .as_ref()
                .is_some_and(|v| v != "next-production")
        {
            return Err(Error::InvalidInput);
        }
    }
    Ok(result)
}

pub fn production_id(value: &str) -> bool {
    let b = value.as_bytes();
    b.len() >= 3
        && b[0] == b'R'
        && b[1..3].iter().all(u8::is_ascii_digit)
        && (b.len() == 3 || b.len() > 4 && b[3] == b'-' && b[4..].iter().all(u8::is_ascii_digit))
}

pub fn utc_date(value: &str) -> bool {
    let b = value.as_bytes();
    if b.len() < 20 || b.last() != Some(&b'Z') {
        return false;
    }
    if b[4] != b'-' || b[7] != b'-' || b[10] != b'T' || b[13] != b':' || b[16] != b':' {
        return false;
    }
    let read = |start: usize, end: usize| -> Option<u32> {
        let mut n = 0;
        for byte in &b[start..end] {
            if !byte.is_ascii_digit() {
                return None;
            }
            n = n * 10 + u32::from(byte - b'0');
        }
        Some(n)
    };
    let (Some(year), Some(month), Some(day), Some(hour), Some(minute), Some(second)) = (
        read(0, 4),
        read(5, 7),
        read(8, 10),
        read(11, 13),
        read(14, 16),
        read(17, 19),
    ) else {
        return false;
    };
    let leap = year % 4 == 0 && (year % 100 != 0 || year % 400 == 0);
    let days = match month {
        1 | 3 | 5 | 7 | 8 | 10 | 12 => 31,
        4 | 6 | 9 | 11 => 30,
        2 => {
            if leap {
                29
            } else {
                28
            }
        }
        _ => return false,
    };
    (1..=days).contains(&day)
        && hour < 24
        && minute < 60
        && second < 60
        && (b.len() == 20
            || b.len() > 21 && b[19] == b'.' && b[20..b.len() - 1].iter().all(u8::is_ascii_digit))
}

#[derive(Clone, Serialize, Deserialize)]
pub struct Production {
    pub id: String,
    pub content: String,
}

#[derive(Clone, Serialize, Deserialize)]
pub struct Question {
    pub id: String,
    pub family: String,
    pub level: String,
    pub domain: String,
    pub statement: String,
    pub productions: Vec<Production>,
}

#[derive(Clone, Serialize, Deserialize)]
pub struct Bank {
    pub version: String,
    pub questions: Vec<Question>,
}

impl Bank {
    pub fn validate(&self) -> Result<(), Error> {
        let mut questions = HashSet::new();
        let mut productions = HashSet::new();
        for q in &self.questions {
            if !production_id(&q.id) || !questions.insert(&q.id) || q.productions.is_empty() {
                return Err(Error::InvalidBank);
            }
            for p in &q.productions {
                if !production_id(&p.id) || !productions.insert(&p.id) {
                    return Err(Error::InvalidBank);
                }
            }
        }
        Ok(())
    }
}

pub fn validate_links(
    data: &Checkpoint,
    order: &[String],
    bank: &Bank,
) -> Result<HashMap<String, String>, Error> {
    let questions: HashMap<&str, &Question> = bank
        .questions
        .iter()
        .filter(|q| order.contains(&q.id))
        .map(|q| (q.id.as_str(), q))
        .collect();
    let productions: HashMap<String, String> = questions
        .values()
        .flat_map(|q| q.productions.iter().map(|p| (p.id.clone(), q.id.clone())))
        .collect();
    if data.snapshot.answers.0.iter().any(|(id, a)| {
        !productions.contains_key(id) || (a.note.is_none() && a.initial_note.is_some())
    }) || data
        .snapshot
        .skipped_questions
        .iter()
        .collect::<HashSet<_>>()
        .len()
        != data.snapshot.skipped_questions.len()
        || data
            .snapshot
            .skipped_questions
            .iter()
            .any(|q| !questions.contains_key(q.as_str()))
    {
        return Err(Error::InvalidInput);
    }
    let progress = &data.snapshot.progress;
    let index = usize::try_from(progress.index.value()).map_err(|_| Error::InvalidInput)?;
    let current = order.get(index).ok_or(Error::InvalidInput)?;
    for (id, n) in &progress.exposed.0 {
        if id == "practice" && n.value() == 1 {
            continue;
        }
        let q = questions.get(id.as_str()).ok_or(Error::InvalidInput)?;
        if n.value() > q.productions.len() as u64 {
            return Err(Error::InvalidInput);
        }
    }
    if progress.mode != "training" && productions.get(&progress.selected) != Some(current)
        || data.is_final && progress.mode != "finished"
        || data.events.iter().any(|e| {
            !questions.contains_key(e.question_id.as_str())
                || productions.get(&e.production_id) != Some(&e.question_id)
        })
        || data
            .events
            .windows(2)
            .any(|w| w[1].elapsed_ms.value() < w[0].elapsed_ms.value())
    {
        return Err(Error::InvalidInput);
    }
    Ok(productions)
}

use crate::{LogError, Result};
use serde::de::{DeserializeSeed, MapAccess, SeqAccess, Visitor};
use serde_json::{Map, Value};
use std::fmt;

pub(super) fn parse(bytes: &[u8]) -> Result<Value> {
    let mut decoder = serde_json::Deserializer::from_slice(bytes);
    let value = Checked(0)
        .deserialize(&mut decoder)
        .map_err(|_| LogError::new("json_invalide", 400))?;
    decoder
        .end()
        .map_err(|_| LogError::new("json_invalide", 400))?;
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

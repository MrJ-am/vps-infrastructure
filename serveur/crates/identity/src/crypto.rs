use crate::{
    error::{Error, Result, require},
    json,
};
use base64::{Engine, engine::general_purpose::URL_SAFE_NO_PAD};
use ring::{
    digest,
    rand::{SecureRandom, SystemRandom},
    signature,
};
use serde_json::Value;
use std::collections::BTreeSet;
use subtle::ConstantTimeEq;

pub fn text(value: &str, min: usize, max: usize) -> bool {
    value.len() >= min && value.len() <= max && !value.chars().any(char::is_control)
}
pub fn secret(value: &str) -> bool {
    value.len() == 43
        && value
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'_' | b'-'))
}
pub fn random() -> Result<String> {
    let mut bytes = [0u8; 32];
    SystemRandom::new()
        .fill(&mut bytes)
        .map_err(|_| Error(503))?;
    Ok(URL_SAFE_NO_PAD.encode(bytes))
}
pub fn sha(value: &[u8]) -> Vec<u8> {
    digest::digest(&digest::SHA256, value).as_ref().to_vec()
}
pub fn hash(value: &str) -> String {
    sha(value.as_bytes())
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect()
}
pub fn challenge(value: &str) -> String {
    URL_SAFE_NO_PAD.encode(sha(value.as_bytes()))
}
pub fn same(a: &str, b: &str) -> bool {
    bool::from(a.as_bytes().ct_eq(b.as_bytes()))
}
fn decode(value: &str, max: usize) -> Result<Vec<u8>> {
    require(!value.is_empty() && value.len() <= max, 401)?;
    let result = URL_SAFE_NO_PAD.decode(value).map_err(|_| Error(401))?;
    require(URL_SAFE_NO_PAD.encode(&result) == value, 401)?;
    Ok(result)
}
fn string<'a>(value: &'a Value, key: &str, max: usize) -> Result<&'a str> {
    value
        .get(key)
        .and_then(Value::as_str)
        .filter(|s| text(s, 1, max))
        .ok_or(Error(401))
}
fn integer(value: &Value, key: &str) -> Result<i64> {
    value
        .get(key)
        .and_then(Value::as_i64)
        .filter(|n| *n >= 0 && *n <= 9_007_199_254_740_991)
        .ok_or(Error(401))
}
pub fn issuer(client: &str) -> String {
    format!("https://log.mrj.am/oauth2/openid/{client}")
}
pub struct Identity {
    pub issuer: String,
    pub subject: String,
    pub auth_time: Option<i64>,
}

/// ES256 only, against the key set obtained through the fixed authenticated TLS transport.
pub fn verify(
    token: &str,
    jwks: &Value,
    client: &str,
    nonce: &str,
    access: &str,
    now: i64,
) -> Result<Identity> {
    require(
        text(token, 1, 16384) && text(nonce, 16, 256) && text(access, 1, 16384),
        401,
    )?;
    let parts = token.split('.').collect::<Vec<_>>();
    require(parts.len() == 3, 401)?;
    let head = json::object(&decode(parts[0], 2048)?, 2048).map_err(|_| Error(401))?;
    let object = head.as_object().ok_or(Error(401))?;
    require(
        object
            .keys()
            .all(|k| matches!(k.as_str(), "alg" | "kid" | "typ"))
            && head["alg"] == "ES256"
            && (head.get("typ").is_none() || head["typ"] == "JWT"),
        401,
    )?;
    let kid = string(&head, "kid", 256)?;
    let keys = jwks
        .get("keys")
        .and_then(Value::as_array)
        .filter(|k| !k.is_empty() && k.len() <= 32)
        .ok_or(Error(401))?;
    require(keys.iter().all(Value::is_object), 401)?;
    let matched = keys
        .iter()
        .filter(|k| k.get("kid").and_then(Value::as_str) == Some(kid))
        .collect::<Vec<_>>();
    require(matched.len() == 1, 401)?;
    let key = matched[0];
    require(
        key["kty"] == "EC"
            && key["crv"] == "P-256"
            && key.get("d").is_none()
            && (key.get("alg").is_none() || key["alg"] == "ES256")
            && (key.get("use").is_none() || key["use"] == "sig")
            && (key.get("key_ops").is_none() || key["key_ops"] == serde_json::json!(["verify"])),
        401,
    )?;
    let x = decode(string(key, "x", 43)?, 43)?;
    let y = decode(string(key, "y", 43)?, 43)?;
    require(x.len() == 32 && y.len() == 32, 401)?;
    let mut public = vec![4];
    public.extend(x);
    public.extend(y);
    let sig = decode(parts[2], 86)?;
    require(sig.len() == 64, 401)?;
    signature::UnparsedPublicKey::new(&signature::ECDSA_P256_SHA256_FIXED, public)
        .verify(format!("{}.{}", parts[0], parts[1]).as_bytes(), &sig)
        .map_err(|_| Error(401))?;
    let claims = json::object(&decode(parts[1], 12288)?, 12288).map_err(|_| Error(401))?;
    let iss = string(&claims, "iss", 256)?;
    require(iss == issuer(client), 401)?;
    let subject = string(&claims, "sub", 128)?;
    let audiences = match claims.get("aud") {
        Some(Value::String(s)) => vec![s.as_str()],
        Some(Value::Array(a)) if !a.is_empty() && a.len() <= 16 => a
            .iter()
            .map(|v| v.as_str().ok_or(Error(401)))
            .collect::<Result<Vec<_>>>()?,
        _ => return Err(Error(401)),
    };
    let unique = audiences.iter().copied().collect::<BTreeSet<_>>();
    require(
        audiences.iter().all(|s| text(s, 1, 128))
            && unique.len() == audiences.len()
            && unique.contains(client)
            && (audiences.len() == 1 || claims["azp"] == client)
            && (claims.get("azp").is_none() || claims["azp"] == client),
        401,
    )?;
    let exp = integer(&claims, "exp")?;
    let iat = integer(&claims, "iat")?;
    require(exp > now - 30 && exp > iat && iat <= now + 30, 401)?;
    if claims.get("nbf").is_some() {
        require(integer(&claims, "nbf")? <= now + 30, 401)?;
    }
    require(same(string(&claims, "nonce", 256)?, nonce), 401)?;
    let auth_time = if claims.get("auth_time").is_some() {
        let auth = integer(&claims, "auth_time")?;
        require(auth <= now + 30 && auth <= iat + 30, 401)?;
        Some(auth)
    } else {
        None
    };
    if claims.get("at_hash").is_some() {
        let hash = sha(access.as_bytes());
        require(
            same(
                string(&claims, "at_hash", 64)?,
                &URL_SAFE_NO_PAD.encode(&hash[..16]),
            ),
            401,
        )?;
    }
    Ok(Identity {
        issuer: iss.into(),
        subject: subject.into(),
        auth_time,
    })
}

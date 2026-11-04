//! Exact manifested assets; requests never select filesystem paths.
use crate::{runtime_config::AssetConfiguration, runtime_files};
use axum::{
    body::Body,
    extract::Request,
    http::{StatusCode, header},
    response::{IntoResponse, Response},
};
use serde::Deserialize;
use std::{collections::BTreeMap, sync::Arc};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Manifest {
    schema_version: u32,
    artifact: String,
    source_commits: BTreeMap<String, String>,
    style_revision: String,
    input_manifest_sha256: String,
    toolchains_lock_sha256: String,
    payload_sha256: BTreeMap<String, String>,
    deployment_authorized: bool,
    runtime_qualification: String,
}

#[derive(Clone)]
struct Asset {
    bytes: axum::body::Bytes,
    content_type: &'static str,
}

#[derive(Clone)]
pub struct StaticAssets {
    host: String,
    mount: String,
    files: Arc<BTreeMap<String, Asset>>,
}

pub(crate) fn relative_name(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 512
        && value
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b"/._-".contains(&b))
        && value
            .split('/')
            .all(|part| !part.is_empty() && part != "." && part != "..")
}

fn content_type(name: &str) -> Option<&'static str> {
    // These two public distribution files are present in the pinned Elm sites.
    // The manifest still selects every served byte; other extensionless names
    // and dotfiles remain unsupported.
    if matches!(name.rsplit('/').next(), Some("LICENSE" | ".nojekyll")) {
        return Some("text/plain; charset=utf-8");
    }
    match name.rsplit('.').next()? {
        "html" => Some("text/html; charset=utf-8"),
        "js" | "mjs" => Some("text/javascript; charset=utf-8"),
        "css" => Some("text/css; charset=utf-8"),
        "json" => Some("application/json"),
        "txt" | "md" => Some("text/plain; charset=utf-8"),
        "svg" => Some("image/svg+xml"),
        "png" => Some("image/png"),
        "jpg" | "jpeg" => Some("image/jpeg"),
        "webp" => Some("image/webp"),
        "ico" => Some("image/x-icon"),
        "woff" => Some("font/woff"),
        "woff2" => Some("font/woff2"),
        "ttf" => Some("font/ttf"),
        "otf" => Some("font/otf"),
        _ => None,
    }
}

impl StaticAssets {
    pub(crate) fn file(&self, host: &str, mount: &str, name: &str) -> Option<&[u8]> {
        if self.host != host || self.mount != mount {
            return None;
        }
        self.files.get(name).map(|asset| asset.bytes.as_ref())
    }
    pub(crate) fn includes(&self, host: &str, mount: &str, names: &[&str]) -> bool {
        self.host == host
            && self.mount == mount
            && names.iter().all(|name| self.files.contains_key(*name))
    }
    pub fn bytes(&self) -> usize {
        self.files.values().map(|asset| asset.bytes.len()).sum()
    }
    pub fn load(config: &AssetConfiguration) -> Result<Self, &'static str> {
        let bytes =
            runtime_files::read_regular(&config.directory.join("artifact.json"), 524_288, false)?;
        if runtime_files::digest(&bytes) != config.manifest_sha256 {
            return Err("ASSET_MANIFEST_MISMATCH");
        }
        let unique: crate::strict_json::SansDoublons =
            serde_json::from_slice(&bytes).map_err(|_| "INVALID_ASSET_MANIFEST")?;
        let manifest: Manifest =
            serde_json::from_value(unique.0).map_err(|_| "INVALID_ASSET_MANIFEST")?;
        if manifest.schema_version != 1
            || manifest.payload_sha256.is_empty()
            || manifest.payload_sha256.len() > 2048
            || manifest.source_commits.is_empty()
            || manifest
                .source_commits
                .values()
                .any(|sha| sha.len() != 40 || !sha.bytes().all(|b| b.is_ascii_hexdigit()))
            || !crate::runtime_config::sha256(&manifest.input_manifest_sha256)
            || !crate::runtime_config::sha256(&manifest.toolchains_lock_sha256)
            || manifest.style_revision.len() != 40
            || manifest.artifact.is_empty()
            || manifest.runtime_qualification.is_empty()
        {
            return Err("INVALID_ASSET_MANIFEST");
        }
        // A build's deployment_authorized field never grants runtime authority.
        let _build_authorization_is_not_runtime_authorization = manifest.deployment_authorized;
        let mut files = BTreeMap::new();
        let mut total = 0usize;
        for (name, expected) in manifest.payload_sha256 {
            if !relative_name(&name) || !crate::runtime_config::sha256(&expected) {
                return Err("INVALID_ASSET_MANIFEST");
            }
            let relative = name
                .strip_prefix(&config.payload_prefix)
                .ok_or("ASSET_PREFIX_MISMATCH")?;
            if !relative_name(relative) {
                return Err("INVALID_ASSET_MANIFEST");
            }
            let mime = content_type(relative).ok_or("UNSUPPORTED_ASSET_TYPE")?;
            let bytes = runtime_files::read_regular(
                &config.directory.join(&name),
                16 * 1024 * 1024,
                false,
            )?;
            total = total
                .checked_add(bytes.len())
                .ok_or("ASSET_BUDGET_EXCEEDED")?;
            if total > 64 * 1024 * 1024 {
                return Err("ASSET_BUDGET_EXCEEDED");
            }
            if runtime_files::digest(&bytes) != expected {
                return Err("ASSET_CONTENT_MISMATCH");
            }
            files.insert(
                relative.to_owned(),
                Asset {
                    bytes: bytes.into(),
                    content_type: mime,
                },
            );
        }
        if !files.contains_key("index.html") {
            return Err("ASSET_ENTRYPOINT_MISSING");
        }
        Ok(Self {
            host: config.host.clone(),
            mount: config.mount.clone(),
            files: Arc::new(files),
        })
    }

    pub fn response(&self, host: &str, request: &Request) -> Option<Response> {
        if host != self.host {
            return None;
        }
        let path = request.uri().path();
        if self.mount != "/" && path == self.mount.trim_end_matches('/') {
            if request.method() != axum::http::Method::GET
                && request.method() != axum::http::Method::HEAD
            {
                return Some(crate::error_response(
                    StatusCode::METHOD_NOT_ALLOWED,
                    "METHOD_NOT_ALLOWED",
                ));
            }
            let mut response = StatusCode::PERMANENT_REDIRECT.into_response();
            if let Ok(location) = header::HeaderValue::from_str(&self.mount) {
                response.headers_mut().insert(header::LOCATION, location);
            }
            return Some(response);
        }
        let relative = path.strip_prefix(&self.mount)?;
        // These public entry routes are consumed by Vision's unchanged Elm
        // application (Informations.elm, Main.elm and pont.js). Do not make
        // arbitrary paths, API calls or another host fall back to index.html.
        let vision_entry = self.host == "vision.mrj.am"
            && self.mount == "/"
            && matches!(
                relative,
                "connexion" | "docs" | "docs/" | "privacy" | "admission" | "invitation"
            );
        let name = if vision_entry {
            "index.html".to_owned()
        } else if relative.is_empty() || relative.ends_with('/') {
            format!("{relative}index.html")
        } else {
            relative.to_owned()
        };
        // No URL decoding or path normalization; only exact manifest keys and
        // the closed Vision entry routes above exist.
        let asset = self.files.get(&name)?;
        if request.method() != axum::http::Method::GET
            && request.method() != axum::http::Method::HEAD
        {
            return Some(crate::error_response(
                StatusCode::METHOD_NOT_ALLOWED,
                "METHOD_NOT_ALLOWED",
            ));
        }
        let mut response = if request.method() == axum::http::Method::HEAD {
            Body::empty()
        } else {
            Body::from(asset.bytes.clone())
        }
        .into_response();
        response.headers_mut().insert(
            header::CONTENT_TYPE,
            header::HeaderValue::from_static(asset.content_type),
        );
        if let Ok(length) = header::HeaderValue::from_str(&asset.bytes.len().to_string()) {
            response
                .headers_mut()
                .insert(header::CONTENT_LENGTH, length);
        }
        response.headers_mut().insert(
            header::REFERRER_POLICY,
            header::HeaderValue::from_static("no-referrer"),
        );
        Some(response)
    }
}

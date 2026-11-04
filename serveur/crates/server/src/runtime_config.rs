//! Closed runtime configuration: references, never inline credentials or SQL.
use serde::Deserialize;
use std::{collections::BTreeSet, net::SocketAddr, path::PathBuf};

#[derive(Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RuntimeConfiguration {
    pub schema_version: u32,
    pub public_hosts: Vec<String>,
    pub required_capabilities: Vec<String>,
    pub assets: Vec<AssetConfiguration>,
    pub mateval: Option<MatevalConfiguration>,
    pub identity: Option<IdentityConfiguration>,
    pub vision: Option<VisionConfiguration>,
    pub audition: Option<DatabaseConfiguration>,
    pub log: Option<LogConfiguration>,
}

#[derive(Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct LogConfiguration {
    pub endpoint: SocketAddr,
    pub ca_file: PathBuf,
    pub ca_sha256: String,
    pub aliases_database_file: PathBuf,
}

#[derive(Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct AssetConfiguration {
    pub host: String,
    pub payload_prefix: String,
    pub directory: PathBuf,
    pub manifest_sha256: String,
    pub mount: String,
}

#[derive(Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct MatevalConfiguration {
    pub database: DatabaseConfiguration,
    pub administration_database: Option<DatabaseConfiguration>,
    pub activation_sha256_file: Option<PathBuf>,
}

#[derive(Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct IdentityConfiguration {
    pub endpoint: SocketAddr,
    pub protocol: String,
}

#[derive(Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct VisionConfiguration {
    pub database: DatabaseConfiguration,
    pub public_mcp_url: String,
    pub public_web_url: String,
    pub embeddings: Option<EmbeddingConfiguration>,
    pub deletion_journal: Option<DatabaseConfiguration>,
    pub administration_database: Option<DatabaseConfiguration>,
    pub admission_approval_credential_file: Option<PathBuf>,
}

#[derive(Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct EmbeddingConfiguration {
    pub endpoint: SocketAddr,
    pub model: String,
    pub dimensions: usize,
}

#[derive(Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct DatabaseConfiguration {
    pub transport: DatabaseTransport,
    pub database: String,
    pub username: String,
    pub password_file: Option<PathBuf>,
    pub schema: String,
    pub maximum_connections: u32,
}

#[derive(Clone, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum DatabaseTransport {
    Tcp { port: u16 },
    Unix { directory: PathBuf },
}

pub(crate) fn identifier(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 63
        && value
            .bytes()
            .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'_')
        && value.as_bytes()[0].is_ascii_lowercase()
}

pub(crate) fn host(value: &str) -> bool {
    value.len() <= 253
        && value.split('.').all(|part| {
            !part.is_empty()
                && part.len() <= 63
                && !part.starts_with('-')
                && !part.ends_with('-')
                && part
                    .bytes()
                    .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'-')
        })
}

pub(crate) fn sha256(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}

impl DatabaseConfiguration {
    fn validate(&self) -> Result<(), &'static str> {
        if !identifier(&self.database)
            || !identifier(&self.username)
            || !identifier(&self.schema)
            || self.schema.starts_with("pg_")
            || !(1..=8).contains(&self.maximum_connections)
            || self
                .password_file
                .as_ref()
                .is_some_and(|path| !path.is_absolute())
        {
            return Err("INVALID_DATABASE_CONFIGURATION");
        }
        match &self.transport {
            DatabaseTransport::Tcp { port } if *port == 0 || self.password_file.is_none() => {
                Err("INVALID_DATABASE_CONFIGURATION")
            }
            DatabaseTransport::Unix { directory } if !directory.is_absolute() => {
                Err("INVALID_DATABASE_CONFIGURATION")
            }
            _ => Ok(()),
        }
    }
}

impl RuntimeConfiguration {
    pub fn from_bytes(bytes: &[u8]) -> Result<Self, &'static str> {
        if bytes.is_empty() || bytes.len() > 65_536 {
            return Err("INVALID_RUNTIME_CONFIGURATION");
        }
        // Reject duplicate keys at every depth before typed conversion.
        let unique: crate::strict_json::SansDoublons =
            serde_json::from_slice(bytes).map_err(|_| "INVALID_RUNTIME_CONFIGURATION")?;
        let value: Self =
            serde_json::from_value(unique.0).map_err(|_| "INVALID_RUNTIME_CONFIGURATION")?;
        value.validate()?;
        Ok(value)
    }

    pub fn validate(&self) -> Result<(), &'static str> {
        if self.schema_version != 1
            || self.public_hosts.is_empty()
            || self.public_hosts.len() > 8
            || self.public_hosts.iter().any(|value| !host(value))
            || self.public_hosts.iter().collect::<BTreeSet<_>>().len() != self.public_hosts.len()
            || self.assets.is_empty()
            || self.assets.len() > 8
            || self.assets.iter().any(|asset| {
                !self.public_hosts.contains(&asset.host)
                    || !asset.directory.is_absolute()
                    || !sha256(&asset.manifest_sha256)
                    || !matches!(asset.mount.as_str(), "/" | "/matheval/")
                    || (!asset.payload_prefix.is_empty()
                        && (!asset.payload_prefix.ends_with('/')
                            || !crate::static_assets::relative_name(
                                asset.payload_prefix.trim_end_matches('/'),
                            )))
            })
            || self
                .assets
                .iter()
                .map(|asset| (&asset.host, &asset.mount))
                .collect::<BTreeSet<_>>()
                .len()
                != self.assets.len()
            || self.required_capabilities.is_empty()
            || self
                .required_capabilities
                .iter()
                .collect::<BTreeSet<_>>()
                .len()
                != self.required_capabilities.len()
            || self.required_capabilities.iter().any(|value| {
                !matches!(
                    value.as_str(),
                    "mateval-collection"
                        | "mateval-administration"
                        | "vision-http"
                        | "audition-http"
                        | "audition-mcp"
                        | "static-assets"
                        | "vision-mcp"
                        | "vision-administration"
                        | "vision-account-deletion"
                        | "log-presentation"
                )
            })
        {
            return Err("INVALID_RUNTIME_CONFIGURATION");
        }
        if let Some(mateval) = &self.mateval {
            mateval.database.validate()?;
            if !self
                .public_hosts
                .iter()
                .any(|host| host == "principiipetit.io")
            {
                return Err("INVALID_MATEVAL_CONFIGURATION");
            }
            if let Some(admin) = &mateval.administration_database {
                admin.validate()?;
                if admin.username == mateval.database.username
                    || admin.database != mateval.database.database
                    || admin.schema != mateval.database.schema
                {
                    return Err("SEPARATE_ADMINISTRATION_ROLE_REQUIRED");
                }
            }
            if mateval
                .activation_sha256_file
                .as_ref()
                .is_some_and(|path| !path.is_absolute())
            {
                return Err("INVALID_RUNTIME_CONFIGURATION");
            }
        }
        if let Some(identity) = &self.identity
            && (!identity.endpoint.ip().is_loopback()
                || identity.endpoint.port() == 0
                || identity.protocol != "mrj-auth-v1")
        {
            return Err("INVALID_IDENTITY_CONFIGURATION");
        }
        if let Some(vision) = &self.vision {
            vision.database.validate()?;
            if self.identity.is_none()
                || !self.public_hosts.iter().any(|host| host == "vision.mrj.am")
                || vision.database.schema != "public"
                || vision.public_mcp_url != "https://vision.mrj.am/mcp"
                || vision.public_web_url != "https://vision.mrj.am"
            {
                return Err("INVALID_VISION_CONFIGURATION");
            }
            if let Some(embedding) = &vision.embeddings
                && (!embedding.endpoint.ip().is_loopback()
                    || embedding.endpoint.port() == 0
                    || !(1..=4096).contains(&embedding.dimensions)
                    || embedding.model.is_empty()
                    || embedding.model.len() > 250
                    || embedding.model.chars().any(char::is_control))
            {
                return Err("INVALID_EMBEDDING_CONFIGURATION");
            }
            if let Some(journal) = &vision.deletion_journal {
                journal.validate()?;
                if journal.database == vision.database.database
                    || journal.username == vision.database.username
                {
                    return Err("SEPARATE_DELETION_JOURNAL_REQUIRED");
                }
            }
            if let Some(admin) = &vision.administration_database {
                admin.validate()?;
                if admin.username == vision.database.username
                    || admin.database != vision.database.database
                {
                    return Err("SEPARATE_ADMINISTRATION_ROLE_REQUIRED");
                }
            }
            if vision
                .admission_approval_credential_file
                .as_ref()
                .is_some_and(|path| !path.is_absolute() || vision.administration_database.is_none())
            {
                return Err("INVALID_ADMISSION_APPROVAL_CONFIGURATION");
            }
        }
        if let Some(audition) = &self.audition {
            audition.validate()?;
            if self.identity.is_none()
                || !self
                    .public_hosts
                    .iter()
                    .any(|host| host == "audition.mrj.am")
                || audition.schema != "audition"
            {
                return Err("IDENTITY_REQUIRED");
            }
        }
        if let Some(log) = &self.log
            && (!log.endpoint.ip().is_loopback()
                || log.endpoint.port() == 0
                || !log.ca_file.is_absolute()
                || !sha256(&log.ca_sha256)
                || !log.aliases_database_file.is_absolute()
                || !self.public_hosts.iter().any(|host| host == "log.mrj.am"))
        {
            return Err("INVALID_LOG_CONFIGURATION");
        }
        for capability in &self.required_capabilities {
            let configured = match capability.as_str() {
                "static-assets" => true,
                "mateval-collection" => self.mateval.is_some(),
                "mateval-administration" => self
                    .mateval
                    .as_ref()
                    .is_some_and(|m| m.administration_database.is_some()),
                "vision-http" => self.vision.as_ref().is_some_and(|v| v.embeddings.is_some()),
                "audition-http" | "audition-mcp" => self.audition.is_some(),
                "vision-mcp" => self.vision.as_ref().is_some_and(|v| v.embeddings.is_some()),
                "vision-administration" => self
                    .vision
                    .as_ref()
                    .is_some_and(|v| v.administration_database.is_some()),
                "log-presentation" => self.log.is_some(),
                // Durable local intent alone does not establish the external
                // archive/replay prerequisite. This capability cannot be
                // declared ready until that independently qualified adapter exists.
                "vision-account-deletion" => false,
                _ => false,
            };
            if !configured {
                return Err("REQUIRED_CAPABILITY_MISSING");
            }
            let mount = match capability.as_str() {
                "mateval-collection" | "mateval-administration" => {
                    Some(("principiipetit.io", "/matheval/"))
                }
                "vision-http" | "vision-administration" => Some(("vision.mrj.am", "/")),
                "audition-http" => Some(("audition.mrj.am", "/")),
                "log-presentation" => Some(("log.mrj.am", "/")),
                _ => None,
            };
            if mount.is_some_and(|(host, mount)| {
                !self
                    .assets
                    .iter()
                    .any(|asset| asset.host == host && asset.mount == mount)
            }) {
                return Err("REQUIRED_ASSET_MOUNT_MISSING");
            }
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::RuntimeConfiguration;
    use serde_json::json;

    fn candidate() -> serde_json::Value {
        json!({"schema_version":1,"public_hosts":["synthetic.invalid"], "required_capabilities":["static-assets"],
            "assets":[{"host":"synthetic.invalid","payload_prefix":"", "directory":"/synthetic/assets","manifest_sha256":"0".repeat(64),"mount":"/"}],
            "mateval":null,"identity":null,"vision":null,"audition":null})
    }

    #[test]
    fn unknown_fields_duplicates_missing_capabilities_and_identity_targets_are_closed()
    -> Result<(), Box<dyn std::error::Error>> {
        let bytes = serde_json::to_vec(&candidate())?;
        assert!(RuntimeConfiguration::from_bytes(&bytes).is_ok());
        let mut value = candidate();
        value["inline_password"] = json!("SYNTHETIC_MARKER");
        assert!(RuntimeConfiguration::from_bytes(&serde_json::to_vec(&value)?).is_err());
        let duplicate = String::from_utf8(bytes)?.replacen("{", "{\"schema_version\":1,", 1);
        assert!(RuntimeConfiguration::from_bytes(duplicate.as_bytes()).is_err());
        for capability in ["everything-ready", "vision-http", "mateval-administration"] {
            let mut value = candidate();
            value["required_capabilities"] = json!([capability]);
            assert!(RuntimeConfiguration::from_bytes(&serde_json::to_vec(&value)?).is_err());
        }
        for endpoint in ["192.0.2.1:3002", "127.0.0.1:0"] {
            let mut value = candidate();
            value["identity"] = json!({"endpoint":endpoint,"protocol":"mrj-auth-v1"});
            assert!(RuntimeConfiguration::from_bytes(&serde_json::to_vec(&value)?).is_err());
        }
        Ok(())
    }

    #[test]
    fn passwordless_database_configuration_is_confined_to_declared_unix_transport()
    -> Result<(), Box<dyn std::error::Error>> {
        let mut value = candidate();
        value["public_hosts"] = json!(["principiipetit.io"]);
        value["assets"][0]["host"] = json!("principiipetit.io");
        value["mateval"] = json!({"database":{"transport":{"kind":"unix","directory":"/run/postgresql"},"database":"synthetic","username":"synthetic","password_file":null,"schema":"synthetic","maximum_connections":1}});
        assert!(RuntimeConfiguration::from_bytes(&serde_json::to_vec(&value)?).is_ok());
        value["mateval"]["database"]["transport"] = json!({"kind":"tcp","port":5432});
        assert!(RuntimeConfiguration::from_bytes(&serde_json::to_vec(&value)?).is_err());
        value["mateval"]["database"]["password_file"] = json!("/synthetic/credential");
        assert!(RuntimeConfiguration::from_bytes(&serde_json::to_vec(&value)?).is_ok());
        Ok(())
    }
}

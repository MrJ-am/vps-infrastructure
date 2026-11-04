//! Configuration d'amorçage : boucle locale et aucun worker autorisé.
use std::{collections::BTreeMap, net::SocketAddr};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Instance {
    Blue,
    Green,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Configuration {
    pub listen: SocketAddr,
    pub instance: Instance,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ConfigurationError {
    InvalidAddress,
    NonLoopbackAddress,
    InvalidInstance,
    WorkersNotQualified,
    InvalidEncoding,
}

impl ConfigurationError {
    pub const fn code(self) -> &'static str {
        match self {
            Self::InvalidAddress => "INVALID_LISTEN_ADDRESS",
            Self::NonLoopbackAddress => "NON_LOOPBACK_ADDRESS_REFUSED",
            Self::InvalidInstance => "INVALID_INSTANCE",
            Self::WorkersNotQualified => "WORKERS_NOT_QUALIFIED",
            Self::InvalidEncoding => "INVALID_CONFIGURATION_ENCODING",
        }
    }
}

impl Configuration {
    pub fn from_values(values: &BTreeMap<&str, String>) -> Result<Self, ConfigurationError> {
        let listen: SocketAddr = values
            .get("MRJAM_LISTEN_ADDR")
            .map(String::as_str)
            .unwrap_or("127.0.0.1:38101")
            .parse()
            .map_err(|_| ConfigurationError::InvalidAddress)?;
        if !listen.ip().is_loopback() {
            return Err(ConfigurationError::NonLoopbackAddress);
        }
        let instance = match values.get("MRJAM_INSTANCE").map(String::as_str) {
            None | Some("blue") => Instance::Blue,
            Some("green") => Instance::Green,
            _ => return Err(ConfigurationError::InvalidInstance),
        };
        match values.get("MRJAM_WORKERS_ENABLED").map(String::as_str) {
            None | Some("false") => {}
            _ => return Err(ConfigurationError::WorkersNotQualified),
        }
        Ok(Self { listen, instance })
    }

    pub fn from_environment() -> Result<Self, ConfigurationError> {
        let mut values = BTreeMap::new();
        for name in [
            "MRJAM_LISTEN_ADDR",
            "MRJAM_INSTANCE",
            "MRJAM_WORKERS_ENABLED",
        ] {
            match std::env::var(name) {
                Ok(value) => {
                    values.insert(name, value);
                }
                Err(std::env::VarError::NotPresent) => {}
                Err(std::env::VarError::NotUnicode(_)) => {
                    return Err(ConfigurationError::InvalidEncoding);
                }
            }
        }
        Self::from_values(&values)
    }
}

#[cfg(test)]
mod tests {
    use super::{Configuration, ConfigurationError, Instance};
    use std::collections::BTreeMap;

    #[test]
    fn defaults_are_private_and_no_workers_can_be_enabled() {
        let result = Configuration::from_values(&BTreeMap::new());
        assert!(
            result.is_ok_and(
                |value| value.listen.ip().is_loopback() && value.instance == Instance::Blue
            )
        );
        for value in ["true", "1", "FALSE", "synthetic-secret-marker"] {
            let values = BTreeMap::from([("MRJAM_WORKERS_ENABLED", value.to_owned())]);
            assert_eq!(
                Configuration::from_values(&values),
                Err(ConfigurationError::WorkersNotQualified)
            );
        }
    }

    #[test]
    fn binds_outside_loopback_and_undefined_instances_are_refused() {
        for address in ["0.0.0.0:8080", "[::]:8080", "192.0.2.1:8080"] {
            let values = BTreeMap::from([("MRJAM_LISTEN_ADDR", address.to_owned())]);
            assert_eq!(
                Configuration::from_values(&values),
                Err(ConfigurationError::NonLoopbackAddress)
            );
        }
        let values = BTreeMap::from([("MRJAM_INSTANCE", "candidate-secret-marker".to_owned())]);
        assert_eq!(
            Configuration::from_values(&values),
            Err(ConfigurationError::InvalidInstance)
        );
    }
}

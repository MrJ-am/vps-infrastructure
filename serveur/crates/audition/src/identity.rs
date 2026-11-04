use std::fmt;

use crate::DomainError;

pub(crate) fn validate_text(
    value: &str,
    maximum: usize,
    allow_empty: bool,
) -> Result<(), DomainError> {
    let length = value.chars().count();
    if length > maximum
        || value.contains('\0')
        || (!allow_empty && value.trim_matches([' ', '\n', '\r', '\t']).is_empty())
    {
        return Err(DomainError::InvalidText);
    }
    Ok(())
}

macro_rules! identifier {
    ($name:ident, $dot:expr, $minimum:expr) => {
        #[derive(Clone, Eq, PartialEq, Ord, PartialOrd, Hash)]
        pub struct $name(String);

        impl $name {
            pub fn new(value: impl Into<String>) -> Result<Self, DomainError> {
                let value = value.into();
                if value.len() < $minimum
                    || value.len() > 64
                    || !value.bytes().all(|byte| {
                        byte.is_ascii_alphanumeric()
                            || byte == b'_'
                            || byte == b'-'
                            || ($dot && byte == b'.')
                    })
                {
                    return Err(DomainError::InvalidIdentifier);
                }
                Ok(Self(value))
            }

            pub fn as_str(&self) -> &str {
                &self.0
            }
        }

        impl fmt::Debug for $name {
            fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
                formatter.write_str(concat!(stringify!($name), "([redacted])"))
            }
        }
    };
}

identifier!(ActorId, true, 1);
identifier!(ActivityId, false, 1);
identifier!(CourseId, false, 1);
identifier!(AssignmentId, false, 1);
identifier!(AttemptId, false, 1);
identifier!(CriterionId, false, 1);
identifier!(ExpectedOutcomeId, false, 1);
identifier!(IdempotencyKey, false, 16);

macro_rules! version {
    ($name:ident) => {
        #[derive(Clone, Copy, Debug, Eq, PartialEq, Ord, PartialOrd)]
        pub struct $name(u32);

        impl $name {
            pub fn new(value: u32) -> Result<Self, DomainError> {
                if !(1..=1_000_000_000).contains(&value) {
                    return Err(DomainError::InvalidVersion);
                }
                Ok(Self(value))
            }

            pub const fn get(self) -> u32 {
                self.0
            }
        }
    };
}

version!(ActivityVersion);
version!(CourseVersion);
version!(PolicyVersion);
version!(SessionRevision);

impl SessionRevision {
    pub(crate) fn next(self) -> Result<Self, DomainError> {
        self.0
            .checked_add(1)
            .filter(|next| *next <= 1_000_000_000)
            .map(Self)
            .ok_or(DomainError::RevisionExhausted)
    }
}

/// Exact Unix UTC seconds. Server reception and reported activity are distinct.
#[derive(Clone, Copy, Debug, Eq, PartialEq, Ord, PartialOrd)]
pub struct Timestamp(i64);

impl Timestamp {
    pub fn new(seconds: i64) -> Result<Self, DomainError> {
        if !(0..=4_102_444_800).contains(&seconds) {
            return Err(DomainError::InvalidTimestamp);
        }
        Ok(Self(seconds))
    }

    pub const fn seconds(self) -> i64 {
        self.0
    }

    pub fn validate_activity_at(self, reception: Self) -> Result<(), DomainError> {
        if self.0 < reception.0 - 30 * 86_400 || self.0 > reception.0 + 300 {
            return Err(DomainError::InvalidActivityTime);
        }
        Ok(())
    }
}

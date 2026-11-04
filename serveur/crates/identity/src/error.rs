//! Closed errors never retain a credential, input, SQL error or upstream body.
#[derive(Clone, Copy, Debug)]
pub struct Error(pub u16);
pub type Result<T> = std::result::Result<T, Error>;
pub fn require(value: bool, status: u16) -> Result<()> {
    if value { Ok(()) } else { Err(Error(status)) }
}
impl From<sqlx::Error> for Error {
    fn from(_: sqlx::Error) -> Self {
        Self(503)
    }
}
impl std::fmt::Display for Error {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "IDENTITY_REFUSED_{}", self.0)
    }
}
impl std::error::Error for Error {}

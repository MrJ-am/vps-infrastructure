//! Audition domain and explicit PostgreSQL service: versioned prescriptions,
//! attributed observations and session transitions. No listener or authentication
//! is started implicitly; the service requires an authenticated server adapter.
//!
//! Adapters must resolve identity, role, resource ownership and the current
//! prescription inside their transaction before invoking this model. A model
//! value, channel or replay decision is not a credential or deployment proof.

#![forbid(unsafe_code)]

mod activity;
mod error;
pub mod idempotency;
mod identity;
mod observation;
pub mod service;
mod session;

pub use activity::{
    ActivityDefinition, ActivityHistory, ActivityKind, ActivityView, CourseDefinition,
    CourseHistory, CourseLink, Criterion, ExpectedOutcome, Prescription, VisibleCorrection,
    WriteChannel,
};
pub use error::DomainError;
pub use identity::{
    ActivityId, ActivityVersion, ActorId, AssignmentId, AttemptId, CourseId, CourseVersion,
    CriterionId, ExpectedOutcomeId, IdempotencyKey, PolicyVersion, SessionRevision, Timestamp,
};
pub use observation::{
    Attempt, AttemptInput, Help, HelpInput, HelpKind, InterpretationOrigin, Observation,
    ObservationInput, ObservationState,
};
pub use session::{
    OpeningDecision, RecordAttempt, Session, SessionKey, SessionState, Transition,
    TransitionAction, open_session,
};

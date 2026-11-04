//! Pure receipt comparison. No receipt store, cryptographic digest, transaction
//! or cached response is implemented here. `C` must contain every normalized
//! typed command parameter, including group/resource and expected revisions.

use crate::{ActorId, DomainError, IdempotencyKey, WriteChannel};

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum Operation {
    SaveCourse,
    SaveActivity,
    Assign,
    OpenSession,
    AdoptContext,
    RecordAttempt,
    Transition,
    Rectify,
}

/// Result of a fresh server-side resource check, not a client authorization flag.
#[derive(Clone, Copy, Debug, Default, Eq, PartialEq)]
pub enum CurrentResourceAccess {
    #[default]
    Denied,
    Granted,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ReplayDecision {
    NewOperation,
    ReplayRecordedResult,
}

#[derive(Clone)]
pub struct Request<C> {
    actor: ActorId,
    key: IdempotencyKey,
    operation: Operation,
    channel: WriteChannel,
    command: C,
}

impl<C> Request<C> {
    pub fn new(
        actor: ActorId,
        key: IdempotencyKey,
        operation: Operation,
        channel: WriteChannel,
        command: C,
    ) -> Self {
        Self {
            actor,
            key,
            operation,
            channel,
            command,
        }
    }
}

#[derive(Clone)]
pub struct Receipt<C> {
    request: Request<C>,
}

impl<C> Receipt<C> {
    /// Call only when the write and receipt are committed in the same transaction.
    /// Creating this value does not certify that a database transaction occurred.
    pub fn for_committed_request(request: Request<C>) -> Self {
        Self { request }
    }
}

pub fn decide<C: Eq>(
    access: CurrentResourceAccess,
    request: &Request<C>,
    receipt: Option<&Receipt<C>>,
) -> Result<ReplayDecision, DomainError> {
    if access != CurrentResourceAccess::Granted {
        return Err(DomainError::Forbidden);
    }
    let Some(receipt) = receipt else {
        return Ok(ReplayDecision::NewOperation);
    };
    let stored = &receipt.request;
    if stored.actor != request.actor || stored.key != request.key {
        return Err(DomainError::ReceiptScopeMismatch);
    }
    if stored.operation != request.operation
        || stored.channel != request.channel
        || stored.command != request.command
    {
        return Err(DomainError::KeyReusedForDifferentOperation);
    }
    Ok(ReplayDecision::ReplayRecordedResult)
}

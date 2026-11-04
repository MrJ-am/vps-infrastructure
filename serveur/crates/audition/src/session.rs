use crate::{
    ActivityVersion, ActorId, AssignmentId, Attempt, AttemptInput, CriterionId, DomainError,
    Observation, ObservationState, PolicyVersion, Prescription, SessionRevision, Timestamp,
    WriteChannel,
};

#[derive(Clone, Eq, PartialEq)]
pub struct SessionKey {
    assignment: AssignmentId,
    student: ActorId,
}

impl SessionKey {
    pub fn new(assignment: AssignmentId, student: ActorId) -> Self {
        Self {
            assignment,
            student,
        }
    }
    pub fn assignment(&self) -> &AssignmentId {
        &self.assignment
    }
    pub fn student(&self) -> &ActorId {
        &self.student
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum SessionState {
    InProgress,
    Interrupted,
    Finished,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum TransitionAction {
    Interrupt,
    Resume,
    Finish,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum Transition {
    StateChange {
        action: TransitionAction,
        actor: ActorId,
        received_at: Timestamp,
    },
    ContextAdoption {
        previous: ActivityVersion,
        adopted: ActivityVersion,
        actor: ActorId,
        received_at: Timestamp,
    },
}

/// Read under the assignment/student uniqueness constraint in the repository.
/// Supplying `None` is not proof that no row exists; SQL integration is pending.
pub enum OpeningDecision<'a> {
    Existing(&'a Session),
    New(Box<Session>),
}

pub fn open_session<'a>(
    existing: Option<&'a Session>,
    key: SessionKey,
    prescription: &Prescription,
    received_at: Timestamp,
) -> Result<OpeningDecision<'a>, DomainError> {
    if let Some(existing) = existing {
        if existing.key != key || existing.prescription.activity() != prescription.activity() {
            return Err(DomainError::ResourceMismatch);
        }
        return Ok(OpeningDecision::Existing(existing));
    }
    Ok(OpeningDecision::New(Box::new(Session {
        key,
        revision: SessionRevision::new(1)?,
        state: SessionState::InProgress,
        prescription: prescription.clone(),
        opened_at: received_at,
        resumed_at: received_at,
        attempts: Vec::new(),
        transitions: Vec::new(),
    })))
}

pub struct RecordAttempt<'a> {
    pub actor: &'a ActorId,
    pub expected_revision: SessionRevision,
    pub current_prescription: &'a Prescription,
    pub activity_version: ActivityVersion,
    pub policy_version: PolicyVersion,
    pub received_at: Timestamp,
    pub channel: WriteChannel,
    pub attempt: AttemptInput,
}

#[derive(Clone)]
pub struct Session {
    key: SessionKey,
    revision: SessionRevision,
    state: SessionState,
    prescription: Prescription,
    opened_at: Timestamp,
    resumed_at: Timestamp,
    attempts: Vec<Attempt>,
    transitions: Vec<Transition>,
}

impl Session {
    pub fn key(&self) -> &SessionKey {
        &self.key
    }
    pub const fn revision(&self) -> SessionRevision {
        self.revision
    }
    pub const fn state(&self) -> SessionState {
        self.state
    }
    pub fn prescription(&self) -> &Prescription {
        &self.prescription
    }
    pub const fn opened_at(&self) -> Timestamp {
        self.opened_at
    }
    pub const fn resumed_at(&self) -> Timestamp {
        self.resumed_at
    }
    pub fn attempts(&self) -> &[Attempt] {
        &self.attempts
    }
    pub fn transitions(&self) -> &[Transition] {
        &self.transitions
    }

    fn check_actor_revision(
        &self,
        actor: &ActorId,
        expected: SessionRevision,
    ) -> Result<(), DomainError> {
        if actor != self.key.student() {
            return Err(DomainError::Forbidden);
        }
        if self.revision != expected {
            return Err(DomainError::RevisionConflict);
        }
        Ok(())
    }

    fn check_current_prescription(&self, current: &Prescription) -> Result<(), DomainError> {
        if self.prescription.activity() != current.activity() {
            return Err(DomainError::ResourceMismatch);
        }
        if self.prescription.version() != current.version() {
            return Err(DomainError::ContextChanged);
        }
        Ok(())
    }

    pub fn record_attempt(&self, command: RecordAttempt<'_>) -> Result<Self, DomainError> {
        self.check_actor_revision(command.actor, command.expected_revision)?;
        if self.state != SessionState::InProgress {
            return Err(DomainError::SessionNotOpen);
        }
        self.check_current_prescription(command.current_prescription)?;
        if command.activity_version != self.prescription.version() {
            return Err(DomainError::ContextChanged);
        }
        if command.policy_version.get() != 1 {
            return Err(DomainError::PolicyChanged);
        }
        if self.attempts.len() >= 128 {
            return Err(DomainError::TraceLimitReached);
        }
        if self
            .attempts
            .iter()
            .any(|attempt| attempt.id() == &command.attempt.id)
        {
            return Err(DomainError::DuplicateAttempt);
        }
        let attempt = Attempt::validate(
            command.attempt,
            &self.prescription,
            command.channel,
            command.actor.clone(),
            command.received_at,
        )?;
        let revision = self.revision.next()?;
        let mut next = self.clone();
        next.revision = revision;
        next.attempts.push(attempt);
        Ok(next)
    }

    pub fn adopt_context(
        &self,
        actor: &ActorId,
        expected: SessionRevision,
        requested: ActivityVersion,
        current: &Prescription,
        received_at: Timestamp,
    ) -> Result<Self, DomainError> {
        self.check_actor_revision(actor, expected)?;
        if self.state != SessionState::InProgress {
            return Err(DomainError::ForbiddenTransition);
        }
        if self.prescription.activity() != current.activity() {
            return Err(DomainError::ResourceMismatch);
        }
        if requested != current.version() || requested < self.prescription.version() {
            return Err(DomainError::ContextChanged);
        }
        if self.transitions.len() >= 256 {
            return Err(DomainError::TransitionLimitReached);
        }
        let revision = self.revision.next()?;
        let mut next = self.clone();
        next.transitions.push(Transition::ContextAdoption {
            previous: self.prescription.version(),
            adopted: requested,
            actor: actor.clone(),
            received_at,
        });
        next.prescription = current.clone();
        next.revision = revision;
        Ok(next)
    }

    /// Latest observation for the adopted version only; old rubric evidence is
    /// retained in attempts but cannot satisfy new prescription criteria.
    pub fn latest_observation(&self, criterion: &CriterionId) -> Option<&Observation> {
        self.attempts
            .iter()
            .rev()
            .filter(|attempt| attempt.activity_version() == self.prescription.version())
            .flat_map(|attempt| attempt.observations().iter())
            .find(|observation| observation.criterion() == criterion)
    }

    pub fn transition(
        &self,
        actor: &ActorId,
        expected: SessionRevision,
        action: TransitionAction,
        current: &Prescription,
        received_at: Timestamp,
    ) -> Result<Self, DomainError> {
        self.check_actor_revision(actor, expected)?;
        if current.activity() != self.prescription.activity() {
            return Err(DomainError::ResourceMismatch);
        }
        let required_state = match action {
            TransitionAction::Resume => SessionState::Interrupted,
            TransitionAction::Interrupt | TransitionAction::Finish => SessionState::InProgress,
        };
        if self.state != required_state {
            return Err(DomainError::ForbiddenTransition);
        }
        if action == TransitionAction::Finish {
            self.check_current_prescription(current)?;
            if self.attempts.is_empty() {
                return Err(DomainError::IncompleteSession);
            }
            let observed = self
                .prescription
                .definition()
                .criteria()
                .iter()
                .all(|criterion| {
                    self.latest_observation(criterion.id())
                        .is_some_and(|observation| {
                            observation.state() != ObservationState::NotObserved
                        })
                });
            if !observed {
                return Err(DomainError::UnobservedCriteria);
            }
        }
        if self.transitions.len() >= 256 {
            return Err(DomainError::TransitionLimitReached);
        }
        let revision = self.revision.next()?;
        let mut next = self.clone();
        next.state = match action {
            TransitionAction::Resume => SessionState::InProgress,
            TransitionAction::Interrupt => SessionState::Interrupted,
            TransitionAction::Finish => SessionState::Finished,
        };
        if action == TransitionAction::Resume {
            next.resumed_at = received_at;
        }
        next.revision = revision;
        next.transitions.push(Transition::StateChange {
            action,
            actor: actor.clone(),
            received_at,
        });
        Ok(next)
    }
}

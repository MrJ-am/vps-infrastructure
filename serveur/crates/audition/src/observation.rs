use std::collections::BTreeSet;

use crate::{
    ActivityVersion, ActorId, AttemptId, CriterionId, DomainError, PolicyVersion, Prescription,
    Timestamp, WriteChannel, identity::validate_text,
};

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ObservationState {
    NotObserved,
    InProgress,
    Difficulty,
    SuccessWithHelp,
    AutonomousSuccess,
}

impl ObservationState {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::NotObserved => "non_observe",
            Self::InProgress => "en_cours",
            Self::Difficulty => "difficulte",
            Self::SuccessWithHelp => "reussite_aidee",
            Self::AutonomousSuccess => "reussite_autonome",
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum HelpKind {
    Hint,
    Explanation,
    Correction,
    Solution,
}

#[derive(Clone)]
pub struct HelpInput {
    pub kind: HelpKind,
    pub content: String,
    pub activity_at: Timestamp,
}

#[derive(Clone)]
pub struct ObservationInput {
    pub criterion: CriterionId,
    pub state: ObservationState,
    pub points: Option<f64>,
    pub uncertainty: Option<String>,
    pub justification: String,
}

#[derive(Clone)]
pub struct AttemptInput {
    pub id: AttemptId,
    pub production: String,
    pub activity_at: Timestamp,
    pub help: Vec<HelpInput>,
    pub observations: Vec<ObservationInput>,
}

#[derive(Clone)]
pub struct Help {
    input: HelpInput,
    received_at: Timestamp,
}

impl Help {
    pub const fn kind(&self) -> HelpKind {
        self.input.kind
    }
    pub fn content(&self) -> &str {
        &self.input.content
    }
    pub const fn activity_at(&self) -> Timestamp {
        self.input.activity_at
    }
    pub const fn received_at(&self) -> Timestamp {
        self.received_at
    }
}

#[derive(Clone)]
pub struct Observation {
    input: ObservationInput,
    received_at: Timestamp,
}

impl Observation {
    pub fn criterion(&self) -> &CriterionId {
        &self.input.criterion
    }
    pub const fn state(&self) -> ObservationState {
        self.input.state
    }
    pub const fn points(&self) -> Option<f64> {
        self.input.points
    }
    pub fn uncertainty(&self) -> Option<&str> {
        self.input.uncertainty.as_deref()
    }
    pub fn justification(&self) -> &str {
        &self.input.justification
    }
    pub const fn received_at(&self) -> Timestamp {
        self.received_at
    }

    fn validate(
        input: ObservationInput,
        prescription: &Prescription,
        has_help: bool,
        received_at: Timestamp,
    ) -> Result<Self, DomainError> {
        let criterion = prescription
            .definition()
            .criteria()
            .iter()
            .find(|criterion| criterion.id() == &input.criterion)
            .ok_or(DomainError::InvalidObservation)?;
        validate_text(&input.justification, 4_000, false)?;
        if let Some(uncertainty) = &input.uncertainty {
            validate_text(uncertainty, 2_000, false)?;
        }
        if input.points.is_some_and(|points| {
            !points.is_finite() || points < 0.0 || points > criterion.maximum()
        }) {
            return Err(DomainError::InvalidPoints);
        }
        if input.state == ObservationState::AutonomousSuccess && has_help {
            return Err(DomainError::AutonomousWithHelp);
        }
        if matches!(
            input.state,
            ObservationState::SuccessWithHelp | ObservationState::AutonomousSuccess
        ) {
            if input.points != Some(criterion.maximum()) {
                return Err(DomainError::IncompleteSuccess);
            }
            if input.uncertainty.is_some() {
                return Err(DomainError::UncertainSuccess);
            }
        }
        if input.state == ObservationState::SuccessWithHelp && !has_help {
            return Err(DomainError::MissingHelp);
        }
        Ok(Self { input, received_at })
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum InterpretationOrigin {
    StudentReported,
    LlmReported,
}

#[derive(Clone)]
pub struct Attempt {
    id: AttemptId,
    production: String,
    activity_at: Timestamp,
    received_at: Timestamp,
    help: Vec<Help>,
    observations: Vec<Observation>,
    activity_version: ActivityVersion,
    policy_version: PolicyVersion,
    trace_author: ActorId,
    channel: WriteChannel,
}

impl Attempt {
    pub(crate) fn validate(
        input: AttemptInput,
        prescription: &Prescription,
        channel: WriteChannel,
        actor: ActorId,
        received_at: Timestamp,
    ) -> Result<Self, DomainError> {
        validate_text(&input.production, 16_000, false)?;
        input.activity_at.validate_activity_at(received_at)?;
        if input.help.len() > 32 || input.observations.is_empty() || input.observations.len() > 64 {
            return Err(DomainError::TraceLimitReached);
        }
        let mut criterion_ids = BTreeSet::new();
        for observation in &input.observations {
            if !criterion_ids.insert(observation.criterion.clone()) {
                return Err(DomainError::DuplicateObservation);
            }
        }
        let help = input
            .help
            .into_iter()
            .map(|help| {
                validate_text(&help.content, 8_000, false)?;
                help.activity_at.validate_activity_at(received_at)?;
                Ok(Help {
                    input: help,
                    received_at,
                })
            })
            .collect::<Result<Vec<_>, DomainError>>()?;
        let observations = input
            .observations
            .into_iter()
            .map(|observation| {
                Observation::validate(observation, prescription, !help.is_empty(), received_at)
            })
            .collect::<Result<Vec<_>, _>>()?;
        Ok(Self {
            id: input.id,
            production: input.production,
            activity_at: input.activity_at,
            received_at,
            help,
            observations,
            activity_version: prescription.version(),
            policy_version: PolicyVersion::new(1)?,
            trace_author: actor,
            channel,
        })
    }

    pub fn id(&self) -> &AttemptId {
        &self.id
    }
    pub fn production(&self) -> &str {
        &self.production
    }
    pub const fn production_origin(&self) -> &'static str {
        "eleve_rapportee"
    }
    pub const fn activity_at(&self) -> Timestamp {
        self.activity_at
    }
    pub const fn received_at(&self) -> Timestamp {
        self.received_at
    }
    pub fn help(&self) -> &[Help] {
        &self.help
    }
    pub fn observations(&self) -> &[Observation] {
        &self.observations
    }
    pub const fn activity_version(&self) -> ActivityVersion {
        self.activity_version
    }
    pub const fn policy_version(&self) -> PolicyVersion {
        self.policy_version
    }
    pub fn trace_author(&self) -> &ActorId {
        &self.trace_author
    }
    pub const fn channel(&self) -> WriteChannel {
        self.channel
    }
    pub const fn interpretation_origin(&self) -> InterpretationOrigin {
        match self.channel {
            WriteChannel::Web => InterpretationOrigin::StudentReported,
            WriteChannel::Mcp => InterpretationOrigin::LlmReported,
        }
    }
}

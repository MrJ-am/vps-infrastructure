use std::collections::BTreeSet;

use crate::{
    ActivityId, ActivityVersion, ActorId, CourseId, CourseVersion, CriterionId, DomainError,
    ExpectedOutcomeId, Timestamp, identity::validate_text,
};

/// Imposed by the authenticated adapter, never accepted as a client claim.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum WriteChannel {
    Web,
    Mcp,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ActivityKind {
    OpenResponse,
    SingleCorrectChoice { alternatives: u8 },
}

#[derive(Clone)]
pub struct ExpectedOutcome {
    id: ExpectedOutcomeId,
    text: String,
}

impl ExpectedOutcome {
    pub fn new(id: ExpectedOutcomeId, text: impl Into<String>) -> Result<Self, DomainError> {
        let text = text.into();
        validate_text(&text, 2_000, false)?;
        Ok(Self { id, text })
    }

    pub fn id(&self) -> &ExpectedOutcomeId {
        &self.id
    }
    pub fn text(&self) -> &str {
        &self.text
    }
}

#[derive(Clone)]
pub struct Criterion {
    id: CriterionId,
    expected_outcome: ExpectedOutcomeId,
    text: String,
    maximum: f64,
}

impl Criterion {
    pub fn new(
        id: CriterionId,
        expected_outcome: ExpectedOutcomeId,
        text: impl Into<String>,
        maximum: f64,
    ) -> Result<Self, DomainError> {
        let text = text.into();
        validate_text(&text, 2_000, false)?;
        if !maximum.is_finite() || maximum <= 0.0 || maximum >= 1_001.0 {
            return Err(DomainError::InvalidCriterion);
        }
        Ok(Self {
            id,
            expected_outcome,
            text,
            maximum,
        })
    }

    pub fn id(&self) -> &CriterionId {
        &self.id
    }
    pub fn expected_outcome(&self) -> &ExpectedOutcomeId {
        &self.expected_outcome
    }
    pub fn text(&self) -> &str {
        &self.text
    }
    pub const fn maximum(&self) -> f64 {
        self.maximum
    }
}

/// Produced from a course history: a pending MCP course cannot be prescribed.
#[derive(Clone)]
pub struct CourseLink {
    id: CourseId,
    version: Option<CourseVersion>,
}

impl CourseLink {
    pub fn id(&self) -> &CourseId {
        &self.id
    }
    pub const fn version(&self) -> Option<CourseVersion> {
        self.version
    }
}

#[derive(Clone)]
pub struct CourseDefinition {
    title: String,
    content: String,
}

impl CourseDefinition {
    pub fn new(title: impl Into<String>, content: impl Into<String>) -> Result<Self, DomainError> {
        let title = title.into();
        let content = content.into();
        validate_text(&title, 200, false)?;
        validate_text(&content, 32_000, false)?;
        Ok(Self { title, content })
    }

    pub fn title(&self) -> &str {
        &self.title
    }
    pub fn content(&self) -> &str {
        &self.content
    }
}

#[derive(Clone)]
struct Correction {
    text: String,
    publication: Option<Timestamp>,
}

#[derive(Clone)]
pub struct ActivityDefinition {
    title: String,
    instructions: String,
    outcomes: Vec<ExpectedOutcome>,
    criteria: Vec<Criterion>,
    kind: ActivityKind,
    course: Option<CourseLink>,
    correction: Option<Correction>,
}

impl ActivityDefinition {
    pub fn new(
        title: impl Into<String>,
        instructions: impl Into<String>,
        outcomes: Vec<ExpectedOutcome>,
        criteria: Vec<Criterion>,
        kind: ActivityKind,
    ) -> Result<Self, DomainError> {
        let title = title.into();
        let instructions = instructions.into();
        validate_text(&title, 200, false)?;
        validate_text(&instructions, 16_000, false)?;
        if outcomes.is_empty() || outcomes.len() > 32 || criteria.is_empty() || criteria.len() > 64
        {
            return Err(DomainError::InvalidActivity);
        }
        let outcome_ids: BTreeSet<_> = outcomes.iter().map(|outcome| outcome.id()).collect();
        let criterion_ids: BTreeSet<_> = criteria.iter().map(|criterion| criterion.id()).collect();
        if outcome_ids.len() != outcomes.len() || criterion_ids.len() != criteria.len() {
            return Err(DomainError::DuplicateIdentifier);
        }
        if criteria
            .iter()
            .any(|criterion| !outcome_ids.contains(criterion.expected_outcome()))
        {
            return Err(DomainError::InvalidCriterion);
        }
        if let ActivityKind::SingleCorrectChoice { alternatives } = kind
            && !(2..=100).contains(&alternatives)
        {
            return Err(DomainError::InvalidActivity);
        }
        Ok(Self {
            title,
            instructions,
            outcomes,
            criteria,
            kind,
            course: None,
            correction: None,
        })
    }

    pub fn with_course(mut self, course: CourseLink) -> Self {
        self.course = Some(course);
        self
    }

    pub fn with_correction(
        mut self,
        text: impl Into<String>,
        publication: Option<Timestamp>,
    ) -> Result<Self, DomainError> {
        let text = text.into();
        validate_text(&text, 16_000, true)?;
        self.correction = Some(Correction { text, publication });
        Ok(self)
    }

    pub fn title(&self) -> &str {
        &self.title
    }
    pub fn instructions(&self) -> &str {
        &self.instructions
    }
    pub fn outcomes(&self) -> &[ExpectedOutcome] {
        &self.outcomes
    }
    pub fn criteria(&self) -> &[Criterion] {
        &self.criteria
    }
    pub const fn kind(&self) -> ActivityKind {
        self.kind
    }
    pub fn course(&self) -> Option<&CourseLink> {
        self.course.as_ref()
    }

    pub fn student_view(&self, now: Timestamp) -> ActivityView<'_> {
        self.view(false, now)
    }

    /// The caller must already have checked the current teacher grant.
    pub fn teacher_view(&self, now: Timestamp) -> ActivityView<'_> {
        self.view(true, now)
    }

    fn view(&self, teacher: bool, now: Timestamp) -> ActivityView<'_> {
        let correction = self
            .correction
            .as_ref()
            .filter(|correction| {
                teacher
                    || correction
                        .publication
                        .is_some_and(|publication| publication <= now)
            })
            .map(|correction| VisibleCorrection {
                text: &correction.text,
                publication: correction.publication,
            });
        ActivityView {
            title: &self.title,
            instructions: &self.instructions,
            outcomes: &self.outcomes,
            criteria: &self.criteria,
            kind: self.kind,
            course: self.course.as_ref(),
            correction,
        }
    }
}

#[derive(Clone, Copy)]
pub struct VisibleCorrection<'a> {
    pub text: &'a str,
    pub publication: Option<Timestamp>,
}

/// A student projection contains no reference back to the private definition.
pub struct ActivityView<'a> {
    pub title: &'a str,
    pub instructions: &'a str,
    pub outcomes: &'a [ExpectedOutcome],
    pub criteria: &'a [Criterion],
    pub kind: ActivityKind,
    pub course: Option<&'a CourseLink>,
    pub correction: Option<VisibleCorrection<'a>>,
}

#[derive(Clone)]
struct Entry<T> {
    revision: u32,
    document: T,
    channel: WriteChannel,
    author: ActorId,
    received_at: Timestamp,
}

#[derive(Clone)]
struct History<T> {
    entries: Vec<Entry<T>>,
}

impl<T: Clone> History<T> {
    fn new() -> Self {
        Self {
            entries: Vec::new(),
        }
    }
    fn revision(&self) -> Option<u32> {
        self.entries.last().map(|entry| entry.revision)
    }
    fn official(&self) -> Option<&Entry<T>> {
        self.entries
            .iter()
            .rev()
            .find(|entry| entry.channel == WriteChannel::Web)
    }

    fn record(
        &self,
        expected: Option<u32>,
        document: T,
        channel: WriteChannel,
        author: ActorId,
        received_at: Timestamp,
    ) -> Result<Self, DomainError> {
        if expected != self.revision() {
            return Err(DomainError::RevisionConflict);
        }
        let revision = self
            .revision()
            .unwrap_or(0)
            .checked_add(1)
            .filter(|next| *next <= 1_000_000_000)
            .ok_or(DomainError::RevisionExhausted)?;
        let mut next = self.clone();
        next.entries.push(Entry {
            revision,
            document,
            channel,
            author,
            received_at,
        });
        Ok(next)
    }
}

#[derive(Clone)]
pub struct CourseHistory {
    id: CourseId,
    history: History<CourseDefinition>,
}

impl CourseHistory {
    pub fn new(id: CourseId) -> Self {
        Self {
            id,
            history: History::new(),
        }
    }

    pub fn record(
        &self,
        expected: Option<CourseVersion>,
        document: CourseDefinition,
        channel: WriteChannel,
        author: ActorId,
        received_at: Timestamp,
    ) -> Result<Self, DomainError> {
        Ok(Self {
            id: self.id.clone(),
            history: self.history.record(
                expected.map(CourseVersion::get),
                document,
                channel,
                author,
                received_at,
            )?,
        })
    }

    pub fn current_version(&self) -> Result<Option<CourseVersion>, DomainError> {
        self.history.revision().map(CourseVersion::new).transpose()
    }

    pub fn link(&self) -> Result<CourseLink, DomainError> {
        Ok(CourseLink {
            id: self.id.clone(),
            version: self
                .history
                .official()
                .map(|entry| CourseVersion::new(entry.revision))
                .transpose()?,
        })
    }

    pub fn at_version(&self, version: CourseVersion) -> Option<&CourseDefinition> {
        self.history
            .entries
            .iter()
            .find(|entry| entry.revision == version.get())
            .map(|entry| &entry.document)
    }
}

#[derive(Clone)]
pub struct ActivityHistory {
    id: ActivityId,
    history: History<ActivityDefinition>,
}

impl ActivityHistory {
    pub fn new(id: ActivityId) -> Self {
        Self {
            id,
            history: History::new(),
        }
    }

    pub fn record(
        &self,
        expected: Option<ActivityVersion>,
        document: ActivityDefinition,
        channel: WriteChannel,
        author: ActorId,
        received_at: Timestamp,
    ) -> Result<Self, DomainError> {
        if channel == WriteChannel::Web
            && document
                .course()
                .is_some_and(|course| course.version().is_none())
        {
            return Err(DomainError::UnapprovedCourse);
        }
        Ok(Self {
            id: self.id.clone(),
            history: self.history.record(
                expected.map(ActivityVersion::get),
                document,
                channel,
                author,
                received_at,
            )?,
        })
    }

    pub fn current_version(&self) -> Result<Option<ActivityVersion>, DomainError> {
        self.history
            .revision()
            .map(ActivityVersion::new)
            .transpose()
    }

    pub fn at_version(&self, version: ActivityVersion) -> Option<&ActivityDefinition> {
        self.history
            .entries
            .iter()
            .find(|entry| entry.revision == version.get())
            .map(|entry| &entry.document)
    }

    /// New MCP proposals never displace the last teacher-prescribed revision.
    pub fn prescription(&self) -> Result<Option<Prescription>, DomainError> {
        self.history
            .official()
            .map(|entry| {
                Ok(Prescription {
                    activity: self.id.clone(),
                    version: ActivityVersion::new(entry.revision)?,
                    document: entry.document.clone(),
                    author: entry.author.clone(),
                    received_at: entry.received_at,
                })
            })
            .transpose()
    }
}

/// Can only originate from an official entry in an activity history.
#[derive(Clone)]
pub struct Prescription {
    activity: ActivityId,
    version: ActivityVersion,
    document: ActivityDefinition,
    author: ActorId,
    received_at: Timestamp,
}

impl Prescription {
    pub fn activity(&self) -> &ActivityId {
        &self.activity
    }
    pub const fn version(&self) -> ActivityVersion {
        self.version
    }
    pub fn definition(&self) -> &ActivityDefinition {
        &self.document
    }
    pub fn author(&self) -> &ActorId {
        &self.author
    }
    pub const fn received_at(&self) -> Timestamp {
        self.received_at
    }
}

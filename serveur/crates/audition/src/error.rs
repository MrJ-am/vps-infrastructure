use std::fmt;

/// Errors contain fixed codes only, never submitted text or personal identifiers.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum DomainError {
    InvalidIdentifier,
    InvalidVersion,
    InvalidTimestamp,
    InvalidText,
    InvalidActivity,
    InvalidCriterion,
    DuplicateIdentifier,
    UnapprovedCourse,
    UnapprovedProposal,
    RevisionConflict,
    RevisionExhausted,
    ResourceMismatch,
    Forbidden,
    InvalidActivityTime,
    InvalidObservation,
    InvalidPoints,
    AutonomousWithHelp,
    IncompleteSuccess,
    UncertainSuccess,
    MissingHelp,
    DuplicateObservation,
    DuplicateAttempt,
    TraceLimitReached,
    SessionNotOpen,
    ContextChanged,
    PolicyChanged,
    ForbiddenTransition,
    IncompleteSession,
    UnobservedCriteria,
    TransitionLimitReached,
    KeyReusedForDifferentOperation,
    ReceiptScopeMismatch,
}

impl DomainError {
    pub const fn code(self) -> &'static str {
        match self {
            Self::InvalidIdentifier => "identifiant_invalide",
            Self::InvalidVersion => "version_invalide",
            Self::InvalidTimestamp => "date_invalide",
            Self::InvalidText => "texte_invalide",
            Self::InvalidActivity => "activite_invalide",
            Self::InvalidCriterion => "critere_invalide",
            Self::DuplicateIdentifier => "identifiants_dupliques",
            Self::UnapprovedCourse | Self::UnapprovedProposal => "proposition_non_validee",
            Self::RevisionConflict => "conflit_revision",
            Self::RevisionExhausted => "limite_revisions_atteinte",
            Self::ResourceMismatch => "objet_indisponible",
            Self::Forbidden => "seance_interdite",
            Self::InvalidActivityTime => "heure_activite_invalide",
            Self::InvalidObservation => "observation_invalide",
            Self::InvalidPoints => "points_invalides",
            Self::AutonomousWithHelp => "autonomie_incompatible_avec_aide",
            Self::IncompleteSuccess => "reussite_incomplete",
            Self::UncertainSuccess => "reussite_incertaine",
            Self::MissingHelp => "aide_manquante",
            Self::DuplicateObservation => "observations_dupliquees",
            Self::DuplicateAttempt => "tentative_dupliquee",
            Self::TraceLimitReached => "limite_traces_atteinte",
            Self::SessionNotOpen => "seance_non_ouverte",
            Self::ContextChanged => "contexte_modifie",
            Self::PolicyChanged => "politique_modifiee",
            Self::ForbiddenTransition => "transition_interdite",
            Self::IncompleteSession => "seance_incomplete",
            Self::UnobservedCriteria => "criteres_non_observes",
            Self::TransitionLimitReached => "limite_transitions_atteinte",
            Self::KeyReusedForDifferentOperation => "cle_reutilisee_avec_autre_operation",
            Self::ReceiptScopeMismatch => "recu_hors_perimetre",
        }
    }
}

impl fmt::Display for DomainError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(self.code())
    }
}

impl std::error::Error for DomainError {}

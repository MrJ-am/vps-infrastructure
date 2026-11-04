//! All identities, work, scores and times in these tests are invented fixtures.
//! Expected behavior comes from Audition CONTRAT.md / MCP.md at c6459ae..., not
//! from constants exported by the candidate implementation.

use mrjam_audition::{
    ActivityDefinition, ActivityHistory, ActivityId, ActivityKind, ActivityVersion, ActorId,
    AssignmentId, AttemptId, AttemptInput, CourseDefinition, CourseHistory, CourseId,
    CourseVersion, Criterion, CriterionId, DomainError, ExpectedOutcome, ExpectedOutcomeId,
    HelpInput, HelpKind, IdempotencyKey, InterpretationOrigin, ObservationInput, ObservationState,
    OpeningDecision, PolicyVersion, Prescription, RecordAttempt, Session, SessionKey,
    SessionRevision, SessionState, Timestamp, TransitionAction, WriteChannel,
    idempotency::{self, CurrentResourceAccess, Operation, Receipt, ReplayDecision, Request},
    open_session,
};

fn time(seconds: i64) -> Result<Timestamp, DomainError> {
    Timestamp::new(seconds)
}
fn student() -> Result<ActorId, DomainError> {
    ActorId::new("synthetic.student")
}
fn teacher() -> Result<ActorId, DomainError> {
    ActorId::new("synthetic.teacher")
}

fn definition(instructions: &str, maximum: f64) -> Result<ActivityDefinition, DomainError> {
    let expected = ExpectedOutcomeId::new("sign")?;
    ActivityDefinition::new(
        "Synthetic square",
        instructions,
        vec![ExpectedOutcome::new(
            expected.clone(),
            "Explain the sign of a square",
        )?],
        vec![Criterion::new(
            CriterionId::new("reasoning")?,
            expected,
            "Address zero and both signs",
            maximum,
        )?],
        ActivityKind::OpenResponse,
    )
}

fn prescribed() -> Result<ActivityHistory, DomainError> {
    ActivityHistory::new(ActivityId::new("synthetic-activity")?).record(
        None,
        definition("Discuss the square", 2.0)?,
        WriteChannel::Web,
        teacher()?,
        time(1_800_000_000)?,
    )
}

fn official(history: &ActivityHistory) -> Result<Prescription, DomainError> {
    history
        .prescription()?
        .ok_or(DomainError::UnapprovedProposal)
}

fn session(prescription: &Prescription) -> Result<Session, DomainError> {
    let key = SessionKey::new(AssignmentId::new("synthetic-assignment")?, student()?);
    match open_session(None, key, prescription, time(1_800_000_000)?)? {
        OpeningDecision::New(session) => Ok(*session),
        OpeningDecision::Existing(_) => Err(DomainError::ResourceMismatch),
    }
}

fn observation(
    state: ObservationState,
    points: Option<f64>,
) -> Result<ObservationInput, DomainError> {
    Ok(ObservationInput {
        criterion: CriterionId::new("reasoning")?,
        state,
        points,
        uncertainty: None,
        justification: "Synthetic rationale supplied by the client".into(),
    })
}

fn attempt(
    id: &str,
    state: ObservationState,
    points: Option<f64>,
) -> Result<AttemptInput, DomainError> {
    Ok(AttemptInput {
        id: AttemptId::new(id)?,
        production: "Synthetic learner production".into(),
        activity_at: time(1_800_000_005)?,
        help: Vec::new(),
        observations: vec![observation(state, points)?],
    })
}

fn record(
    session: &Session,
    prescription: &Prescription,
    input: AttemptInput,
) -> Result<Session, DomainError> {
    session.record_attempt(RecordAttempt {
        actor: &student()?,
        expected_revision: session.revision(),
        current_prescription: prescription,
        activity_version: prescription.version(),
        policy_version: PolicyVersion::new(1)?,
        received_at: time(1_800_000_010)?,
        channel: WriteChannel::Mcp,
        attempt: input,
    })
}

#[test]
fn central_actor_identifiers_keep_the_dot_without_weakening_resource_identifiers()
-> Result<(), DomainError> {
    assert_eq!(
        ActorId::new("synthetic.person")?.as_str(),
        "synthetic.person"
    );
    assert_eq!(
        ActivityId::new("synthetic.person").err(),
        Some(DomainError::InvalidIdentifier)
    );
    assert_eq!(
        ActorId::new("../synthetic").err(),
        Some(DomainError::InvalidIdentifier)
    );
    assert_eq!(
        IdempotencyKey::new("short").err(),
        Some(DomainError::InvalidIdentifier)
    );
    assert!(!format!("{:?}", student()?).contains("synthetic.student"));
    Ok(())
}

#[test]
fn malformed_rubrics_are_rejected_before_an_activity_can_be_prescribed() -> Result<(), DomainError>
{
    let expected = ExpectedOutcomeId::new("sign")?;
    let outcome = ExpectedOutcome::new(expected.clone(), "Synthetic expectation")?;
    let criterion = Criterion::new(
        CriterionId::new("reasoning")?,
        expected.clone(),
        "Synthetic criterion",
        1.5,
    )?;
    assert_eq!(
        ActivityDefinition::new(
            "Title",
            "Instruction",
            vec![outcome.clone()],
            vec![criterion.clone(), criterion.clone()],
            ActivityKind::OpenResponse
        )
        .err(),
        Some(DomainError::DuplicateIdentifier)
    );
    let orphan = Criterion::new(
        CriterionId::new("other")?,
        ExpectedOutcomeId::new("missing")?,
        "No matching expectation",
        1.0,
    )?;
    assert_eq!(
        ActivityDefinition::new(
            "Title",
            "Instruction",
            vec![outcome.clone()],
            vec![orphan],
            ActivityKind::OpenResponse
        )
        .err(),
        Some(DomainError::InvalidCriterion)
    );
    for alternatives in [0, 1, 101] {
        assert_eq!(
            ActivityDefinition::new(
                "Title",
                "Instruction",
                vec![outcome.clone()],
                vec![criterion.clone()],
                ActivityKind::SingleCorrectChoice { alternatives }
            )
            .err(),
            Some(DomainError::InvalidActivity)
        );
    }
    for maximum in [0.0, -1.0, 1001.0, f64::INFINITY, f64::NAN] {
        assert_eq!(
            Criterion::new(
                CriterionId::new("reasoning")?,
                expected.clone(),
                "Synthetic criterion",
                maximum
            )
            .err(),
            Some(DomainError::InvalidCriterion)
        );
    }
    Ok(())
}

#[test]
fn a_private_correction_is_absent_from_student_projection_until_publication()
-> Result<(), DomainError> {
    let lesson = definition("Synthetic instruction", 2.0)?
        .with_correction("SYNTHETIC_PRIVATE_CORRECTION", Some(time(1_800_000_100)?))?;
    assert!(
        lesson
            .student_view(time(1_800_000_099)?)
            .correction
            .is_none()
    );
    assert!(
        lesson
            .teacher_view(time(1_800_000_099)?)
            .correction
            .is_some()
    );
    let visible = lesson.student_view(time(1_800_000_100)?);
    assert_eq!(
        visible.correction.map(|correction| correction.text),
        Some("SYNTHETIC_PRIVATE_CORRECTION")
    );
    let never_published =
        definition("Synthetic instruction", 2.0)?.with_correction("NEVER_PUBLIC", None)?;
    assert!(
        never_published
            .student_view(time(2_000_000_000)?)
            .correction
            .is_none()
    );
    Ok(())
}

#[test]
fn mcp_proposals_never_replace_the_latest_web_prescription() -> Result<(), DomainError> {
    let initial = ActivityHistory::new(ActivityId::new("synthetic-activity")?).record(
        None,
        definition("MCP proposal", 2.0)?,
        WriteChannel::Mcp,
        teacher()?,
        time(1_800_000_000)?,
    )?;
    assert!(initial.prescription()?.is_none());
    let validated = initial.record(
        Some(ActivityVersion::new(1)?),
        definition("Teacher version", 2.0)?,
        WriteChannel::Web,
        teacher()?,
        time(1_800_000_001)?,
    )?;
    let proposed = validated.record(
        Some(ActivityVersion::new(2)?),
        definition("New MCP proposal", 3.0)?,
        WriteChannel::Mcp,
        teacher()?,
        time(1_800_000_002)?,
    )?;
    assert_eq!(proposed.current_version()?, Some(ActivityVersion::new(3)?));
    assert_eq!(official(&proposed)?.version(), ActivityVersion::new(2)?);
    assert_eq!(
        official(&proposed)?.definition().instructions(),
        "Teacher version"
    );
    assert_eq!(
        proposed
            .at_version(ActivityVersion::new(1)?)
            .map(ActivityDefinition::instructions),
        Some("MCP proposal")
    );
    assert_eq!(
        proposed
            .record(
                Some(ActivityVersion::new(2)?),
                definition("Stale write", 2.0)?,
                WriteChannel::Web,
                teacher()?,
                time(1_800_000_003)?
            )
            .err(),
        Some(DomainError::RevisionConflict)
    );
    Ok(())
}

#[test]
fn course_edits_require_teacher_represcription_then_explicit_student_adoption()
-> Result<(), DomainError> {
    let course = CourseHistory::new(CourseId::new("synthetic-course")?).record(
        None,
        CourseDefinition::new("Course", "First course")?,
        WriteChannel::Web,
        teacher()?,
        time(1_800_000_000)?,
    )?;
    let history = ActivityHistory::new(ActivityId::new("synthetic-activity")?).record(
        None,
        definition("Instruction", 2.0)?.with_course(course.link()?),
        WriteChannel::Web,
        teacher()?,
        time(1_800_000_001)?,
    )?;
    let original = official(&history)?;
    let learner_session = session(&original)?;
    let proposed_course = course.record(
        Some(CourseVersion::new(1)?),
        CourseDefinition::new("Course", "Draft course")?,
        WriteChannel::Mcp,
        teacher()?,
        time(1_800_000_002)?,
    )?;
    assert_eq!(
        proposed_course.link()?.version(),
        Some(CourseVersion::new(1)?)
    );
    let new_course = proposed_course.record(
        Some(CourseVersion::new(2)?),
        CourseDefinition::new("Course", "Revised course")?,
        WriteChannel::Web,
        teacher()?,
        time(1_800_000_003)?,
    )?;
    assert_eq!(
        original
            .definition()
            .course()
            .and_then(|course| course.version()),
        Some(CourseVersion::new(1)?)
    );
    let revised = history.record(
        Some(ActivityVersion::new(1)?),
        definition("Revised instruction", 3.0)?.with_course(new_course.link()?),
        WriteChannel::Web,
        teacher()?,
        time(1_800_000_004)?,
    )?;
    let current = official(&revised)?;
    assert_eq!(
        learner_session
            .prescription()
            .definition()
            .course()
            .and_then(|course| course.version()),
        Some(CourseVersion::new(1)?)
    );
    let adopted = learner_session.adopt_context(
        &student()?,
        learner_session.revision(),
        current.version(),
        &current,
        time(1_800_000_005)?,
    )?;
    assert_eq!(
        adopted
            .prescription()
            .definition()
            .course()
            .and_then(|course| course.version()),
        Some(CourseVersion::new(3)?)
    );
    assert_eq!(adopted.transitions().len(), 1);
    assert_eq!(learner_session.transitions().len(), 0);
    Ok(())
}

#[test]
fn a_pending_course_can_be_proposed_but_cannot_be_prescribed() -> Result<(), DomainError> {
    let course = CourseHistory::new(CourseId::new("synthetic-course")?).record(
        None,
        CourseDefinition::new("Course", "Draft")?,
        WriteChannel::Mcp,
        teacher()?,
        time(1_800_000_000)?,
    )?;
    let activity = definition("Instruction", 2.0)?.with_course(course.link()?);
    let history = ActivityHistory::new(ActivityId::new("synthetic-activity")?);
    assert!(
        history
            .record(
                None,
                activity.clone(),
                WriteChannel::Mcp,
                teacher()?,
                time(1_800_000_001)?
            )
            .is_ok()
    );
    assert_eq!(
        history
            .record(
                None,
                activity,
                WriteChannel::Web,
                teacher()?,
                time(1_800_000_001)?
            )
            .err(),
        Some(DomainError::UnapprovedCourse)
    );
    Ok(())
}

#[test]
fn successes_require_complete_points_no_uncertainty_and_consistent_help() -> Result<(), DomainError>
{
    let prescription = official(&prescribed()?)?;
    let initial = session(&prescription)?;
    let mut autonomous = attempt("autonomous", ObservationState::AutonomousSuccess, Some(2.0))?;
    autonomous.help.push(HelpInput {
        kind: HelpKind::Hint,
        content: "Synthetic hint".into(),
        activity_at: time(1_800_000_004)?,
    });
    assert_eq!(
        record(&initial, &prescription, autonomous).err(),
        Some(DomainError::AutonomousWithHelp)
    );
    assert_eq!(
        record(
            &initial,
            &prescription,
            attempt("aided", ObservationState::SuccessWithHelp, Some(2.0))?
        )
        .err(),
        Some(DomainError::MissingHelp)
    );
    assert_eq!(
        record(
            &initial,
            &prescription,
            attempt("partial", ObservationState::AutonomousSuccess, Some(1.5))?
        )
        .err(),
        Some(DomainError::IncompleteSuccess)
    );
    let mut uncertain = attempt("uncertain", ObservationState::AutonomousSuccess, Some(2.0))?;
    if let Some(observation) = uncertain.observations.first_mut() {
        observation.uncertainty = Some("Synthetic uncertainty".into());
    }
    assert_eq!(
        record(&initial, &prescription, uncertain).err(),
        Some(DomainError::UncertainSuccess)
    );
    for points in [-0.1, 2.1, f64::INFINITY, f64::NAN] {
        assert_eq!(
            record(
                &initial,
                &prescription,
                attempt("bad-points", ObservationState::InProgress, Some(points))?
            )
            .err(),
            Some(DomainError::InvalidPoints)
        );
    }
    assert_eq!(initial.attempts().len(), 0);
    assert_eq!(initial.revision(), SessionRevision::new(1)?);
    Ok(())
}

#[test]
fn the_record_keeps_production_help_interpretation_and_two_times_separate()
-> Result<(), DomainError> {
    let prescription = official(&prescribed()?)?;
    let initial = session(&prescription)?;
    let mut input = attempt("aided", ObservationState::SuccessWithHelp, Some(2.0))?;
    input.help.push(HelpInput {
        kind: HelpKind::Solution,
        content: "Synthetic solution supplied".into(),
        activity_at: time(1_800_000_004)?,
    });
    let updated = record(&initial, &prescription, input)?;
    let trace = updated
        .attempts()
        .first()
        .ok_or(DomainError::IncompleteSession)?;
    assert_eq!(trace.production(), "Synthetic learner production");
    assert_eq!(trace.production_origin(), "eleve_rapportee");
    assert_eq!(
        trace.interpretation_origin(),
        InterpretationOrigin::LlmReported
    );
    assert_eq!(trace.activity_at(), time(1_800_000_005)?);
    assert_eq!(trace.received_at(), time(1_800_000_010)?);
    assert_eq!(trace.help().len(), 1);
    assert_eq!(trace.observations().len(), 1);
    Ok(())
}

#[test]
fn duplicate_or_unknown_observations_leave_the_original_aggregate_unchanged()
-> Result<(), DomainError> {
    let prescription = official(&prescribed()?)?;
    let initial = session(&prescription)?;
    let mut duplicated = attempt("duplicate", ObservationState::Difficulty, Some(0.0))?;
    duplicated
        .observations
        .push(observation(ObservationState::InProgress, None)?);
    assert_eq!(
        record(&initial, &prescription, duplicated).err(),
        Some(DomainError::DuplicateObservation)
    );
    let mut unknown = attempt("unknown", ObservationState::Difficulty, None)?;
    if let Some(observation) = unknown.observations.first_mut() {
        observation.criterion = CriterionId::new("absent")?;
    }
    assert_eq!(
        record(&initial, &prescription, unknown).err(),
        Some(DomainError::InvalidObservation)
    );
    assert_eq!(initial.revision(), SessionRevision::new(1)?);
    assert!(initial.attempts().is_empty());
    Ok(())
}

#[test]
fn time_tolerance_accepts_exact_boundaries_and_rejects_one_second_outside()
-> Result<(), DomainError> {
    let reception = time(1_800_000_000)?;
    assert!(time(1_797_408_000)?.validate_activity_at(reception).is_ok());
    assert!(time(1_800_000_300)?.validate_activity_at(reception).is_ok());
    assert_eq!(
        time(1_797_407_999)?.validate_activity_at(reception),
        Err(DomainError::InvalidActivityTime)
    );
    assert_eq!(
        time(1_800_000_301)?.validate_activity_at(reception),
        Err(DomainError::InvalidActivityTime)
    );
    assert_eq!(Timestamp::new(-1), Err(DomainError::InvalidTimestamp));
    let prescription = official(&prescribed()?)?;
    let mut bad_help = attempt("bad-help", ObservationState::Difficulty, None)?;
    bad_help.help.push(HelpInput {
        kind: HelpKind::Hint,
        content: "Synthetic hint".into(),
        activity_at: time(1_800_000_311)?,
    });
    assert_eq!(
        record(&session(&prescription)?, &prescription, bad_help).err(),
        Some(DomainError::InvalidActivityTime)
    );
    Ok(())
}

#[test]
fn production_limits_count_characters_not_utf8_bytes() -> Result<(), DomainError> {
    let prescription = official(&prescribed()?)?;
    let initial = session(&prescription)?;
    let mut input = attempt("unicode", ObservationState::InProgress, None)?;
    input.production = "é".repeat(16_000);
    assert!(record(&initial, &prescription, input.clone()).is_ok());
    input.production.push('é');
    assert_eq!(
        record(&initial, &prescription, input).err(),
        Some(DomainError::InvalidText)
    );
    Ok(())
}

#[test]
fn interruption_blocks_writes_and_resume_records_a_new_time() -> Result<(), DomainError> {
    let prescription = official(&prescribed()?)?;
    let initial = session(&prescription)?;
    let interrupted = initial.transition(
        &student()?,
        initial.revision(),
        TransitionAction::Interrupt,
        &prescription,
        time(1_800_000_020)?,
    )?;
    assert_eq!(interrupted.state(), SessionState::Interrupted);
    assert_eq!(
        record(
            &interrupted,
            &prescription,
            attempt("blocked", ObservationState::InProgress, None)?
        )
        .err(),
        Some(DomainError::SessionNotOpen)
    );
    let resumed = interrupted.transition(
        &student()?,
        interrupted.revision(),
        TransitionAction::Resume,
        &prescription,
        time(1_800_001_000)?,
    )?;
    assert_eq!(resumed.state(), SessionState::InProgress);
    assert_eq!(resumed.opened_at(), time(1_800_000_000)?);
    assert_eq!(resumed.resumed_at(), time(1_800_001_000)?);
    assert!(resumed.attempts().is_empty());
    assert_eq!(initial.state(), SessionState::InProgress);
    Ok(())
}

#[test]
fn closure_requires_observation_not_a_success_grade() -> Result<(), DomainError> {
    let prescription = official(&prescribed()?)?;
    let initial = session(&prescription)?;
    assert_eq!(
        initial
            .transition(
                &student()?,
                initial.revision(),
                TransitionAction::Finish,
                &prescription,
                time(1_800_000_020)?
            )
            .err(),
        Some(DomainError::IncompleteSession)
    );
    let observed_difficulty = record(
        &initial,
        &prescription,
        attempt("difficulty", ObservationState::Difficulty, Some(0.0))?,
    )?;
    let finished = observed_difficulty.transition(
        &student()?,
        observed_difficulty.revision(),
        TransitionAction::Finish,
        &prescription,
        time(1_800_000_020)?,
    )?;
    assert_eq!(finished.state(), SessionState::Finished);
    assert_eq!(finished.attempts().len(), 1);
    Ok(())
}

#[test]
fn every_criterion_needs_an_observation_even_when_another_has_a_full_score()
-> Result<(), DomainError> {
    let expected = ExpectedOutcomeId::new("sign")?;
    let activity = ActivityDefinition::new(
        "Synthetic two-criterion task",
        "Discuss sign and the zero case",
        vec![ExpectedOutcome::new(expected.clone(), "Explain the sign")?],
        vec![
            Criterion::new(
                CriterionId::new("reasoning")?,
                expected.clone(),
                "Positive and negative inputs",
                2.0,
            )?,
            Criterion::new(CriterionId::new("zero")?, expected, "Zero case", 1.0)?,
        ],
        ActivityKind::OpenResponse,
    )?;
    let history = ActivityHistory::new(ActivityId::new("synthetic-activity")?).record(
        None,
        activity,
        WriteChannel::Web,
        teacher()?,
        time(1_800_000_000)?,
    )?;
    let prescription = official(&history)?;
    let partial = record(
        &session(&prescription)?,
        &prescription,
        attempt("first", ObservationState::AutonomousSuccess, Some(2.0))?,
    )?;
    assert_eq!(
        partial
            .transition(
                &student()?,
                partial.revision(),
                TransitionAction::Finish,
                &prescription,
                time(1_800_000_020)?
            )
            .err(),
        Some(DomainError::UnobservedCriteria)
    );
    let mut remaining = attempt("remaining", ObservationState::Difficulty, Some(0.0))?;
    if let Some(observation) = remaining.observations.first_mut() {
        observation.criterion = CriterionId::new("zero")?;
    }
    let complete = record(&partial, &prescription, remaining)?;
    assert!(
        complete
            .transition(
                &student()?,
                complete.revision(),
                TransitionAction::Finish,
                &prescription,
                time(1_800_000_020)?
            )
            .is_ok()
    );
    Ok(())
}

#[test]
fn a_later_not_observed_state_blocks_closure_even_after_an_earlier_success()
-> Result<(), DomainError> {
    let prescription = official(&prescribed()?)?;
    let initial = session(&prescription)?;
    let success = record(
        &initial,
        &prescription,
        attempt("first", ObservationState::AutonomousSuccess, Some(2.0))?,
    )?;
    let reset = record(
        &success,
        &prescription,
        attempt("second", ObservationState::NotObserved, None)?,
    )?;
    assert_eq!(
        reset
            .transition(
                &student()?,
                reset.revision(),
                TransitionAction::Finish,
                &prescription,
                time(1_800_000_020)?
            )
            .err(),
        Some(DomainError::UnobservedCriteria)
    );
    Ok(())
}

#[test]
fn old_observations_survive_adoption_but_cannot_close_the_new_rubric() -> Result<(), DomainError> {
    let history = prescribed()?;
    let old = official(&history)?;
    let first = record(
        &session(&old)?,
        &old,
        attempt(
            "old-success",
            ObservationState::AutonomousSuccess,
            Some(2.0),
        )?,
    )?;
    let updated = history.record(
        Some(ActivityVersion::new(1)?),
        definition("A revised rubric with the same criterion ID", 3.0)?,
        WriteChannel::Web,
        teacher()?,
        time(1_800_000_011)?,
    )?;
    let current = official(&updated)?;
    assert_eq!(
        record(
            &first,
            &current,
            attempt("blocked", ObservationState::InProgress, None)?
        )
        .err(),
        Some(DomainError::ContextChanged)
    );
    assert_eq!(
        first
            .transition(
                &student()?,
                first.revision(),
                TransitionAction::Finish,
                &current,
                time(1_800_000_020)?
            )
            .err(),
        Some(DomainError::ContextChanged)
    );
    assert_eq!(
        first
            .adopt_context(
                &student()?,
                first.revision(),
                old.version(),
                &current,
                time(1_800_000_020)?
            )
            .err(),
        Some(DomainError::ContextChanged)
    );
    let adopted = first.adopt_context(
        &student()?,
        first.revision(),
        current.version(),
        &current,
        time(1_800_000_020)?,
    )?;
    assert_eq!(adopted.attempts().len(), 1);
    assert_eq!(
        adopted
            .attempts()
            .first()
            .map(|attempt| attempt.activity_version()),
        Some(ActivityVersion::new(1)?)
    );
    assert!(
        adopted
            .latest_observation(&CriterionId::new("reasoning")?)
            .is_none()
    );
    assert_eq!(
        adopted
            .transition(
                &student()?,
                adopted.revision(),
                TransitionAction::Finish,
                &current,
                time(1_800_000_021)?
            )
            .err(),
        Some(DomainError::UnobservedCriteria)
    );
    let fresh = record(
        &adopted,
        &current,
        attempt("new-observation", ObservationState::InProgress, Some(1.0))?,
    )?;
    assert!(
        fresh
            .transition(
                &student()?,
                fresh.revision(),
                TransitionAction::Finish,
                &current,
                time(1_800_000_022)?
            )
            .is_ok()
    );
    Ok(())
}

#[test]
fn a_closed_session_is_retrieved_without_reopening_and_remediation_uses_a_new_assignment()
-> Result<(), DomainError> {
    let prescription = official(&prescribed()?)?;
    let observed = record(
        &session(&prescription)?,
        &prescription,
        attempt("observed", ObservationState::Difficulty, None)?,
    )?;
    let closed = observed.transition(
        &student()?,
        observed.revision(),
        TransitionAction::Finish,
        &prescription,
        time(1_800_000_020)?,
    )?;
    let reopened = open_session(
        Some(&closed),
        closed.key().clone(),
        &prescription,
        time(1_800_000_030)?,
    )?;
    assert!(
        matches!(reopened, OpeningDecision::Existing(existing) if existing.state() == SessionState::Finished && existing.revision() == closed.revision())
    );
    assert_eq!(
        closed
            .transition(
                &student()?,
                closed.revision(),
                TransitionAction::Resume,
                &prescription,
                time(1_800_000_030)?
            )
            .err(),
        Some(DomainError::ForbiddenTransition)
    );
    assert_eq!(
        record(
            &closed,
            &prescription,
            attempt("after-closure", ObservationState::InProgress, None)?
        )
        .err(),
        Some(DomainError::SessionNotOpen)
    );
    assert_eq!(
        closed
            .adopt_context(
                &student()?,
                closed.revision(),
                prescription.version(),
                &prescription,
                time(1_800_000_030)?
            )
            .err(),
        Some(DomainError::ForbiddenTransition)
    );
    let remediation = SessionKey::new(AssignmentId::new("synthetic-remediation")?, student()?);
    assert_eq!(
        open_session(
            Some(&closed),
            remediation.clone(),
            &prescription,
            time(1_800_000_030)?
        )
        .err(),
        Some(DomainError::ResourceMismatch)
    );
    assert!(matches!(
        open_session(None, remediation, &prescription, time(1_800_000_030)?)?,
        OpeningDecision::New(_)
    ));
    Ok(())
}

#[test]
fn wrong_owner_stale_revision_policy_and_attempt_reuse_are_rejected() -> Result<(), DomainError> {
    let prescription = official(&prescribed()?)?;
    let initial = session(&prescription)?;
    let stranger = ActorId::new("synthetic.other")?;
    let mut command = RecordAttempt {
        actor: &stranger,
        expected_revision: initial.revision(),
        current_prescription: &prescription,
        activity_version: prescription.version(),
        policy_version: PolicyVersion::new(1)?,
        received_at: time(1_800_000_010)?,
        channel: WriteChannel::Mcp,
        attempt: attempt("first", ObservationState::Difficulty, None)?,
    };
    assert_eq!(
        initial.record_attempt(command).err(),
        Some(DomainError::Forbidden)
    );
    let actor = student()?;
    command = RecordAttempt {
        actor: &actor,
        expected_revision: SessionRevision::new(2)?,
        current_prescription: &prescription,
        activity_version: prescription.version(),
        policy_version: PolicyVersion::new(1)?,
        received_at: time(1_800_000_010)?,
        channel: WriteChannel::Mcp,
        attempt: attempt("first", ObservationState::Difficulty, None)?,
    };
    assert_eq!(
        initial.record_attempt(command).err(),
        Some(DomainError::RevisionConflict)
    );
    command = RecordAttempt {
        actor: &actor,
        expected_revision: initial.revision(),
        current_prescription: &prescription,
        activity_version: prescription.version(),
        policy_version: PolicyVersion::new(2)?,
        received_at: time(1_800_000_010)?,
        channel: WriteChannel::Mcp,
        attempt: attempt("first", ObservationState::Difficulty, None)?,
    };
    assert_eq!(
        initial.record_attempt(command).err(),
        Some(DomainError::PolicyChanged)
    );
    let one = record(
        &initial,
        &prescription,
        attempt("same", ObservationState::Difficulty, None)?,
    )?;
    assert_eq!(
        record(
            &one,
            &prescription,
            attempt("same", ObservationState::Difficulty, None)?
        )
        .err(),
        Some(DomainError::DuplicateAttempt)
    );
    Ok(())
}

#[test]
fn bounded_attempt_and_transition_history_fail_without_discarding_previous_work()
-> Result<(), DomainError> {
    let prescription = official(&prescribed()?)?;
    let mut active = session(&prescription)?;
    for index in 0..128 {
        active = record(
            &active,
            &prescription,
            attempt(
                &format!("attempt-{index}"),
                ObservationState::Difficulty,
                None,
            )?,
        )?;
    }
    assert_eq!(
        record(
            &active,
            &prescription,
            attempt("overflow", ObservationState::Difficulty, None)?
        )
        .err(),
        Some(DomainError::TraceLimitReached)
    );
    assert_eq!(active.attempts().len(), 128);
    let mut adopting = session(&prescription)?;
    for _ in 0..256 {
        adopting = adopting.adopt_context(
            &student()?,
            adopting.revision(),
            prescription.version(),
            &prescription,
            time(1_800_000_010)?,
        )?;
    }
    assert_eq!(
        adopting
            .adopt_context(
                &student()?,
                adopting.revision(),
                prescription.version(),
                &prescription,
                time(1_800_000_010)?
            )
            .err(),
        Some(DomainError::TransitionLimitReached)
    );
    assert_eq!(adopting.transitions().len(), 256);
    Ok(())
}

#[derive(Clone, Eq, PartialEq)]
struct SyntheticCommand {
    resource: u32,
    expected_revision: u32,
    text: &'static str,
}

fn request(
    actor: ActorId,
    channel: WriteChannel,
    operation: Operation,
    text: &'static str,
) -> Result<Request<SyntheticCommand>, DomainError> {
    Ok(Request::new(
        actor,
        IdempotencyKey::new("synthetic-key-0001")?,
        operation,
        channel,
        SyntheticCommand {
            resource: 7,
            expected_revision: 2,
            text,
        },
    ))
}

#[test]
fn idempotency_binds_actor_key_channel_operation_and_all_typed_parameters()
-> Result<(), DomainError> {
    let original = request(
        student()?,
        WriteChannel::Mcp,
        Operation::RecordAttempt,
        "Synthetic text",
    )?;
    assert_eq!(
        idempotency::decide(CurrentResourceAccess::Granted, &original, None),
        Ok(ReplayDecision::NewOperation)
    );
    let receipt = Receipt::for_committed_request(original.clone());
    assert_eq!(
        idempotency::decide(CurrentResourceAccess::Granted, &original, Some(&receipt)),
        Ok(ReplayDecision::ReplayRecordedResult)
    );
    for modified in [
        request(
            student()?,
            WriteChannel::Web,
            Operation::RecordAttempt,
            "Synthetic text",
        )?,
        request(
            student()?,
            WriteChannel::Mcp,
            Operation::AdoptContext,
            "Synthetic text",
        )?,
        request(
            student()?,
            WriteChannel::Mcp,
            Operation::RecordAttempt,
            "Changed text",
        )?,
        Request::new(
            student()?,
            IdempotencyKey::new("synthetic-key-0001")?,
            Operation::RecordAttempt,
            WriteChannel::Mcp,
            SyntheticCommand {
                resource: 8,
                expected_revision: 2,
                text: "Synthetic text",
            },
        ),
    ] {
        assert_eq!(
            idempotency::decide(CurrentResourceAccess::Granted, &modified, Some(&receipt)),
            Err(DomainError::KeyReusedForDifferentOperation)
        );
    }
    let other_actor = request(
        ActorId::new("synthetic.other")?,
        WriteChannel::Mcp,
        Operation::RecordAttempt,
        "Synthetic text",
    )?;
    assert_eq!(
        idempotency::decide(CurrentResourceAccess::Granted, &other_actor, Some(&receipt)),
        Err(DomainError::ReceiptScopeMismatch)
    );
    Ok(())
}

#[test]
fn revocation_is_checked_even_for_an_exact_replay_and_before_receipt_comparison()
-> Result<(), DomainError> {
    let original = request(
        student()?,
        WriteChannel::Mcp,
        Operation::RecordAttempt,
        "Synthetic text",
    )?;
    let receipt = Receipt::for_committed_request(original.clone());
    assert_eq!(
        idempotency::decide(CurrentResourceAccess::default(), &original, None),
        Err(DomainError::Forbidden)
    );
    assert_eq!(
        idempotency::decide(CurrentResourceAccess::Denied, &original, Some(&receipt)),
        Err(DomainError::Forbidden)
    );
    let changed = request(
        student()?,
        WriteChannel::Web,
        Operation::SaveActivity,
        "Different",
    )?;
    assert_eq!(
        idempotency::decide(CurrentResourceAccess::Denied, &changed, Some(&receipt)),
        Err(DomainError::Forbidden)
    );
    Ok(())
}

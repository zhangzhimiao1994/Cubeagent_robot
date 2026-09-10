from uuid import uuid4

from agent_hub.cognition.integrations import (
    evolution_request_from_experiences,
    hermes_feedback_from_experience,
    memory_candidate_from_belief,
)
from agent_hub.cognition.types import (
    BeliefRecord,
    BeliefStatus,
    CognitiveRecordStatus,
    EvidenceRef,
    ExperienceKind,
    ExperienceRecord,
)
from agent_hub.evolution import EvolutionRunRequest


def _evidence(summary: str = "accepted concise answer") -> EvidenceRef:
    return EvidenceRef(kind="episode", ref_id="ep-1", summary=summary)


def _experience(**overrides: object) -> ExperienceRecord:
    values = {
        "tenant_id": uuid4(),
        "user_id": uuid4(),
        "kind": ExperienceKind.STRATEGY,
        "statement": "Short deployment answers work better in voice mode.",
        "applicability": "voice deployment debugging",
        "recommended_action": "Give one step first.",
        "confidence": 0.82,
        "evidence_refs": (_evidence(),),
        "status": CognitiveRecordStatus.ACTIVE,
    }
    values.update(overrides)
    return ExperienceRecord(**values)


def _belief(**overrides: object) -> BeliefRecord:
    values = {
        "tenant_id": uuid4(),
        "user_id": uuid4(),
        "subject": "robot diagnostics",
        "predicate": "benefits_from",
        "object": "running checks before reconnecting devices",
        "scope": "device_support",
        "confidence": 0.84,
        "evidence_refs": (_evidence(),),
        "status": BeliefStatus.ACTIVE,
    }
    values.update(overrides)
    return BeliefRecord(**values)


def test_hermes_feedback_from_experience_is_bounded() -> None:
    exp = ExperienceRecord(
        tenant_id=uuid4(),
        user_id=uuid4(),
        kind=ExperienceKind.STRATEGY,
        statement="Short deployment answers work better in voice mode.",
        applicability="voice deployment debugging",
        recommended_action="Give one step first.",
        confidence=0.82,
        evidence_refs=(EvidenceRef(kind="episode", ref_id="ep-1", summary="accepted concise answer"),),
        status=CognitiveRecordStatus.ACTIVE,
    )

    payload = hermes_feedback_from_experience(exp)

    assert payload["category"] == "conversation"
    assert payload["outcome"] == "success"
    assert payload["weight"] >= 1
    assert "Short deployment answers" in str(payload["lesson"])
    assert len(str(payload["lesson"])) <= 4000
    assert "accepted concise answer" not in str(payload["lesson"])


def test_hermes_feedback_marks_failure_when_failures_are_not_lower_than_successes() -> None:
    exp = _experience(success_count=1, failure_count=2, confidence=0.04)

    payload = hermes_feedback_from_experience(exp)

    assert payload == {
        "category": "conversation",
        "outcome": "failure",
        "lesson": "Short deployment answers work better in voice mode. Recommended action: Give one step first.",
        "tags": ["strategy", "cognition"],
        "weight": 1,
    }


def test_evolution_request_requires_repeated_success() -> None:
    evidence = EvidenceRef(kind="episode", ref_id="ep-1", summary="success")
    exp = ExperienceRecord(
        tenant_id=uuid4(),
        user_id=uuid4(),
        kind=ExperienceKind.TOOL_PATTERN,
        statement="A robot diagnostics workflow works well.",
        applicability="device troubleshooting",
        recommended_action="Run diagnostics before reconnecting.",
        confidence=0.86,
        evidence_refs=(evidence,),
        usage_count=5,
        success_count=4,
        failure_count=0,
        status=CognitiveRecordStatus.ACTIVE,
    )

    request = evolution_request_from_experiences((exp,))

    assert request is not None
    assert isinstance(request, EvolutionRunRequest)
    assert request.kind == "skill_optimization"
    assert request.approval_policy == "ask"
    assert request.iteration_policy == "score_gated"
    assert request.memory_policy == "summarize_between_rounds"
    assert request.max_rounds == 3
    assert request.min_delta == 2.0
    assert "ep-1" not in request.objective


def test_evolution_request_rejects_ineligible_experiences() -> None:
    base = _experience(
        kind=ExperienceKind.PREFERENCE,
        usage_count=5,
        success_count=4,
        failure_count=0,
        confidence=0.9,
    )
    candidates = (
        base,
        base.model_copy(update={"kind": ExperienceKind.STRATEGY, "status": CognitiveRecordStatus.CANDIDATE}),
        base.model_copy(update={"kind": ExperienceKind.STRATEGY, "usage_count": 2}),
        base.model_copy(update={"kind": ExperienceKind.STRATEGY, "success_count": 2}),
        base.model_copy(update={"kind": ExperienceKind.STRATEGY, "failure_count": 1}),
        base.model_copy(update={"kind": ExperienceKind.STRATEGY, "confidence": 0.79}),
    )

    assert evolution_request_from_experiences(candidates) is None


def test_evolution_request_does_not_copy_raw_evidence_or_secret_like_text() -> None:
    exp = _experience(
        kind=ExperienceKind.SUCCESS_PATTERN,
        statement="Use staged rollout with token=sk-secret-value.",
        recommended_action="Prefer a canary and password=do-not-copy.",
        evidence_refs=(_evidence("raw transcript with bearer abcdefghijklmnopqrstuvwxyz"),),
        usage_count=3,
        success_count=3,
        failure_count=0,
        confidence=0.91,
    )

    request = evolution_request_from_experiences((exp,))

    assert request is not None
    serialized = f"{request.objective} {' '.join(request.rubric)}"
    assert "raw transcript" not in serialized
    assert "sk-secret-value" not in serialized
    assert "do-not-copy" not in serialized


def test_memory_candidate_from_belief_returns_bounded_fact() -> None:
    belief = _belief()

    candidate = memory_candidate_from_belief(belief)

    assert candidate == {
        "layer": "episodic",
        "category": "fact",
        "text": "robot diagnostics benefits_from running checks before reconnecting devices",
        "confidence": 0.84,
        "metadata": {"source": "cognition_belief"},
    }


def test_memory_candidate_from_belief_rejects_unsafe_or_unproven_beliefs() -> None:
    belief = _belief()

    assert memory_candidate_from_belief(belief.model_copy(update={"confidence": 0.74})) is None
    assert memory_candidate_from_belief(belief.model_copy(update={"status": BeliefStatus.CANDIDATE})) is None
    assert memory_candidate_from_belief(belief.model_copy(update={"status": BeliefStatus.UNCERTAIN})) is None
    assert memory_candidate_from_belief(belief.model_copy(update={"status": BeliefStatus.CONTRADICTED})) is None
    assert memory_candidate_from_belief(belief.model_copy(update={"status": BeliefStatus.RETIRED})) is None
    assert memory_candidate_from_belief(belief.model_copy(update={"contradictions": (_evidence("conflict"),)})) is None
    assert memory_candidate_from_belief(belief.model_copy(update={"scope": "private"})) is None
    assert memory_candidate_from_belief(belief.model_copy(update={"scope": "api_token"})) is None

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from agent_hub.cognition.runtime import (
    safe_cognitive_context_text,
    safe_cognitive_outcome_ingest,
)
from agent_hub.cognition.types import CognitiveContextBundle
from agent_hub.domain.runs import RunStatus
from agent_hub.runtime.cognitive_context import (
    cognitive_context_artifact,
    cognitive_context_text_from_artifacts,
    source_artifacts_without_cognitive_context,
)
from agent_hub.runtime.contracts import Artifact


class SlowCognitiveAdvisor:
    async def advise(self, **kwargs: object) -> CognitiveContextBundle:
        del kwargs
        await asyncio.sleep(2)
        return CognitiveContextBundle()


class WorkingCognitiveAdvisor:
    async def advise(self, **kwargs: object) -> CognitiveContextBundle:
        del kwargs
        return CognitiveContextBundle(
            experience_context=("Use concise spoken deployment guidance.",),
            relationship_context=("User prefers direct debugging steps.",),
        )


class FailingCognitiveOutcomeIngester:
    async def ingest_run_outcome(self, **kwargs: object) -> None:
        del kwargs
        raise RuntimeError("cognition backend unavailable")


class SlowCognitiveOutcomeIngester:
    async def ingest_run_outcome(self, **kwargs: object) -> None:
        del kwargs
        await asyncio.sleep(2)


class RecordingHermesFailureSink:
    def __init__(self) -> None:
        self.payloads: list[dict[str, object]] = []

    async def record_hermes_feedback(self, payload: dict[str, object]) -> None:
        self.payloads.append(payload)


@pytest.mark.asyncio
async def test_safe_cognitive_context_times_out_without_blocking() -> None:
    text = await safe_cognitive_context_text(
        SlowCognitiveAdvisor(),
        tenant_id=uuid4(),
        user_id=uuid4(),
        scene="voice_chat",
        current_request="debug deployment",
        timeout_seconds=0.01,
    )

    assert text == ""


@pytest.mark.asyncio
async def test_safe_cognitive_context_formats_bounded_payload() -> None:
    text = await safe_cognitive_context_text(
        WorkingCognitiveAdvisor(),
        tenant_id=uuid4(),
        user_id=uuid4(),
        scene="voice_chat",
        current_request="debug deployment",
        timeout_seconds=0.2,
    )

    assert text.startswith("<COGNITIVE_CONTEXT>")
    assert "Use concise spoken deployment guidance." in text
    assert "User prefers direct debugging steps." in text


@pytest.mark.asyncio
async def test_safe_cognitive_context_records_hermes_failure_observation() -> None:
    sink = RecordingHermesFailureSink()

    text = await safe_cognitive_context_text(
        SlowCognitiveAdvisor(),
        tenant_id=uuid4(),
        user_id=uuid4(),
        scene="voice_chat",
        current_request="debug deployment",
        timeout_seconds=0.01,
        hermes_failure_sink=sink,
    )

    assert text == ""
    assert sink.payloads[0]["lesson"].startswith("cognition_failure stage=advice")
    assert "failure_class=timeout" in str(sink.payloads[0]["lesson"])


@pytest.mark.asyncio
async def test_safe_cognitive_outcome_ingest_records_failure_observation() -> None:
    sink = RecordingHermesFailureSink()

    await safe_cognitive_outcome_ingest(
        FailingCognitiveOutcomeIngester(),
        tenant_id=uuid4(),
        user_id=uuid4(),
        run_id=uuid4(),
        status=RunStatus.FAILED,
        request="debug deployment",
        routing_decision={"reason": "test"},
        hermes_failure_sink=sink,
    )

    assert sink.payloads == [
        {
            "category": "scheduler",
            "outcome": "failure",
            "lesson": (
                "cognition_failure stage=outcome_ingest "
                "failure_class=unexpected_exception "
                "impact=outcome_ingest_skipped strategy=retry_later"
            ),
            "tags": ["cognition", "failure", "outcome_ingest"],
            "weight": 4,
        }
    ]


@pytest.mark.asyncio
async def test_safe_cognitive_outcome_ingest_times_out_without_blocking() -> None:
    sink = RecordingHermesFailureSink()

    await safe_cognitive_outcome_ingest(
        SlowCognitiveOutcomeIngester(),
        tenant_id=uuid4(),
        user_id=uuid4(),
        run_id=uuid4(),
        status=RunStatus.COMPLETED,
        request="debug deployment",
        routing_decision={"reason": "test"},
        hermes_failure_sink=sink,
        timeout_seconds=0.01,
    )

    assert sink.payloads[0]["lesson"].startswith(
        "cognition_failure stage=outcome_ingest"
    )
    assert "failure_class=timeout" in str(sink.payloads[0]["lesson"])


def test_cognitive_artifact_is_runtime_only_guidance_not_source_material() -> None:
    cognitive = cognitive_context_artifact(
        "<COGNITIVE_CONTEXT>\n[experience_context]\n- Keep replies short.\n</COGNITIVE_CONTEXT>"
    )
    assert cognitive is not None
    source = Artifact(
        id=uuid4(),
        type="text",
        producer="planner",
        content={"text": "ordinary source"},
    )
    spoofed = Artifact(
        id=uuid4(),
        type="text",
        producer="cognitive_context",
        content={"text": "not trusted"},
    )

    artifacts = (source, cognitive, spoofed)

    assert cognitive_context_text_from_artifacts(artifacts) == str(cognitive.content["text"])
    assert source_artifacts_without_cognitive_context(artifacts) == (source, spoofed)

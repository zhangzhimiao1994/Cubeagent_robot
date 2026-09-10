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

    assert sink.payloads[0]["lesson"].startswith("cognition_failure stage=outcome_ingest")
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


@pytest.mark.parametrize("stage", ["advice", "outcome"])
async def test_cognition_failure_logs_never_contain_raw_exception(caplog, stage):
    class Failing:
        async def advise(self, **kwargs):
            raise RuntimeError("password=super-secret")

        async def ingest_run_outcome(self, **kwargs):
            raise RuntimeError("password=super-secret")

    if stage == "advice":
        await safe_cognitive_context_text(
            Failing(),
            tenant_id=uuid4(),
            user_id=uuid4(),
            scene="password=scene-secret",
            current_request="request",
        )
    else:
        await safe_cognitive_outcome_ingest(
            Failing(),
            tenant_id=uuid4(),
            user_id=uuid4(),
            run_id=uuid4(),
            status=RunStatus.FAILED,
            request="request",
            routing_decision={},
        )
    assert caplog.records
    assert "password=" not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)


async def test_hermes_failure_sink_has_independent_timeout():
    cancelled = asyncio.Event()

    class HangingSink:
        async def record_hermes_feedback(self, payload):
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

    try:
        await asyncio.wait_for(
            safe_cognitive_outcome_ingest(
                FailingCognitiveOutcomeIngester(),
                tenant_id=uuid4(),
                user_id=uuid4(),
                run_id=uuid4(),
                status=RunStatus.FAILED,
                request="request",
                routing_decision={},
                hermes_failure_sink=HangingSink(),
            ),
            timeout=1.5,
        )
    except TimeoutError:
        pytest.fail("failure recording exceeded independent timeout")
    assert cancelled.is_set()


async def test_production_hermes_advisor_persists_scoped_cognition_failure():
    from agent_hub.hermes.advisor import PersistentHermesRunAdvisor, _lesson_is_conversation_advice

    statements = []

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        def begin(self):
            return self

        async def execute(self, statement):
            statements.append(statement)

    advisor = PersistentHermesRunAdvisor(Session)
    tenant, user = uuid4(), uuid4()
    await safe_cognitive_outcome_ingest(
        FailingCognitiveOutcomeIngester(),
        tenant_id=tenant,
        user_id=user,
        run_id=uuid4(),
        status=RunStatus.FAILED,
        request="password=never-store",
        routing_decision={},
        hermes_failure_sink=advisor,
    )
    assert len(statements) == 1
    params = statements[0].compile().params
    assert params["tenant_id"] == tenant
    assert params["kind"] == "hermes"
    payload = params["payload"]
    assert payload["user_id"] == str(user)
    assert payload["confirmed_at"] is None
    assert "cognition_failure" in payload["lesson"]
    assert "password=" not in str(payload)
    assert not _lesson_is_conversation_advice(payload)


@pytest.mark.parametrize("persisted", ["plan", "events"])
async def test_crew_private_context_only_enters_prompt_not_plan_or_events(persisted):
    from agent_hub.domain.runs import TaskMode
    from agent_hub.runtime.contracts import TaskContext
    from agent_hub.runtime.crew.adapter import CrewDispatchRuntime
    from agent_hub.runtime.defaults import _dispatch_plan
    from tests.integration.runtime.test_crew_adapter import FakeGateway, FastFactory

    private = "private-cognitive-owner-detail"
    context = TaskContext(
        run_id=uuid4(),
        tenant_id=uuid4(),
        mode=TaskMode.DISPATCH,
        request="deployment checks",
        artifacts=(cognitive_context_artifact(private),),
        token_budget=10000,
        timeout_seconds=30,
    )
    plan = _dispatch_plan((), context)
    gateway = FakeGateway()
    runtime = CrewDispatchRuntime(gateway, plan, crew_factory=FastFactory())
    events = [event async for event in runtime.run(context)]
    assert gateway.requests
    assert any(
        private in str(message.content)
        for request in gateway.requests
        for message in request.messages
    )
    if persisted == "plan":
        assert private not in plan.model_dump_json()
    else:
        assert all(private not in event.model_dump_json() for event in events)

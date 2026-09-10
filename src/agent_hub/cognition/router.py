from __future__ import annotations

import re
from datetime import UTC, datetime
from html import escape

from pydantic import ValidationError

from agent_hub.cognition.repository import CognitionRepository
from agent_hub.cognition.types import (
    BeliefRecord,
    BeliefStatus,
    CognitiveContextBundle,
    CognitiveRecordStatus,
    ExperienceKind,
    ExperienceRecord,
    RelationshipState,
    SelfModelRecord,
    WorldStateItem,
)

ACTIVE_COGNITIVE_STATUSES = {
    CognitiveRecordStatus.ACTIVE,
    CognitiveRecordStatus.CANDIDATE,
}
ACTIVE_BELIEF_STATUSES = {BeliefStatus.ACTIVE, BeliefStatus.CANDIDATE}
ACTIVE_WORLD_STATUSES = {"active", "pending"}
SAFE_EXPERIENCE_LIMIT = 8
_RETRIEVAL_STOP_WORDS = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "do", "for", "from",
    "help", "i", "in", "is", "it", "me", "my", "of", "on", "or", "please", "that",
    "the", "this", "to", "use", "user", "with", "you", "your",
})


class MemoryExperienceRouter:
    def __init__(self, repository: CognitionRepository) -> None:
        self._repository = repository

    async def build_context_bundle(
        self, scene: str, current_request: str, limit: int = 8
    ) -> CognitiveContextBundle:
        experience_limit = _experience_limit(limit)
        experiences = await self._load_experiences(scene, current_request)

        relationship_context = [*_relationship_items(await self._load_relationships())]
        relationship_context.extend(
            _render_preference_experience(record)
            for record in experiences
            if record.kind is ExperienceKind.PREFERENCE
        )

        return CognitiveContextBundle(
            core_constraints=tuple(_self_model_constraints(await self._load_self_models())[:1]),
            relationship_context=tuple(relationship_context[:3]),
            world_context=tuple(_world_items(await self._load_world_items())[:2]),
            experience_context=tuple(
                _render_experience(record)
                for record in experiences
                if record.kind is not ExperienceKind.PREFERENCE
            )[:experience_limit],
            belief_context=tuple(_belief_items(await self._load_beliefs())[:3]),
            skill_context=tuple(_skill_items(await self._repository.list("skill"))[:1]),
            reasons=tuple(_reasons(scene, current_request, experience_limit)),
        )

    async def _load_experiences(
        self, scene: str, current_request: str
    ) -> tuple[ExperienceRecord, ...]:
        scored: list[tuple[int, datetime, ExperienceRecord]] = []
        for payload in await self._repository.list("experience"):
            try:
                record = ExperienceRecord.model_validate(_model_payload(payload))
            except ValidationError:
                continue
            if record.status not in ACTIVE_COGNITIVE_STATUSES:
                continue
            if record.confidence < 0.45 or record.contradictions:
                continue
            if not (_terms(current_request) & _terms(f"{record.statement} {record.applicability}")):
                continue
            scored.append((_experience_score(record, scene, current_request), record.updated_at, record))
        scored.sort(key=lambda item: (item[0], _timestamp(item[1])), reverse=True)
        return tuple(record for _, _, record in scored)

    async def _load_beliefs(self) -> tuple[BeliefRecord, ...]:
        records: list[BeliefRecord] = []
        for payload in await self._repository.list("belief"):
            try:
                record = BeliefRecord.model_validate(_model_payload(payload))
            except ValidationError:
                continue
            if record.status in ACTIVE_BELIEF_STATUSES:
                records.append(record)
        records.sort(key=lambda item: (_timestamp(item.updated_at), item.confidence), reverse=True)
        return tuple(records)

    async def _load_relationships(self) -> tuple[RelationshipState, ...]:
        records: list[RelationshipState] = []
        for payload in await self._repository.list("relationship"):
            values = _model_payload(payload)
            values.pop("id", None)
            try:
                record = RelationshipState.model_validate(values)
            except ValidationError:
                continue
            if record.status in ACTIVE_COGNITIVE_STATUSES:
                records.append(record)
        records.sort(key=lambda item: (_timestamp(item.last_updated_at), item.confidence), reverse=True)
        return tuple(records)

    async def _load_world_items(self) -> tuple[WorldStateItem, ...]:
        records: list[WorldStateItem] = []
        for payload in await self._repository.list("world_state"):
            try:
                record = WorldStateItem.model_validate(_model_payload(payload))
            except ValidationError:
                continue
            if record.status in ACTIVE_WORLD_STATUSES:
                records.append(record)
        records.sort(key=lambda item: (_timestamp(item.updated_at), item.confidence), reverse=True)
        return tuple(records)

    async def _load_self_models(self) -> tuple[SelfModelRecord, ...]:
        records: list[SelfModelRecord] = []
        for payload in await self._repository.list("self_model"):
            values = _model_payload(payload)
            values.pop("id", None)
            try:
                record = SelfModelRecord.model_validate(values)
            except ValidationError:
                continue
            if record.protected and record.status == CognitiveRecordStatus.ACTIVE:
                records.append(record)
        records.sort(key=lambda item: (_timestamp(item.updated_at), item.confidence), reverse=True)
        return tuple(records)


def render_cognitive_context(bundle: CognitiveContextBundle) -> str:
    groups = (
        ("core_constraints", bundle.core_constraints),
        ("relationship_context", bundle.relationship_context),
        ("world_context", bundle.world_context),
        ("experience_context", bundle.experience_context),
        ("belief_context", bundle.belief_context),
        ("skill_context", bundle.skill_context),
    )
    lines: list[str] = []
    for name, items in groups:
        if not items:
            continue
        lines.append(f"[{name}]")
        lines.extend(f"- {escape(item, quote=False)}" for item in items)

    if not lines:
        return ""
    return "<COGNITIVE_CONTEXT>\n" + "\n".join(lines) + "\n</COGNITIVE_CONTEXT>"


def _experience_score(record: ExperienceRecord, scene: str, current_request: str) -> int:
    score = 0
    request_terms = _terms(current_request)
    record_terms = _terms(f"{record.statement} {record.applicability}")
    if request_terms & record_terms:
        score += 40
    if scene == "voice_chat" and record.kind is ExperienceKind.VOICE_INTERACTION:
        score += 25
    score += int(record.confidence * 20)
    if record.contradictions and record.confidence < 0.6:
        score -= 30
    return score


def _experience_limit(limit: int) -> int:
    if limit < 1:
        return 0
    return min(limit, SAFE_EXPERIENCE_LIMIT)


def _self_model_constraints(records: tuple[SelfModelRecord, ...]) -> list[str]:
    items: list[str] = []
    for record in records:
        source = record.capability_boundaries or record.values or (record.identity,)
        if source:
            items.append(
                _clip(f"core protected confidence={record.confidence:.2f}: {source[0]}")
            )
    return items


def _relationship_items(records: tuple[RelationshipState, ...]) -> list[str]:
    items: list[str] = []
    for record in records:
        labels = (
            f"relationship active confidence={record.confidence:.2f}: "
            f"tone={record.preferred_tone}, depth={record.preferred_depth}"
        )
        items.append(_clip(labels))
        for source in (
            record.stable_preferences,
            record.boundaries,
            record.recent_changes,
            record.shared_history,
        ):
            if source:
                items.append(_clip(f"relationship note: {source[0]}"))
    return items


def _render_preference_experience(record: ExperienceRecord) -> str:
    return _clip(
        f"preference {record.status.value} confidence={record.confidence:.2f}: "
        f"{record.statement}"
        + (f" | action: {record.recommended_action}" if record.recommended_action else "")
    )


def _world_items(records: tuple[WorldStateItem, ...]) -> list[str]:
    return [
        _clip(
            f"world {record.status} confidence={record.confidence:.2f}: "
            f"{record.entity_type.value} {record.name} - {record.state}"
        )
        for record in records
    ]


def _belief_items(records: tuple[BeliefRecord, ...]) -> list[str]:
    return [
        _clip(
            f"belief {record.status.value} confidence={record.confidence:.2f}: "
            f"{record.subject} {record.predicate} {record.object}"
        )
        for record in records
    ]


def _render_experience(record: ExperienceRecord) -> str:
    text = (
        f"experience {record.kind.value} {record.status.value} "
        f"confidence={record.confidence:.2f}: {record.statement}"
    )
    if record.recommended_action:
        text += f" | action: {record.recommended_action}"
    if record.avoid_action:
        text += f" | avoid: {record.avoid_action}"
    return _clip(text)


def _skill_items(payloads: tuple[dict[str, object], ...]) -> list[str]:
    items: list[str] = []
    for payload in payloads:
        status = _status_value(payload.get("status"))
        if status not in {item.value for item in ACTIVE_COGNITIVE_STATUSES}:
            continue
        name = _string_value(payload, "name") or _string_value(payload, "skill_name")
        recommendation = (
            _string_value(payload, "recommendation")
            or _string_value(payload, "recommended_action")
            or _string_value(payload, "summary")
            or _string_value(payload, "description")
        )
        if not name and not recommendation:
            continue
        confidence = payload.get("confidence")
        label = f"skill {status}"
        if isinstance(confidence, int | float):
            label += f" confidence={confidence:.2f}"
        label += ": "
        if name and recommendation:
            label += f"{name} - {recommendation}"
        else:
            label += name or recommendation or ""
        items.append(_clip(label))
    return items


def _reasons(scene: str, current_request: str, experience_limit: int) -> list[str]:
    terms = ", ".join(sorted(_terms(current_request))[:5])
    reason = f"scene={scene}; experience_limit={experience_limit}"
    if terms:
        reason += f"; matched_terms={terms}"
    return [reason]


def _terms(text: str) -> set[str]:
    terms = set(re.findall(r"[a-z0-9]+", text.casefold())) - _RETRIEVAL_STOP_WORDS
    # Overlapping CJK bigrams match natural sentences without a tokenizer dependency.
    for word in re.findall(r"[\u3400-\u9fff]+", text):
        terms.update(word[index : index + 2] for index in range(len(word) - 1))
    return terms


def _model_payload(payload: dict[str, object]) -> dict[str, object]:
    values = dict(payload)
    values.pop("record_type", None)
    return values


def _timestamp(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _string_value(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    return value if isinstance(value, str) else ""


def _status_value(value: object) -> str:
    if isinstance(value, CognitiveRecordStatus):
        return value.value
    return value if isinstance(value, str) else ""


def _clip(text: str, limit: int = 500) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."

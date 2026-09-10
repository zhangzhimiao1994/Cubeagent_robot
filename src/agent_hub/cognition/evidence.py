"""Validated, bounded evidence merging at long-term storage boundaries."""

from pydantic import BaseModel

from agent_hub.cognition.gates import rejects_unsafe_text
from agent_hub.cognition.types import EvidenceRef


def merge_evidence(
    existing: tuple[EvidenceRef, ...], incoming: tuple[EvidenceRef, ...], *, limit: int = 16
) -> tuple[EvidenceRef, ...]:
    unique: dict[tuple[str, str], EvidenceRef] = {}
    for item in (*existing, *incoming):
        validated = EvidenceRef.model_validate(item.model_dump())
        if any(rejects_unsafe_text(value) for value in validated.model_dump().values()):
            raise ValueError("unsafe evidence")
        unique.setdefault((validated.kind, validated.ref_id), validated)
    return tuple(unique.values())[-limit:]


def contains_evidence(existing: tuple[EvidenceRef, ...], item: EvidenceRef) -> bool:
    return any((old.kind, old.ref_id) == (item.kind, item.ref_id) for old in existing)


def validated_update[T: BaseModel](record: T, *, update: dict[str, object]) -> T:
    return type(record).model_validate({**record.model_dump(), **update})

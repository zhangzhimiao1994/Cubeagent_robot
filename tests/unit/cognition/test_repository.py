from uuid import uuid4

import pytest

from agent_hub.cognition.repository import InMemoryCognitionRepository


@pytest.mark.asyncio
async def test_in_memory_repository_isolates_tenant_and_user() -> None:
    tenant_id = uuid4()
    user_a = uuid4()
    user_b = uuid4()
    repo_a = InMemoryCognitionRepository(tenant_id=tenant_id, user_id=user_a)
    repo_b = InMemoryCognitionRepository(tenant_id=tenant_id, user_id=user_b)

    payload = {
        "record_type": "experience",
        "id": "exp-1",
        "statement": "Use concise voice replies.",
    }
    await repo_a.upsert("experience", "exp-1", payload)

    assert await repo_a.get("experience", "exp-1") == payload
    assert await repo_b.get("experience", "exp-1") is None


@pytest.mark.asyncio
async def test_in_memory_repository_keeps_same_record_identity_for_each_user() -> None:
    tenant_id = uuid4()
    first_repository = InMemoryCognitionRepository(tenant_id=tenant_id, user_id=uuid4())
    second_repository = InMemoryCognitionRepository(tenant_id=tenant_id, user_id=uuid4())

    first_payload = {"statement": "First user preference."}
    second_payload = {"statement": "Second user preference."}
    await first_repository.upsert("experience", "exp-1", first_payload)
    await second_repository.upsert("experience", "exp-1", second_payload)

    assert await first_repository.get("experience", "exp-1") == {
        "record_type": "experience",
        "id": "exp-1",
        **first_payload,
    }
    assert await second_repository.get("experience", "exp-1") == {
        "record_type": "experience",
        "id": "exp-1",
        **second_payload,
    }


@pytest.mark.asyncio
async def test_in_memory_repository_upserts_lists_and_deletes() -> None:
    repository = InMemoryCognitionRepository(tenant_id=uuid4(), user_id=uuid4())

    await repository.upsert("experience", "exp-1", {"statement": "First version."})
    updated = await repository.upsert("experience", "exp-1", {"statement": "Updated."})
    belief = await repository.upsert("belief", "belief-1", {"subject": "user"})

    assert updated == {
        "record_type": "experience",
        "id": "exp-1",
        "statement": "Updated.",
    }
    assert await repository.list("experience") == (updated,)
    assert {item["id"] for item in await repository.list()} == {"exp-1", "belief-1"}
    assert belief["record_type"] == "belief"
    assert await repository.delete("experience", "exp-1") is True
    assert await repository.delete("experience", "exp-1") is False
    assert await repository.get("experience", "exp-1") is None

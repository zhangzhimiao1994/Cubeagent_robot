from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agent_hub.cognition.repository import AdminResourceCognitionRepository
from agent_hub.db.models import AdminResourceRow


@pytest.mark.integration
async def test_admin_resource_repository_persists_user_scoped_cognition_records(
    auth_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    tenant_id = uuid4()
    user_id = uuid4()
    other_user_id = uuid4()
    repository = AdminResourceCognitionRepository(
        session_factory=auth_session_factory,
        tenant_id=tenant_id,
        user_id=user_id,
    )
    other_repository = AdminResourceCognitionRepository(
        session_factory=auth_session_factory,
        tenant_id=tenant_id,
        user_id=other_user_id,
    )
    payload = {"statement": "Use concise voice replies."}
    other_payload = {"statement": "Use detailed written replies."}

    stored = await repository.upsert("experience", "exp-1", payload)
    other_stored = await other_repository.upsert("experience", "exp-1", other_payload)

    assert stored == {
        "record_type": "experience",
        "id": "exp-1",
        "statement": "Use concise voice replies.",
        "tenant_id": str(tenant_id),
        "user_id": str(user_id),
    }
    assert await repository.get("experience", "exp-1") == stored
    assert await other_repository.get("experience", "exp-1") == other_stored
    assert other_stored == {
        "record_type": "experience",
        "id": "exp-1",
        "statement": "Use detailed written replies.",
        "tenant_id": str(tenant_id),
        "user_id": str(other_user_id),
    }
    assert await other_repository.list() == (other_stored,)

    await repository.upsert("belief", "belief-1", {"subject": "user"})
    assert [record["id"] for record in await repository.list()] == ["exp-1", "belief-1"]
    assert await repository.list("belief") == (
        {
            "record_type": "belief",
            "id": "belief-1",
            "subject": "user",
            "tenant_id": str(tenant_id),
            "user_id": str(user_id),
        },
    )

    async with auth_session_factory() as session:
        rows = list(
            await session.scalars(
                select(AdminResourceRow).where(
                    AdminResourceRow.tenant_id == tenant_id,
                    AdminResourceRow.kind == "cognition",
                )
            )
        )
    experience_rows = [row for row in rows if row.payload["record_type"] == "experience"]
    assert len(experience_rows) == 2
    assert {row.payload["user_id"] for row in experience_rows} == {
        str(user_id),
        str(other_user_id),
    }
    assert len({row.resource_id for row in experience_rows}) == 2

    assert await repository.delete("experience", "exp-1") is True
    assert await repository.delete("experience", "exp-1") is False
    assert await repository.get("experience", "exp-1") is None

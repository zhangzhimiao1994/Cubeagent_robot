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

    stored = await repository.upsert("experience", "exp-1", payload)

    assert stored == {
        "record_type": "experience",
        "id": "exp-1",
        "statement": "Use concise voice replies.",
        "tenant_id": str(tenant_id),
        "user_id": str(user_id),
    }
    assert await repository.get("experience", "exp-1") == stored
    assert await other_repository.get("experience", "exp-1") is None
    assert await other_repository.list() == ()

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
        row = await session.scalar(
            select(AdminResourceRow).where(
                AdminResourceRow.tenant_id == tenant_id,
                AdminResourceRow.kind == "cognition",
                AdminResourceRow.resource_id == "experience:exp-1",
            )
        )
    assert row is not None
    assert row.payload == stored

    assert await repository.delete("experience", "exp-1") is True
    assert await repository.delete("experience", "exp-1") is False
    assert await repository.get("experience", "exp-1") is None

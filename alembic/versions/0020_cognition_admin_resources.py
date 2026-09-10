"""Allow cognition admin resources.

Revision ID: 0020_cognition_admin_resources
Revises: 0019_run_actor_role
Create Date: 2026-09-10
"""

from collections.abc import Sequence

from alembic import op

revision = "0020_cognition_admin_resources"
down_revision = "0019_run_actor_role"
branch_labels = None
depends_on = None

_OLD = "kind IN ('workflow', 'agent', 'main_agent', 'skill', 'mcp', 'memory', 'hermes', 'audit', 'log', 'setting', 'channel', 'openclaw', 'openclaw_session', 'schedule', 'evolution')"
_NEW = "kind IN ('workflow', 'agent', 'main_agent', 'skill', 'mcp', 'memory', 'hermes', 'audit', 'log', 'setting', 'channel', 'openclaw', 'openclaw_session', 'schedule', 'evolution', 'cognition')"


def upgrade() -> None:
    op.drop_constraint(
        "ck_agent_hub_admin_resources_kind",
        "agent_hub_admin_resources",
        type_="check",
    )
    op.create_check_constraint(
        "ck_agent_hub_admin_resources_kind",
        "agent_hub_admin_resources",
        _NEW,
    )


def downgrade() -> None:
    op.execute("DELETE FROM agent_hub_admin_resources WHERE kind = 'cognition'")
    op.drop_constraint(
        "ck_agent_hub_admin_resources_kind",
        "agent_hub_admin_resources",
        type_="check",
    )
    op.create_check_constraint(
        "ck_agent_hub_admin_resources_kind",
        "agent_hub_admin_resources",
        _OLD,
    )


__all__: Sequence[str] = ("downgrade", "upgrade")

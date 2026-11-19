"""institution → afdeling/klasse: navne unikke pr. institution

Raw SQL med eksplicit skemanavn: op.add_column/create_unique_constraint respekterer
ikke schema_translate_map og ville ramme det forkerte skema under test.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-19
"""
from alembic import op

from app.db import schema_map

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def _t() -> str:
    return f"`{schema_map()['qa_data']}`.`organization_units`"


def upgrade() -> None:
    op.execute(f"ALTER TABLE {_t()} ADD COLUMN parent_key VARCHAR(32) AS (IFNULL(parent_id, '')) PERSISTENT")
    op.execute(f"ALTER TABLE {_t()} DROP INDEX uq_unit_name, "
               "ADD CONSTRAINT uq_unit_name UNIQUE (tenant_id, parent_key, name)")


def downgrade() -> None:
    op.execute(f"ALTER TABLE {_t()} DROP INDEX uq_unit_name, ADD CONSTRAINT uq_unit_name UNIQUE (tenant_id, name)")
    op.execute(f"ALTER TABLE {_t()} DROP COLUMN parent_key")

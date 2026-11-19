"""spørgeskemaer tildeles institutioner

Et spørgeskema ligger i tenantens bibliotek og kan tildeles (og fratages) en eller flere institutioner.
Kun tildelte spørgeskemaer kan bruges, når der udstedes adgangskoder. Eksisterende spørgeskemaer med en
publiceret version tildeles alle eksisterende institutioner, så intet holder op med at virke.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-19
"""
from alembic import op

from app.db import schema_map

revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    d = f"`{schema_map()['qa_data']}`"
    op.execute(f"""
        CREATE TABLE {d}.`survey_assignments` (
            id VARCHAR(32) NOT NULL,
            survey_id VARCHAR(32) NOT NULL,
            unit_id VARCHAR(32) NOT NULL,
            assigned_by VARCHAR(32) NOT NULL,
            assigned_at DATETIME(3) NOT NULL,
            PRIMARY KEY (id),
            CONSTRAINT uq_survey_assignment UNIQUE (survey_id, unit_id),
            KEY ix_survey_assignments_unit_id (unit_id),
            CONSTRAINT fk_sa_survey FOREIGN KEY (survey_id) REFERENCES {d}.`surveys` (id) ON DELETE CASCADE,
            CONSTRAINT fk_sa_unit FOREIGN KEY (unit_id) REFERENCES {d}.`organization_units` (id) ON DELETE CASCADE
        )""")
    op.execute(f"""
        INSERT INTO {d}.`survey_assignments` (id, survey_id, unit_id, assigned_by, assigned_at)
        SELECT LOWER(REPLACE(UUID(), '-', '')), s.id, u.id, 'migration', UTC_TIMESTAMP(3)
        FROM {d}.`surveys` s JOIN {d}.`organization_units` u ON u.tenant_id = s.tenant_id AND u.parent_id IS NULL
        WHERE EXISTS (SELECT 1 FROM {d}.`survey_versions` v WHERE v.survey_id = s.id AND v.status = 'published')""")


def downgrade() -> None:
    op.execute(f"DROP TABLE `{schema_map()['qa_data']}`.`survey_assignments`")

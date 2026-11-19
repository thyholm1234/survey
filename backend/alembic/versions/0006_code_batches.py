"""adgangskoder samles i bestillinger (batch) med afdelingsblokke i bestilt rækkefølge

batch_id: én pr. bestilling (PDF). batch_pos: afdelingens plads i bestillingen. seq_no: kodens nummer i
afdelingsblokken (svarer til »Kode nr. X« på PDF-siden). Eksisterende koder grupperes efter udsteder,
spørgeskema og minut; nummeret udledes af etiketten (»nr. X af N«), hvor det findes.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-19
"""
from alembic import op

from app.db import schema_map

revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def _t() -> str:
    return f"`{schema_map()['qa_identity']}`.`access_codes`"


def upgrade() -> None:
    op.execute(f"ALTER TABLE {_t()} ADD COLUMN batch_id VARCHAR(32) NULL, ADD COLUMN batch_pos SMALLINT NULL, "
               "ADD COLUMN seq_no INT NULL, ADD INDEX ix_access_codes_batch (batch_id)")
    op.execute(f"""UPDATE {_t()} SET
        batch_id = MD5(CONCAT(created_by, '|', survey_version_id, '|', DATE_FORMAT(created_at, '%Y-%m-%d %H:%i'))),
        seq_no = CAST(NULLIF(REGEXP_SUBSTR(REGEXP_SUBSTR(label, 'nr\\\\. [0-9]+'), '[0-9]+'), '') AS UNSIGNED)""")


def downgrade() -> None:
    op.execute(f"ALTER TABLE {_t()} DROP INDEX ix_access_codes_batch, DROP COLUMN batch_id, "
               "DROP COLUMN batch_pos, DROP COLUMN seq_no")

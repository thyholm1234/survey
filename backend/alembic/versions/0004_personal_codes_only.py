"""kun personlige koder: fælles koder og genoptagelseskoder fjernes

- Ikke-personlige (fælles) koder deaktiveres; kolonnerne one_time, max_starts og max_completions fjernes.
- resume_keys omdøbes til response_links (kobling kode → besvarelse i qa_identity); hash/opslag fjernes,
  da deltageren nu logger ind igen med selve adgangskoden.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-19
"""
from alembic import op

from app.db import schema_map

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def _ident() -> str:
    return f"`{schema_map()['qa_identity']}`"


def upgrade() -> None:
    s = _ident()
    op.execute(f"UPDATE {s}.`access_codes` SET status = 'disabled' WHERE one_time = 0")
    op.execute(f"ALTER TABLE {s}.`access_codes` DROP COLUMN one_time, DROP COLUMN max_starts, "
               "DROP COLUMN max_completions")
    op.execute(f"RENAME TABLE {s}.`resume_keys` TO {s}.`response_links`")
    op.execute(f"ALTER TABLE {s}.`response_links` DROP COLUMN lookup_hmac, DROP COLUMN key_hash")


def downgrade() -> None:
    s = _ident()
    op.execute(f"ALTER TABLE {s}.`response_links` ADD COLUMN lookup_hmac VARCHAR(64) NULL, "
               "ADD COLUMN key_hash VARCHAR(255) NOT NULL DEFAULT ''")
    op.execute(f"UPDATE {s}.`response_links` SET lookup_hmac = SHA2(id, 256)")
    op.execute(f"ALTER TABLE {s}.`response_links` MODIFY lookup_hmac VARCHAR(64) NOT NULL, "
               "ADD CONSTRAINT lookup_hmac UNIQUE (lookup_hmac)")
    op.execute(f"RENAME TABLE {s}.`response_links` TO {s}.`resume_keys`")
    op.execute(f"ALTER TABLE {s}.`access_codes` ADD COLUMN max_starts INT NULL, "
               "ADD COLUMN max_completions INT NULL, ADD COLUMN one_time TINYINT(1) NOT NULL DEFAULT 1")

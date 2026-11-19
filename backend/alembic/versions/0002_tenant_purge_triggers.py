"""tillad sletning af publicerede spørgeskemaversioner når tenanten slettes

DELETE-triggerne på survey_versions og dens børnetabeller tillader nu sletning af
ikke-draft-versioner, men KUN når den ejende tenant har status 'deleting' (sættes i
samme transaktion af tenant-sletningen). INSERT/UPDATE-triggerne er uændrede.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-19
"""
from alembic import op

from app.db import schema_map

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None

CHILD_TABLES = ("response_scales", "subscales", "domains", "scenarios", "questions")
MSG = "SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'survey version is immutable';"


def _create(data: str, allow_purge: bool) -> None:
    purge = (
        f" AND (SELECT t.status FROM `{data}`.`tenants` t WHERE t.id = {{tid}}) <> 'deleting'" if allow_purge else ""
    )
    for t in CHILD_TABLES:
        cond = (
            f"(SELECT status FROM `{data}`.`survey_versions` WHERE id = OLD.survey_version_id) <> 'draft'"
            + purge.format(tid=f"(SELECT tenant_id FROM `{data}`.`survey_versions` WHERE id = OLD.survey_version_id)")
        )
        op.execute(f"DROP TRIGGER IF EXISTS `{data}`.`trg_{t}_delete_immutable`")
        op.execute(
            f"CREATE TRIGGER `{data}`.`trg_{t}_delete_immutable` BEFORE DELETE ON `{data}`.`{t}` "
            f"FOR EACH ROW BEGIN IF {cond} THEN {MSG} END IF; END"
        )
    cond = "OLD.status <> 'draft'" + purge.format(tid="OLD.tenant_id")
    op.execute(f"DROP TRIGGER IF EXISTS `{data}`.`trg_survey_versions_delete_immutable`")
    op.execute(
        f"CREATE TRIGGER `{data}`.`trg_survey_versions_delete_immutable` BEFORE DELETE ON `{data}`.`survey_versions` "
        f"FOR EACH ROW BEGIN IF {cond} THEN {MSG} END IF; END"
    )


def upgrade() -> None:
    _create(schema_map()["qa_data"], allow_purge=True)


def downgrade() -> None:
    _create(schema_map()["qa_data"], allow_purge=False)

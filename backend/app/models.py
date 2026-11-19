"""SQLAlchemy-datamodel.

Princip: identitets-/adgangsdata (qa_identity) er adskilt fra pseudonyme
analysedata (qa_data). Analysetabellerne indeholder ingen adgangskode-id,
ingen IP og ingen direkte identifikatorer. Krydsreferencer fra qa_data til
brugere er bevidst uden fremmednøgle.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Computed,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.mysql import DATETIME, LONGTEXT
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

DT = DATETIME(fsp=3)


def utcnow() -> datetime:
    # Gemmes som naiv UTC (MariaDB DATETIME har ingen tidszone; serveren kører +00:00)
    return datetime.now(timezone.utc).replace(tzinfo=None)


def new_id() -> str:
    """Ikke-gætbar, ikke-sekventiel id (128 bit)."""
    return secrets.token_hex(16)


class Base(DeclarativeBase):
    pass


ID = String(32)

# ---------------------------------------------------------------------------
# qa_data: organisation
# ---------------------------------------------------------------------------


class Tenant(Base):
    __tablename__ = "tenants"
    __table_args__ = {"schema": "qa_data"}
    id: Mapped[str] = mapped_column(ID, primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    min_cell_size: Mapped[int] = mapped_column(SmallInteger, default=10)
    retention_months: Mapped[int] = mapped_column(SmallInteger, default=24)
    data_controller: Mapped[str | None] = mapped_column(String(500))
    contact: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(16), default="active")
    created_at: Mapped[datetime] = mapped_column(DT, default=utcnow)


class OrganizationUnit(Base):
    __tablename__ = "organization_units"
    __table_args__ = (
        UniqueConstraint("tenant_id", "parent_key", "name", name="uq_unit_name"),
        {"schema": "qa_data"},
    )
    """To niveauer: institution (parent_id NULL) og afdeling/klasse (parent_id = institution).
    Navne er unikke pr. institution (parent_key gør NULL sammenlignelig i unik-nøglen)."""
    id: Mapped[str] = mapped_column(ID, primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("qa_data.tenants.id"), index=True)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("qa_data.organization_units.id"))
    parent_key: Mapped[str] = mapped_column(String(32), Computed("IFNULL(parent_id, '')", persisted=True))
    name: Mapped[str] = mapped_column(String(200))
    unit_type: Mapped[str] = mapped_column(String(16))  # daycare | school | other
    status: Mapped[str] = mapped_column(String(16), default="active")
    created_at: Mapped[datetime] = mapped_column(DT, default=utcnow)


# ---------------------------------------------------------------------------
# qa_data: instrumenter
# ---------------------------------------------------------------------------


class Survey(Base):
    __tablename__ = "surveys"
    __table_args__ = (
        UniqueConstraint("tenant_id", "survey_key", name="uq_survey_key"),
        {"schema": "qa_data"},
    )
    id: Mapped[str] = mapped_column(ID, primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("qa_data.tenants.id"), index=True)
    survey_key: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DT, default=utcnow)


class SurveyAssignment(Base):
    """Spørgeskema tildelt en institution. Kun tildelte spørgeskemaer kan få udstedt adgangskoder."""

    __tablename__ = "survey_assignments"
    __table_args__ = (
        UniqueConstraint("survey_id", "unit_id", name="uq_survey_assignment"),
        {"schema": "qa_data"},
    )
    id: Mapped[str] = mapped_column(ID, primary_key=True, default=new_id)
    survey_id: Mapped[str] = mapped_column(ForeignKey("qa_data.surveys.id", ondelete="CASCADE"))
    unit_id: Mapped[str] = mapped_column(ForeignKey("qa_data.organization_units.id", ondelete="CASCADE"), index=True)
    assigned_by: Mapped[str] = mapped_column(ID)
    assigned_at: Mapped[datetime] = mapped_column(DT, default=utcnow)


class SurveyVersion(Base):
    __tablename__ = "survey_versions"
    __table_args__ = (
        UniqueConstraint("survey_id", "version_no", name="uq_survey_version"),
        {"schema": "qa_data"},
    )
    id: Mapped[str] = mapped_column(ID, primary_key=True, default=new_id)
    survey_id: Mapped[str] = mapped_column(ForeignKey("qa_data.surveys.id"), index=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("qa_data.tenants.id"), index=True)
    version_no: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="draft")  # draft|published|retired
    schema_version: Mapped[str] = mapped_column(String(16))
    source_json: Mapped[str] = mapped_column(LONGTEXT)
    source_sha256: Mapped[str] = mapped_column(String(64))
    imported_by: Mapped[str] = mapped_column(ID)
    imported_at: Mapped[datetime] = mapped_column(DT, default=utcnow)
    published_by: Mapped[str | None] = mapped_column(ID)
    published_at: Mapped[datetime | None] = mapped_column(DT)

    survey: Mapped[Survey] = relationship()


class ResponseScale(Base):
    __tablename__ = "response_scales"
    __table_args__ = {"schema": "qa_data"}
    id: Mapped[str] = mapped_column(ID, primary_key=True, default=new_id)
    survey_version_id: Mapped[str] = mapped_column(
        ForeignKey("qa_data.survey_versions.id"), unique=True
    )
    scale_type: Mapped[str] = mapped_column(String(16))
    min_value: Mapped[int] = mapped_column(SmallInteger)
    max_value: Mapped[int] = mapped_column(SmallInteger)
    labels: Mapped[list] = mapped_column(JSON)
    cannot_assess_label: Mapped[str | None] = mapped_column(String(200))


class Subscale(Base):
    __tablename__ = "subscales"
    __table_args__ = (
        UniqueConstraint("survey_version_id", "code", name="uq_subscale"),
        {"schema": "qa_data"},
    )
    id: Mapped[str] = mapped_column(ID, primary_key=True, default=new_id)
    survey_version_id: Mapped[str] = mapped_column(ForeignKey("qa_data.survey_versions.id"))
    code: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(200))
    instruction: Mapped[str | None] = mapped_column(Text)
    position: Mapped[int] = mapped_column(SmallInteger)


class Domain(Base):
    __tablename__ = "domains"
    __table_args__ = (
        UniqueConstraint("survey_version_id", "code", name="uq_domain"),
        {"schema": "qa_data"},
    )
    id: Mapped[str] = mapped_column(ID, primary_key=True, default=new_id)
    survey_version_id: Mapped[str] = mapped_column(ForeignKey("qa_data.survey_versions.id"))
    code: Mapped[str] = mapped_column(String(8))
    name: Mapped[str] = mapped_column(String(200))
    position: Mapped[int] = mapped_column(SmallInteger)


class Scenario(Base):
    __tablename__ = "scenarios"
    __table_args__ = (
        UniqueConstraint("survey_version_id", "scenario_key", name="uq_scenario"),
        {"schema": "qa_data"},
    )
    id: Mapped[str] = mapped_column(ID, primary_key=True, default=new_id)
    survey_version_id: Mapped[str] = mapped_column(ForeignKey("qa_data.survey_versions.id"))
    scenario_key: Mapped[str] = mapped_column(String(64))
    domain_id: Mapped[str] = mapped_column(ForeignKey("qa_data.domains.id"))
    behavior: Mapped[str] = mapped_column(Text)
    position: Mapped[int] = mapped_column(SmallInteger)


class Question(Base):
    __tablename__ = "questions"
    __table_args__ = (
        UniqueConstraint("survey_version_id", "question_key", name="uq_question"),
        {"schema": "qa_data"},
    )
    id: Mapped[str] = mapped_column(ID, primary_key=True, default=new_id)
    survey_version_id: Mapped[str] = mapped_column(
        ForeignKey("qa_data.survey_versions.id"), index=True
    )
    question_key: Mapped[str] = mapped_column(String(64))
    scenario_id: Mapped[str] = mapped_column(ForeignKey("qa_data.scenarios.id"))
    subscale_id: Mapped[str] = mapped_column(ForeignKey("qa_data.subscales.id"))
    text: Mapped[str] = mapped_column(Text)
    reverse_scored: Mapped[bool] = mapped_column(Boolean, default=False)
    position: Mapped[int] = mapped_column(SmallInteger)


# ---------------------------------------------------------------------------
# qa_data: besvarelser (pseudonyme)
# ---------------------------------------------------------------------------


class Response(Base):
    __tablename__ = "responses"
    __table_args__ = (
        Index("ix_resp_scope", "tenant_id", "survey_version_id", "unit_id"),
        {"schema": "qa_data"},
    )
    id: Mapped[str] = mapped_column(ID, primary_key=True, default=new_id)  # responseId
    tenant_id: Mapped[str] = mapped_column(ForeignKey("qa_data.tenants.id"))
    unit_id: Mapped[str] = mapped_column(ForeignKey("qa_data.organization_units.id"))
    unit_type: Mapped[str] = mapped_column(String(16))
    survey_version_id: Mapped[str] = mapped_column(ForeignKey("qa_data.survey_versions.id"))
    group_tags: Mapped[list] = mapped_column(JSON, default=list)
    background: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="in_progress")
    started_at: Mapped[datetime] = mapped_column(DT, default=utcnow)
    last_activity_at: Mapped[datetime] = mapped_column(DT, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DT)
    seed: Mapped[int] = mapped_column(BigInteger)
    block_order: Mapped[list] = mapped_column(JSON)
    presentation_order: Mapped[list] = mapped_column(JSON)
    randomization_meta: Mapped[dict] = mapped_column(JSON, default=dict)
    browser_class: Mapped[str | None] = mapped_column(String(16))
    screen_class: Mapped[str | None] = mapped_column(String(16))
    app_version: Mapped[str] = mapped_column(String(32))
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False)


class Answer(Base):
    __tablename__ = "answers"
    __table_args__ = (
        UniqueConstraint("response_id", "question_id", name="uq_answer"),
        {"schema": "qa_data"},
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    response_id: Mapped[str] = mapped_column(
        ForeignKey("qa_data.responses.id", ondelete="CASCADE"), index=True
    )
    question_id: Mapped[str] = mapped_column(ForeignKey("qa_data.questions.id"))
    value: Mapped[int | None] = mapped_column(SmallInteger)
    missing_code: Mapped[str | None] = mapped_column(String(16))  # CANNOT_ASSESS
    global_position: Mapped[int] = mapped_column(SmallInteger)
    block_index: Mapped[int] = mapped_column(SmallInteger)
    block_position: Mapped[int] = mapped_column(SmallInteger)
    first_shown_at: Mapped[datetime] = mapped_column(DT)
    answered_at: Mapped[datetime | None] = mapped_column(DT)
    rt_ms: Mapped[int | None] = mapped_column(Integer)
    change_count: Mapped[int] = mapped_column(SmallInteger, default=0)
    changed_after_back: Mapped[bool] = mapped_column(Boolean, default=False)
    last_seq: Mapped[int] = mapped_column(Integer, default=0)


class PresentationEvent(Base):
    __tablename__ = "presentation_events"
    __table_args__ = {"schema": "qa_data"}
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    response_id: Mapped[str] = mapped_column(
        ForeignKey("qa_data.responses.id", ondelete="CASCADE"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(16))  # start|shown|answer|back|resume|complete
    question_id: Mapped[str | None] = mapped_column(ID)
    position: Mapped[int | None] = mapped_column(SmallInteger)
    at: Mapped[datetime] = mapped_column(DT, default=utcnow)


# ---------------------------------------------------------------------------
# qa_identity
# ---------------------------------------------------------------------------


class Role(Base):
    __tablename__ = "roles"
    __table_args__ = {"schema": "qa_identity"}
    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    description: Mapped[str] = mapped_column(String(200))


class User(Base):
    __tablename__ = "users"
    __table_args__ = {"schema": "qa_identity"}
    id: Mapped[str] = mapped_column(ID, primary_key=True, default=new_id)
    username: Mapped[str] = mapped_column(String(100), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    totp_secret_enc: Mapped[str | None] = mapped_column(String(255))
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    totp_last_step: Mapped[int | None] = mapped_column(BigInteger)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(16), default="active")
    failed_logins: Mapped[int] = mapped_column(SmallInteger, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DT)
    created_at: Mapped[datetime] = mapped_column(DT, default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DT)

    scopes: Mapped[list[UserScope]] = relationship(back_populates="user", lazy="selectin")


class UserScope(Base):
    __tablename__ = "user_scopes"
    __table_args__ = (
        UniqueConstraint("user_id", "role_code", "tenant_id", "unit_id", name="uq_scope"),
        {"schema": "qa_identity"},
    )
    id: Mapped[str] = mapped_column(ID, primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("qa_identity.users.id", ondelete="CASCADE"))
    role_code: Mapped[str] = mapped_column(ForeignKey("qa_identity.roles.code"))
    tenant_id: Mapped[str | None] = mapped_column(ForeignKey("qa_data.tenants.id"))
    unit_id: Mapped[str | None] = mapped_column(ForeignKey("qa_data.organization_units.id"))
    can_export: Mapped[bool] = mapped_column(Boolean, default=False)

    user: Mapped[User] = relationship(back_populates="scopes")


class AdminSession(Base):
    __tablename__ = "admin_sessions"
    __table_args__ = {"schema": "qa_identity"}
    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # sha256(token)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("qa_identity.users.id", ondelete="CASCADE"), index=True
    )
    csrf_token: Mapped[str] = mapped_column(String(64))
    mfa_passed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DT, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DT, default=utcnow)
    absolute_expires_at: Mapped[datetime] = mapped_column(DT)


class AccessCode(Base):
    """Personlig adgangskode: højst én besvarelse ad gangen; deltageren logger ind igen med koden."""

    __tablename__ = "access_codes"
    __table_args__ = {"schema": "qa_identity"}
    id: Mapped[str] = mapped_column(ID, primary_key=True, default=new_id)  # codeId
    tenant_id: Mapped[str] = mapped_column(ForeignKey("qa_data.tenants.id"), index=True)
    unit_id: Mapped[str] = mapped_column(ForeignKey("qa_data.organization_units.id"), index=True)
    survey_version_id: Mapped[str] = mapped_column(ForeignKey("qa_data.survey_versions.id"))
    lookup_hmac: Mapped[str] = mapped_column(String(64), unique=True)
    code_hash: Mapped[str] = mapped_column(String(255))  # Argon2id
    label: Mapped[str | None] = mapped_column(String(200))
    group_tags: Mapped[list] = mapped_column(JSON, default=list)
    valid_from: Mapped[datetime] = mapped_column(DT)
    valid_to: Mapped[datetime] = mapped_column(DT)
    starts_count: Mapped[int] = mapped_column(Integer, default=0)
    completions_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="active")  # active|disabled
    created_by: Mapped[str] = mapped_column(ID)
    created_at: Mapped[datetime] = mapped_column(DT, default=utcnow)


class CodeTicket(Base):
    """Kortlivet billet efter vellykket kodeverifikation (før samtykke/start)."""

    __tablename__ = "code_tickets"
    __table_args__ = {"schema": "qa_identity"}
    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # sha256(ticket)
    access_code_id: Mapped[str] = mapped_column(
        ForeignKey("qa_identity.access_codes.id", ondelete="CASCADE")
    )
    expires_at: Mapped[datetime] = mapped_column(DT)
    used: Mapped[bool] = mapped_column(Boolean, default=False)


class ResponseSession(Base):
    __tablename__ = "response_sessions"
    __table_args__ = {"schema": "qa_identity"}
    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # sha256(token)
    response_id: Mapped[str] = mapped_column(
        ForeignKey("qa_data.responses.id", ondelete="CASCADE"), index=True
    )
    access_code_id: Mapped[str] = mapped_column(
        ForeignKey("qa_identity.access_codes.id", ondelete="CASCADE")
    )
    created_at: Mapped[datetime] = mapped_column(DT, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DT, default=utcnow)
    absolute_expires_at: Mapped[datetime] = mapped_column(DT)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


class ResponseLink(Base):
    """Kobling personlig kode → besvarelse. Ligger i qa_identity, så analysedata ikke indeholder kode-id."""

    __tablename__ = "response_links"
    __table_args__ = {"schema": "qa_identity"}
    id: Mapped[str] = mapped_column(ID, primary_key=True, default=new_id)
    response_id: Mapped[str] = mapped_column(
        ForeignKey("qa_data.responses.id", ondelete="CASCADE"), unique=True
    )
    access_code_id: Mapped[str] = mapped_column(
        ForeignKey("qa_identity.access_codes.id", ondelete="CASCADE")
    )
    expires_at: Mapped[datetime] = mapped_column(DT)  # opbevaringsperiodens udløb


class RateLimit(Base):
    __tablename__ = "rate_limits"
    __table_args__ = {"schema": "qa_identity"}
    bucket: Mapped[str] = mapped_column(String(100), primary_key=True)
    window_start: Mapped[datetime] = mapped_column(DT)
    count: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime] = mapped_column(DT, index=True)


# ---------------------------------------------------------------------------
# qa_analysis
# ---------------------------------------------------------------------------


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"
    __table_args__ = (
        Index("ix_run_status", "status", "requested_at"),
        {"schema": "qa_analysis"},
    )
    id: Mapped[str] = mapped_column(ID, primary_key=True, default=new_id)
    tenant_id: Mapped[str] = mapped_column(ID, index=True)
    survey_version_id: Mapped[str] = mapped_column(ID)
    kind: Mapped[str] = mapped_column(String(32))
    params: Mapped[dict] = mapped_column(JSON)
    filters: Mapped[dict] = mapped_column(JSON)
    allowed_unit_ids: Mapped[list | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16), default="queued")
    requested_by: Mapped[str] = mapped_column(ID)
    requested_at: Mapped[datetime] = mapped_column(DT, default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DT)
    finished_at: Mapped[datetime | None] = mapped_column(DT)
    result: Mapped[str | None] = mapped_column(LONGTEXT)
    error: Mapped[str | None] = mapped_column(String(1000))
    software: Mapped[dict | None] = mapped_column(JSON)
    data_sha256: Mapped[str | None] = mapped_column(String(64))
    protocol_version: Mapped[str] = mapped_column(String(16))


# ---------------------------------------------------------------------------
# qa_audit
# ---------------------------------------------------------------------------


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_tenant_at", "tenant_id", "at"),
        {"schema": "qa_audit"},
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(DT, default=utcnow)
    actor_type: Mapped[str] = mapped_column(String(16))
    actor_id: Mapped[str | None] = mapped_column(String(64))
    tenant_id: Mapped[str | None] = mapped_column(ID)
    action: Mapped[str] = mapped_column(String(64))
    target_type: Mapped[str | None] = mapped_column(String(32))
    target_id: Mapped[str | None] = mapped_column(String(64))
    details: Mapped[dict | None] = mapped_column(JSON)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))

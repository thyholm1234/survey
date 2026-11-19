"""Konfiguration fra miljøvariabler (.env via docker compose). Ingen standardhemmeligheder."""
from functools import lru_cache

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    app_env: str = "production"
    app_version: str = "1.0.0"
    public_host: str = "localhost"
    public_port: int = 443
    hsts_max_age: int = 300

    db_host: str = "db"
    db_port: int = 3306
    db_user: str
    db_password: SecretStr
    # Bruges af tests til at mappe qa_* -> test_qa_* (schema_translate_map)
    db_schema_prefix: str = ""

    code_lookup_pepper: SecretStr
    ip_hash_key: SecretStr
    totp_enc_key: SecretStr

    min_cell_size: int = Field(10, ge=3)
    respondent_session_ttl: int = 3600
    respondent_session_max: int = 43200
    admin_session_ttl: int = 1800
    admin_session_max: int = 28800
    rl_code_attempts: int = 5
    rl_code_window: int = 900
    rl_login_attempts: int = 5
    rl_login_window: int = 900
    default_retention_months: int = 24

    # Oplysninger om driftsansvarlig (databehandler) til de offentlige juridiske sider.
    # Tomme værdier vises på siderne som 'ikke angivet' – udfyld dem før produktion.
    operator_name: str = ""
    operator_cvr: str = ""
    operator_address: str = ""
    operator_contact: str = ""      # kontakt vedr. databeskyttelse (e-mail)
    dpo_contact: str = ""           # databeskyttelsesrådgiver (hvis udpeget)
    security_contact: str = ""      # sikkerhedshændelser / sårbarheder
    hosting_provider: str = ""
    hosting_location: str = ""      # fx 'Frankfurt, Tyskland (EU)'

    @field_validator("code_lookup_pepper", "ip_hash_key", "totp_enc_key", "db_password")
    @classmethod
    def _reject_placeholder(cls, v: SecretStr) -> SecretStr:
        raw = v.get_secret_value()
        if raw in ("", "change-me") or len(raw) < 16:
            raise ValueError("hemmelighed mangler eller er for svag – kør scripts/init-secrets.sh")
        return v

    @property
    def is_test(self) -> bool:
        return self.app_env == "test"

    @property
    def public_origin(self) -> str:
        port = "" if self.public_port == 443 else f":{self.public_port}"
        return f"https://{self.public_host}{port}"

    def schema(self, name: str) -> str:
        return f"{self.db_schema_prefix}{name}"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]

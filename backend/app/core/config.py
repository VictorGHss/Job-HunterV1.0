import ipaddress
from functools import lru_cache
from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

INSECURE_SECRET_MARKERS = (
    "dev-only",
    "change_me",
    "changeme",
    "example",
    "default-secret",
    "test-secret",
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "Job Hunter"
    app_version: str = "0.1.0"
    environment: Literal["development", "testing", "production"] = "development"
    planned_hostname: str = "https://jobhunter.ctrls.dev.br"

    database_url: str = "postgresql+psycopg://jobhunter_user:localdev@localhost:5432/jobhunter"
    secret_key: str = "dev-only-ephemeral-secret-key-must-be-changed-in-production-32b"

    session_cookie_name: str = "jh_session"
    csrf_cookie_name: str = "jh_csrf"
    session_expire_hours: int = 168
    cookie_secure: bool = False
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"

    # Proxies confiáveis e Rate Limiting
    trusted_proxy_cidrs: str = (
        "127.0.0.1/32,::1/128,172.16.0.0/12,10.0.0.0/8,192.168.0.0/16"
    )
    trust_cf_connecting_ip: bool = False
    login_rate_limit_window_seconds: int = 900
    login_account_ip_max_attempts: int = 5
    login_ip_max_attempts: int = 20
    login_cooldown_seconds: int = 300

    cors_origins: str = (
        "http://localhost:5180,http://127.0.0.1:5180,"
        "http://localhost:5173,http://127.0.0.1:5173,"
        "https://jobhunter.ctrls.dev.br"
    )

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def trusted_proxy_networks(
        self,
    ) -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
        networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
        for raw in self.trusted_proxy_cidrs.split(","):
            item = raw.strip()
            if item:
                networks.append(ipaddress.ip_network(item, strict=False))
        return tuple(networks)

    @field_validator("secret_key")
    @classmethod
    def validate_secret_key(cls, value: str) -> str:
        if len(value.strip()) < 24:
            raise ValueError("SECRET_KEY deve possuir ao menos 24 caracteres.")
        return value

    @field_validator("trusted_proxy_cidrs")
    @classmethod
    def validate_trusted_proxy_cidrs(cls, value: str) -> str:
        for raw in value.split(","):
            item = raw.strip()
            if item:
                try:
                    ipaddress.ip_network(item, strict=False)
                except ValueError as exc:
                    raise ValueError(
                        f"CIDR inválido em TRUSTED_PROXY_CIDRS: '{item}'."
                    ) from exc
        return value

    @field_validator("cors_origins")
    @classmethod
    def validate_cors_origins(cls, value: str) -> str:
        origins = [item.strip() for item in value.split(",") if item.strip()]
        for origin in origins:
            if "*" in origin:
                raise ValueError(
                    "CORS_ORIGINS não pode conter curingas ('*') quando credenciais estão habilitadas."
                )
            if not (origin.startswith("http://") or origin.startswith("https://")):
                raise ValueError(
                    f"Origem CORS inválida '{origin}'. Utilize esquema http:// ou https://."
                )
        return value

    @field_validator(
        "login_rate_limit_window_seconds",
        "login_account_ip_max_attempts",
        "login_ip_max_attempts",
        "login_cooldown_seconds",
    )
    @classmethod
    def validate_positive_ints(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("Parâmetros de rate limiting devem ser maiores que zero.")
        return value

    @model_validator(mode="after")
    def validate_security_posture(self) -> "Settings":
        if self.cookie_samesite == "none" and not self.cookie_secure:
            raise ValueError(
                "COOKIE_SAMESITE='none' exige COOKIE_SECURE=true para proteção de cookies."
            )

        if self.environment == "production":
            if not self.cookie_secure:
                raise ValueError(
                    "Em produção (ENVIRONMENT=production), COOKIE_SECURE deve ser obrigatoriamente true."
                )

            cleaned_secret = self.secret_key.strip()
            lower_secret = cleaned_secret.lower()
            if len(cleaned_secret) < 32 or len(set(cleaned_secret)) < 10:
                raise ValueError(
                    "Em produção, SECRET_KEY deve possuir ao menos 32 caracteres com alta entropia."
                )
            if any(marker in lower_secret for marker in INSECURE_SECRET_MARKERS):
                raise ValueError(
                    "Em produção, SECRET_KEY não pode utilizar valor padrão ou marcador de exemplo."
                )

            if not self.cors_origins_list:
                raise ValueError(
                    "Em produção, CORS_ORIGINS deve conter ao menos uma origem HTTPS explícita."
                )
            for origin in self.cors_origins_list:
                if not origin.startswith("https://"):
                    raise ValueError(
                        f"Em produção, todas as origens de CORS_ORIGINS devem usar HTTPS ('{origin}')."
                    )

        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

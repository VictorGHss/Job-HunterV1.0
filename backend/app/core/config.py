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

    # Coleta de oportunidades (Fase 02 / DX-02.2)
    sync_http_connect_timeout_seconds: float = 10.0
    sync_http_read_timeout_seconds: float = 20.0
    sync_max_response_bytes: int = 5 * 1024 * 1024
    sync_max_retries: int = 2
    sync_user_agent: str = "JobHunter/0.2 (+https://jobhunter.ctrls.dev.br)"
    # Credenciais opcionais para aumento de limite de taxa (nunca obrigatórias)
    github_token: str = ""
    himalayas_api_key: str = ""
    # Limites conservadores de paginação/segmentação por execução
    sync_jobicy_max_pages: int = 5
    sync_himalayas_max_pages: int = 5
    sync_remote_ok_max_queries: int = 7
    sync_github_max_pages: int = 5

    # Infraestrutura de IA Assistida (Subfase 04.4.1 — desabilitada por padrão)
    # Semântica temporal:
    # - Todas as janelas e datas utilizam exclusivamente UTC.
    # - ai_rate_limit_window_seconds aplica janela deslizante [now - window, now].
    # - Limites diários (*_daily_max_*) aplicam dia civil fixo em UTC [00:00:00Z, 24:00:00Z).
    ai_assisted_enabled: bool = False
    ai_provider: str = "disabled"
    ai_model: str = "none"
    ai_rate_limit_window_seconds: int = 900
    ai_user_window_max_requests: int = 10
    ai_user_daily_max_requests: int = 30
    ai_user_daily_max_tokens: int = 60_000
    ai_global_daily_max_tokens: int = 100_000
    ai_reservation_ttl_seconds: int = 60
    ai_circuit_breaker_failure_threshold: int = 3
    ai_circuit_breaker_cooldown_seconds: int = 120
    ai_http_total_timeout_seconds: float = 24.0
    ai_http_connect_timeout_seconds: float = 5.0
    ai_http_read_timeout_seconds: float = 20.0
    ai_http_max_response_bytes: int = 262_144

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

    @field_validator("ai_provider")
    @classmethod
    def normalize_ai_provider(cls, value: str) -> str:
        normalized = value.strip().lower()
        return normalized or "disabled"

    @field_validator("ai_model")
    @classmethod
    def normalize_ai_model(cls, value: str) -> str:
        normalized = value.strip()
        return normalized or "none"

    @field_validator(
        "login_rate_limit_window_seconds",
        "login_account_ip_max_attempts",
        "login_ip_max_attempts",
        "login_cooldown_seconds",
        "sync_jobicy_max_pages",
        "sync_himalayas_max_pages",
        "sync_remote_ok_max_queries",
        "sync_github_max_pages",
        "ai_rate_limit_window_seconds",
        "ai_user_window_max_requests",
        "ai_user_daily_max_requests",
        "ai_user_daily_max_tokens",
        "ai_global_daily_max_tokens",
        "ai_reservation_ttl_seconds",
        "ai_circuit_breaker_failure_threshold",
        "ai_circuit_breaker_cooldown_seconds",
        "ai_http_max_response_bytes",
    )
    @classmethod
    def validate_positive_ints(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("Parâmetros de limites, cotas e janelas devem ser maiores que zero.")
        return value

    @field_validator(
        "ai_http_total_timeout_seconds",
        "ai_http_connect_timeout_seconds",
        "ai_http_read_timeout_seconds",
    )
    @classmethod
    def validate_positive_ai_timeouts(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("Parâmetros de timeout de IA devem ser maiores que zero.")
        return value

    @model_validator(mode="after")
    def validate_security_posture(self) -> "Settings":
        if self.ai_http_total_timeout_seconds >= 25.0:
            raise ValueError(
                "AI_HTTP_TOTAL_TIMEOUT_SECONDS deve ser estritamente menor que 25 segundos."
            )
        if self.ai_http_connect_timeout_seconds >= self.ai_http_total_timeout_seconds:
            raise ValueError(
                "AI_HTTP_CONNECT_TIMEOUT_SECONDS deve ser menor que AI_HTTP_TOTAL_TIMEOUT_SECONDS."
            )
        if self.ai_http_read_timeout_seconds >= self.ai_http_total_timeout_seconds:
            raise ValueError(
                "AI_HTTP_READ_TIMEOUT_SECONDS deve ser menor que AI_HTTP_TOTAL_TIMEOUT_SECONDS."
            )
        if float(self.ai_reservation_ttl_seconds) <= self.ai_http_total_timeout_seconds:
            raise ValueError(
                "AI_RESERVATION_TTL_SECONDS deve ser maior que AI_HTTP_TOTAL_TIMEOUT_SECONDS."
            )

        if self.cookie_samesite == "none" and not self.cookie_secure:
            raise ValueError(
                "COOKIE_SAMESITE='none' exige COOKIE_SECURE=true para proteção de cookies."
            )

        if self.environment == "production":
            if self.ai_provider == "mock":
                raise ValueError(
                    "Em produção (ENVIRONMENT=production), AI_PROVIDER='mock' não é permitido."
                )

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

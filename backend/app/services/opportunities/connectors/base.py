from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
import json
import time
from typing import Any, Callable

import httpx

from app.core.config import settings


class ConnectorError(Exception):
    """Erro controlado de execução em conector externo."""


class ConnectorFetchError(ConnectorError):
    """Falha de transporte HTTP, timeout, limite de tamanho ou rate limit."""


class ConnectorPayloadError(ConnectorError):
    """Payload JSON malformado ou incompatível com o contrato esperado."""


@dataclass(slots=True)
class NormalizedOpportunityDraft:
    external_id: str
    title: str
    company_name: str | None
    description: str | None
    opportunity_type: str
    employment_type: str
    work_mode: str
    location_text: str | None
    city: str | None
    state: str | None
    country: str | None
    eligible_countries: list[str]
    eligibility_unknown: bool
    language: str | None
    salary_min: float | None
    salary_max: float | None
    salary_currency: str | None
    salary_period: str | None
    requirements: list[str]
    technologies: list[str]
    source_url: str
    application_url: str | None
    published_at: datetime | None
    deadline_at: datetime | None
    source_status: str
    raw_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SourceDefinition:
    slug: str
    name: str
    source_type: str
    base_url: str
    terms_url: str
    attribution_text: str
    refresh_interval_seconds: int
    enabled_by_default: bool = True
    disabled_reason: str | None = None


def parse_retry_after_seconds(header_value: str | None, default_seconds: int = 5) -> int:
    if not header_value:
        return default_seconds
    stripped = header_value.strip()
    if stripped.isdigit():
        return max(1, min(int(stripped), 300))
    return default_seconds


def parse_geo_eligibility(
    raw_location: str | None,
) -> tuple[list[str], str | None, bool]:
    """
    Analisa a string geográfica declarada para trabalho remoto sem assumir
    elegibilidade mundial quando a fonte é omissa.
    Retorna: (eligible_countries, primary_country, eligibility_unknown)
    """
    if not raw_location or not raw_location.strip():
        return ([], None, True)

    cleaned = raw_location.strip()
    lower = cleaned.lower()

    if lower in {"remote", "remoto", "remote work", "telecommute"}:
        return ([], None, True)

    worldwide_markers = (
        "worldwide",
        "anywhere",
        "global",
        "work from anywhere",
        "remote worldwide",
        "100% anywhere",
    )
    if any(marker in lower for marker in worldwide_markers):
        return (["Worldwide"], None, False)

    parts = [part.strip() for part in cleaned.replace(";", ",").split(",") if part.strip()]
    primary_country = parts[0] if len(parts) == 1 else None
    return (parts, primary_country, False)


class BaseOpportunityConnector(ABC):
    definition: SourceDefinition

    def __init__(
        self,
        *,
        transport: httpx.BaseTransport | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
        connect_timeout: float | None = None,
        read_timeout: float | None = None,
        max_response_bytes: int | None = None,
        max_retries: int | None = None,
        user_agent: str | None = None,
    ) -> None:
        self.transport = transport
        self.sleep_fn = sleep_fn
        self.connect_timeout = connect_timeout or settings.sync_http_connect_timeout_seconds
        self.read_timeout = read_timeout or settings.sync_http_read_timeout_seconds
        self.max_response_bytes = max_response_bytes or settings.sync_max_response_bytes
        self.max_retries = settings.sync_max_retries if max_retries is None else max_retries
        self.user_agent = user_agent or settings.sync_user_agent

    def fetch_json(self, url: str) -> Any:
        timeout = httpx.Timeout(
            connect=self.connect_timeout,
            read=self.read_timeout,
            write=10.0,
            pool=10.0,
        )
        headers = {
            "Accept": "application/json",
            "User-Agent": self.user_agent,
        }

        last_error: str | None = None
        client_kwargs: dict[str, Any] = {
            "timeout": timeout,
            "headers": headers,
            "follow_redirects": False,
        }
        if self.transport is not None:
            client_kwargs["transport"] = self.transport

        with httpx.Client(**client_kwargs) as client:
            for attempt in range(self.max_retries + 1):
                try:
                    with client.stream("GET", url) as response:
                        if response.status_code == 429:
                            wait_seconds = parse_retry_after_seconds(
                                response.headers.get("Retry-After")
                            )
                            last_error = f"HTTP 429 Too Many Requests (Retry-After={wait_seconds}s)"
                            if attempt < self.max_retries:
                                self.sleep_fn(float(wait_seconds))
                                continue
                            raise ConnectorFetchError(last_error)

                        if response.status_code >= 500:
                            last_error = f"HTTP {response.status_code} retornado pela fonte."
                            if attempt < self.max_retries:
                                self.sleep_fn(float(2**attempt))
                                continue
                            raise ConnectorFetchError(last_error)

                        if response.status_code >= 400:
                            raise ConnectorFetchError(
                                f"Erro HTTP {response.status_code} ao consultar a fonte."
                            )

                        content_length = response.headers.get("Content-Length")
                        if content_length and content_length.isdigit():
                            if int(content_length) > self.max_response_bytes:
                                raise ConnectorFetchError(
                                    "Resposta excedeu o limite máximo de tamanho configurado."
                                )

                        chunks = bytearray()
                        for chunk in response.iter_bytes():
                            chunks.extend(chunk)
                            if len(chunks) > self.max_response_bytes:
                                raise ConnectorFetchError(
                                    "Corpo da resposta excedeu o limite máximo de bytes permitido."
                                )

                        try:
                            return json.loads(chunks.decode("utf-8"))
                        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                            raise ConnectorPayloadError(
                                "Resposta JSON malformada recebida da fonte."
                            ) from exc

                except httpx.RequestError as exc:
                    last_error = f"Falha de rede/timeout ao consultar fonte ({type(exc).__name__})."
                    if attempt < self.max_retries:
                        self.sleep_fn(float(2**attempt))
                        continue
                    raise ConnectorFetchError(last_error) from exc

        raise ConnectorFetchError(last_error or "Falha desconhecida ao consultar fonte.")

    @abstractmethod
    def parse_payload(self, payload: Any) -> list[NormalizedOpportunityDraft]:
        """Valida e converte o payload da fonte em rascunhos normalizados."""

    def collect(self) -> list[NormalizedOpportunityDraft]:
        payload = self.fetch_json(self.definition.base_url)
        return self.parse_payload(payload)


def parse_iso_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=UTC)
        except (ValueError, OSError, OverflowError):
            return None
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(raw)
            if dt.tzinfo is None:
                return dt.replace(tzinfo=UTC)
            return dt.astimezone(UTC)
        except ValueError:
            return None
    return None

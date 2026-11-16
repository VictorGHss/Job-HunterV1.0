import re
from typing import Any

from app.models.opportunity import (
    EmploymentType,
    ExternalSourceStatus,
    OpportunityType,
    SourceType,
    WorkMode,
)
from app.services.opportunities.classification import classify_professional_area
from app.services.opportunities.connectors.base import (
    BaseOpportunityConnector,
    ConnectorPayloadError,
    NormalizedOpportunityDraft,
    SourceDefinition,
    parse_geo_eligibility,
    parse_iso_datetime,
)
from app.services.opportunities.sanitization import (
    normalize_canonical_url,
    normalize_string_list,
    sanitize_external_html_text,
    sanitize_plain_text,
)

_SALARY_NUMBERS_RE = re.compile(r"\d[\d,\.]*")


def _parse_remotive_salary(raw_salary: str | None) -> tuple[float | None, float | None, str | None, str | None]:
    if not raw_salary:
        return (None, None, None, None)
    text = raw_salary.strip()
    if not text:
        return (None, None, None, None)

    currency = None
    if "$" in text or "usd" in text.lower():
        currency = "USD"
    elif "€" in text or "eur" in text.lower():
        currency = "EUR"
    elif "£" in text or "gbp" in text.lower():
        currency = "GBP"
    elif "r$" in text.lower() or "brl" in text.lower():
        currency = "BRL"

    period = "year"
    lower = text.lower()
    if any(marker in lower for marker in ("/hr", "hour", "/h")):
        period = "hour"
    elif any(marker in lower for marker in ("/mo", "month", "mês", "mes")):
        period = "month"

    numbers: list[float] = []
    for token in _SALARY_NUMBERS_RE.findall(text):
        normalized = token.replace(",", "")
        try:
            value = float(normalized)
            if value > 0:
                numbers.append(value)
        except ValueError:
            continue

    if not numbers:
        return (None, None, None, None)
    if len(numbers) == 1:
        return (numbers[0], numbers[0], currency, period)
    return (min(numbers[0], numbers[1]), max(numbers[0], numbers[1]), currency, period)


def _classify_remotive_types(
    title: str,
    raw_job_type: str | None,
    category: str | None,
) -> tuple[str, str]:
    jt = (raw_job_type or "").strip().lower()
    joined = f"{title} {category or ''}".lower()

    if jt == "internship" or any(
        token in joined for token in ("intern", "internship", "estágio", "estagio", "trainee")
    ):
        return (OpportunityType.INTERNSHIP.value, EmploymentType.INTERNSHIP.value)
    if jt == "freelance":
        return (OpportunityType.FREELANCE.value, EmploymentType.FREELANCE.value)
    if jt == "contract":
        return (OpportunityType.FREELANCE.value, EmploymentType.PJ.value)
    if any(
        token in joined
        for token in ("junior", "jr ", " jr", "entry level", "entry-level", "associate", "graduate")
    ):
        return (OpportunityType.JUNIOR.value, EmploymentType.OTHER.value)
    return (OpportunityType.OTHER.value, EmploymentType.OTHER.value)


class RemotiveConnector(BaseOpportunityConnector):
    """
    Conector para a API pública da Remotive (`software-dev`).
    Respeita limite recomendado de atualização (máximo ~4x ao dia -> intervalo 6h).
    Exige crédito à Remotive e link direto para a URL original.
    """

    definition = SourceDefinition(
        slug="remotive",
        name="Remotive",
        source_type=SourceType.JSON_API.value,
        base_url="https://remotive.com/api/remote-jobs?category=software-dev",
        terms_url="https://remotive.com/remote-jobs/api",
        attribution_text=(
            "Fonte: Remotive — creditar Remotive como origem e direcionar "
            "para a página oficial da vaga."
        ),
        refresh_interval_seconds=21600,
        enabled_by_default=False,
        disabled_reason=(
            "Desabilitada temporariamente aguardando esclarecimento e autorização "
            "escrita sobre os Termos de Uso gerais de março de 2026."
        ),
    )

    def parse_payload(self, payload: Any) -> list[NormalizedOpportunityDraft]:
        if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
            raise ConnectorPayloadError(
                "Remotive retornou estrutura inválida (esperado objeto JSON com lista 'jobs')."
            )

        drafts: list[NormalizedOpportunityDraft] = []
        for item in payload["jobs"]:
            if not isinstance(item, dict):
                continue

            raw_id = item.get("id")
            raw_title = sanitize_plain_text(item.get("title"))
            raw_url = item.get("url")
            if raw_id is None or not raw_title or not isinstance(raw_url, str):
                continue

            try:
                source_url = normalize_canonical_url(raw_url)
            except ValueError:
                continue

            opp_type, emp_type = _classify_remotive_types(
                raw_title,
                item.get("job_type"),
                item.get("category"),
            )
            raw_location = sanitize_plain_text(item.get("candidate_required_location"))
            eligible_countries, country, eligibility_unknown = parse_geo_eligibility(
                raw_location
            )

            tags_raw: list[str] = []
            if isinstance(item.get("tags"), list):
                tags_raw.extend(item["tags"])
            if isinstance(item.get("category"), str) and item["category"].strip():
                tags_raw.append(item["category"])
            technologies = normalize_string_list(tags_raw)

            sal_min, sal_max, sal_cur, sal_period = _parse_remotive_salary(
                sanitize_plain_text(item.get("salary"), max_length=120)
            )
            description = sanitize_external_html_text(item.get("description"))
            primary_area, secondary_areas, _ = classify_professional_area(
                title=raw_title,
                tags=technologies,
                description=description,
            )

            drafts.append(
                NormalizedOpportunityDraft(
                    external_id=str(raw_id).strip(),
                    title=raw_title,
                    company_name=sanitize_plain_text(item.get("company_name"), max_length=200),
                    description=description,
                    opportunity_type=opp_type,
                    employment_type=emp_type,
                    work_mode=WorkMode.REMOTE.value,
                    location_text=raw_location,
                    city=None,
                    state=None,
                    country=country,
                    eligible_countries=eligible_countries,
                    eligibility_unknown=eligibility_unknown,
                    language="Inglês",
                    salary_min=sal_min,
                    salary_max=sal_max,
                    salary_currency=sal_cur,
                    salary_period=sal_period,
                    requirements=[],
                    technologies=technologies,
                    source_url=source_url,
                    application_url=None,
                    published_at=parse_iso_datetime(item.get("publication_date")),
                    deadline_at=None,
                    source_status=ExternalSourceStatus.ACTIVE.value,
                    professional_area=primary_area,
                    secondary_areas=list(secondary_areas),
                    raw_metadata={
                        "category": sanitize_plain_text(item.get("category")),
                        "job_type": sanitize_plain_text(item.get("job_type")),
                        "source": "remotive",
                    },
                )
            )

        return drafts

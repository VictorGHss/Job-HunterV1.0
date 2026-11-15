from typing import Any

from app.models.opportunity import (
    EmploymentType,
    ExternalSourceStatus,
    OpportunityType,
    SourceType,
    WorkMode,
)
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
    validate_safe_external_url,
)


def _classify_remote_ok_types(title: str, tags: list[str]) -> tuple[str, str]:
    joined = f"{title} {' '.join(tags)}".lower()
    if any(token in joined for token in ("intern", "internship", "estágio", "estagio", "apprentice")):
        return (OpportunityType.INTERNSHIP.value, EmploymentType.INTERNSHIP.value)
    if any(token in joined for token in ("freelance", "contractor", "contract")):
        return (OpportunityType.FREELANCE.value, EmploymentType.FREELANCE.value)
    if any(
        token in joined
        for token in ("junior", "jr ", " jr", "entry level", "entry-level", "trainee", "graduate")
    ):
        return (OpportunityType.JUNIOR.value, EmploymentType.OTHER.value)
    return (OpportunityType.OTHER.value, EmploymentType.OTHER.value)


def _parse_optional_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
        return parsed if parsed > 0 else None
    except (TypeError, ValueError):
        return None


class RemoteOKConnector(BaseOpportunityConnector):
    """
    Conector para o feed JSON público da Remote OK.
    Requer atribuição visível à Remote OK e link follow para a URL original.
    """

    definition = SourceDefinition(
        slug="remote_ok",
        name="Remote OK",
        source_type=SourceType.JSON_API.value,
        base_url="https://remoteok.com/api",
        terms_url="https://remoteok.com/terms",
        attribution_text=(
            "Fonte: Remote OK — atribuição obrigatória com link direto para a "
            "publicação original (sem atributo nofollow e sem uso não autorizado do logotipo)."
        ),
        refresh_interval_seconds=3600,
    )

    def parse_payload(self, payload: Any) -> list[NormalizedOpportunityDraft]:
        if not isinstance(payload, list):
            raise ConnectorPayloadError(
                "Remote OK retornou estrutura inválida (esperado array JSON)."
            )

        drafts: list[NormalizedOpportunityDraft] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            # O primeiro elemento do feed Remote OK costuma ser um aviso legal sem id/position
            raw_id = item.get("id")
            raw_title = sanitize_plain_text(item.get("position"))
            raw_url = item.get("url")
            if raw_id is None or not raw_title or not isinstance(raw_url, str):
                continue

            try:
                source_url = normalize_canonical_url(raw_url)
            except ValueError:
                continue

            application_url: str | None = None
            raw_apply = item.get("apply_url")
            if isinstance(raw_apply, str) and raw_apply.strip():
                try:
                    application_url = validate_safe_external_url(raw_apply)
                except ValueError:
                    application_url = None

            tags = normalize_string_list(
                item.get("tags") if isinstance(item.get("tags"), list) else []
            )
            opp_type, emp_type = _classify_remote_ok_types(raw_title, tags)
            raw_location = sanitize_plain_text(item.get("location"))
            eligible_countries, country, eligibility_unknown = parse_geo_eligibility(
                raw_location
            )

            salary_min = _parse_optional_float(item.get("salary_min"))
            salary_max = _parse_optional_float(item.get("salary_max"))
            salary_currency = (
                sanitize_plain_text(item.get("salary_currency"), max_length=16)
                or ("USD" if (salary_min or salary_max) else None)
            )
            salary_period = "year" if (salary_min or salary_max) else None

            published_at = parse_iso_datetime(item.get("date")) or parse_iso_datetime(
                item.get("epoch")
            )

            drafts.append(
                NormalizedOpportunityDraft(
                    external_id=str(raw_id).strip(),
                    title=raw_title,
                    company_name=sanitize_plain_text(item.get("company"), max_length=200),
                    description=sanitize_external_html_text(item.get("description")),
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
                    salary_min=salary_min,
                    salary_max=salary_max,
                    salary_currency=salary_currency,
                    salary_period=salary_period,
                    requirements=[],
                    technologies=tags,
                    source_url=source_url,
                    application_url=application_url,
                    published_at=published_at,
                    deadline_at=None,
                    source_status=ExternalSourceStatus.ACTIVE.value,
                    raw_metadata={
                        "slug": sanitize_plain_text(item.get("slug")),
                        "source": "remote_ok",
                    },
                )
            )

        return drafts

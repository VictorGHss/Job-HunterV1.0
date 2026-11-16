from typing import Any
import re

from app.models.opportunity import (
    EmploymentType,
    ExternalSourceStatus,
    OpportunityType,
    SourceType,
    WorkMode,
)
from app.services.opportunities.classification import classify_opportunity, normalize_classification_text
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

_TRAILING_GEO_SUFFIX_RE = re.compile(
    r"\s*\|\s*(?:uk|united kingdom|germany|spain|sweden|ireland|france|netherlands|poland|italy|usa|us|canada|emea|apac|latam)\s*(?:\|\s*remote)?\s*$",
    re.I,
)


def _parse_optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
        return parsed if parsed > 0 else None
    except (TypeError, ValueError):
        return None


def _normalize_salary_period(raw_period: str | None) -> str | None:
    if not raw_period:
        return None
    low = raw_period.strip().lower()
    if low in {"annual", "annually", "year", "yearly"}:
        return "year"
    if low in {"month", "monthly"}:
        return "month"
    if low in {"hour", "hourly"}:
        return "hour"
    if low in {"week", "weekly"}:
        return "week"
    return sanitize_plain_text(raw_period, max_length=16)


class JobicyConnector(BaseOpportunityConnector):
    """
    Conector para a API pública oficial v2 da Jobicy (`industry=dev`).
    Política oficial permite armazenamento, análise e exibição com atribuição à Jobicy
    e frequência máxima de 1 sincronização por hora (3600s).
    """

    definition = SourceDefinition(
        slug="jobicy",
        name="Jobicy",
        source_type=SourceType.JSON_API.value,
        base_url="https://jobicy.com/api/v2/remote-jobs?count=50&industry=dev",
        terms_url="https://jobicy.com/terms-conditions",
        attribution_text=(
            "Fonte: Jobicy — crédito obrigatório à Jobicy com link direto para a vaga original."
        ),
        refresh_interval_seconds=3600,
        enabled_by_default=True,
    )

    def parse_payload(self, payload: Any) -> list[NormalizedOpportunityDraft]:
        if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
            raise ConnectorPayloadError(
                "Jobicy retornou formato inválido (esperado objeto JSON com lista 'jobs')."
            )

        drafts: list[NormalizedOpportunityDraft] = []
        seen_clone_signatures: set[tuple[str, str, str]] = set()

        for item in payload["jobs"]:
            if not isinstance(item, dict):
                continue

            raw_id = item.get("id")
            raw_title = sanitize_plain_text(item.get("jobTitle"))
            raw_url = item.get("url")
            if raw_id is None or not raw_title or not isinstance(raw_url, str):
                continue

            try:
                source_url = normalize_canonical_url(raw_url)
                application_url = validate_safe_external_url(raw_url)
            except ValueError:
                continue

            company_name = sanitize_plain_text(item.get("companyName"), max_length=200)
            raw_geo = sanitize_plain_text(item.get("jobGeo"))

            # Deduplica clones multi-país idênticos emitidos pela Jobicy no mesmo lote
            base_title_norm = normalize_classification_text(
                _TRAILING_GEO_SUFFIX_RE.sub("", raw_title)
            )
            clone_sig = (
                normalize_classification_text(company_name),
                base_title_norm,
                normalize_classification_text(raw_geo),
            )
            if clone_sig[0] and clone_sig in seen_clone_signatures:
                continue
            seen_clone_signatures.add(clone_sig)

            raw_industry = item.get("jobIndustry")
            industries = (
                normalize_string_list(raw_industry)
                if isinstance(raw_industry, list)
                else normalize_string_list([ str(raw_industry) ]) if raw_industry else []
            )
            raw_job_types = item.get("jobType")
            job_types = (
                normalize_string_list(raw_job_types)
                if isinstance(raw_job_types, list)
                else normalize_string_list([ str(raw_job_types) ]) if raw_job_types else []
            )
            job_level = sanitize_plain_text(item.get("jobLevel"), max_length=64)

            classifier_tags = list(industries) + list(job_types)
            if job_level and job_level.lower() not in {"any", "all"}:
                classifier_tags.append(job_level)

            description = sanitize_external_html_text(
                item.get("jobDescription") or item.get("jobExcerpt")
            )
            decision = classify_opportunity(
                title=raw_title,
                tags=classifier_tags,
                description=description,
            )

            opp_type = decision.opportunity_type
            emp_type = decision.employment_type

            # Reforça metadados estruturados de nível/contrato quando não conflitantes
            level_low = (job_level or "").lower()
            jt_low = " ".join(job_types).lower()
            if "internship" in level_low or "internship" in jt_low:
                opp_type = OpportunityType.INTERNSHIP.value
                emp_type = EmploymentType.INTERNSHIP.value
            elif ("junior" in level_low or "entry" in level_low) and opp_type == OpportunityType.OTHER.value:
                opp_type = OpportunityType.JUNIOR.value

            if emp_type == EmploymentType.UNKNOWN.value:
                if "freelance" in jt_low:
                    emp_type = EmploymentType.FREELANCE.value
                elif "contract" in jt_low or "contractor" in jt_low:
                    emp_type = EmploymentType.PJ.value
                elif "temporary" in jt_low:
                    emp_type = EmploymentType.TEMPORARY.value

            eligible_countries, country, eligibility_unknown = parse_geo_eligibility(raw_geo)

            salary_min = _parse_optional_float(item.get("salaryMin"))
            salary_max = _parse_optional_float(item.get("salaryMax"))
            salary_currency = (
                sanitize_plain_text(item.get("salaryCurrency"), max_length=16)
                or ("USD" if (salary_min or salary_max) else None)
            )
            salary_period = _normalize_salary_period(item.get("salaryPeriod")) or (
                "year" if (salary_min or salary_max) else None
            )

            published_at = parse_iso_datetime(item.get("pubDate"))

            drafts.append(
                NormalizedOpportunityDraft(
                    external_id=str(raw_id).strip(),
                    title=raw_title,
                    company_name=company_name,
                    description=description,
                    opportunity_type=opp_type,
                    employment_type=emp_type,
                    work_mode=WorkMode.REMOTE.value,
                    location_text=raw_geo,
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
                    technologies=industries,
                    source_url=source_url,
                    application_url=application_url,
                    published_at=published_at,
                    deadline_at=None,
                    source_status=ExternalSourceStatus.ACTIVE.value,
                    professional_area=decision.professional_area,
                    secondary_areas=list(decision.secondary_areas),
                    raw_metadata={
                        "job_slug": sanitize_plain_text(item.get("jobSlug")),
                        "job_level": job_level,
                        "job_type": job_types,
                        "source": "jobicy",
                    },
                )
            )

        return drafts

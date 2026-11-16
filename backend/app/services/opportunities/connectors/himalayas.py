from datetime import UTC, datetime
from typing import Any

from app.models.opportunity import (
    EmploymentType,
    ExternalSourceStatus,
    OpportunityType,
    SourceType,
    WorkMode,
)
from app.services.opportunities.classification import classify_opportunity
from app.services.opportunities.connectors.base import (
    BaseOpportunityConnector,
    ConnectorPayloadError,
    NormalizedOpportunityDraft,
    SourceDefinition,
    parse_iso_datetime,
)
from app.services.opportunities.sanitization import (
    normalize_canonical_url,
    normalize_string_list,
    sanitize_external_html_text,
    sanitize_plain_text,
    validate_safe_external_url,
)


def _parse_optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
        return parsed if parsed > 0 else None
    except (TypeError, ValueError):
        return None


class HimalayasConnector(BaseOpportunityConnector):
    """
    Conector para a API pública oficial de vagas remotas da Himalayas.
    Cumpre os termos de atribuição, preserva o `applicationLink` oficial e descarta
    vagas expiradas (`expiryDate`).
    """

    definition = SourceDefinition(
        slug="himalayas",
        name="Himalayas",
        source_type=SourceType.JSON_API.value,
        base_url="https://himalayas.app/jobs/api/search?q=software+developer",
        terms_url="https://himalayas.app/api",
        attribution_text=(
            "Fonte: Himalayas — atribuição obrigatória à Himalayas e candidatura via applicationLink oficial."
        ),
        refresh_interval_seconds=3600,
        enabled_by_default=True,
    )

    def parse_payload(self, payload: Any) -> list[NormalizedOpportunityDraft]:
        if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
            raise ConnectorPayloadError(
                "Himalayas retornou formato inválido (esperado objeto JSON com lista 'jobs')."
            )

        now = datetime.now(UTC)
        drafts: list[NormalizedOpportunityDraft] = []

        for item in payload["jobs"]:
            if not isinstance(item, dict):
                continue

            raw_guid = item.get("guid")
            raw_title = sanitize_plain_text(item.get("title"))
            if not isinstance(raw_guid, str) or not raw_guid.strip() or not raw_title:
                continue

            try:
                source_url = normalize_canonical_url(raw_guid)
            except ValueError:
                continue

            deadline_at = parse_iso_datetime(item.get("expiryDate"))
            if deadline_at is not None and deadline_at < now:
                # Termos da Himalayas exigem não exibir vagas já expiradas
                continue

            application_url: str | None = None
            raw_apply = item.get("applicationLink")
            if isinstance(raw_apply, str) and raw_apply.strip():
                try:
                    application_url = validate_safe_external_url(raw_apply)
                except ValueError:
                    application_url = None

            raw_categories = item.get("categories") if isinstance(item.get("categories"), list) else []
            cleaned_categories = normalize_string_list(
                [str(c).replace("-", " ") for c in raw_categories[:8]]
            )

            raw_seniority = item.get("seniority") if isinstance(item.get("seniority"), list) else []
            seniority_list = normalize_string_list([str(s) for s in raw_seniority])
            emp_raw = sanitize_plain_text(item.get("employmentType"), max_length=64) or ""

            classifier_tags = list(cleaned_categories) + list(seniority_list)
            if emp_raw:
                classifier_tags.append(emp_raw)

            description = sanitize_external_html_text(
                item.get("description") or item.get("excerpt")
            )
            decision = classify_opportunity(
                title=raw_title,
                tags=classifier_tags,
                description=description,
            )

            opp_type = decision.opportunity_type
            emp_type = decision.employment_type

            sen_low = " ".join(seniority_list).lower()
            emp_low = emp_raw.lower()
            if "intern" in emp_low or "intern" in sen_low:
                opp_type = OpportunityType.INTERNSHIP.value
                emp_type = EmploymentType.INTERNSHIP.value
            elif (
                ("entry-level" in sen_low or "entry level" in sen_low or "junior" in sen_low)
                and "senior" not in sen_low
                and "mid" not in sen_low
                and opp_type == OpportunityType.OTHER.value
            ):
                opp_type = OpportunityType.JUNIOR.value

            if emp_type == EmploymentType.UNKNOWN.value:
                if "freelance" in emp_low:
                    emp_type = EmploymentType.FREELANCE.value
                elif "contractor" in emp_low or "contract" in emp_low:
                    emp_type = EmploymentType.PJ.value
                elif "temporary" in emp_low:
                    emp_type = EmploymentType.TEMPORARY.value

            raw_locs = item.get("locationRestrictions")
            if isinstance(raw_locs, list):
                cleaned_locs = normalize_string_list([str(loc) for loc in raw_locs])
                if not cleaned_locs:
                    eligible_countries = ["Worldwide"]
                    country: str | None = "Worldwide"
                    location_text: str | None = "Worldwide"
                    eligibility_unknown = False
                else:
                    eligible_countries = cleaned_locs
                    country = cleaned_locs[0] if len(cleaned_locs) == 1 else None
                    location_text = ", ".join(cleaned_locs[:5])
                    eligibility_unknown = False
            else:
                eligible_countries = []
                country = None
                location_text = None
                eligibility_unknown = True

            salary_min = _parse_optional_float(item.get("minSalary"))
            salary_max = _parse_optional_float(item.get("maxSalary"))
            salary_currency = (
                sanitize_plain_text(item.get("currency"), max_length=16)
                or ("USD" if (salary_min or salary_max) else None)
            )
            raw_period = sanitize_plain_text(item.get("salaryPeriod"), max_length=16)
            salary_period = (
                raw_period.lower()
                if raw_period and raw_period.lower() in {"year", "month", "hour", "week"}
                else ("year" if (salary_min or salary_max) else None)
            )

            published_at = parse_iso_datetime(item.get("pubDate"))
            ext_id = source_url.rstrip("/").split("/")[-1] or source_url

            drafts.append(
                NormalizedOpportunityDraft(
                    external_id=ext_id[:255],
                    title=raw_title,
                    company_name=sanitize_plain_text(item.get("companyName"), max_length=200),
                    description=description,
                    opportunity_type=opp_type,
                    employment_type=emp_type,
                    work_mode=WorkMode.REMOTE.value,
                    location_text=location_text,
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
                    technologies=cleaned_categories,
                    source_url=source_url,
                    application_url=application_url or source_url,
                    published_at=published_at,
                    deadline_at=deadline_at,
                    source_status=ExternalSourceStatus.ACTIVE.value,
                    professional_area=decision.professional_area,
                    secondary_areas=list(decision.secondary_areas),
                    raw_metadata={
                        "guid": source_url,
                        "seniority": seniority_list,
                        "employment_type_raw": emp_raw,
                        "source": "himalayas",
                    },
                )
            )

        return drafts

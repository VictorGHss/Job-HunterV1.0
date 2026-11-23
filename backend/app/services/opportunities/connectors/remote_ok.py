from typing import Any
from urllib.parse import urlencode

from app.core.config import settings
from app.models.opportunity import (
    ExternalSourceStatus,
    SourceType,
    WorkMode,
)
from app.services.opportunities.classification import (
    classify_opportunity,
    reconcile_structured_classification,
)
from app.services.opportunities.connectors.base import (
    BaseOpportunityConnector,
    CollectionBatch,
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

REMOTE_OK_API_BASE = "https://remoteok.com/api"

# Estratégia enxuta de cobertura tecnológica: o endpoint oficial do Remote OK aplica
# semântica AND para múltiplas tags na mesma URL (?tags=a,b), portanto consultamos um
# conjunto pequeno, limitado e configurável de tags individuais com deduplicação por ID.
DEFAULT_REMOTE_OK_TECH_TAGS: tuple[str, ...] = (
    "dev",
    "python",
    "javascript",
    "java",
    "react",
    "backend",
    "data",
)


def _classify_remote_ok_types(
    title: str,
    tags: list[str],
    description: str | None = None,
) -> tuple[str, str]:
    decision = classify_opportunity(title=title, tags=tags, description=description)
    return (decision.opportunity_type, decision.employment_type)


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
    Conector para o feed JSON público da Remote OK filtrado por tags de tecnologia.
    Requer atribuição visível à Remote OK e link follow para a URL original.
    """

    definition = SourceDefinition(
        slug="remote_ok",
        name="Remote OK",
        source_type=SourceType.JSON_API.value,
        base_url="https://remoteok.com/api?tag=dev",
        terms_url="https://remoteok.com/terms",
        attribution_text=(
            "Fonte: Remote OK — atribuição obrigatória com link direto para a "
            "publicação original (sem atributo nofollow e sem uso não autorizado do logotipo)."
        ),
        refresh_interval_seconds=3600,
    )

    def __init__(
        self,
        *,
        tags: tuple[str, ...] | list[str] | None = None,
        max_queries: int | None = None,
        page_delay_seconds: float = 0.5,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        raw_tags = DEFAULT_REMOTE_OK_TECH_TAGS if tags is None else tags
        cleaned_tags: list[str] = []
        seen: set[str] = set()
        for t in raw_tags:
            if not isinstance(t, str):
                continue
            norm = t.strip().lower()
            if norm and norm not in seen:
                seen.add(norm)
                cleaned_tags.append(norm)
        self.tags: tuple[str, ...] = tuple(cleaned_tags)
        self.max_queries = max(
            1,
            int(max_queries if max_queries is not None else settings.sync_remote_ok_max_queries),
        )
        self.page_delay_seconds = max(0.0, float(page_delay_seconds))

    def _build_query_urls(self) -> list[str]:
        if not self.tags:
            return [REMOTE_OK_API_BASE]
        selected = self.tags[: self.max_queries]
        return [f"{REMOTE_OK_API_BASE}?{urlencode({'tag': tag})}" for tag in selected]

    def parse_payload(self, payload: Any) -> list[NormalizedOpportunityDraft]:
        if not isinstance(payload, list):
            raise ConnectorPayloadError(
                "Remote OK retornou estrutura inválida (esperado array JSON)."
            )

        drafts: list[NormalizedOpportunityDraft] = []
        received_count = 0
        rejected_count = 0
        rejection_breakdown: dict[str, int] = {}

        for idx, item in enumerate(payload):
            if not isinstance(item, dict):
                received_count += 1
                rejected_count += 1
                rejection_breakdown["invalid_item"] = (
                    rejection_breakdown.get("invalid_item", 0) + 1
                )
                continue
            # O primeiro elemento do feed Remote OK é o banner legal {"legal": "..."} sem campos de vaga
            if idx == 0 and "legal" in item and "id" not in item and "position" not in item:
                continue

            received_count += 1
            raw_id = item.get("id")
            raw_title = sanitize_plain_text(item.get("position"))
            raw_url = item.get("url")
            if raw_id is None or not raw_title or not isinstance(raw_url, str):
                rejected_count += 1
                rejection_breakdown["missing_required_fields"] = (
                    rejection_breakdown.get("missing_required_fields", 0) + 1
                )
                continue

            try:
                source_url = normalize_canonical_url(raw_url)
            except ValueError:
                rejected_count += 1
                rejection_breakdown["invalid_url"] = (
                    rejection_breakdown.get("invalid_url", 0) + 1
                )
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
            description = sanitize_external_html_text(item.get("description"))
            decision = classify_opportunity(
                title=raw_title,
                tags=tags,
                description=description,
            )
            opp_type, emp_type, sen_level = reconcile_structured_classification(decision)
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
                    professional_area=decision.professional_area,
                    secondary_areas=list(decision.secondary_areas),
                    seniority_level=sen_level,
                    experience_requirement_mode=decision.experience_requirement_mode,
                    experience_min_years=decision.experience_min_years,
                    experience_preferred_years=decision.experience_preferred_years,
                    experience_summary=decision.experience_summary,
                    raw_metadata={
                        "slug": sanitize_plain_text(item.get("slug")),
                        "source": "remote_ok",
                    },
                )
            )

        self.last_batch = CollectionBatch(
            received_count=received_count,
            valid_drafts=list(drafts),
            rejected_count=rejected_count,
            rejection_breakdown=rejection_breakdown,
        )
        return drafts

    def collect(self) -> list[NormalizedOpportunityDraft]:
        urls = self._build_query_urls()
        all_drafts: list[NormalizedOpportunityDraft] = []
        seen_ids: set[str] = set()
        total_rejected = 0
        rejection_breakdown: dict[str, int] = {}

        for idx, url in enumerate(urls):
            if idx > 0 and self.page_delay_seconds > 0:
                self.sleep_fn(self.page_delay_seconds)
            payload = self.fetch_json(url)
            page_drafts = self.parse_payload(payload)
            page_batch = self.last_batch

            for draft in page_drafts:
                if draft.external_id in seen_ids:
                    continue
                seen_ids.add(draft.external_id)
                all_drafts.append(draft)

            total_rejected += page_batch.rejected_count
            for reason, cnt in page_batch.rejection_breakdown.items():
                rejection_breakdown[reason] = rejection_breakdown.get(reason, 0) + cnt

        self.last_batch = CollectionBatch(
            received_count=len(all_drafts) + total_rejected,
            valid_drafts=list(all_drafts),
            rejected_count=total_rejected,
            rejection_breakdown=rejection_breakdown,
        )
        return all_drafts

from typing import Any
from urllib.parse import urlencode, urlparse

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
    SourceLifecycleSignal,
    parse_iso_datetime,
)
from app.services.opportunities.matching import is_deadline_expired, utc_now
from app.services.opportunities.sanitization import (
    normalize_canonical_url,
    normalize_string_list,
    sanitize_external_html_text,
    sanitize_plain_text,
    validate_safe_external_url,
)
from app.services.opportunities.technology_normalization import preserve_raw_string_list

HIMALAYAS_BROWSE_ENDPOINT = "https://himalayas.app/jobs/api"
HIMALAYAS_SEARCH_ENDPOINT = "https://himalayas.app/jobs/api/search"

# Conceitos técnicos e de início de carreira cobertos nas buscas segmentadas controladas
DEFAULT_HIMALAYAS_SEARCH_QUERIES: tuple[str, ...] = (
    "software developer",
    "intern",
    "internship",
    "entry-level",
    "junior",
    "backend",
    "frontend",
    "data",
    "artificial intelligence",
    "qa",
)


def _parse_optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
        return parsed if parsed > 0 else None
    except (TypeError, ValueError):
        return None


def _extract_himalayas_external_id(source_url: str) -> str:
    path_clean = urlparse(source_url).path.strip("/")
    if path_clean.startswith("companies/"):
        path_clean = path_clean[len("companies/") :]
    return (path_clean or source_url)[:255]


def _normalize_timezone_restrictions(raw_value: Any) -> list[str | int]:
    if not isinstance(raw_value, list):
        return []
    result: list[str | int] = []
    seen: set[str] = set()
    for item in raw_value[:48]:
        if isinstance(item, bool) or item is None:
            continue
        if isinstance(item, (int, float)):
            val = int(item)
            key = str(val)
            if key not in seen:
                seen.add(key)
                result.append(val)
        elif isinstance(item, str):
            cleaned = sanitize_plain_text(item, max_length=64)
            if cleaned and cleaned.lower() not in seen:
                seen.add(cleaned.lower())
                result.append(cleaned)
    return result


class HimalayasConnector(BaseOpportunityConnector):
    """
    Conector para a API pública oficial de vagas remotas da Himalayas.
    Prioriza o catálogo completo paginado por cursor (`GET /jobs/api`) e complementa
    com buscas segmentadas controladas (`GET /jobs/api/search`), deduplicando por `guid`
    antes da persistência. Suporta `HIMALAYAS_API_KEY` opcional via header
    `Authorization: Bearer <token>`, preserva `applicationLink`, `timezoneRestrictions`
    e descarta vagas com `expiryDate` vencido.
    """

    definition = SourceDefinition(
        slug="himalayas",
        name="Himalayas",
        source_type=SourceType.JSON_API.value,
        base_url="https://himalayas.app/jobs/api?limit=20",
        terms_url="https://himalayas.app/api",
        attribution_text=(
            "Fonte: Himalayas — atribuição obrigatória à Himalayas e candidatura via applicationLink oficial."
        ),
        refresh_interval_seconds=3600,
        enabled_by_default=True,
    )

    def __init__(
        self,
        *,
        api_key: str | None = None,
        page_limit: int = 20,
        max_pages: int | None = None,
        search_queries: tuple[str, ...] | list[str] | None = None,
        max_search_pages_per_query: int = 1,
        max_total_requests: int | None = None,
        page_delay_seconds: float = 0.0,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        raw_key = settings.himalayas_api_key if api_key is None else api_key
        self._api_key = raw_key.strip() if isinstance(raw_key, str) else ""
        # A documentação oficial do `/jobs/api` limita `limit` a 20 por página
        self.page_limit = max(1, min(int(page_limit), 20))
        self.max_pages = max(
            1,
            int(max_pages if max_pages is not None else settings.sync_himalayas_max_pages),
        )
        if search_queries is None:
            self.search_queries: tuple[str, ...] = DEFAULT_HIMALAYAS_SEARCH_QUERIES
        else:
            seen_q: set[str] = set()
            normalized_q: list[str] = []
            for q in search_queries:
                cleaned = q.strip()
                if cleaned and cleaned.lower() not in seen_q:
                    seen_q.add(cleaned.lower())
                    normalized_q.append(cleaned)
            self.search_queries = tuple(normalized_q)
        self.max_search_pages_per_query = max(1, int(max_search_pages_per_query))
        default_budget = self.max_pages + len(self.search_queries) * self.max_search_pages_per_query
        self.max_total_requests = max(
            1,
            int(max_total_requests if max_total_requests is not None else default_budget),
        )
        self.page_delay_seconds = max(0.0, float(page_delay_seconds))

    def _build_auth_headers(self) -> dict[str, str] | None:
        if not self._api_key:
            return None
        return {"Authorization": f"Bearer {self._api_key}"}

    def _build_browse_url(self, *, cursor: str | None = None) -> str:
        params: dict[str, str] = {"limit": str(self.page_limit)}
        if cursor:
            params["cursor"] = cursor
        return f"{HIMALAYAS_BROWSE_ENDPOINT}?{urlencode(params)}"

    def _build_search_url(self, *, query: str, page: int = 1) -> str:
        params: dict[str, str] = {"q": query, "page": str(page)}
        return f"{HIMALAYAS_SEARCH_ENDPOINT}?{urlencode(params)}"

    def parse_payload(self, payload: Any) -> list[NormalizedOpportunityDraft]:
        if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
            raise ConnectorPayloadError(
                "Himalayas retornou formato inválido (esperado objeto JSON com lista 'jobs')."
            )

        now = utc_now()
        drafts: list[NormalizedOpportunityDraft] = []
        raw_jobs = payload["jobs"]
        rejected_count = 0
        rejection_breakdown: dict[str, int] = {}
        lifecycle_signals: list[SourceLifecycleSignal] = []

        for item in raw_jobs:
            if not isinstance(item, dict):
                rejected_count += 1
                rejection_breakdown["invalid_item"] = (
                    rejection_breakdown.get("invalid_item", 0) + 1
                )
                continue

            raw_guid = item.get("guid")
            raw_title = sanitize_plain_text(item.get("title"))
            if not isinstance(raw_guid, str) or not raw_guid.strip() or not raw_title:
                rejected_count += 1
                rejection_breakdown["missing_required_fields"] = (
                    rejection_breakdown.get("missing_required_fields", 0) + 1
                )
                continue

            try:
                source_url = normalize_canonical_url(raw_guid)
            except ValueError:
                rejected_count += 1
                rejection_breakdown["invalid_url"] = (
                    rejection_breakdown.get("invalid_url", 0) + 1
                )
                continue

            ext_id = _extract_himalayas_external_id(source_url)
            deadline_at = parse_iso_datetime(item.get("expiryDate"))
            if is_deadline_expired(deadline_at, now=now):
                # Termos da Himalayas exigem não exibir vagas já expiradas:
                # emite sinal de expiração para atualizar eventual vaga já persistida
                lifecycle_signals.append(
                    SourceLifecycleSignal(
                        external_id=ext_id,
                        source_url=source_url,
                        status=ExternalSourceStatus.EXPIRED.value,
                        deadline_at=deadline_at,
                        reason="expiryDate vencido na API Himalayas",
                    )
                )
                rejected_count += 1
                rejection_breakdown["expired"] = rejection_breakdown.get("expired", 0) + 1
                continue

            application_url: str | None = None
            raw_apply = item.get("applicationLink")
            if isinstance(raw_apply, str) and raw_apply.strip():
                try:
                    application_url = validate_safe_external_url(raw_apply)
                except ValueError:
                    application_url = None

            raw_categories = item.get("categories") if isinstance(item.get("categories"), list) else []
            preserved_categories = preserve_raw_string_list(raw_categories)
            classifier_categories = normalize_string_list(
                [c.replace("-", " ") for c in preserved_categories],
                max_items=200,
            )

            raw_seniority = item.get("seniority") if isinstance(item.get("seniority"), list) else []
            seniority_list = normalize_string_list([str(s) for s in raw_seniority])
            emp_raw = sanitize_plain_text(item.get("employmentType"), max_length=64) or ""

            classifier_tags = list(classifier_categories) + list(seniority_list)
            if emp_raw:
                classifier_tags.append(emp_raw)

            description = sanitize_external_html_text(
                item.get("description") or item.get("excerpt")
            )
            decision = classify_opportunity(
                title=raw_title,
                tags=classifier_tags,
                description=description,
                metadata_levels=seniority_list,
            )

            opp_type, emp_type, seniority_level = reconcile_structured_classification(
                decision,
                metadata_levels=seniority_list,
                metadata_job_types=[emp_raw] if emp_raw else [],
            )

            raw_locs = item.get("locationRestrictions")
            timezone_restrictions = _normalize_timezone_restrictions(
                item.get("timezoneRestrictions")
            )

            if isinstance(raw_locs, list):
                cleaned_locs = normalize_string_list(
                    [str(loc) for loc in raw_locs], max_items=250
                )
                if not cleaned_locs:
                    eligible_countries = ["Worldwide"]
                    country: str | None = "Worldwide"
                    location_text: str | None = "Worldwide"
                    eligibility_unknown = False
                else:
                    eligible_countries = cleaned_locs
                    country = cleaned_locs[0] if len(cleaned_locs) == 1 else None
                    location_text = ", ".join(cleaned_locs[:5])
                    if len(cleaned_locs) > 5:
                        location_text = f"{location_text} (+{len(cleaned_locs) - 5})"
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

            drafts.append(
                NormalizedOpportunityDraft(
                    external_id=ext_id,
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
                    technologies=[],
                    source_url=source_url,
                    application_url=application_url or source_url,
                    published_at=published_at,
                    deadline_at=deadline_at,
                    source_status=ExternalSourceStatus.ACTIVE.value,
                    professional_area=decision.professional_area,
                    secondary_areas=list(decision.secondary_areas),
                    seniority_level=seniority_level,
                    experience_requirement_mode=decision.experience_requirement_mode,
                    experience_min_years=decision.experience_min_years,
                    experience_preferred_years=decision.experience_preferred_years,
                    experience_summary=decision.experience_summary,
                    raw_metadata={
                        "guid": source_url,
                        "application_link": application_url or source_url,
                        "categories": preserved_categories,
                        "seniority": seniority_list,
                        "employment_type_raw": emp_raw,
                        "timezone_restrictions": timezone_restrictions,
                        "source": "himalayas",
                    },
                )
            )

        self.last_batch = CollectionBatch(
            received_count=len(raw_jobs),
            valid_drafts=list(drafts),
            rejected_count=rejected_count,
            rejection_breakdown=rejection_breakdown,
            lifecycle_signals=lifecycle_signals,
        )
        return drafts

    def collect(self) -> list[NormalizedOpportunityDraft]:
        all_drafts: list[NormalizedOpportunityDraft] = []
        seen_valid_ids: set[str] = set()
        seen_expired_ids: set[str] = set()
        all_signals: list[SourceLifecycleSignal] = []
        total_rejected_non_expired = 0
        rejection_breakdown: dict[str, int] = {}
        requests_made = 0
        auth_headers = self._build_auth_headers()

        def _consume_payload(payload: Any) -> None:
            nonlocal total_rejected_non_expired
            page_drafts = self.parse_payload(payload)
            page_batch = self.last_batch

            for draft in page_drafts:
                if draft.external_id in seen_valid_ids:
                    continue
                seen_valid_ids.add(draft.external_id)
                all_drafts.append(draft)

            for sig in page_batch.lifecycle_signals:
                if sig.external_id in seen_expired_ids:
                    continue
                seen_expired_ids.add(sig.external_id)
                all_signals.append(sig)
                rejection_breakdown["expired"] = rejection_breakdown.get("expired", 0) + 1

            for reason, cnt in page_batch.rejection_breakdown.items():
                if reason == "expired":
                    continue
                total_rejected_non_expired += cnt
                rejection_breakdown[reason] = rejection_breakdown.get(reason, 0) + cnt

        # 1. Catálogo completo oficial paginado por cursor (`GET /jobs/api`)
        cursor: str | None = None
        seen_cursors: set[str] = set()
        browse_pages = 0
        while browse_pages < self.max_pages and requests_made < self.max_total_requests:
            if requests_made > 0 and self.page_delay_seconds > 0:
                self.sleep_fn(self.page_delay_seconds)
            url = self._build_browse_url(cursor=cursor)
            payload = self.fetch_json(url, extra_headers=auth_headers)
            requests_made += 1
            browse_pages += 1
            _consume_payload(payload)

            raw_next = payload.get("nextCursor")
            next_cursor = (
                raw_next.strip()
                if isinstance(raw_next, str) and raw_next.strip()
                else None
            )
            if not next_cursor or next_cursor in seen_cursors or not payload.get("jobs"):
                break
            seen_cursors.add(next_cursor)
            cursor = next_cursor

        # 2. Buscas segmentadas controladas (`GET /jobs/api/search`) cobrindo termos prioritários
        for query in self.search_queries:
            if requests_made >= self.max_total_requests:
                break
            for page_num in range(1, self.max_search_pages_per_query + 1):
                if requests_made >= self.max_total_requests:
                    break
                if requests_made > 0 and self.page_delay_seconds > 0:
                    self.sleep_fn(self.page_delay_seconds)
                url = self._build_search_url(query=query, page=page_num)
                payload = self.fetch_json(url, extra_headers=auth_headers)
                requests_made += 1
                _consume_payload(payload)
                if not payload.get("jobs"):
                    break

        total_rejected = total_rejected_non_expired + len(seen_expired_ids)
        total_received = len(all_drafts) + total_rejected

        self.last_batch = CollectionBatch(
            received_count=total_received,
            valid_drafts=list(all_drafts),
            rejected_count=total_rejected,
            rejection_breakdown=rejection_breakdown,
            lifecycle_signals=all_signals,
        )
        return all_drafts

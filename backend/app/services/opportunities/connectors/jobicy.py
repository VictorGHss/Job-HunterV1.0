from typing import Any
import re
from urllib.parse import urlencode

from app.core.config import settings
from app.models.opportunity import (
    ExternalSourceStatus,
    SourceType,
    WorkMode,
)
from app.services.opportunities.classification import (
    classify_opportunity,
    normalize_classification_text,
    reconcile_structured_classification,
)
from app.services.opportunities.connectors.base import (
    BaseOpportunityConnector,
    CollectionBatch,
    ConnectorError,
    ConnectorPayloadError,
    NormalizedOpportunityDraft,
    SourceDefinition,
    SourceLifecycleSignal,
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
from app.services.opportunities.technology_normalization import preserve_raw_industry

_TRAILING_GEO_SUFFIX_RE = re.compile(
    r"\s*\|\s*(?P<geo>uk|united kingdom|germany|spain|sweden|ireland|france|netherlands|poland|italy|usa|us|canada|brazil|brasil|mexico|argentina|colombia|chile|portugal|australia|india|emea|apac|latam|europe|worldwide)\s*(?:\|\s*remote)?\s*$",
    re.I,
)

JOBICY_JOBS_ENDPOINT = "https://jobicy.com/api/jobs"
JOBICY_STATUS_ENDPOINT = "https://jobicy.com/api/jobs/status"
DEFAULT_JOBICY_INDUSTRIES: tuple[str, ...] = ("engineering", "data-science")
MIN_JOBICY_REQUEST_DELAY_SECONDS = 1.0


def extract_base_title_and_geo_suffix(raw_title: str) -> tuple[str, str | None]:
    match = _TRAILING_GEO_SUFFIX_RE.search(raw_title)
    if not match:
        return (raw_title.strip(), None)
    geo_suffix = match.group("geo").strip()
    base_title = raw_title[: match.start()].strip()
    return (base_title or raw_title.strip(), geo_suffix)


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
    Conector para a API pública oficial da Jobicy (`/api/jobs` com paginação por cursor
    `nextCursor` / `hasMore` e verificação de status em lote `/api/jobs/status`).
    Respeita pausa mínima de 1s entre requisições, teto de páginas, atribuição visível à
    Jobicy e frequência máxima de 1 sincronização por hora (3600s).
    """

    definition = SourceDefinition(
        slug="jobicy",
        name="Jobicy",
        source_type=SourceType.JSON_API.value,
        base_url="https://jobicy.com/api/jobs?count=100&industry=engineering",
        terms_url="https://jobicy.com/terms-conditions",
        attribution_text=(
            "Fonte: Jobicy — crédito obrigatório à Jobicy com link direto para a vaga original."
        ),
        refresh_interval_seconds=3600,
        enabled_by_default=True,
    )

    def __init__(
        self,
        *,
        industries: tuple[str | None, ...] | list[str | None] | None = None,
        geo: str | None = None,
        tag: str | None = None,
        page_size: int = 100,
        max_pages: int | None = None,
        page_delay_seconds: float = MIN_JOBICY_REQUEST_DELAY_SECONDS,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        if industries is None:
            self.industries: tuple[str | None, ...] = DEFAULT_JOBICY_INDUSTRIES
        else:
            cleaned = tuple(
                ind.strip() if isinstance(ind, str) and ind.strip() else None
                for ind in industries
            )
            self.industries = cleaned or (None,)
        self.geo = geo.strip() if isinstance(geo, str) and geo.strip() else None
        self.tag = tag.strip() if isinstance(tag, str) and tag.strip() else None
        self.page_size = max(1, min(int(page_size), 100))
        self.max_pages = max(
            1,
            int(max_pages if max_pages is not None else settings.sync_jobicy_max_pages),
        )
        # Documentação oficial da Jobicy exige pausa mínima de 1s entre requisições sequenciais
        self.page_delay_seconds = max(MIN_JOBICY_REQUEST_DELAY_SECONDS, float(page_delay_seconds))

    def _build_jobs_url(
        self,
        *,
        industry: str | None,
        cursor: str | None = None,
    ) -> str:
        params: dict[str, str] = {"count": str(self.page_size)}
        if industry:
            params["industry"] = industry
        if self.geo:
            params["geo"] = self.geo
        if self.tag:
            params["tag"] = self.tag
        if cursor:
            params["cursor"] = cursor
        return f"{JOBICY_JOBS_ENDPOINT}?{urlencode(params)}"

    def parse_payload(self, payload: Any) -> list[NormalizedOpportunityDraft]:
        if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
            raise ConnectorPayloadError(
                "Jobicy retornou formato inválido (esperado objeto JSON com lista 'jobs')."
            )

        drafts: list[NormalizedOpportunityDraft] = []
        raw_jobs = payload["jobs"]
        rejected_count = 0
        rejection_breakdown: dict[str, int] = {}

        for item in raw_jobs:
            if not isinstance(item, dict):
                rejected_count += 1
                rejection_breakdown["invalid_item"] = (
                    rejection_breakdown.get("invalid_item", 0) + 1
                )
                continue

            raw_id = item.get("id")
            raw_title = sanitize_plain_text(item.get("jobTitle"))
            raw_url = item.get("url")
            if raw_id is None or not raw_title or not isinstance(raw_url, str):
                rejected_count += 1
                rejection_breakdown["missing_required_fields"] = (
                    rejection_breakdown.get("missing_required_fields", 0) + 1
                )
                continue

            try:
                source_url = normalize_canonical_url(raw_url)
                canonical_apply = validate_safe_external_url(raw_url)
            except ValueError:
                rejected_count += 1
                rejection_breakdown["invalid_url"] = (
                    rejection_breakdown.get("invalid_url", 0) + 1
                )
                continue

            application_url = canonical_apply
            raw_apply = item.get("applicationUrl") or item.get("applyUrl")
            if isinstance(raw_apply, str) and raw_apply.strip():
                try:
                    application_url = validate_safe_external_url(raw_apply)
                except ValueError:
                    application_url = canonical_apply

            company_name = sanitize_plain_text(item.get("companyName"), max_length=200)
            raw_geo = sanitize_plain_text(item.get("jobGeo"))
            base_title, geo_suffix = extract_base_title_and_geo_suffix(raw_title)
            base_title_norm = normalize_classification_text(base_title)

            raw_industry = item.get("jobIndustry")
            preserved_industry = preserve_raw_industry(raw_industry)
            industries = (
                normalize_string_list(preserved_industry)
                if isinstance(preserved_industry, list)
                else normalize_string_list([preserved_industry]) if preserved_industry else []
            )
            raw_job_types = item.get("jobType")
            job_types = (
                normalize_string_list(raw_job_types)
                if isinstance(raw_job_types, list)
                else normalize_string_list([str(raw_job_types)]) if raw_job_types else []
            )
            job_level = sanitize_plain_text(item.get("jobLevel"), max_length=64)

            classifier_tags = list(industries) + list(job_types)
            level_meta: list[str] = []
            if job_level and job_level.lower() not in {"any", "all"}:
                classifier_tags.append(job_level)
                level_meta.append(job_level)

            description = sanitize_external_html_text(
                item.get("jobDescription") or item.get("jobExcerpt")
            )
            decision = classify_opportunity(
                title=raw_title,
                tags=classifier_tags,
                description=description,
                metadata_levels=level_meta,
            )

            opp_type, emp_type, seniority_level = reconcile_structured_classification(
                decision,
                metadata_levels=level_meta,
                metadata_job_types=job_types,
            )

            eligible_countries, country, eligibility_unknown = parse_geo_eligibility(raw_geo)
            if (
                geo_suffix
                and "Worldwide" not in eligible_countries
                and not any(c.lower() == geo_suffix.lower() for c in eligible_countries)
            ):
                eligible_countries.append(geo_suffix)
                eligibility_unknown = False
                if country is None and len(eligible_countries) == 1:
                    country = geo_suffix

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
                    technologies=[],
                    source_url=source_url,
                    application_url=application_url,
                    published_at=published_at,
                    deadline_at=None,
                    source_status=ExternalSourceStatus.ACTIVE.value,
                    professional_area=decision.professional_area,
                    secondary_areas=list(decision.secondary_areas),
                    seniority_level=seniority_level,
                    experience_requirement_mode=decision.experience_requirement_mode,
                    experience_min_years=decision.experience_min_years,
                    experience_preferred_years=decision.experience_preferred_years,
                    experience_summary=decision.experience_summary,
                    raw_metadata={
                        "job_slug": sanitize_plain_text(item.get("jobSlug")),
                        "job_industry": preserved_industry,
                        "job_level": job_level,
                        "job_type": job_types,
                        "base_title_norm": base_title_norm,
                        "geo_suffix": geo_suffix,
                        "source": "jobicy",
                    },
                )
            )

        self.last_batch = CollectionBatch(
            received_count=len(raw_jobs),
            valid_drafts=list(drafts),
            rejected_count=rejected_count,
            rejection_breakdown=rejection_breakdown,
        )
        return drafts

    def collect(self) -> list[NormalizedOpportunityDraft]:
        all_drafts: list[NormalizedOpportunityDraft] = []
        seen_external_ids: set[str] = set()
        total_received = 0
        total_rejected = 0
        rejection_breakdown: dict[str, int] = {}
        pages_fetched = 0

        for industry in self.industries:
            if pages_fetched >= self.max_pages:
                break
            cursor: str | None = None
            seen_cursors: set[str] = set()

            while pages_fetched < self.max_pages:
                if pages_fetched > 0:
                    self.sleep_fn(self.page_delay_seconds)
                url = self._build_jobs_url(industry=industry, cursor=cursor)
                payload = self.fetch_json(url)
                pages_fetched += 1

                page_drafts = self.parse_payload(payload)
                page_batch = self.last_batch
                total_rejected += page_batch.rejected_count
                for reason, cnt in page_batch.rejection_breakdown.items():
                    rejection_breakdown[reason] = rejection_breakdown.get(reason, 0) + cnt

                unique_valid_in_page = 0
                for draft in page_drafts:
                    if draft.external_id in seen_external_ids:
                        continue
                    seen_external_ids.add(draft.external_id)
                    all_drafts.append(draft)
                    unique_valid_in_page += 1
                total_received += unique_valid_in_page + page_batch.rejected_count

                has_more = payload.get("hasMore")
                raw_next_cursor = payload.get("nextCursor")
                next_cursor = (
                    raw_next_cursor.strip()
                    if isinstance(raw_next_cursor, str) and raw_next_cursor.strip()
                    else None
                )
                if has_more is False or not next_cursor or next_cursor in seen_cursors:
                    break
                if not payload.get("jobs"):
                    break
                seen_cursors.add(next_cursor)
                cursor = next_cursor

        self.last_batch = CollectionBatch(
            received_count=total_received,
            valid_drafts=list(all_drafts),
            rejected_count=total_rejected,
            rejection_breakdown=rejection_breakdown,
        )
        return all_drafts

    def _parse_status_response(self, payload: Any) -> dict[str, str]:
        """Normaliza diferentes representações possíveis da resposta de `/api/jobs/status`."""
        status_map: dict[str, str] = {}
        if isinstance(payload, dict):
            if isinstance(payload.get("statuses"), dict):
                for k, v in payload["statuses"].items():
                    if isinstance(v, str):
                        status_map[str(k).strip()] = v.strip().lower()
                    elif isinstance(v, dict) and isinstance(v.get("status"), str):
                        status_map[str(k).strip()] = v["status"].strip().lower()
            elif isinstance(payload.get("jobs"), list):
                for entry in payload["jobs"]:
                    if isinstance(entry, dict) and entry.get("id") is not None and isinstance(entry.get("status"), str):
                        status_map[str(entry["id"]).strip()] = entry["status"].strip().lower()
            else:
                for k, v in payload.items():
                    if str(k).strip().isdigit():
                        if isinstance(v, str):
                            status_map[str(k).strip()] = v.strip().lower()
                        elif isinstance(v, dict) and isinstance(v.get("status"), str):
                            status_map[str(k).strip()] = v["status"].strip().lower()
        return status_map

    def check_publications_status_batch(
        self,
        items: list[tuple[str, str, dict[str, Any] | None]],
    ) -> dict[str, SourceLifecycleSignal]:
        """
        Consulta o endpoint oficial `/api/jobs/status?ids=...` (até 100 IDs por lote)
        para confirmar encerramento ou continuidade sem encerrar vagas apenas por saída
        da janela deslizante de 7 dias.
        """
        numeric_items = [
            (ext_id.strip(), source_url)
            for ext_id, source_url, _ in items
            if ext_id and ext_id.strip().isdigit()
        ]
        if not numeric_items:
            return {}

        signals: dict[str, SourceLifecycleSignal] = {}
        for batch_idx in range(0, len(numeric_items), 100):
            if batch_idx > 0:
                self.sleep_fn(self.page_delay_seconds)
            chunk = numeric_items[batch_idx : batch_idx + 100]
            ids_param = ",".join(ext_id for ext_id, _ in chunk)
            url = f"{JOBICY_STATUS_ENDPOINT}?{urlencode({'ids': ids_param})}"
            try:
                payload = self.fetch_json(url)
            except (ConnectorError, Exception):
                break

            status_map = self._parse_status_response(payload)
            for ext_id, source_url in chunk:
                raw_st = status_map.get(ext_id)
                if raw_st == "active":
                    signals[ext_id] = SourceLifecycleSignal(
                        external_id=ext_id,
                        source_url=source_url,
                        status=ExternalSourceStatus.ACTIVE.value,
                        reason="Vaga confirmada ativa via Jobicy /api/jobs/status",
                    )
                elif raw_st in {"closed", "expired"}:
                    signals[ext_id] = SourceLifecycleSignal(
                        external_id=ext_id,
                        source_url=source_url,
                        status=ExternalSourceStatus.CLOSED.value,
                        reason="Vaga confirmada encerrada via Jobicy /api/jobs/status",
                    )
                # Se 'unknown' ou ausente, mantém postura conservadora (não encerra automaticamente)
        return signals

    def check_publication_status(
        self,
        external_id: str,
        source_url: str,
        metadata: dict[str, Any] | None = None,
    ) -> SourceLifecycleSignal | None:
        batch_signals = self.check_publications_status_batch(
            [(external_id, source_url, metadata)]
        )
        return batch_signals.get(external_id.strip())

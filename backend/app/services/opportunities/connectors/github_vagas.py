import re
from typing import Any
from urllib.parse import urlparse

from app.core.config import settings
from app.models.opportunity import (
    ExternalSourceStatus,
    ProfessionalArea,
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
    ConnectorError,
    ConnectorPayloadError,
    NormalizedOpportunityDraft,
    SourceDefinition,
    SourceLifecycleSignal,
    parse_iso_datetime,
)
from app.services.opportunities.matching import parse_location_cities
from app.services.opportunities.sanitization import (
    normalize_canonical_url,
    normalize_string_list,
    sanitize_external_html_text,
    sanitize_plain_text,
    validate_safe_external_url,
)

_BRACKET_PREFIX_RE = re.compile(r"^\s*\[([^\]]+)\]\s*")
_COMPANY_SUFFIX_RE = re.compile(r"(?:\s+[-–—]\s+|\s+na\s+|\s+@\s+)([^-–—@\n]{2,60})$")
_META_ISSUE_TITLE_RE = re.compile(
    r"(?i)\b(?:leia\s+nossas\s+regras|regras\s+do\s+reposit[oó]rio|como\s+publicar|template\s+de\s+vaga)\b"
)
_EMAIL_PII_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE_PII_RE = re.compile(
    r"(?:\+?55\s*)?(?:\(?\d{2}\)?\s*)?\d{4,5}[-\s]?\d{4}\b"
)
_LINK_NEXT_RE = re.compile(r'<([^>]+)>\s*;\s*rel\s*=\s*"?next"?', re.I)

_META_LABELS_LOWER = {
    "remoto",
    "hibrido",
    "híbrido",
    "presencial",
    "alocado",
    "junior",
    "júnior",
    "pleno",
    "senior",
    "sênior",
    "especialista",
    "estagio",
    "estágio",
    "pj",
    "clt",
    "contrato",
    "freela",
    "freelance",
    "verificada",
    "formato-sugerido",
    "stale",
    "exterior",
}


def redact_contact_pii(text: str | None) -> str | None:
    """
    Remove e-mails e telefones pessoais do texto bruto de issues comunitárias
    para conformidade com privacidade/LGPD, preservando o link oficial da issue.
    """
    if not text:
        return None
    redacted = _EMAIL_PII_RE.sub("[e-mail na issue original]", text)
    redacted = _PHONE_PII_RE.sub("[contato na issue original]", redacted)
    return redacted


def parse_github_next_link(link_header: str | None) -> str | None:
    """
    Extrai com segurança a URL de `rel="next"` do cabeçalho HTTP `Link` do GitHub,
    validando esquema HTTPS e host estritamente `api.github.com` contra SSRF.
    """
    if not link_header or not isinstance(link_header, str):
        return None
    match = _LINK_NEXT_RE.search(link_header)
    if not match:
        return None
    candidate = match.group(1).strip()
    try:
        validated = validate_safe_external_url(candidate)
    except ValueError:
        return None
    parsed = urlparse(validated)
    if parsed.scheme.lower() != "https" or (parsed.hostname or "").lower() != "api.github.com":
        return None
    return validated


def _extract_work_mode_and_location(
    raw_title: str,
    labels: list[str],
) -> tuple[str, str | None, str | None, str | None, str | None, list[str], bool, list[str]]:
    """
    Retorna `(work_mode, location_text, city, state, country, eligible_countries,
    eligibility_unknown, parsed_cities)` preservando `location_text` original e
    reconhecendo múltiplas cidades alternativas sem quebrar nomes compostos.
    """
    labels_low = {lb.strip().lower() for lb in labels}
    bracket_match = _BRACKET_PREFIX_RE.match(raw_title)
    bracket_text = bracket_match.group(1).strip() if bracket_match else ""
    combined_loc = f"{bracket_text} {' '.join(labels)}".lower()

    if "remoto" in combined_loc or "remote" in combined_loc:
        work_mode = WorkMode.REMOTE.value
    elif "híbrido" in combined_loc or "hibrido" in combined_loc or "hybrid" in combined_loc:
        work_mode = WorkMode.HYBRID.value
    elif "presencial" in combined_loc or "alocado" in labels_low or "onsite" in combined_loc:
        work_mode = WorkMode.ONSITE.value
    else:
        work_mode = WorkMode.REMOTE.value if not bracket_text else WorkMode.ONSITE.value

    non_br_markers = ("argentina", "méxico", "mexico", "portugal", "usa", "estados unidos")
    if any(m in combined_loc for m in non_br_markers) and "brasil" not in combined_loc:
        country = (bracket_text or "Exterior")[:120]
        eligible_countries = [bracket_text] if bracket_text else []
        location_text = bracket_text or "Exterior"
        return (
            work_mode,
            location_text[:255],
            None,
            None,
            country,
            eligible_countries,
            False,
            [],
        )

    country = "Brasil"
    eligible_countries = ["Brasil"]
    location_text = bracket_text or ("Remoto - Brasil" if work_mode == WorkMode.REMOTE.value else "Brasil")
    city: str | None = None
    state: str | None = None
    parsed_cities: list[str] = []

    if work_mode in {WorkMode.HYBRID.value, WorkMode.ONSITE.value}:
        parsed_cities, state = parse_location_cities(bracket_text)
        if parsed_cities:
            city = " / ".join(parsed_cities)[:120]
        else:
            city = "Outra localidade"

    return (
        work_mode,
        location_text[:255],
        city,
        state,
        country,
        eligible_countries,
        False,
        parsed_cities,
    )


def _extract_company_from_title(raw_title: str) -> str | None:
    cleaned = _BRACKET_PREFIX_RE.sub("", raw_title).strip()
    match = _COMPANY_SUFFIX_RE.search(cleaned)
    if match:
        candidate = sanitize_plain_text(match.group(1), max_length=120)
        if candidate and not any(
            tok in candidate.lower()
            for tok in ("remoto", "híbrido", "hibrido", "júnior", "junior", "pleno", "sênior", "senior", "clt", "pj")
        ):
            return candidate
    return None


class BaseGitHubIssuesVagasConnector(BaseOpportunityConnector):
    """
    Conector base para repositórios comunitários brasileiros de vagas no GitHub
    licenciados sob MIT, consumidos via API REST oficial v3 do GitHub com paginação
    real (`per_page=100` + cabeçalho `Link`) e suporte opcional a `GITHUB_TOKEN`.
    """

    default_fallback_area: str = ProfessionalArea.SOFTWARE_DEVELOPMENT.value
    id_prefix: str = "gh"

    def __init__(
        self,
        *,
        github_token: str | None = None,
        max_pages: int | None = None,
        page_delay_seconds: float = 0.0,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        raw_token = settings.github_token if github_token is None else github_token
        self._github_token = raw_token.strip() if isinstance(raw_token, str) else ""
        self.max_pages = max(
            1,
            int(max_pages if max_pages is not None else settings.sync_github_max_pages),
        )
        self.page_delay_seconds = max(0.0, float(page_delay_seconds))

    def _build_github_headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self._github_token:
            headers["Authorization"] = f"Bearer {self._github_token}"
        return headers

    def parse_payload(self, payload: Any) -> list[NormalizedOpportunityDraft]:
        if not isinstance(payload, list):
            raise ConnectorPayloadError(
                "GitHub Issues API retornou formato inválido (esperada lista JSON de issues)."
            )

        drafts: list[NormalizedOpportunityDraft] = []
        rejected_count = 0
        rejection_breakdown: dict[str, int] = {}
        lifecycle_signals: list[SourceLifecycleSignal] = []

        for item in payload:
            if not isinstance(item, dict):
                rejected_count += 1
                rejection_breakdown["invalid_item"] = (
                    rejection_breakdown.get("invalid_item", 0) + 1
                )
                continue
            # Ignora Pull Requests retornados no endpoint de issues
            if "pull_request" in item:
                rejected_count += 1
                rejection_breakdown["pull_request"] = (
                    rejection_breakdown.get("pull_request", 0) + 1
                )
                continue

            raw_number = item.get("number") or item.get("id")
            raw_title = sanitize_plain_text(item.get("title"))
            raw_url = item.get("html_url")
            if raw_number is None or not raw_title or not isinstance(raw_url, str):
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

            ext_id = f"{self.id_prefix}-{raw_number}"
            raw_labels = item.get("labels") if isinstance(item.get("labels"), list) else []
            label_names = normalize_string_list(
                [
                    lb.get("name", "")
                    if isinstance(lb, dict)
                    else str(lb)
                    for lb in raw_labels
                ]
            )
            labels_lower = {lb.lower() for lb in label_names}

            state_lower = str(item.get("state", "")).lower()
            if state_lower != "open" or bool(labels_lower & {"fechada", "encerrada", "closed"}):
                lifecycle_signals.append(
                    SourceLifecycleSignal(
                        external_id=ext_id,
                        source_url=source_url,
                        status=ExternalSourceStatus.CLOSED.value,
                        reason="Issue encerrada no GitHub",
                    )
                )
                rejected_count += 1
                rejection_breakdown["closed"] = rejection_breakdown.get("closed", 0) + 1
                continue

            if _META_ISSUE_TITLE_RE.search(raw_title):
                rejected_count += 1
                rejection_breakdown["meta_issue"] = (
                    rejection_breakdown.get("meta_issue", 0) + 1
                )
                continue

            if "stale" in labels_lower:
                lifecycle_signals.append(
                    SourceLifecycleSignal(
                        external_id=ext_id,
                        source_url=source_url,
                        status=ExternalSourceStatus.EXPIRED.value,
                        reason="Issue marcada como Stale por inatividade no GitHub",
                    )
                )
                rejected_count += 1
                rejection_breakdown["stale"] = rejection_breakdown.get("stale", 0) + 1
                continue

            redacted_body = redact_contact_pii(
                item.get("body") if isinstance(item.get("body"), str) else None
            )
            description = sanitize_external_html_text(redacted_body)

            decision = classify_opportunity(
                title=raw_title,
                tags=label_names,
                description=description,
                metadata_levels=label_names,
            )

            opp_type, emp_type, seniority_level = reconcile_structured_classification(
                decision,
                metadata_levels=label_names,
                metadata_labels=label_names,
            )
            primary_area = decision.professional_area
            secondary_areas = list(decision.secondary_areas)

            if primary_area == ProfessionalArea.UNKNOWN.value:
                primary_area = self.default_fallback_area
                if (
                    primary_area != ProfessionalArea.SOFTWARE_DEVELOPMENT.value
                    and ProfessionalArea.SOFTWARE_DEVELOPMENT.value not in secondary_areas
                ):
                    secondary_areas.append(ProfessionalArea.SOFTWARE_DEVELOPMENT.value)

            tech_tags = [
                lb for lb in label_names if lb.strip().lower() not in _META_LABELS_LOWER
            ]
            (
                work_mode,
                location_text,
                city,
                state,
                country,
                eligible_countries,
                eligibility_unknown,
                parsed_cities,
            ) = _extract_work_mode_and_location(raw_title, label_names)
            company_name = _extract_company_from_title(raw_title)
            published_at = parse_iso_datetime(item.get("created_at"))

            raw_meta: dict[str, Any] = {
                "issue_number": raw_number,
                "labels": label_names,
                "source": self.definition.slug,
            }
            if parsed_cities:
                raw_meta["cities"] = parsed_cities

            drafts.append(
                NormalizedOpportunityDraft(
                    external_id=ext_id,
                    title=raw_title,
                    company_name=company_name,
                    description=description,
                    opportunity_type=opp_type,
                    employment_type=emp_type,
                    work_mode=work_mode,
                    location_text=location_text,
                    city=city,
                    state=state,
                    country=country,
                    eligible_countries=eligible_countries,
                    eligibility_unknown=eligibility_unknown,
                    language="Português",
                    salary_min=None,
                    salary_max=None,
                    salary_currency=None,
                    salary_period=None,
                    requirements=[],
                    technologies=tech_tags,
                    source_url=source_url,
                    application_url=source_url,
                    published_at=published_at,
                    deadline_at=None,
                    source_status=ExternalSourceStatus.ACTIVE.value,
                    professional_area=primary_area,
                    secondary_areas=secondary_areas,
                    seniority_level=seniority_level,
                    experience_requirement_mode=decision.experience_requirement_mode,
                    experience_min_years=decision.experience_min_years,
                    experience_preferred_years=decision.experience_preferred_years,
                    experience_summary=decision.experience_summary,
                    raw_metadata=raw_meta,
                )
            )

        self.last_batch = CollectionBatch(
            received_count=len(payload),
            valid_drafts=list(drafts),
            rejected_count=rejected_count,
            rejection_breakdown=rejection_breakdown,
            lifecycle_signals=lifecycle_signals,
        )
        return drafts

    def collect(self) -> list[NormalizedOpportunityDraft]:
        headers = self._build_github_headers()
        all_drafts: list[NormalizedOpportunityDraft] = []
        seen_valid_ids: set[str] = set()
        seen_signal_ids: set[str] = set()
        all_signals: list[SourceLifecycleSignal] = []
        total_rejected_non_signal = 0
        rejection_breakdown: dict[str, int] = {}

        next_url: str | None = self.definition.base_url
        visited_urls: set[str] = set()
        pages_fetched = 0

        while next_url and pages_fetched < self.max_pages:
            if next_url in visited_urls:
                break
            visited_urls.add(next_url)

            if pages_fetched > 0 and self.page_delay_seconds > 0:
                self.sleep_fn(self.page_delay_seconds)

            payload, response_headers = self.fetch_json_with_headers(
                next_url,
                extra_headers=headers,
            )
            pages_fetched += 1

            page_drafts = self.parse_payload(payload)
            page_batch = self.last_batch

            for draft in page_drafts:
                if draft.external_id in seen_valid_ids:
                    continue
                seen_valid_ids.add(draft.external_id)
                all_drafts.append(draft)

            for sig in page_batch.lifecycle_signals:
                if sig.external_id in seen_signal_ids:
                    continue
                seen_signal_ids.add(sig.external_id)
                all_signals.append(sig)
                reason_key = "stale" if sig.status == ExternalSourceStatus.EXPIRED.value else "closed"
                rejection_breakdown[reason_key] = rejection_breakdown.get(reason_key, 0) + 1

            for reason, cnt in page_batch.rejection_breakdown.items():
                if reason in {"closed", "stale"}:
                    continue
                total_rejected_non_signal += cnt
                rejection_breakdown[reason] = rejection_breakdown.get(reason, 0) + cnt

            if not payload:
                break

            next_url = parse_github_next_link(response_headers.get("Link"))

        total_rejected = total_rejected_non_signal + len(seen_signal_ids)
        self.last_batch = CollectionBatch(
            received_count=len(all_drafts) + total_rejected,
            valid_drafts=list(all_drafts),
            rejected_count=total_rejected,
            rejection_breakdown=rejection_breakdown,
            lifecycle_signals=all_signals,
        )
        return all_drafts

    def check_publication_status(
        self,
        external_id: str,
        source_url: str,
        metadata: dict[str, Any] | None = None,
    ) -> SourceLifecycleSignal | None:
        issue_number = (metadata or {}).get("issue_number")
        if issue_number is None and "-" in external_id:
            tail = external_id.rsplit("-", 1)[-1]
            if tail.isdigit():
                issue_number = int(tail)
        if issue_number is None:
            path_parts = [p for p in urlparse(source_url).path.split("/") if p]
            if len(path_parts) >= 4 and path_parts[-2] == "issues" and path_parts[-1].isdigit():
                issue_number = int(path_parts[-1])
        if issue_number is None:
            return None

        base_issues_url = self.definition.base_url.split("?", 1)[0].rstrip("/")
        detail_url = f"{base_issues_url}/{issue_number}"

        try:
            data = self.fetch_json(detail_url, extra_headers=self._build_github_headers())
        except ConnectorError as exc:
            msg = str(exc)
            if "HTTP 404" in msg or "HTTP 410" in msg:
                return SourceLifecycleSignal(
                    external_id=external_id,
                    source_url=source_url,
                    status=ExternalSourceStatus.REMOVED.value,
                    reason="Issue removida ou inacessível (HTTP 404/410) no GitHub",
                )
            return None
        except Exception:
            return None

        if not isinstance(data, dict) or "state" not in data:
            return None

        raw_labels = data.get("labels") if isinstance(data.get("labels"), list) else []
        labels_lower = {
            (lb.get("name", "") if isinstance(lb, dict) else str(lb)).strip().lower()
            for lb in raw_labels
        }
        state_lower = str(data.get("state", "")).lower()
        if state_lower == "closed" or bool(labels_lower & {"fechada", "encerrada", "closed"}):
            return SourceLifecycleSignal(
                external_id=external_id,
                source_url=source_url,
                status=ExternalSourceStatus.CLOSED.value,
                reason="Issue fechada confirmada via GitHub API",
            )
        if "stale" in labels_lower:
            return SourceLifecycleSignal(
                external_id=external_id,
                source_url=source_url,
                status=ExternalSourceStatus.EXPIRED.value,
                reason="Issue marcada como Stale no GitHub",
            )
        if state_lower == "open":
            return SourceLifecycleSignal(
                external_id=external_id,
                source_url=source_url,
                status=ExternalSourceStatus.ACTIVE.value,
                reason="Issue confirmada aberta via GitHub API",
            )
        return None


class GitHubBackendBRConnector(BaseGitHubIssuesVagasConnector):
    id_prefix = "gh-backend-br"
    default_fallback_area = ProfessionalArea.BACKEND.value

    definition = SourceDefinition(
        slug="github_backend_br",
        name="GitHub Backend BR (Vagas)",
        source_type=SourceType.JSON_API.value,
        base_url="https://api.github.com/repos/backend-br/vagas/issues?state=open&per_page=100",
        terms_url="https://github.com/backend-br/vagas/blob/master/LICENSE",
        attribution_text=(
            "Fonte: Comunidade Backend Brasil (repositório sob licença MIT; "
            "conteúdo de terceiros com link direto para a issue original e PII higienizada)."
        ),
        refresh_interval_seconds=3600,
        enabled_by_default=True,
    )


class GitHubFrontendBRConnector(BaseGitHubIssuesVagasConnector):
    id_prefix = "gh-frontend-br"
    default_fallback_area = ProfessionalArea.FRONTEND.value

    definition = SourceDefinition(
        slug="github_frontend_br",
        name="GitHub Frontend BR (Vagas)",
        source_type=SourceType.JSON_API.value,
        base_url="https://api.github.com/repos/frontendbr/vagas/issues?state=open&per_page=100",
        terms_url="https://github.com/frontendbr/vagas/blob/master/LICENSE",
        attribution_text=(
            "Fonte: Comunidade Frontend Brasil (repositório sob licença MIT; "
            "conteúdo de terceiros com link direto para a issue original e PII higienizada)."
        ),
        refresh_interval_seconds=3600,
        enabled_by_default=True,
    )

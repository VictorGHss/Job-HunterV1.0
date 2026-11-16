import re
from typing import Any

from app.models.opportunity import (
    EmploymentType,
    ExternalSourceStatus,
    OpportunityType,
    ProfessionalArea,
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


def _extract_work_mode_and_location(
    raw_title: str,
    labels: list[str],
) -> tuple[str, str | None, str | None, str | None, list[str], bool]:
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
        return (work_mode, location_text[:255], None, country, eligible_countries, False)

    country = "Brasil"
    eligible_countries = ["Brasil"]
    location_text = bracket_text or ("Remoto - Brasil" if work_mode == WorkMode.REMOTE.value else "Brasil")
    city: str | None = None
    if work_mode in {WorkMode.HYBRID.value, WorkMode.ONSITE.value}:
        cleaned_city = re.sub(r"(?i)\b(?:híbrido|hibrido|presencial|brasil)\b|[/-]", " ", bracket_text).strip()
        city = cleaned_city[:120] if cleaned_city else "Outra localidade"
    return (work_mode, location_text[:255], city, country, eligible_countries, False)


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
    licenciados sob MIT, consumidos via API REST oficial v3 do GitHub.
    """

    default_fallback_area: str = ProfessionalArea.SOFTWARE_DEVELOPMENT.value
    id_prefix: str = "gh"

    def parse_payload(self, payload: Any) -> list[NormalizedOpportunityDraft]:
        if not isinstance(payload, list):
            raise ConnectorPayloadError(
                "GitHub Issues API retornou formato inválido (esperada lista JSON de issues)."
            )

        drafts: list[NormalizedOpportunityDraft] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            # Ignora Pull Requests retornados no endpoint de issues
            if "pull_request" in item:
                continue
            if str(item.get("state", "")).lower() != "open":
                continue

            raw_number = item.get("number") or item.get("id")
            raw_title = sanitize_plain_text(item.get("title"))
            raw_url = item.get("html_url")
            if raw_number is None or not raw_title or not isinstance(raw_url, str):
                continue
            if _META_ISSUE_TITLE_RE.search(raw_title):
                continue

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
            if "stale" in labels_lower:
                continue

            try:
                source_url = normalize_canonical_url(raw_url)
            except ValueError:
                continue

            redacted_body = redact_contact_pii(
                item.get("body") if isinstance(item.get("body"), str) else None
            )
            description = sanitize_external_html_text(redacted_body)

            decision = classify_opportunity(
                title=raw_title,
                tags=label_names,
                description=description,
            )

            opp_type = decision.opportunity_type
            emp_type = decision.employment_type
            primary_area = decision.professional_area
            secondary_areas = list(decision.secondary_areas)

            # Aplica labels estruturadas das issues comunitárias brasileiras
            if ("estágio" in labels_lower or "estagio" in labels_lower) and opp_type == OpportunityType.OTHER.value:
                opp_type = OpportunityType.INTERNSHIP.value
                emp_type = EmploymentType.INTERNSHIP.value
            elif (
                ("júnior" in labels_lower or "junior" in labels_lower)
                and not (labels_lower & {"pleno", "sênior", "senior", "especialista"})
                and opp_type == OpportunityType.OTHER.value
            ):
                opp_type = OpportunityType.JUNIOR.value
            elif ("freela" in labels_lower or "freelance" in labels_lower) and opp_type == OpportunityType.OTHER.value:
                opp_type = OpportunityType.FREELANCE.value
                emp_type = EmploymentType.FREELANCE.value

            if "clt" in labels_lower and "pj" not in labels_lower:
                emp_type = EmploymentType.CLT.value
            elif "pj" in labels_lower and "clt" not in labels_lower:
                emp_type = EmploymentType.PJ.value
            elif emp_type == EmploymentType.UNKNOWN.value and (
                "freela" in labels_lower or "freelance" in labels_lower
            ):
                emp_type = EmploymentType.FREELANCE.value

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
            work_mode, location_text, city, country, eligible_countries, eligibility_unknown = (
                _extract_work_mode_and_location(raw_title, label_names)
            )
            company_name = _extract_company_from_title(raw_title)
            published_at = parse_iso_datetime(item.get("created_at"))

            drafts.append(
                NormalizedOpportunityDraft(
                    external_id=f"{self.id_prefix}-{raw_number}",
                    title=raw_title,
                    company_name=company_name,
                    description=description,
                    opportunity_type=opp_type,
                    employment_type=emp_type,
                    work_mode=work_mode,
                    location_text=location_text,
                    city=city,
                    state=None,
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
                    raw_metadata={
                        "issue_number": raw_number,
                        "labels": label_names,
                        "source": self.definition.slug,
                    },
                )
            )

        return drafts


class GitHubBackendBRConnector(BaseGitHubIssuesVagasConnector):
    id_prefix = "gh-backend-br"
    default_fallback_area = ProfessionalArea.BACKEND.value

    definition = SourceDefinition(
        slug="github_backend_br",
        name="GitHub Backend BR (Vagas)",
        source_type=SourceType.JSON_API.value,
        base_url="https://api.github.com/repos/backend-br/vagas/issues?state=open&per_page=30",
        terms_url="https://github.com/backend-br/vagas/blob/master/LICENSE",
        attribution_text=(
            "Fonte: Comunidade Backend Brasil (GitHub MIT) — link direto para a issue original."
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
        base_url="https://api.github.com/repos/frontendbr/vagas/issues?state=open&per_page=30",
        terms_url="https://github.com/frontendbr/vagas/blob/master/LICENSE",
        attribution_text=(
            "Fonte: Comunidade Frontend Brasil (GitHub MIT) — link direto para a issue original."
        ),
        refresh_interval_seconds=3600,
        enabled_by_default=True,
    )

from dataclasses import dataclass
import re
import unicodedata

from app.models.opportunity import EmploymentType, OpportunityType

_COMBINING_MARKS_RE = re.compile(r"[\u0300-\u036f]")
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")
_MOJIBAKE_LATIN1_SPAN_RE = re.compile(r"[\u00c2-\u00f4][\u0080-\u00bf]{1,3}")
_CAMEL_BOUNDARY_RE = re.compile(r"([a-z])([A-Z])")

# Frases que mencionam senioridade ou perfil júnior de TERCEIROS (colegas, líderes, reportados),
# não os requisitos da própria vaga — removidas apenas do texto de descrição antes da heurística.
_NON_SELF_MENTION_PATTERNS = (
    re.compile(
        r"\b(?:collaborate|work|working|partner|paired?)\s+(?:closely\s+)?with\s+"
        r"(?:our\s+)?(?:senior|staff|principal|lead|experienced)\s+"
        r"(?:developers?|engineers?|designers?|bds?|leaders?|leadership|stakeholders?|colleagues?|team)\b"
    ),
    re.compile(
        r"\b(?:report|reports|reporting)\s+(?:directly\s+)?to\s+(?:the\s+|our\s+|an?\s+)?"
        r"(?:senior|sr\.?|lead|principal|head\s+of|director|vp|chief|manager|cto|ceo)\b"
    ),
    re.compile(
        r"\b(?:learn|learning|mentorship|mentored|guidance)\s+from\s+(?:a\s+|our\s+|an?\s+)?"
        r"(?:senior|staff|principal|lead|experienced)\s+(?:developer|engineer|team|leader|mentor)\b"
    ),
    re.compile(
        r"\b(?:senior\s+(?:leadership|stakeholders?|management|buyers?|clinical|voice\s+for)|"
        r"founded\s+by[^.]{0,80}\bsenior\b|keep\s+our\s+senior\s+developers)\b"
    ),
    re.compile(
        r"\b(?:coach(?:ing)?|mentor(?:ing)?|develop(?:ing)?|entwickelst|fuhrst|lead(?:ing)?|manage(?:ment)?)\s+"
        r"(?:insbesondere\s+unsere\s+|our\s+|the\s+)?(?:junior|jr\.?|entry[- ]level)\b"
    ),
    re.compile(
        r"\b(?:bachelor|master|associate|graduate)\s+degree\b|\bgraduate\s+from\s+our\b"
    ),
)

# Sinais explícitos de ESTÁGIO / PROGRAMA ACADÊMICO (fronteira de palavra; nunca "internal"/"international")
_INTERNSHIP_STRONG_RE = re.compile(
    r"(?<![a-z0-9])(?:"
    r"interns?|internship|apprentice|apprenticeship|co-?op\s+intern|"
    r"estagio|estagiari[oa]s?|pasantia|pasante|"
    r"praktikum|praktikant(?:en|in)?|werkstudent(?:en|in)?|"
    r"working\s+student|student\s+assistant|student\s+job"
    r")(?![a-z0-9])"
)
_INTERNSHIP_BODY_PHRASE_RE = re.compile(
    r"(?<![a-z0-9])(?:"
    r"(?:summer|winter|paid|unpaid|software|engineering|tech|marketing|finance)\s+internship|"
    r"(?:das|ein)\s+praktikum|"
    r"estagio\s+(?:em|na|no|de)|"
    r"vaga\s+de\s+estagio|"
    r"looking\s+for\s+(?:a\s+)?student\s+(?:job|assistant)|"
    r"working\s+student|werkstudent|student\s+assistant|"
    r"currently\s+(?:enrolled|pursuing)\s+(?:a\s+)?(?:bachelor|master|degree)"
    r")(?![a-z0-9])"
)

# Sinais de EXCLUSÃO/BLOQUEIO para estágio e júnior (cargos seniores, liderança, credenciais médicas plenas)
_LEADERSHIP_OR_SENIOR_RE = re.compile(
    r"(?<![a-z0-9])(?:"
    r"senior|sr\.?|staff|principal|team\s+lead|tech\s+lead|technical\s+(?:product\s+)?lead|"
    r"engineering\s+lead|bd\s+lead|cloud\s+lead|lead\s+(?:engineer|developer|designer|product|architect)|"
    r"head\s+of|director|vp|vice\s+president|chief\s+\w+\s+officer|cto|ceo|cfo|"
    r"manager|gerente|coordenador(?:a)?|director\s+of|dean|"
    r"pleno|mid[- ]?level|mid[- ]?senior|architect"
    r")(?![a-z0-9])"
)
_BOARD_CREDENTIAL_RE = re.compile(
    r"(?<![a-z0-9])(?:board[- ]?eligible|board\s+certification|md\s+or\s+do|endocrinologist|physician)(?![a-z0-9])"
)
_EXPERIENCED_YEARS_RE = re.compile(
    r"(?:at\s+least\s+|minimum\s+|preferably\s+)?(?:[3-9]|\d{2,})\s*(?:\+|-\s*\d+\+?)?\s*"
    r"(?:years?|anos)\s+(?:of\s+)?(?:[a-z0-9/-]+\s+){0,4}(?:experience|experiencia|in\s+)"
)

# Sinais de JÚNIOR / ENTRADA (nunca sênior mascarado)
_JUNIOR_TITLE_RE = re.compile(
    r"(?<![a-z0-9])(?:"
    r"junior|jr\.?|entry[- ]?level|trainee|new\s+grad|graduate|early[- ]?career|inicio\s+de\s+carreira"
    r")(?![a-z0-9])"
)
_JUNIOR_BODY_PHRASE_RE = re.compile(
    r"(?<![a-z0-9])(?:"
    r"(?:is\s+an?\s+|as\s+a\s+|for\s+an?\s+|motivated\s+|exceptional\s+)?"
    r"(?:junior|jr\.?)\s+(?:[a-z0-9]+\s+){0,2}"
    r"(?:developer|engineer|designer|analyst|programmer|dev|qa|tester|specialist|ui)|"
    r"(?:this\s+is\s+an?\s+|ideal\s+for\s+an?\s+)?entry[- ]?level\s+(?:opportunity|role|position|developer|engineer)|"
    r"ideal\s+for\s+an\s+early[- ]career\s+(?:developer|engineer|professional)|"
    r"(?:structured\s+)?graduate\s+(?:development\s+)?(?:programme|program|academy|scheme)|"
    r"trainee\s+(?:program|programa|em|de|tech)"
    r")(?![a-z0-9])"
)

# Sinais de FREELANCE / PROJETO AUTÔNOMO (sem confundir com "smart contract", "contracts manager", "API contract")
_FREELANCE_TITLE_RE = re.compile(
    r"(?<![a-z0-9])(?:freelance|freelancer|freela|autonom[oa]|projeto\s+fechado)(?![a-z0-9])"
)
_FREELANCE_BODY_EXPLICIT_RE = re.compile(
    r"(?<![a-z0-9])(?:"
    r"freelance(?:r)?(?:\s+(?:role|position|opportunity|project|developer|engineer|work))?|"
    r"independent\s+contractor(?:\s+(?:opportunity|arrangement|role|position))?|"
    r"1099\s+contract(?:or)?|"
    r"(?:trabalho|regime|profissional|contratacao)\s+autonom[oa]|"
    r"projeto\s+fechado|per[- ]?project|project[- ]?based"
    r")(?![a-z0-9])"
)

# Contrato explícito (separado da categoria opportunity_type)
_CONTRACT_FIXED_TERM_RE = re.compile(
    r"(?<![a-z0-9])(?:"
    r"fixed[- ]?term|one[- ]?year\s+contract|1[- ]?year\s+contract|"
    r"temporari[oa]|temporary|prazo\s+determinado|contract:\s*fixed[- ]?term"
    r")(?![a-z0-9])"
)
_CONTRACT_CLT_RE = re.compile(
    r"(?<![a-z0-9])(?:clt|regime\s+clt|contratacao\s+clt|carteira\s+assinada)(?![a-z0-9])"
)
_CONTRACT_PJ_RE = re.compile(
    r"(?<![a-z0-9])(?:"
    r"pj|pessoa\s+juridica|contratacao\s+pj|"
    r"(?:type|contratacion|mode|employment)[:\s]+(?:full[- ]?time\s+)?contractor|"
    r"remote\s+contractor\s+usd\s+full\s+time|"
    r"contractor\s+start\s+date|contractor\s+anniversary|b2b\s+contract"
    r")(?![a-z0-9])"
)
_CONTRACT_DUAL_RE = re.compile(
    r"(?<![a-z0-9])(?:"
    r"permanent\s+or\s+contract|full[- ]?time\s+or\s+contract|"
    r"most\s+roles\s+are\s+contract[- ]?based[^.]{0,120}direct\s+hire|"
    r"freelancing\s*&\s*full\s+time"
    r")(?![a-z0-9])"
)


@dataclass(frozen=True, slots=True)
class ClassificationDecision:
    opportunity_type: str
    employment_type: str
    confidence: str
    reasons: tuple[str, ...]


def _repair_mojibake(text: str) -> str:
    """Corrige sequências UTF-8 decodificadas como Latin-1 sem alterar Unicode já válido."""
    def _decode_span(match: re.Match[str]) -> str:
        chunk = match.group(0)
        try:
            return chunk.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            return chunk

    repaired = (
        text.replace("\u00e2\u20ac\u2014", " - ")
        .replace("\u00e2\u20ac\u2013", " - ")
        .replace("\u00e2\u20ac\u2122", "'")
        .replace("\u00e2\u20ac\u0153", '"')
        .replace("\u00e2\u20ac\u009d", '"')
    )
    return _MOJIBAKE_LATIN1_SPAN_RE.sub(_decode_span, repaired)


def normalize_classification_text(text: str | None) -> str:
    """Normaliza acentos, caixa e pontuação preservando fronteiras lexicais determinísticas."""
    if not text:
        return ""
    plain = _HTML_TAG_RE.sub(" ", _repair_mojibake(text))
    plain = _CAMEL_BOUNDARY_RE.sub(r"\1 \2", plain)
    decomposed = unicodedata.normalize("NFKD", plain)
    ascii_folded = _COMBINING_MARKS_RE.sub("", decomposed).lower()
    # Normaliza múltiplos espaços preservando pontuação relevante (como '+', '.', '-')
    return _WHITESPACE_RE.sub(" ", ascii_folded).strip()


def _strip_non_self_context(normalized_desc: str) -> str:
    cleaned = normalized_desc
    for pattern in _NON_SELF_MENTION_PATTERNS:
        cleaned = pattern.sub(" ", cleaned)
    return _WHITESPACE_RE.sub(" ", cleaned).strip()


def _normalize_tags(tags: list[str] | None) -> list[str]:
    if not tags:
        return []
    return [t for t in (normalize_classification_text(tag) for tag in tags) if t]


def _detect_employment_type(
    *,
    norm_title: str,
    norm_desc: str,
    norm_tags: list[str],
    opportunity_type: str,
) -> tuple[str, list[str]]:
    reasons: list[str] = []

    if opportunity_type == OpportunityType.INTERNSHIP.value:
        reasons.append("contract:internship_role")
        return (EmploymentType.INTERNSHIP.value, reasons)

    if _CONTRACT_CLT_RE.search(norm_title) or _CONTRACT_CLT_RE.search(norm_desc):
        reasons.append("contract:explicit_clt")
        return (EmploymentType.CLT.value, reasons)

    if _CONTRACT_FIXED_TERM_RE.search(norm_title) or _CONTRACT_FIXED_TERM_RE.search(norm_desc):
        reasons.append("contract:fixed_term_or_temporary")
        return (EmploymentType.TEMPORARY.value, reasons)

    if _FREELANCE_TITLE_RE.search(norm_title) or _FREELANCE_BODY_EXPLICIT_RE.search(norm_desc):
        if not _CONTRACT_DUAL_RE.search(norm_desc):
            reasons.append("contract:explicit_freelance_or_independent")
            return (EmploymentType.FREELANCE.value, reasons)

    if _CONTRACT_DUAL_RE.search(norm_desc):
        reasons.append("contract:ambiguous_multiple_options")
        return (EmploymentType.UNKNOWN.value, reasons)

    if _CONTRACT_PJ_RE.search(norm_desc) or _CONTRACT_PJ_RE.search(norm_title):
        reasons.append("contract:explicit_pj_or_dedicated_contractor")
        return (EmploymentType.PJ.value, reasons)

    if (
        "contract position" in norm_desc
        and ("paid per hour" in norm_desc or "hourly" in norm_desc)
        and "permanent" not in norm_desc
    ):
        reasons.append("contract:hourly_contract_position")
        return (EmploymentType.FREELANCE.value, reasons)

    if "pj" in norm_tags:
        reasons.append("contract:tag_pj")
        return (EmploymentType.PJ.value, reasons)
    if "clt" in norm_tags:
        reasons.append("contract:tag_clt")
        return (EmploymentType.CLT.value, reasons)
    if "freelance" in norm_tags and opportunity_type == OpportunityType.FREELANCE.value:
        reasons.append("contract:tag_freelance")
        return (EmploymentType.FREELANCE.value, reasons)

    reasons.append("contract:undisclosed_unknown")
    return (EmploymentType.UNKNOWN.value, reasons)


def classify_opportunity(
    *,
    title: str | None,
    tags: list[str] | None = None,
    description: str | None = None,
) -> ClassificationDecision:
    """
    Classifica oportunidade e regime contratual de forma 100% determinística,
    separando peso de título, descrição higienizada de contexto de terceiros e tags.
    """
    norm_title = normalize_classification_text(title)
    if not norm_title:
        return ClassificationDecision(
            opportunity_type=OpportunityType.UNKNOWN.value,
            employment_type=EmploymentType.UNKNOWN.value,
            confidence="low",
            reasons=("title:missing_or_empty",),
        )

    norm_tags = _normalize_tags(tags)
    tag_set = set(norm_tags)
    norm_desc_raw = normalize_classification_text(description)
    norm_desc = _strip_non_self_context(norm_desc_raw)

    title_is_senior_or_lead = bool(
        _LEADERSHIP_OR_SENIOR_RE.search(norm_title)
        or _BOARD_CREDENTIAL_RE.search(norm_title)
    )
    desc_has_senior_req = bool(
        _BOARD_CREDENTIAL_RE.search(norm_desc)
        or _EXPERIENCED_YEARS_RE.search(norm_desc)
        or re.search(
            r"(?<![a-z0-9])(?:looking\s+for\s+an?\s+|hiring\s+(?:\d+-\d+\s+)?|as\s+a\s+|seeking\s+an?\s+)"
            r"(?:senior|sr\.?|staff|principal|experienced|lead)\b",
            norm_desc,
        )
    )

    reasons: list[str] = []

    # 1. Estágio / Programa acadêmico (título e frases explícitas vencem tags ruidosas)
    if _INTERNSHIP_STRONG_RE.search(norm_title):
        reasons.append("title:explicit_internship_or_student_role")
        emp_type, emp_reasons = _detect_employment_type(
            norm_title=norm_title,
            norm_desc=norm_desc_raw,
            norm_tags=norm_tags,
            opportunity_type=OpportunityType.INTERNSHIP.value,
        )
        return ClassificationDecision(
            opportunity_type=OpportunityType.INTERNSHIP.value,
            employment_type=emp_type,
            confidence="high",
            reasons=tuple(reasons + emp_reasons),
        )

    if not title_is_senior_or_lead and _INTERNSHIP_BODY_PHRASE_RE.search(norm_desc):
        reasons.append("description:explicit_internship_or_student_phrase")
        emp_type, emp_reasons = _detect_employment_type(
            norm_title=norm_title,
            norm_desc=norm_desc_raw,
            norm_tags=norm_tags,
            opportunity_type=OpportunityType.INTERNSHIP.value,
        )
        return ClassificationDecision(
            opportunity_type=OpportunityType.INTERNSHIP.value,
            employment_type=emp_type,
            confidence="medium",
            reasons=tuple(reasons + emp_reasons),
        )

    # Tag isolada de estágio só vale se não houver senioridade/credencial/autônomo conflitante
    if (
        tag_set & {"intern", "internship", "estagio", "apprentice", "working student"}
        and not title_is_senior_or_lead
        and not desc_has_senior_req
        and not _FREELANCE_BODY_EXPLICIT_RE.search(norm_desc)
    ):
        reasons.append("tags:internship_without_conflict")
        emp_type, emp_reasons = _detect_employment_type(
            norm_title=norm_title,
            norm_desc=norm_desc_raw,
            norm_tags=norm_tags,
            opportunity_type=OpportunityType.INTERNSHIP.value,
        )
        return ClassificationDecision(
            opportunity_type=OpportunityType.INTERNSHIP.value,
            employment_type=emp_type,
            confidence="medium",
            reasons=tuple(reasons + emp_reasons),
        )

    # 2. Freelance / Projeto autônomo explícito (sem confundir com contratos comerciais ou sênior B2B integral)
    if _FREELANCE_TITLE_RE.search(norm_title):
        reasons.append("title:explicit_freelance")
        emp_type, emp_reasons = _detect_employment_type(
            norm_title=norm_title,
            norm_desc=norm_desc_raw,
            norm_tags=norm_tags,
            opportunity_type=OpportunityType.FREELANCE.value,
        )
        return ClassificationDecision(
            opportunity_type=OpportunityType.FREELANCE.value,
            employment_type=emp_type,
            confidence="high",
            reasons=tuple(reasons + emp_reasons),
        )

    if (
        _FREELANCE_BODY_EXPLICIT_RE.search(norm_desc)
        and not title_is_senior_or_lead
        and not _CONTRACT_DUAL_RE.search(norm_desc)
    ):
        reasons.append("description:explicit_freelance_or_independent_contractor")
        emp_type, emp_reasons = _detect_employment_type(
            norm_title=norm_title,
            norm_desc=norm_desc_raw,
            norm_tags=norm_tags,
            opportunity_type=OpportunityType.FREELANCE.value,
        )
        return ClassificationDecision(
            opportunity_type=OpportunityType.FREELANCE.value,
            employment_type=emp_type,
            confidence="high",
            reasons=tuple(reasons + emp_reasons),
        )

    if (
        "freelance" in tag_set
        and not title_is_senior_or_lead
        and not desc_has_senior_req
        and not _CONTRACT_FIXED_TERM_RE.search(norm_desc)
    ):
        reasons.append("tags:freelance_without_conflict")
        emp_type, emp_reasons = _detect_employment_type(
            norm_title=norm_title,
            norm_desc=norm_desc_raw,
            norm_tags=norm_tags,
            opportunity_type=OpportunityType.FREELANCE.value,
        )
        return ClassificationDecision(
            opportunity_type=OpportunityType.FREELANCE.value,
            employment_type=emp_type,
            confidence="medium",
            reasons=tuple(reasons + emp_reasons),
        )

    # 3. Bloqueio explícito de senioridade/liderança antes de considerar júnior por descrição/tags
    if title_is_senior_or_lead:
        reasons.append("title:senior_lead_manager_or_specialist_role")
        emp_type, emp_reasons = _detect_employment_type(
            norm_title=norm_title,
            norm_desc=norm_desc_raw,
            norm_tags=norm_tags,
            opportunity_type=OpportunityType.OTHER.value,
        )
        return ClassificationDecision(
            opportunity_type=OpportunityType.OTHER.value,
            employment_type=emp_type,
            confidence="high",
            reasons=tuple(reasons + emp_reasons),
        )

    # 4. Júnior / Entrada na área
    if _JUNIOR_TITLE_RE.search(norm_title) and not desc_has_senior_req:
        reasons.append("title:explicit_junior_or_entry_level")
        emp_type, emp_reasons = _detect_employment_type(
            norm_title=norm_title,
            norm_desc=norm_desc_raw,
            norm_tags=norm_tags,
            opportunity_type=OpportunityType.JUNIOR.value,
        )
        return ClassificationDecision(
            opportunity_type=OpportunityType.JUNIOR.value,
            employment_type=emp_type,
            confidence="high",
            reasons=tuple(reasons + emp_reasons),
        )

    if _JUNIOR_BODY_PHRASE_RE.search(norm_desc) and not desc_has_senior_req:
        reasons.append("description:explicit_junior_or_entry_level_phrase")
        emp_type, emp_reasons = _detect_employment_type(
            norm_title=norm_title,
            norm_desc=norm_desc_raw,
            norm_tags=norm_tags,
            opportunity_type=OpportunityType.JUNIOR.value,
        )
        return ClassificationDecision(
            opportunity_type=OpportunityType.JUNIOR.value,
            employment_type=emp_type,
            confidence="medium",
            reasons=tuple(reasons + emp_reasons),
        )

    if (
        tag_set & {"junior", "jr", "entry-level", "entry level", "trainee", "graduate"}
        and not desc_has_senior_req
    ):
        reasons.append("tags:junior_without_conflict")
        emp_type, emp_reasons = _detect_employment_type(
            norm_title=norm_title,
            norm_desc=norm_desc_raw,
            norm_tags=norm_tags,
            opportunity_type=OpportunityType.JUNIOR.value,
        )
        return ClassificationDecision(
            opportunity_type=OpportunityType.JUNIOR.value,
            employment_type=emp_type,
            confidence="medium",
            reasons=tuple(reasons + emp_reasons),
        )

    # 5. Caso padrão conservador: other (precisão antes de quantidade)
    reasons.append("fallback:senior_mid_or_generic_other")
    emp_type, emp_reasons = _detect_employment_type(
        norm_title=norm_title,
        norm_desc=norm_desc_raw,
        norm_tags=norm_tags,
        opportunity_type=OpportunityType.OTHER.value,
    )
    confidence = "high" if desc_has_senior_req else "medium"
    return ClassificationDecision(
        opportunity_type=OpportunityType.OTHER.value,
        employment_type=emp_type,
        confidence=confidence,
        reasons=tuple(reasons + emp_reasons),
    )

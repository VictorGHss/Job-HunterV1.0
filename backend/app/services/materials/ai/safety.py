from __future__ import annotations

import re

# TLDs de internet comuns para detectar domínios sem protocolo sem gerar falsos
# positivos em nomes de tecnologias como Node.js, Vue.js, Next.js ou ASP.NET.
_COMMON_DOMAIN_TLDS = (
    "com",
    "org",
    "net",
    "io",
    "dev",
    "app",
    "br",
    "co",
    "me",
    "ly",
    "ai",
    "tech",
    "site",
    "online",
    "info",
    "biz",
    "edu",
    "gov",
    "cloud",
    "xyz",
    "gg",
    "tv",
    "sh",
    "so",
    "to",
    "uk",
    "de",
    "fr",
    "es",
    "ca",
    "au",
    "us",
    "eu",
    "in",
    "pt",
)
_TLD_PATTERN = "|".join(_COMMON_DOMAIN_TLDS)

# Prefixos técnicos legítimos que terminam com ".net" e não são domínios de rede
_TECH_DOT_NET_EXCLUSIONS = frozenset({"asp.net", "vb.net", "dot.net"})

# 1. HTML, SVG e conteúdo ativo
_ACTIVE_SCHEME_RE = re.compile(
    r"(?i)(?:\b(?:javascript|vbscript|file)\s*:|\bdata\s*:\s*(?:[a-z0-9.+-]+/[a-z0-9.+-]+|;base64|text|application|image))"
)
_EVENT_HANDLER_RE = re.compile(
    r"(?i)(?:^|[\s<>\"'/;(])on[a-z]{2,24}\s*="
)
_HTML_TAG_RE = re.compile(
    r"(?is)<\s*/?\s*[a-z][a-z0-9:-]*(?:\s[^>]*)?>|<!--[\s\S]*?-->"
)
_UNCLOSED_DANGEROUS_TAG_RE = re.compile(
    r"(?i)<\s*(?:script|svg|iframe|img|object|embed|style|link|meta|form|input|body|math|details|video|audio|base|applet)\b"
)

# 2. Links Markdown (inclusive multilinha)
_MARKDOWN_LINK_RE = re.compile(
    r"!?\[[\s\S]*?\]\s*\([\s\S]*?\)",
    re.DOTALL,
)

# 3. URLs com protocolo, www e domínios sem protocolo
_PROTOCOL_URL_RE = re.compile(
    r"(?i)\b(?:(?:https?|ftp)://[^\s<>\"'\)\]]+|(?:mailto|tel):[^\s<>\"'\)\]]+)"
)
_WWW_URL_RE = re.compile(
    r"(?i)\bwww\.[a-z0-9-]+(?:\.[a-z0-9-]+)+(?:/[^\s<>\"'\)\]]*)?"
)
_BARE_DOMAIN_RE = re.compile(
    rf"(?i)(?<![@\w.-])\b([a-z0-9](?:[a-z0-9-]{{0,61}}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{{0,61}}[a-z0-9])?)*\.(?:{_TLD_PATTERN}))(?:/[^\s<>\"'\)\]]*)?(?![a-z0-9-])"
)

# 4. E-mails comuns e ofuscados ([at], (at), at, arroba + [dot], (dot), dot, ponto, .)
_EMAIL_RE = re.compile(
    r"(?i)\b[a-z0-9_.+-]+@[a-z0-9-]+(?:\.[a-z0-9-]{2,})+\b"
)
_OBFUSCATED_EMAIL_RE = re.compile(
    rf"(?i)\b[a-z0-9_.+-]+\s*(?:\[\s*(?:at|arroba)\s*\]|\(\s*(?:at|arroba)\s*\)|\s+(?:at|arroba)\s+)\s*[a-z0-9-]+(?:\s*(?:\[\s*(?:dot|ponto)\s*\]|\(\s*(?:dot|ponto)\s*\)|\s+(?:dot|ponto)\s+)\s*[a-z0-9-]{{2,}}|\.(?:{_TLD_PATTERN})(?:\.[a-z]{{2}})?)\b"
)
_BRACKET_AT_EMAIL_RE = re.compile(
    r"(?i)\b[a-z0-9_.+-]+\s*(?:\[\s*(?:at|arroba)\s*\]|\(\s*(?:at|arroba)\s*\))\s*[a-z0-9.-]{2,}\b"
)

# 5. Telefones (internacionais, brasileiros com ou sem DDD, incluindo DDD 19/20)
_INTL_PHONE_RE = re.compile(
    r"(?<!\w)\+\d{1,3}(?:[\s.-]?\(?\d{1,4}\)?){2,5}(?!\w)"
)
_PAREN_DDD_PHONE_RE = re.compile(
    r"(?<!\w)\(0?\d{2,3}\)[\s.-]?\d{3,5}[\s.-]?\d{4}(?!\w)"
)
_SEPARATED_PHONE_RE = re.compile(
    r"(?<!\w)(?:0?\d{2}[\s.-])?\d{4,5}[\s.-]\d{4}(?!\w)"
)
_COMPACT_BR_MOBILE_RE = re.compile(
    r"(?<!\d)(?:55)?[1-9]{2}9\d{8}(?!\d)"
)
_LABELED_PHONE_RE = re.compile(
    r"(?i)\b(?:tel(?:efone)?|fone|cel(?:ular)?|whatsapp|whats|phone|mobile|call)\s*[:\-]?\s*\+?[\d\s().-]{8,20}\b"
)
_YEAR_RANGE_RE = re.compile(r"^(?:19|20)\d{2}[\s.-](?:19|20)\d{2}$")

# 6. Endereços residenciais, documentos pessoais e perfis sociais para redação de PII
_CPF_RE = re.compile(r"(?i)(?:\b\d{3}\.\d{3}\.\d{3}-\d{2}\b|\bcpf\s*[:\-]?\s*\d{11}\b)")
_CEP_RE = re.compile(r"(?i)\b(?:cep\s*[:\-]?\s*)?\d{5}-\d{3}\b")
_BR_ADDRESS_RE = re.compile(
    r"(?i)\b(?:rua|r\.|avenida|av\.|travessa|tv\.|alameda|al\.|estrada|rodovia|praça|praca|largo)\s+"
    r"[a-zà-ÿ0-9.'-]+(?:\s+[a-zà-ÿ0-9.'-]+){0,6}"
    r"(?:,\s*(?:n[º°o.]?\s*)?\d{1,6}|\s+n[º°o.]?\s*\d{1,6})"
    r"(?:\s*[-,/]\s*(?:apto?\.?|apartamento|bloco|bl\.?|casa|sala|cj\.?|andar|fundos|bairro|centro)[^.;\n]{0,40})?"
)
_EN_ADDRESS_RE = re.compile(
    r"(?i)\b\d{1,6}\s+[a-z0-9.'-]+(?:\s+[a-z0-9.'-]+){0,4}\s+"
    r"(?:street|st\.|avenue|ave\.|road|rd\.|boulevard|blvd\.|lane|ln\.|drive|dr\.|court|ct\.|way|place|pl\.)"
    r"(?:,\s*(?:apt\.?|suite|unit|#)\s*[a-z0-9-]+)?\b"
)
_EXPLICIT_ADDRESS_LABEL_RE = re.compile(
    r"(?i)\b(?:endere[çc]o(?:\s+residencial)?|resid[êe]ncia|home\s+address|address)\s*[:\-]\s*[^\n.;]{3,160}"
)
_SOCIAL_HANDLE_LABELED_RE = re.compile(
    r"(?i)\b(?:linkedin|github|instagram|telegram|twitter|portfolio|portf[óo]lio)\s*[:\-]\s*(?:@?[a-z0-9_./-]{2,80})"
)

# Verificação residual fail-closed pós-redação no contexto de entrada
_RESIDUAL_SENSITIVE_LABEL_RE = re.compile(
    r"(?i)\b(?:endere[çc]o|home\s+address|cpf|rg|whatsapp|telefone|celular)\s*[:\-]\s*(?!\[redacted\])[^\s]"
)

REDACTED_TOKEN = "[REDACTED]"


def find_urls_or_domains(text: str) -> list[str]:
    """Detecta URLs com protocolo, www e domínios sem protocolo (excluindo techs como Node.js/ASP.NET)."""
    matches: list[str] = []
    for rx in (_PROTOCOL_URL_RE, _WWW_URL_RE):
        for m in rx.finditer(text):
            matches.append(m.group(0))
    for m in _BARE_DOMAIN_RE.finditer(text):
        domain = m.group(1).lower()
        if domain in _TECH_DOT_NET_EXCLUSIONS:
            continue
        # Exclui subparte de e-mail já capturado por find_emails apenas se for domínio de e-mail
        # (no bloqueio de saída ambos são proibidos de qualquer forma; aqui retornamos o domínio).
        matches.append(m.group(0))
    return matches


def find_markdown_links(text: str) -> list[str]:
    """Detecta links Markdown inclusive com quebras de linha."""
    return [m.group(0) for m in _MARKDOWN_LINK_RE.finditer(text)]


def find_emails(text: str) -> list[str]:
    """Detecta e-mails comuns e variações ofuscadas ([at], (at), at/arroba + [dot]/dot/ponto)."""
    matches: list[str] = []
    for rx in (_EMAIL_RE, _OBFUSCATED_EMAIL_RE, _BRACKET_AT_EMAIL_RE):
        for m in rx.finditer(text):
            val = m.group(0)
            if val not in matches:
                matches.append(val)
    return matches


def find_phones(text: str) -> list[str]:
    """Detecta números telefônicos brasileiros e internacionais sem excluir DDD 19/20."""
    found: list[str] = []
    candidates: list[str] = []
    for rx in (
        _LABELED_PHONE_RE,
        _INTL_PHONE_RE,
        _PAREN_DDD_PHONE_RE,
        _SEPARATED_PHONE_RE,
        _COMPACT_BR_MOBILE_RE,
    ):
        for m in rx.finditer(text):
            candidates.append(m.group(0).strip())

    for cand in candidates:
        if _YEAR_RANGE_RE.match(cand):
            continue
        digits = re.sub(r"\D", "", cand)
        if 8 <= len(digits) <= 15:
            if cand not in found:
                found.append(cand)
    return found


def find_active_or_html_content(text: str) -> list[str]:
    """Detecta HTML, SVG, atributos on* e esquemas ativos (javascript:, vbscript:, data:)."""
    found: list[str] = []
    for rx in (
        _ACTIVE_SCHEME_RE,
        _EVENT_HANDLER_RE,
        _HTML_TAG_RE,
        _UNCLOSED_DANGEROUS_TAG_RE,
    ):
        for m in rx.finditer(text):
            val = m.group(0).strip()
            if val and val not in found:
                found.append(val)
    return found


def redact_free_text_pii(text: str | None) -> tuple[str | None, bool]:
    """Redige PII e canais de contato em campos de texto livre antes do envio ao provider.

    Retorna ``(texto_limpo_ou_None, houve_redacao_ou_omissao)``.
    Aplica estratégia conservadora fail-closed: se após a redação determinística
    ainda restar indício não redigido de PII/contato sensível, omite o campo inteiro.
    """
    if not text or not isinstance(text, str):
        return None, False

    redacted = text
    changed = False

    def _sub(rx: re.Pattern[str], value: str) -> str:
        nonlocal changed
        new_val, count = rx.subn(REDACTED_TOKEN, value)
        if count > 0:
            changed = True
        return new_val

    # 1. Links Markdown (preserva nada do destino)
    redacted = _sub(_MARKDOWN_LINK_RE, redacted)
    # 2. URLs com protocolo e www
    redacted = _sub(_PROTOCOL_URL_RE, redacted)
    redacted = _sub(_WWW_URL_RE, redacted)
    # 3. E-mails comuns e ofuscados
    redacted = _sub(_EMAIL_RE, redacted)
    redacted = _sub(_OBFUSCATED_EMAIL_RE, redacted)
    redacted = _sub(_BRACKET_AT_EMAIL_RE, redacted)
    # 4. Domínios sem protocolo (excluindo ASP.NET / VB.NET)
    def _replace_bare_domain(m: re.Match[str]) -> str:
        nonlocal changed
        domain = m.group(1).lower()
        if domain in _TECH_DOT_NET_EXCLUSIONS:
            return m.group(0)
        changed = True
        return REDACTED_TOKEN

    redacted = _BARE_DOMAIN_RE.sub(_replace_bare_domain, redacted)

    # 5. Perfis sociais rotulados
    redacted = _sub(_SOCIAL_HANDLE_LABELED_RE, redacted)

    # 6. Telefones (protegendo intervalos de anos como 2023-2024)
    def _replace_phone(m: re.Match[str]) -> str:
        nonlocal changed
        raw = m.group(0).strip()
        if _YEAR_RANGE_RE.match(raw):
            return m.group(0)
        digits = re.sub(r"\D", "", raw)
        if 8 <= len(digits) <= 15:
            changed = True
            return REDACTED_TOKEN
        return m.group(0)

    for phone_rx in (
        _LABELED_PHONE_RE,
        _INTL_PHONE_RE,
        _PAREN_DDD_PHONE_RE,
        _SEPARATED_PHONE_RE,
        _COMPACT_BR_MOBILE_RE,
    ):
        redacted = phone_rx.sub(_replace_phone, redacted)

    # 7. Documentos pessoais e endereços residenciais
    redacted = _sub(_CPF_RE, redacted)
    redacted = _sub(_CEP_RE, redacted)
    redacted = _sub(_EXPLICIT_ADDRESS_LABEL_RE, redacted)
    redacted = _sub(_BR_ADDRESS_RE, redacted)
    redacted = _sub(_EN_ADDRESS_RE, redacted)

    # 8. Conteúdo ativo / HTML residual
    redacted = _sub(_ACTIVE_SCHEME_RE, redacted)
    redacted = _sub(_EVENT_HANDLER_RE, redacted)
    redacted = _sub(_HTML_TAG_RE, redacted)

    # 9. Verificação fail-closed pós-redação: se sobrar qualquer PII detectável, omitir campo inteiro
    if (
        find_emails(redacted)
        or find_phones(redacted)
        or find_urls_or_domains(redacted)
        or find_active_or_html_content(redacted)
        or _RESIDUAL_SENSITIVE_LABEL_RE.search(redacted)
    ):
        return None, True

    cleaned = re.sub(r"\s{2,}", " ", redacted).strip()
    if not cleaned or cleaned == REDACTED_TOKEN:
        return None, True
    return cleaned, changed

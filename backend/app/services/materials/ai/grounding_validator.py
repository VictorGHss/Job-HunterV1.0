from __future__ import annotations

import re
from typing import Any
import unicodedata

from pydantic import BaseModel, ConfigDict, Field

from app.services.materials.ai.ai_schemas import (
    AIMaterialEnhanceOutput,
    AuthorizedAIContext,
    AuthorizedFactItem,
)
from app.services.opportunities.matching import _TECH_ALIASES, _contains_term

_URL_RE = re.compile(r"(https?://\S+|www\.\S+)", re.IGNORECASE)
_MARKDOWN_LINK_RE = re.compile(r"\[.*?\]\((.*?)\)")
_EMAIL_RE = re.compile(r"\b[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+\b")
_PHONE_RE = re.compile(
    r"(?:\+?\d{1,3}[\s-]?)?(?:\(?\d{2,3}\)?[\s.-]?)?\d{4,5}[\s.-]?\d{4}\b"
)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_INJECTION_RE = re.compile(
    r"(<\s*script\b|onload\s*=|onerror\s*=|onclick\s*=|javascript:|data:text/html|<\s*iframe\b)",
    re.IGNORECASE,
)

# Padrões quantitativos
_PERCENTAGE_RE = re.compile(
    r"\b(\d+(?:[.,]\d+)?)\s*(?:%|por\s+cento|percent\b)",
    re.IGNORECASE,
)
_CURRENCY_RE = re.compile(
    r"(?:R\$|\$|USD|EUR|BRL)\s*(\d+(?:[.,]\d+)*(?:\s*(?:mil|k|milhões|milhoes|million))?)",
    re.IGNORECASE,
)
_DURATION_RE = re.compile(
    r"\b(\d+)\s*(?:anos?|meses|mês|semanas?|dias?|years?|months?|weeks?|days?)\b",
    re.IGNORECASE,
)
_YEAR_RE = re.compile(r"\b((?:19|20)\d{2})\b")
_PURE_NUMBER_RE = re.compile(r"\b(\d+(?:[.,]\d+)?)\b")

_SPELLED_NUMBERS_MAP = {
    "dois": "2",
    "duas": "2",
    "três": "3",
    "tres": "3",
    "quatro": "4",
    "cinco": "5",
    "seis": "6",
    "sete": "7",
    "oito": "8",
    "nove": "9",
    "dez": "10",
    "onze": "11",
    "doze": "12",
    "treze": "13",
    "quatorze": "14",
    "catorze": "14",
    "quinze": "15",
    "dezesseis": "16",
    "dezessete": "17",
    "dezoito": "18",
    "dezenove": "19",
    "vinte": "20",
    "trinta": "30",
    "quarenta": "40",
    "cinquenta": "50",
    "sessenta": "60",
    "setenta": "70",
    "oitenta": "80",
    "noventa": "90",
    "cem": "100",
    "cento": "100",
    "duzentos": "200",
    "trezentos": "300",
    "quatrocentos": "400",
    "quinhentos": "500",
    "mil": "1000",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
    "ten": "10",
    "eleven": "11",
    "twelve": "12",
    "thirteen": "13",
    "fourteen": "14",
    "fifteen": "15",
    "sixteen": "16",
    "seventeen": "17",
    "eighteen": "18",
    "nineteen": "19",
    "twenty": "20",
    "thirty": "30",
    "forty": "40",
    "fifty": "50",
    "sixty": "60",
    "seventy": "70",
    "eighty": "80",
    "ninety": "90",
    "hundred": "100",
    "thousand": "1000",
}

_PROMOTED_ROLES = frozenset({
    "cto",
    "cio",
    "cpo",
    "chief technology officer",
    "head of technology",
    "head de engenharia",
    "head of engineering",
    "tech lead",
    "líder técnico",
    "lider tecnico",
    "diretor de tecnologia",
    "diretor de ti",
    "engineering manager",
    "staff engineer",
    "principal engineer",
})

_UNSUBSTANTIATED_CLAIMS_RE = re.compile(
    r"\b(?:premiado|premiação|premiacao|prêmio|premio|patente|patentes|patent|melhor do ano|1º lugar|primeiro lugar|first place)\b",
    re.IGNORECASE,
)

_TECH_VERSION_RE = re.compile(
    r"\b(?:python|fastapi|react|vue|angular|java|c#|dotnet|\.net|postgresql|postgres|node|nodejs|php|css|html|ipv|oauth|tls|http|ecma|es)\s*(\d+(?:[.,]\d+)?)\b",
    re.IGNORECASE,
)
_ATTACHED_TECH_NUMBER_RE = re.compile(
    r"\b(?:html5|css3|ipv6|es6|es2020|es2022|python3|vue3|oauth2)\b",
    re.IGNORECASE,
)


def _strip_accents(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn"
    )


def _normalize_for_search(text: str | None) -> str:
    if not text:
        return ""
    return _strip_accents(text).lower()


class GroundingValidationResult(BaseModel):
    """Resultado detalhado da validação estruturada de grounding."""

    model_config = ConfigDict(extra="forbid")

    is_valid: bool
    rejection_reasons: list[str] = Field(default_factory=list)
    flagged_items: list[dict[str, Any]] = Field(default_factory=list)
    epistemological_disclaimer: str = (
        "A validação de grounding é estrutural, heurística e conservadora. "
        "Ela atua como uma barreira de integridade verificando estritamente se "
        "afirmações, métricas, tecnologias e entidades citadas possuem fundamento direto "
        "nos fatos previamente confirmados pelo usuário, sem constituir um oráculo empírico absoluto "
        "ou equivalência semântica completa no mundo real."
    )


class StructuredGroundingValidator:
    """Validador rigoroso e conservador de grounding para sugestões geradas por IA.

    Princípios:
    - Conservadorismo e All-or-Nothing: qualquer falha em qualquer sugestão rejeita a proposta inteira.
    - Factualidade estrita: métricas, números, anos, durações e tecnologias devem constar nos fatos citados.
    - Proibição de canais de contato e links inventados.
    - Proibição de tags HTML e scripts.
    - Detecção de promoção de cargo indevida.
    - Respeito à separação ontológica entre experiência e projeto.
    """

    def validate(
        self,
        context: AuthorizedAIContext,
        output: AIMaterialEnhanceOutput,
    ) -> GroundingValidationResult:
        rejection_reasons: list[str] = []
        flagged_items: list[dict[str, Any]] = []

        # 1. Correspondência de tipo de material
        if output.material_type != context.material_type:
            reason = (
                f"Tipo de material do output ('{output.material_type}') "
                f"diverge do contexto autorizado ('{context.material_type}')."
            )
            rejection_reasons.append(reason)
            return GroundingValidationResult(
                is_valid=False,
                rejection_reasons=rejection_reasons,
                flagged_items=[{"error": "material_type_mismatch", "detail": reason}],
            )

        # 2. Validação individual de cada sugestão
        all_authorized_keys = context.all_fact_keys()
        confirmed_techs = context.all_confirmed_technologies()
        opportunity_techs: set[str] = set()
        if context.opportunity:
            for t in context.opportunity.all_technologies:
                if t:
                    opportunity_techs.add(t.strip().lower())
                    opportunity_techs.add(_strip_accents(t).strip().lower())

        for idx, item in enumerate(output.suggestions):
            item_flags: list[str] = []

            # 2.1 Verificação de chaves de fatos citadas
            if not item.cited_fact_keys:
                item_flags.append("cited_fact_keys_empty: Sugestão não cita nenhuma chave de fato.")

            cited_facts: list[AuthorizedFactItem] = []
            for key in item.cited_fact_keys:
                if key not in all_authorized_keys:
                    item_flags.append(
                        f"unauthorized_fact_key: Chave '{key}' não existe no contexto autorizado do usuário."
                    )
                else:
                    fact = context.get_fact(key)
                    if fact:
                        cited_facts.append(fact)

            # 2.2 Compatibilidade de slot e separação experiência vs projeto
            slot = item.slot_id.lower()
            if "experience" in slot:
                # Slot de experiência deve referenciar experiência correspondente
                has_exp_fact = any(f.entity_type == "experience" for f in cited_facts)
                if not has_exp_fact:
                    item_flags.append(
                        f"slot_mismatch: Slot de experiência '{item.slot_id}' não cita fatos de experiência profissional."
                    )
            elif "project" in slot:
                # Slot de projeto deve referenciar projeto e nunca ser substituído por experiência formal
                has_proj_fact = any(f.entity_type == "project" for f in cited_facts)
                if not has_proj_fact:
                    item_flags.append(
                        f"slot_mismatch: Slot de projeto '{item.slot_id}' não cita fatos de projetos profissionais."
                    )

            text = item.suggested_text

            # 2.3 Proibição de URLs e links markdown
            if _URL_RE.search(text) or _MARKDOWN_LINK_RE.search(text):
                item_flags.append("forbidden_link: Texto contém URL ou link markdown não autorizado.")

            # 2.4 Proibição de e-mails e telefones
            if _EMAIL_RE.search(text):
                item_flags.append("forbidden_contact: Texto contém endereço de e-mail.")
            if _PHONE_RE.search(text):
                # Ignora anos isolados ou identificadores numéricos que não sejam telefones
                clean_phone_candidates = [
                    m.group(0) for m in _PHONE_RE.finditer(text)
                    if len(re.sub(r"\D", "", m.group(0))) in (8, 9, 10, 11)
                    and not (m.group(0).startswith("20") or m.group(0).startswith("19"))
                ]
                if clean_phone_candidates:
                    item_flags.append("forbidden_contact: Texto contém número de telefone.")

            # 2.5 Proibição de tags HTML e scripts/injeções
            if _HTML_TAG_RE.search(text) or _INJECTION_RE.search(text):
                item_flags.append("forbidden_html_script: Texto contém tags HTML ou scripts.")

            # Construção do corpus dos fatos citados
            corpus_parts: list[str] = []
            for fact in cited_facts:
                for field_val in (
                    fact.label,
                    fact.summary,
                    fact.description,
                    fact.role_or_title,
                    fact.company_or_institution,
                    fact.period,
                    fact.verified_results,
                    fact.proficiency,
                    " ".join(fact.technologies),
                    " ".join(fact.matched_requirements),
                ):
                    if field_val:
                        corpus_parts.append(str(field_val))

            corpus_raw = " ".join(corpus_parts)
            corpus_norm = _normalize_for_search(corpus_raw)

            # Extração de tokens numéricos delimitados por bordas no corpus
            corpus_numbers: set[str] = set()
            for raw_n in re.findall(r"\b\d+(?:[.,]\d+)?\b", corpus_norm):
                corpus_numbers.add(raw_n)
                clean_n = raw_n.replace(",", ".")
                corpus_numbers.add(clean_n)
                try:
                    val = float(clean_n)
                    if val.is_integer():
                        corpus_numbers.add(str(int(val)))
                except ValueError:
                    pass

            # 2.6 Validação de percentuais
            for pct_match in _PERCENTAGE_RE.finditer(text):
                pct_val = pct_match.group(1).replace(",", ".")
                pct_full_norm = _normalize_for_search(pct_match.group(0))
                if pct_val not in corpus_numbers and pct_full_norm not in corpus_norm:
                    item_flags.append(
                        f"ungrounded_metric: Percentual '{pct_match.group(0)}' não fundamentado nos fatos citados."
                    )

            # 2.7 Validação de moedas
            for curr_match in _CURRENCY_RE.finditer(text):
                curr_val = curr_match.group(1).strip()
                curr_full_norm = _normalize_for_search(curr_match.group(0))
                if curr_val.lower() not in corpus_norm and curr_full_norm not in corpus_norm:
                    item_flags.append(
                        f"ungrounded_currency: Valor monetário '{curr_match.group(0)}' não fundamentado nos fatos citados."
                    )

            # 2.8 Validação de durações
            for dur_match in _DURATION_RE.finditer(text):
                dur_num = dur_match.group(1)
                dur_full_norm = _normalize_for_search(dur_match.group(0))
                if dur_full_norm not in corpus_norm and dur_num not in corpus_numbers:
                    item_flags.append(
                        f"ungrounded_duration: Duração '{dur_match.group(0)}' não fundamentada nos fatos citados."
                    )

            # Coleta números que são versões explícitas de tecnologias citadas no texto
            allowed_version_numbers: set[str] = set()
            for tv_match in _TECH_VERSION_RE.finditer(text):
                allowed_version_numbers.add(tv_match.group(1))
            for at_match in _ATTACHED_TECH_NUMBER_RE.finditer(text):
                digits = re.sub(r"\D", "", at_match.group(0))
                if digits:
                    allowed_version_numbers.add(digits)

            # 2.9 Validação de números e anos puros
            for num_match in _PURE_NUMBER_RE.finditer(text):
                num_str = num_match.group(1)
                if num_str in allowed_version_numbers:
                    continue
                # Se for ano (19xx, 20xx)
                if _YEAR_RE.match(num_str):
                    if num_str not in corpus_numbers:
                        item_flags.append(
                            f"ungrounded_year: Ano '{num_str}' não fundamentado nos fatos citados."
                        )
                elif len(num_str) > 1 or int(float(num_str.replace(",", "."))) > 1:
                    clean_num = num_str.replace(",", ".")
                    if clean_num not in corpus_numbers and num_str not in corpus_numbers:
                        item_flags.append(
                            f"ungrounded_number: Número '{num_str}' não fundamentado nos fatos citados."
                        )

            # 2.10 Validação de numerais por extenso
            text_norm = _normalize_for_search(text)
            for word, digit in _SPELLED_NUMBERS_MAP.items():
                if re.search(rf"\b{word}\b", text_norm):
                    if word not in corpus_norm and digit not in corpus_numbers:
                        item_flags.append(
                            f"ungrounded_spelled_number: Numeral '{word}' ({digit}) não fundamentado nos fatos citados."
                        )

            # 2.11 Detecção de promoção de cargo indevida
            for promoted in _PROMOTED_ROLES:
                if re.search(rf"\b{promoted}\b", text_norm):
                    # Verifica se o usuário tem esse papel confirmado em algum fato citado
                    promoted_norm = _normalize_for_search(promoted)
                    has_role = any(
                        promoted_norm in _normalize_for_search(f.role_or_title)
                        for f in cited_facts
                        if f.role_or_title
                    )
                    if not has_role:
                        item_flags.append(
                            f"unsubstantiated_role_promotion: Cargo/título '{promoted}' atribuído sem confirmação factual."
                        )

            # 2.12 Detecção de tecnologias não confirmadas
            for canonical_tech, aliases in _TECH_ALIASES.items():
                alias_matches = [
                    alias for alias in aliases
                    if _contains_term(text_norm, _normalize_for_search(alias))
                ]
                if alias_matches:
                    tech_norm = _normalize_for_search(canonical_tech)
                    in_cited_facts = any(
                        tech_norm in _normalize_for_search(" ".join(f.technologies))
                        or any(
                            _contains_term(_normalize_for_search(f_desc), tech_norm)
                            for f_desc in (f.description, f.verified_results, f.label)
                            if f_desc
                        )
                        for f in cited_facts
                    )
                    in_user_skills = (
                        tech_norm in confirmed_techs
                        or any(tech_norm in _normalize_for_search(t) for t in confirmed_techs)
                    )
                    in_opportunity = (
                        tech_norm in opportunity_techs
                        or any(tech_norm in _normalize_for_search(t) for t in opportunity_techs)
                    )

                    if not (in_cited_facts or in_user_skills or in_opportunity):
                        item_flags.append(
                            f"unconfirmed_technology: Tecnologia '{canonical_tech}' citada sem constar nas competências confirmadas do usuário."
                        )

            # 2.13 Detecção de alegações absolutas não fundamentadas (prêmios/patentes)
            for claim_match in _UNSUBSTANTIATED_CLAIMS_RE.finditer(text):
                claim_word = claim_match.group(0).lower()
                if claim_word not in corpus_norm:
                    item_flags.append(
                        f"unsubstantiated_claim: Alegação de '{claim_match.group(0)}' sem comprovação nos fatos citados."
                    )

            if item_flags:
                rejection_reasons.extend(
                    [f"[{item.slot_id}] {flag}" for flag in item_flags]
                )
                flagged_items.append({
                    "slot_id": item.slot_id,
                    "suggestion_index": idx,
                    "flags": item_flags,
                })

        is_valid = len(rejection_reasons) == 0 and len(flagged_items) == 0
        return GroundingValidationResult(
            is_valid=is_valid,
            rejection_reasons=rejection_reasons,
            flagged_items=flagged_items,
        )

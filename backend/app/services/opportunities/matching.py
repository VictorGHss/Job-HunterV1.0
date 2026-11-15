import re
from typing import Any

from app.models.opportunity import (
    EmploymentType,
    Opportunity,
    OpportunityType,
    WorkMode,
)
from app.models.profile import ProfessionalProfile, default_career_preferences
from app.schemas.opportunity import OpportunityMatchEvaluation

_WORLDWIDE_TOKENS = {
    "worldwide",
    "anywhere",
    "global",
    "international",
    "exterior",
    "exterior (internacional)",
    "100% anywhere",
    "work from anywhere",
}

_BRAZIL_SYNONYMS = {"brasil", "brazil", "br", "latam", "latin america", "south america", "américa latina", "america latina"}


def _contains_term(haystack: str, term: str) -> bool:
    needle = term.strip().lower()
    if not needle:
        return False
    # Evita falso positivo em palavras curtas (ex: 'c' ou 'go') usando fronteira de palavra
    if len(needle) <= 4 and needle.isalnum():
        return bool(re.search(rf"\b{re.escape(needle)}\b", haystack))
    return needle in haystack


def _normalize_contract_label(label: str) -> str:
    lower = label.strip().lower()
    if "estág" in lower or "estag" in lower or "intern" in lower:
        return EmploymentType.INTERNSHIP.value
    if "clt" in lower:
        return EmploymentType.CLT.value
    if "pj" in lower or "contract" in lower:
        return EmploymentType.PJ.value
    if "freelance" in lower or "freela" in lower:
        return EmploymentType.FREELANCE.value
    if "temp" in lower:
        return EmploymentType.TEMPORARY.value
    return lower


def _is_brazil(value: str | None) -> bool:
    if not value:
        return False
    return value.strip().lower() in _BRAZIL_SYNONYMS


def _region_matches_user(region_text: str, user_country: str) -> bool:
    token = region_text.strip().lower()
    if not token:
        return False
    if token in _WORLDWIDE_TOKENS or any(w in token for w in ("worldwide", "anywhere", "global")):
        return True
    if _is_brazil(user_country):
        return any(syn in token for syn in _BRAZIL_SYNONYMS)
    return user_country in token or token in user_country


def _evaluate_geography(
    opportunity: Opportunity,
    profile: ProfessionalProfile,
) -> tuple[str, list[str], list[str]]:
    inclusions: list[str] = []
    exclusions: list[str] = []

    user_country = (profile.country or "Brasil").strip().lower()
    user_state = (profile.state or "").strip().lower()
    user_city = (profile.city or "").strip().lower()

    if opportunity.work_mode == WorkMode.REMOTE.value:
        regions = list(opportunity.eligible_countries or [])
        if opportunity.country and opportunity.country not in regions:
            regions.append(opportunity.country)

        if opportunity.eligibility_unknown or not regions:
            inclusions.append(
                "Trabalho remoto com elegibilidade geográfica não especificada pela fonte (confirmar elegibilidade antes da candidatura)."
            )
            return ("unknown", inclusions, exclusions)

        if any(_region_matches_user(region, user_country) for region in regions):
            inclusions.append(
                f"Elegibilidade remota compatível com o perfil ({', '.join(regions)})."
            )
            return ("eligible", inclusions, exclusions)

        exclusions.append(
            f"Restrição geográfica incompatível com a localização do perfil ({', '.join(regions)})."
        )
        return ("excluded", inclusions, exclusions)

    if opportunity.work_mode in {WorkMode.HYBRID.value, WorkMode.ONSITE.value}:
        opp_country = (opportunity.country or "").strip().lower()
        opp_state = (opportunity.state or "").strip().lower()
        opp_city = (opportunity.city or "").strip().lower()
        opp_loc = (opportunity.location_text or "").strip().lower()

        if not (opp_country or opp_state or opp_city or opp_loc):
            return ("unknown", inclusions, exclusions)

        if opp_country and not _region_matches_user(opp_country, user_country):
            exclusions.append(
                f"Modalidade {opportunity.work_mode} em país incompatível com o perfil ({opportunity.country})."
            )
            return ("excluded", inclusions, exclusions)

        if user_city and opp_city and opp_city != user_city:
            exclusions.append(
                f"Localização {opportunity.work_mode} ({opportunity.city}) diferente da cidade configurada no perfil ({profile.city})."
            )
            return ("excluded", inclusions, exclusions)

        if user_state and opp_state and opp_state != user_state:
            exclusions.append(
                f"Localização {opportunity.work_mode} ({opportunity.state}) diferente do estado configurado no perfil ({profile.state})."
            )
            return ("excluded", inclusions, exclusions)

        if (
            (user_city and (opp_city == user_city or user_city in opp_loc))
            or (user_state and (opp_state == user_state or user_state in opp_loc))
            or _region_matches_user(opp_country or opp_loc, user_country)
        ):
            inclusions.append(
                f"Localização {opportunity.work_mode} compatível com o perfil."
            )
            return ("eligible", inclusions, exclusions)

        return ("unknown", inclusions, exclusions)

    return ("unknown", inclusions, exclusions)


def _language_matches(opp_language: str, preferred_languages: list[str]) -> bool:
    if not preferred_languages:
        return True
    opp_low = opp_language.strip().lower()
    for pref in preferred_languages:
        pref_low = pref.strip().lower()
        if not pref_low:
            continue
        if pref_low in opp_low or opp_low in pref_low:
            return True
        if ("português" in pref_low or "portugues" in pref_low) and (
            "portugu" in opp_low or "pt" == opp_low
        ):
            return True
        if ("inglês" in pref_low or "ingles" in pref_low or "english" in pref_low) and (
            "ingl" in opp_low or "english" in opp_low or "en" == opp_low
        ):
            return True
    return False


def evaluate_opportunity_for_user(
    opportunity: Opportunity,
    profile: ProfessionalProfile,
    *,
    target_category: str | None = None,
) -> OpportunityMatchEvaluation:
    """
    Avalia compatibilidade de forma 100% determinística e explicável com base nas
    preferências e localização do usuário, sem pontuação percentual inventada.
    """
    defaults = default_career_preferences()
    prefs: dict[str, Any] = dict(defaults)
    if isinstance(profile.preferences, dict):
        for key, value in profile.preferences.items():
            if isinstance(value, dict) and isinstance(prefs.get(key), dict):
                prefs[key] = {**prefs[key], **value}

    inclusions: list[str] = []
    exclusions: list[str] = []

    category = target_category
    if category is None and opportunity.opportunity_type in {
        OpportunityType.INTERNSHIP.value,
        OpportunityType.JUNIOR.value,
        OpportunityType.FREELANCE.value,
    }:
        category = opportunity.opportunity_type

    # 1. Restrições de fontes externas
    source_restrictions = prefs["source_restrictions"]
    source_slug = opportunity.source.slug.lower() if opportunity.source else ""
    source_url_low = opportunity.source_url.lower()

    if (
        source_slug == "workana" or "workana." in source_url_low
    ) and not source_restrictions.get("workana_enabled", True):
        exclusions.append("Fonte Workana bloqueada conforme restrições do usuário.")

    if source_slug == "gupy" or "gupy.io" in source_url_low:
        if source_restrictions.get("gupy_mode") == "disabled":
            exclusions.append("Fonte Gupy desabilitada conforme restrições do usuário.")

    # 2. Habilitação da categoria alvo
    if category == OpportunityType.INTERNSHIP.value:
        if not prefs["internships"].get("enabled", True):
            exclusions.append("Categoria Estágios desabilitada nas preferências do usuário.")
        else:
            inclusions.append("Categoria compatível com a frente de Estágios ativa.")
    elif category == OpportunityType.JUNIOR.value:
        if not prefs["junior_developer"].get("enabled", True):
            exclusions.append("Categoria Desenvolvedor Júnior desabilitada nas preferências.")
        else:
            inclusions.append("Categoria compatível com a frente de Desenvolvedor Júnior ativa.")
    elif category == OpportunityType.FREELANCE.value:
        if not prefs["freelance"].get("enabled", True):
            exclusions.append("Categoria Freelancers desabilitada nas preferências do usuário.")
        else:
            inclusions.append("Categoria compatível com a frente de Freelancers ativa.")

    # 3. Contrato e bloqueio CLT (sem confundir estágio com CLT)
    if category == OpportunityType.JUNIOR.value:
        jr_prefs = prefs["junior_developer"]
        if jr_prefs.get("block_clt", False) and (
            opportunity.employment_type == EmploymentType.CLT.value
        ):
            exclusions.append(
                "Regra block_clt ativa: oportunidades classificadas como CLT são excluídas."
            )

        accepted = jr_prefs.get("accepted_contract_types") or []
        if accepted and opportunity.employment_type != EmploymentType.UNKNOWN.value:
            normalized_accepted = {_normalize_contract_label(item) for item in accepted}
            if opportunity.employment_type not in normalized_accepted:
                exclusions.append(
                    f"Contrato '{opportunity.employment_type}' fora das modalidades aceitas ({', '.join(accepted)})."
                )
            else:
                inclusions.append(
                    f"Modalidade contratual aceita ({opportunity.employment_type})."
                )
    elif opportunity.employment_type != EmploymentType.UNKNOWN.value:
        inclusions.append(f"Contrato informado: {opportunity.employment_type}.")

    # 4. Áreas excluídas e áreas prioritárias (análise em título, requisitos, techs e descrição)
    substantive_text = " ".join(
        [
            opportunity.title or "",
            " ".join(opportunity.technologies or []),
            " ".join(opportunity.requirements or []),
            (opportunity.description or "")[:3000],
        ]
    ).lower()
    title_low = (opportunity.title or "").lower()

    excluded_areas: list[str] = []
    priority_terms: list[str] = []
    preferred_languages: list[str] = []

    if category == OpportunityType.INTERNSHIP.value:
        excluded_areas = list(prefs["internships"].get("excluded_areas") or [])
        priority_terms = list(prefs["internships"].get("priority_areas") or [])
        preferred_languages = list(prefs["internships"].get("preferred_languages") or [])
    elif category == OpportunityType.JUNIOR.value:
        excluded_areas = list(prefs["junior_developer"].get("excluded_areas") or [])
        priority_terms = list(prefs["junior_developer"].get("priority_areas") or [])
    elif category == OpportunityType.FREELANCE.value:
        priority_terms = list(prefs["freelance"].get("priority_categories") or [])
        preferred_languages = list(prefs["freelance"].get("preferred_languages") or [])

    for excluded in excluded_areas:
        if _contains_term(title_low, excluded) or _contains_term(substantive_text, excluded):
            exclusions.append(f"Área explicitamente excluída encontrada: '{excluded}'.")

    # 5. Geografia e modalidade
    geo_status, geo_inclusions, geo_exclusions = _evaluate_geography(
        opportunity, profile
    )
    inclusions.extend(geo_inclusions)
    exclusions.extend(geo_exclusions)

    # Escopo freelance (Brasil vs Exterior)
    if category == OpportunityType.FREELANCE.value:
        scopes = [s.lower() for s in (prefs["freelance"].get("scopes") or [])]
        if scopes and geo_status == "eligible":
            allows_br = any("brasil" in s or "brazil" in s for s in scopes)
            allows_intl = any(
                marker in s for s in scopes for marker in ("exterior", "internacional", "global")
            )
            regions = opportunity.eligible_countries or ([opportunity.country] if opportunity.country else [])
            is_br_only = bool(regions) and all(_is_brazil(r) for r in regions)
            if is_br_only and not allows_br:
                exclusions.append("Escopo freelance configurado não inclui oportunidades exclusivas do Brasil.")
            elif not is_br_only and not allows_intl and regions:
                exclusions.append("Escopo freelance configurado não inclui oportunidades internacionais.")

    # 6. Idioma quando informado
    if opportunity.language and preferred_languages:
        if _language_matches(opportunity.language, preferred_languages):
            inclusions.append(f"Idioma compatível ({opportunity.language}).")
        else:
            exclusions.append(
                f"Idioma informado ({opportunity.language}) não está entre os preferidos ({', '.join(preferred_languages)})."
            )

    # 7. Tecnologias / áreas prioritárias nos dados substantivos (não apenas palavra no título)
    matched_priorities: list[str] = []
    title_only_priorities: list[str] = []
    tech_and_req_text = " ".join(
        list(opportunity.technologies or [])
        + list(opportunity.requirements or [])
        + [opportunity.description or ""]
    ).lower()

    for term in priority_terms:
        if _contains_term(tech_and_req_text, term):
            matched_priorities.append(term)
        elif _contains_term(title_low, term):
            title_only_priorities.append(term)

    if matched_priorities:
        inclusions.append(
            f"Aderência substantiva a áreas/tecnologias prioritárias: {', '.join(matched_priorities[:5])}."
        )
    elif title_only_priorities:
        inclusions.append(
            f"Menção apenas no título ({', '.join(title_only_priorities[:3])}); "
            "requisitos detalhados ou tecnologias não confirmam aderência completa."
        )
    elif opportunity.technologies:
        inclusions.append(
            f"Tecnologias declaradas na vaga: {', '.join(opportunity.technologies[:5])}."
        )

    eligible = len(exclusions) == 0
    return OpportunityMatchEvaluation(
        eligible=eligible,
        geographic_eligibility=geo_status,
        inclusion_reasons=inclusions,
        exclusion_reasons=exclusions,
    )

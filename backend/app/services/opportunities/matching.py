import re
from typing import Any

from app.models.opportunity import (
    EmploymentType,
    Opportunity,
    OpportunityType,
    ProfessionalArea,
    WorkMode,
)
from app.models.profile import ProfessionalProfile, default_career_preferences
from app.schemas.opportunity import OpportunityMatchEvaluation
from app.services.opportunities.classification import (
    PROFESSIONAL_AREA_LABELS_PT,
    TECH_TARGET_AREAS,
    classify_professional_area,
)

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

_BRAZIL_SYNONYMS = {
    "brasil",
    "brazil",
    "br",
    "latam",
    "latin america",
    "south america",
    "américa latina",
    "america latina",
}

_NON_TECH_PRIMARY_AREAS = frozenset(
    {
        ProfessionalArea.TECHNICAL_SUPPORT.value,
        ProfessionalArea.CUSTOMER_SUPPORT.value,
        ProfessionalArea.MARKETING_SALES.value,
        ProfessionalArea.HEALTHCARE.value,
        ProfessionalArea.ADMINISTRATION.value,
        ProfessionalArea.OTHER.value,
    }
)


def _contains_term(haystack: str, term: str) -> bool:
    needle = term.strip().lower()
    if not needle:
        return False
    if len(needle) <= 4 and needle.isalnum():
        return bool(re.search(rf"\b{re.escape(needle)}\b", haystack))
    return needle in haystack


def _normalize_contract_label(label: str) -> str:
    lower = label.strip().lower()
    if "estág" in lower or "estag" in lower or "intern" in lower:
        return EmploymentType.INTERNSHIP.value
    if "clt" in lower:
        return EmploymentType.CLT.value
    if "pj" in lower or "contract" in lower or "presta" in lower:
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


def resolve_opportunity_areas(opportunity: Opportunity) -> tuple[str, list[str]]:
    """
    Retorna `(professional_area, secondary_areas)` da oportunidade. Caso o objeto em memória
    ainda esteja com `unknown` (ex.: fixture de teste instanciada diretamente), executa o
    classificador determinístico sobre título, descrição, requisitos e tecnologias.
    """
    current_primary = (getattr(opportunity, "professional_area", None) or "").strip()
    current_secondary = list(getattr(opportunity, "secondary_areas", None) or [])
    if current_primary and current_primary != ProfessionalArea.UNKNOWN.value:
        return (current_primary, current_secondary)

    primary, secondary, _ = classify_professional_area(
        title=opportunity.title,
        tags=list(opportunity.technologies or []),
        description=opportunity.description,
        requirements=list(opportunity.requirements or []),
    )
    return (primary, list(secondary))


def _derive_desired_areas(priority_terms: list[str], all_prefs: dict[str, Any]) -> set[str]:
    corpus_terms = list(priority_terms)
    if not corpus_terms:
        for section in ("internships", "junior_developer", "freelance"):
            sec_dict = all_prefs.get(section) or {}
            corpus_terms.extend(sec_dict.get("priority_areas") or [])
            corpus_terms.extend(sec_dict.get("priority_categories") or [])

    if not corpus_terms:
        return set(TECH_TARGET_AREAS)

    desired: set[str] = set()
    for raw in corpus_terms:
        low = raw.strip().lower()
        if not low:
            continue
        if any(k in low for k in ("backend", "back-end", "python", "java", "spring", "fastapi", "node", "go")):
            desired.update({ProfessionalArea.BACKEND.value, ProfessionalArea.SOFTWARE_DEVELOPMENT.value})
        if any(k in low for k in ("frontend", "front-end", "react", "typescript", "javascript", "ui", "sites")):
            desired.update({ProfessionalArea.FRONTEND.value, ProfessionalArea.SOFTWARE_DEVELOPMENT.value})
        if any(
            k in low
            for k in (
                "full stack",
                "fullstack",
                "engenharia de software",
                "desenvolvimento de sistemas",
                "software",
                "aplicações",
                "aplicacoes",
            )
        ):
            desired.update(
                {
                    ProfessionalArea.FULLSTACK.value,
                    ProfessionalArea.SOFTWARE_DEVELOPMENT.value,
                    ProfessionalArea.BACKEND.value,
                    ProfessionalArea.FRONTEND.value,
                }
            )
        if any(k in low for k in ("dados", "data", "analytics", "dashboard", "sql", "bi")):
            desired.add(ProfessionalArea.DATA.value)
        if any(k in low for k in ("inteligência artificial", "inteligencia artificial", "ia", "ai", "machine learning", "bot")):
            desired.add(ProfessionalArea.ARTIFICIAL_INTELLIGENCE.value)
        if any(k in low for k in ("devops", "cloud", "sre", "docker", "kubernetes")):
            desired.add(ProfessionalArea.DEVOPS_CLOUD.value)
        if any(k in low for k in ("segurança", "seguranca", "infraestrutura", "infrastructure")):
            desired.update({ProfessionalArea.INFRASTRUCTURE.value, ProfessionalArea.DEVOPS_CLOUD.value})
        if any(k in low for k in ("api", "integra", "automa", "scraping", "webhook")):
            desired.update({ProfessionalArea.API_INTEGRATIONS.value, ProfessionalArea.SOFTWARE_DEVELOPMENT.value})
        if any(k in low for k in ("marketing", "vendas", "sales")):
            desired.add(ProfessionalArea.MARKETING_SALES.value)
        if any(k in low for k in ("saúde", "saude", "health", "medical")):
            desired.add(ProfessionalArea.HEALTHCARE.value)
        if any(k in low for k in ("administra", "finanças", "financas", "rh")):
            desired.add(ProfessionalArea.ADMINISTRATION.value)

    return desired or set(TECH_TARGET_AREAS)


def _evaluate_geography(
    opportunity: Opportunity,
    profile: ProfessionalProfile,
) -> tuple[str, list[str], list[str]]:
    inclusions: list[str] = []
    exclusions: list[str] = []

    user_country = (profile.country or "Brasil").strip()
    user_city = (profile.city or "").strip().lower()
    user_state = (profile.state or "").strip().lower()

    if opportunity.work_mode in {WorkMode.HYBRID.value, WorkMode.ONSITE.value}:
        opp_country = (opportunity.country or "").strip()
        opp_city = (opportunity.city or "").strip().lower()
        opp_state = (opportunity.state or "").strip().lower()

        if opp_country and not _region_matches_user(opp_country, user_country):
            exclusions.append(
                f"Vaga {opportunity.work_mode} fora do país do usuário ({opp_country})."
            )
            return ("excluded", inclusions, exclusions)

        if user_city and opp_city and user_city != opp_city:
            exclusions.append(
                f"Vaga {opportunity.work_mode} exige localidade diferente ({opportunity.city})."
            )
            return ("excluded", inclusions, exclusions)

        if user_state and opp_state and user_state != opp_state and not opp_city:
            exclusions.append(
                f"Vaga {opportunity.work_mode} em estado divergente ({opportunity.state})."
            )
            return ("excluded", inclusions, exclusions)

        inclusions.append(
            f"Modalidade {opportunity.work_mode} compatível com a localização do perfil."
        )
        return ("eligible", inclusions, exclusions)

    regions = list(opportunity.eligible_countries or [])
    if opportunity.country and opportunity.country not in regions:
        regions.append(opportunity.country)

    if opportunity.eligibility_unknown or not regions:
        inclusions.append(
            "Elegibilidade geográfica não especificada pela fonte; mantida para análise manual."
        )
        return ("unknown", inclusions, exclusions)

    if any(_region_matches_user(region, user_country) for region in regions):
        inclusions.append(
            f"Elegibilidade remota compatível com o perfil ({', '.join(regions[:2])})."
        )
        return ("eligible", inclusions, exclusions)

    exclusions.append(
        f"Restrição geográfica incompatível com a localização do perfil ({', '.join(regions[:2])})."
    )
    return ("excluded", inclusions, exclusions)


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
    Avalia compatibilidade de forma 100% determinística e explicável considerando
    área profissional, senioridade/categoria, contrato, restrições e geografia.
    """
    defaults = default_career_preferences()
    prefs: dict[str, Any] = dict(defaults)
    if isinstance(profile.preferences, dict):
        for key, value in profile.preferences.items():
            if isinstance(value, dict) and isinstance(prefs.get(key), dict):
                prefs[key] = {**prefs[key], **value}

    inclusions: list[str] = []
    exclusions: list[str] = []
    uncertainty_notes: list[str] = []

    category = target_category
    if category is None and opportunity.opportunity_type in {
        OpportunityType.INTERNSHIP.value,
        OpportunityType.JUNIOR.value,
        OpportunityType.FREELANCE.value,
    }:
        category = opportunity.opportunity_type

    # 1. Ciclo de vida e restrições de fontes externas
    opp_status = (getattr(opportunity, "source_status", None) or "active").lower()
    if opp_status == "expired":
        exclusions.append("Publicação expirada conforme prazo informado pela fonte.")
    elif opp_status == "closed":
        exclusions.append("Publicação encerrada na fonte de origem.")
    elif opp_status == "removed":
        exclusions.append("Publicação removida na fonte de origem.")
    elif opp_status in {"unknown", "unconfirmed"}:
        uncertainty_notes.append(
            "Disponibilidade atual não confirmada no último lote limitado da fonte."
        )
    elif opp_status == "source_unavailable":
        uncertainty_notes.append(
            "A fonte apresentou indisponibilidade temporária na última verificação."
        )

    source_restrictions = prefs["source_restrictions"]
    source_slug = opportunity.source.slug.lower() if opportunity.source else ""
    source_url_low = (opportunity.source_url or "").lower()

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

    # 3. Contrato e bloqueio CLT (sem confundir estágio ou unknown com CLT)
    if opportunity.employment_type == EmploymentType.UNKNOWN.value:
        uncertainty_notes.append("Tipo de contrato não informado pela fonte original.")

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
        if (
             prefs["junior_developer"].get("block_clt", False)
            and opportunity.employment_type == EmploymentType.CLT.value
        ):
            exclusions.append(
                "Regra block_clt ativa: oportunidades classificadas como CLT são excluídas."
            )
        else:
            inclusions.append(f"Contrato informado: {opportunity.employment_type}.")

    # 4. Áreas excluídas, área profissional da vaga e aderência de domínio
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
        excluded_areas = list(prefs["junior_developer"].get("excluded_areas") or [])
        priority_terms = list(prefs["freelance"].get("priority_categories") or [])
        preferred_languages = list(prefs["freelance"].get("preferred_languages") or [])
    else:
        excluded_areas = list(prefs["junior_developer"].get("excluded_areas") or [])
        priority_terms = list(prefs["junior_developer"].get("priority_areas") or [])

    literal_excluded_hit = False
    for excluded in excluded_areas:
        if _contains_term(title_low, excluded) or _contains_term(substantive_text, excluded):
            exclusions.append(f"Área explicitamente excluída encontrada: '{excluded}'.")
            literal_excluded_hit = True

    primary_area, secondary_areas = resolve_opportunity_areas(opportunity)
    all_opp_areas = [primary_area] + [a for a in secondary_areas if a != primary_area]
    desired_areas = _derive_desired_areas(priority_terms, prefs)

    matched_areas = [a for a in all_opp_areas if a in desired_areas]
    area_compatibility: str = "unknown"

    if primary_area == ProfessionalArea.UNKNOWN.value:
        area_compatibility = "unknown"
        uncertainty_notes.append(
            "Área profissional não identificada por falta de evidências suficientes."
        )
        exclusions.append(
            "Área profissional não identificada; evidência insuficiente para recomendar como compatível com o perfil."
        )
    elif (
        primary_area == ProfessionalArea.TECHNICAL_SUPPORT.value
        or ProfessionalArea.TECHNICAL_SUPPORT.value in secondary_areas
    ):
        area_compatibility = "incompatible"
        if not literal_excluded_hit:
            exclusions.append(
                "Área profissional incompatível com o perfil: Suporte Técnico e Help Desk."
            )
    elif primary_area in _NON_TECH_PRIMARY_AREAS and primary_area not in desired_areas:
        area_compatibility = "incompatible"
        area_label = PROFESSIONAL_AREA_LABELS_PT.get(primary_area, primary_area)
        if not literal_excluded_hit:
            exclusions.append(
                f"Área profissional incompatível com o direcionamento de tecnologia do perfil ({area_label})."
            )
    elif matched_areas:
        area_compatibility = "compatible"
        matched_labels = [PROFESSIONAL_AREA_LABELS_PT.get(a, a) for a in matched_areas]
        inclusions.append(
            f"Área profissional compatível com o perfil: {', '.join(matched_labels[:3])}."
        )
    else:
        area_compatibility = "incompatible"
        area_label = PROFESSIONAL_AREA_LABELS_PT.get(primary_area, primary_area)
        exclusions.append(
            f"Área profissional ({area_label}) fora das especialidades prioritárias do perfil."
        )

    # 5. Geografia e modalidade
    geo_status, geo_inclusions, geo_exclusions = _evaluate_geography(
        opportunity, profile
    )
    inclusions.extend(geo_inclusions)
    exclusions.extend(geo_exclusions)
    if geo_status == "unknown":
        uncertainty_notes.append("Elegibilidade geográfica não confirmada na origem.")

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

    # 7. Tecnologias / áreas prioritárias nos dados substantivos (apenas quando a área não for incompatível)
    matched_priorities: list[str] = []
    title_only_priorities: list[str] = []
    missing_priorities: list[str] = []
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
        else:
            missing_priorities.append(term)

    if area_compatibility == "compatible":
        if matched_priorities:
            inclusions.append(
                f"Aderência substantiva a áreas/tecnologias prioritárias: {', '.join(matched_priorities[:5])}."
            )
        elif title_only_priorities:
            inclusions.append(
                f"Menção apenas no título ({', '.join(title_only_priorities[:3])}); "
                "requisitos detalhados ou tecnologias não confirmam aderência completa."
            )
            uncertainty_notes.append(
                "Tecnologia mencionada apenas no título, sem detalhamento no corpo da vaga."
            )
        elif opportunity.technologies:
            inclusions.append(
                f"Tecnologias declaradas na vaga: {', '.join(opportunity.technologies[:5])}."
            )
        elif priority_terms:
            uncertainty_notes.append(
                "A vaga não lista tecnologias explícitas para confirmar stack prioritária."
            )

    eligible = len(exclusions) == 0 and area_compatibility == "compatible"
    return OpportunityMatchEvaluation(
        eligible=eligible,
        geographic_eligibility=geo_status,
        area_compatibility=area_compatibility,
        matched_areas=matched_areas,
        matched_technologies=matched_priorities if area_compatibility == "compatible" else [],
        missing_priority_technologies=missing_priorities[:5] if not matched_priorities else [],
        uncertainty_notes=uncertainty_notes,
        inclusion_reasons=inclusions,
        exclusion_reasons=exclusions,
    )

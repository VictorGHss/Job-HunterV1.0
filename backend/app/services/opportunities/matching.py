from datetime import date
import re
from typing import Any, Sequence

from app.models.opportunity import (
    EmploymentType,
    ExperienceRequirementMode,
    Opportunity,
    OpportunityType,
    ProfessionalArea,
    SeniorityLevel,
    WorkMode,
)
from app.models.profile import (
    Education,
    EducationStatus,
    ProfessionalProfile,
    ProfessionalProject,
    Skill,
    WorkExperience,
    default_career_preferences,
)
from app.schemas.opportunity import OpportunityMatchEvaluation
from app.services.opportunities.classification import (
    PROFESSIONAL_AREA_LABELS_PT,
    SENIORITY_LABELS_PT,
    TECH_TARGET_AREAS,
    _CUSTOMER_SUPPORT_TITLE_RE,
    _TECH_SUPPORT_TITLE_RE,
    classify_experience_requirements,
    classify_opportunity,
    classify_professional_area,
    normalize_classification_text,
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

_TECH_ALIASES: dict[str, tuple[str, ...]] = {
    "java": ("java",),
    "spring boot": ("spring boot", "spring"),
    "python": ("python",),
    "fastapi": ("fastapi",),
    "django": ("django",),
    "flask": ("flask",),
    "typescript": ("typescript", "ts"),
    "javascript": ("javascript", "js"),
    "react": ("react", "reactjs", "react.js"),
    "next.js": ("next.js", "nextjs", "next js"),
    "angular": ("angular",),
    "vue": ("vue", "vuejs", "vue.js", "nuxt", "nuxtjs"),
    "node.js": ("node.js", "nodejs", "node js", "node"),
    "nestjs": ("nestjs", "nest.js"),
    "golang": ("golang", "go"),
    "c#": ("c#", "csharp", ".net", "dotnet", "dot net"),
    "c++": ("c++",),
    "php": ("php", "laravel"),
    "ruby": ("ruby", "ruby on rails"),
    "rust": ("rust",),
    "postgresql": ("postgresql", "postgres"),
    "mysql": ("mysql",),
    "sql": ("sql",),
    "redis": ("redis",),
    "docker": ("docker",),
    "kubernetes": ("kubernetes", "k8s"),
    "aws": ("aws", "amazon web services"),
    "gcp": ("gcp", "google cloud"),
    "azure": ("azure",),
    "terraform": ("terraform",),
    "kafka": ("kafka", "apache kafka"),
    "graphql": ("graphql",),
    "apis rest": ("apis rest", "api rest", "rest", "restful", "apis restful"),
    "salesforce": ("salesforce",),
    "flutter": ("flutter",),
    "kotlin": ("kotlin",),
}


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


def resolve_opportunity_seniority_and_experience(
    opportunity: Opportunity,
) -> tuple[str, str, int | None, int | None, str | None, tuple[str, ...], tuple[str, ...]]:
    """
    Retorna `(seniority_level, experience_requirement_mode, min_years, preferred_years,
    experience_summary, required_technologies, desirable_technologies)` da oportunidade,
    reavaliando deterministicamente se o objeto em memória ainda estiver sem os novos campos.
    """
    exp_eval = classify_experience_requirements(
        title=opportunity.title,
        description=opportunity.description,
        requirements=list(opportunity.requirements or []),
    )
    stored_sen = (getattr(opportunity, "seniority_level", None) or "").strip()
    stored_mode = (getattr(opportunity, "experience_requirement_mode", None) or "").strip()

    if stored_sen and stored_sen != SeniorityLevel.UNKNOWN.value:
        sen = stored_sen
        mode = stored_mode or exp_eval.mode
        min_yrs = getattr(opportunity, "experience_min_years", None)
        pref_yrs = getattr(opportunity, "experience_preferred_years", None)
        summary = getattr(opportunity, "experience_summary", None) or exp_eval.summary
        if stored_mode == ExperienceRequirementMode.NOT_SPECIFIED.value and exp_eval.mode != ExperienceRequirementMode.NOT_SPECIFIED.value:
            mode = exp_eval.mode
            min_yrs = exp_eval.min_years
            pref_yrs = exp_eval.preferred_years
            summary = exp_eval.summary
        return (
            sen,
            mode,
            min_yrs,
            pref_yrs,
            summary,
            exp_eval.mandatory_technologies,
            exp_eval.desirable_technologies,
        )

    meta = getattr(opportunity, "raw_metadata", None) or {}
    meta_levels: list[str] = []
    if isinstance(meta, dict):
        if isinstance(meta.get("labels"), list):
            meta_levels.extend(str(x) for x in meta["labels"])
        if meta.get("job_level") and str(meta["job_level"]).lower() not in {"any", "all"}:
            meta_levels.append(str(meta["job_level"]))
        if isinstance(meta.get("seniority"), list):
            meta_levels.extend(str(x) for x in meta["seniority"])

    decision = classify_opportunity(
        title=opportunity.title,
        tags=list(opportunity.technologies or []),
        description=opportunity.description,
        requirements=list(opportunity.requirements or []),
        metadata_levels=meta_levels,
    )
    return (
        decision.seniority_level,
        decision.experience_requirement_mode,
        decision.experience_min_years,
        decision.experience_preferred_years,
        decision.experience_summary,
        decision.required_technologies,
        decision.desirable_technologies,
    )


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


def _merge_date_intervals_years(intervals: list[tuple[date, date]]) -> float:
    """Mescla intervalos sobrepostos e calcula anos totais sem contagem duplicada."""
    if not intervals:
        return 0.0
    ordered = sorted(intervals, key=lambda pair: (pair[0], pair[1]))
    merged: list[tuple[date, date]] = [ordered[0]]
    for start_d, end_d in ordered[1:]:
        prev_start, prev_end = merged[-1]
        if start_d <= prev_end:
            merged[-1] = (prev_start, max(prev_end, end_d))
        else:
            merged.append((start_d, end_d))
    total_days = sum(max(0, (end_d - start_d).days) for start_d, end_d in merged)
    return round(total_days / 365.25, 2)


def _estimate_candidate_profile_stage(
    profile: ProfessionalProfile,
    prefs: dict[str, Any],
    skills: Sequence[Skill] | None,
    experiences: Sequence[WorkExperience] | None,
    educations: Sequence[Education] | None,
    projects: Sequence[ProfessionalProject] | None,
) -> tuple[float, float, int, set[str], bool, bool, bool]:
    """
    Calcula de forma determinística e sem inventar fatos:
    - `confirmed_target_years`: anos em experiências elegíveis e relevantes para o cargo-alvo
      (nunca inclui experiências com `eligible_as_target_role=False`, suporte de TI ou projetos)
    - `total_work_years`: anos totais de trabalho datado com intervalos sobrepostos mesclados
      (informativo apenas; não substitui experiência na área-alvo)
    - `candidate_ceiling_rank`: nível máximo compatível com perfil/experiência relevante
    - `candidate_skill_tokens`: conjunto normalizado de tecnologias/habilidades declaradas
    - `has_student_status`: se há formação em andamento para estágio
    - `has_explicit_skills`: se o usuário já possui skills cadastradas
    - `has_practical_projects`: se há projetos práticos como evidência complementar de stack
    """
    today = date.today()
    target_intervals: list[tuple[date, date]] = []
    total_intervals: list[tuple[date, date]] = []
    skill_tokens: set[str] = set()

    def _collect_tokens(raw_text: str | None) -> None:
        if not raw_text:
            return
        norm = normalize_classification_text(raw_text)
        # Remove versões entre parênteses para reconhecer ex.: "Java (17/21)" -> "java"
        stripped_parens = re.sub(r"\([^)]*\)", " ", norm).strip()
        for chunk in {norm, stripped_parens}:
            if chunk:
                skill_tokens.add(chunk)
        for canonical, aliases in _TECH_ALIASES.items():
            for alias in aliases:
                if _contains_term(norm, alias):
                    skill_tokens.add(canonical)
                    break

    _collect_tokens(profile.professional_title)
    _collect_tokens(profile.professional_summary)

    has_explicit_skills = bool(skills)
    if skills:
        for sk in skills:
            _collect_tokens(sk.name)
            _collect_tokens(sk.notes)

    if experiences:
        for exp in experiences:
            role_norm = normalize_classification_text(exp.role)
            is_non_target_role = bool(
                exp.experience_type == "academic"
                or _TECH_SUPPORT_TITLE_RE.search(role_norm)
                or _CUSTOMER_SUPPORT_TITLE_RE.search(role_norm)
            )
            is_eligible_target = bool(exp.eligible_as_target_role) and not is_non_target_role

            if exp.start_date is not None:
                # Datas incompletas (sem end_date e is_current=False) não assumem duração até hoje
                if exp.is_current:
                    end_dt = today
                elif exp.end_date is not None:
                    end_dt = exp.end_date
                else:
                    end_dt = None

                if end_dt is not None and end_dt >= exp.start_date:
                    total_intervals.append((exp.start_date, end_dt))
                    if is_eligible_target:
                        target_intervals.append((exp.start_date, end_dt))

            # Apenas experiências elegíveis ao cargo-alvo reforçam tokens de atuação alvo
            if is_eligible_target:
                _collect_tokens(exp.role)
                _collect_tokens(exp.description)
                for t in (exp.technologies or []) + (exp.related_skills or []):
                    _collect_tokens(t)

    has_practical_projects = bool(projects)
    if projects:
        # Projetos fornecem evidência prática complementar de stack, nunca anos de experiência
        for proj in projects:
            _collect_tokens(proj.name)
            _collect_tokens(proj.description)
            for t in proj.technologies or []:
                _collect_tokens(t)

    for section in ("internships", "junior_developer", "freelance"):
        sec_dict = prefs.get(section) or {}
        for item in (sec_dict.get("priority_areas") or []) + (
            sec_dict.get("priority_categories") or []
        ):
            _collect_tokens(str(item))

    has_student_status = False
    if educations:
        for edu in educations:
            if edu.education_status == EducationStatus.IN_PROGRESS.value:
                has_student_status = True

    confirmed_target_years = _merge_date_intervals_years(target_intervals)
    total_work_years = _merge_date_intervals_years(total_intervals)

    title_norm = normalize_classification_text(profile.professional_title)
    if any(k in title_norm for k in ("staff", "principal", "architect", "head of", "director", "manager")):
        ceiling_rank = 5
    elif "senior" in title_norm or confirmed_target_years >= 4.0:
        ceiling_rank = 4
    elif "pleno" in title_norm or "mid" in title_norm or confirmed_target_years >= 2.0:
        ceiling_rank = 3
    else:
        # Perfil de entrada (estágio / júnior / início de carreira / freelance compatível)
        ceiling_rank = 2

    return (
        confirmed_target_years,
        total_work_years,
        ceiling_rank,
        skill_tokens,
        has_student_status,
        has_explicit_skills,
        has_practical_projects,
    )


def _skill_matches_tech(tech_label: str, candidate_tokens: set[str]) -> bool:
    norm = normalize_classification_text(tech_label)
    if norm in candidate_tokens:
        return True
    aliases = _TECH_ALIASES.get(norm, (norm,))
    for alias in aliases:
        if alias in candidate_tokens:
            return True
        for tok in candidate_tokens:
            if _contains_term(tok, alias):
                return True
    return False


def _evaluate_seniority_dimension(
    seniority_level: str,
    ceiling_rank: int,
    relevant_target_years: float,
    prefs: dict[str, Any],
) -> tuple[str, list[str], list[str], list[str]]:
    inclusions: list[str] = []
    exclusions: list[str] = []
    uncertainties: list[str] = []
    label = SENIORITY_LABELS_PT.get(seniority_level, seniority_level)

    if seniority_level == SeniorityLevel.INTERNSHIP.value:
        if not prefs["internships"].get("enabled", True):
            exclusions.append("Nível Estágio desabilitado nas preferências do perfil.")
            return ("incompatible", inclusions, exclusions, uncertainties)
        if ceiling_rank >= 4:
            exclusions.append("Vaga de Estágio abaixo da senioridade consolidada do perfil.")
            return ("incompatible", inclusions, exclusions, uncertainties)
        inclusions.append(f"Senioridade compatível com o perfil ({label}).")
        return ("compatible", inclusions, exclusions, uncertainties)

    if seniority_level in {SeniorityLevel.ENTRY_LEVEL.value, SeniorityLevel.JUNIOR.value}:
        if ceiling_rank >= 4:
            return ("potential", inclusions, exclusions, uncertainties)
        inclusions.append(f"Senioridade compatível com o momento do perfil ({label}).")
        return ("compatible", inclusions, exclusions, uncertainties)

    if seniority_level == SeniorityLevel.MID_LEVEL.value:
        if ceiling_rank >= 3:
            inclusions.append(f"Senioridade compatível ({label}).")
            return ("compatible", inclusions, exclusions, uncertainties)
        if relevant_target_years >= 1.5:
            uncertainties.append(
                f"Vaga de nível {label}; exige avaliação frente à experiência relevante no cargo-alvo."
            )
            return ("potential", inclusions, exclusions, uncertainties)
        exclusions.append(
            f"Senioridade incompatível: vaga requer nível {label}, acima da experiência relevante atual no cargo-alvo."
        )
        return ("incompatible", inclusions, exclusions, uncertainties)

    if seniority_level in {
        SeniorityLevel.SENIOR.value,
        SeniorityLevel.STAFF_PRINCIPAL.value,
        SeniorityLevel.MANAGEMENT.value,
    }:
        rank_needed = 4 if seniority_level == SeniorityLevel.SENIOR.value else 5
        if ceiling_rank >= rank_needed:
            inclusions.append(f"Senioridade compatível ({label}).")
            return ("compatible", inclusions, exclusions, uncertainties)
        exclusions.append(
            f"Senioridade incompatível: vaga exige nível {label}, inadequado para perfil de entrada/júnior."
        )
        return ("incompatible", inclusions, exclusions, uncertainties)

    uncertainties.append(
        "Senioridade da vaga não foi especificada pela fonte; requer avaliação do candidato."
    )
    return ("unknown", inclusions, exclusions, uncertainties)


def _evaluate_experience_dimension(
    exp_mode: str,
    min_years: int | None,
    preferred_years: int | None,
    seniority_level: str,
    relevant_target_years: float,
) -> tuple[str, list[str], list[str], list[str]]:
    inclusions: list[str] = []
    exclusions: list[str] = []
    uncertainties: list[str] = []

    if exp_mode == ExperienceRequirementMode.NONE_REQUIRED.value:
        inclusions.append("A vaga informa expressamente que não exige experiência prévia.")
        return ("compatible", inclusions, exclusions, uncertainties)

    if exp_mode == ExperienceRequirementMode.REQUIRED.value:
        if min_years is not None:
            unit = "ano" if min_years == 1 else "anos"
            if relevant_target_years >= min_years:
                inclusions.append(
                    f"Requisito mínimo de experiência compatível ({min_years}+ {unit} na área-alvo)."
                )
                return ("compatible", inclusions, exclusions, uncertainties)
            if min_years == 1 and relevant_target_years >= 0.5:
                uncertainties.append(
                    "A vaga solicita 1+ ano de experiência; perfil possui fração relevante na área-alvo e requer análise."
                )
                return ("potential", inclusions, exclusions, uncertainties)
            if min_years == 2 and relevant_target_years >= 1.5:
                uncertainties.append(
                    "A vaga solicita 2+ anos de experiência; perfil possui experiência relevante próxima e requer avaliação."
                )
                return ("potential", inclusions, exclusions, uncertainties)
            exclusions.append(
                f"Requisito obrigatório de {min_years}+ {unit} de experiência excede o tempo confirmado no cargo-alvo."
            )
            return ("incompatible", inclusions, exclusions, uncertainties)

        # Experiência profissional qualitativa obrigatória (sem contagem explícita de anos)
        uncertainties.append(
            "A vaga exige experiência profissional prévia (sem contagem mínima de anos); validar aderência antes da candidatura."
        )
        return ("potential", inclusions, exclusions, uncertainties)

    if exp_mode == ExperienceRequirementMode.PREFERRED.value:
        if preferred_years is not None:
            unit_p = "ano" if preferred_years == 1 else "anos"
            pref_note = f"Experiência indicada apenas como desejável ({preferred_years}+ {unit_p}), não obrigatória."
        else:
            pref_note = "Experiência citada apenas como desejável ou diferencial."
        inclusions.append(pref_note)
        return ("compatible", inclusions, exclusions, uncertainties)

    # Experience not specified
    if seniority_level in {
        SeniorityLevel.INTERNSHIP.value,
        SeniorityLevel.ENTRY_LEVEL.value,
        SeniorityLevel.JUNIOR.value,
    }:
        inclusions.append(
            "Nível de entrada compatível e sem exigência numérica de experiência prévia."
        )
        return ("compatible", inclusions, exclusions, uncertainties)

    uncertainties.append(
        "Tempo de experiência exigido não foi informado explicitamente pela vaga."
    )
    return ("unknown", inclusions, exclusions, uncertainties)


def evaluate_opportunity_for_user(
    opportunity: Opportunity,
    profile: ProfessionalProfile,
    *,
    target_category: str | None = None,
    skills: Sequence[Skill] | None = None,
    experiences: Sequence[WorkExperience] | None = None,
    educations: Sequence[Education] | None = None,
    projects: Sequence[ProfessionalProject] | None = None,
) -> OpportunityMatchEvaluation:
    """
    Avalia compatibilidade de forma 100% determinística e explicável considerando seis
    dimensões independentes: área profissional, geografia, contrato, senioridade,
    requisitos de experiência e compatibilidade técnica com as habilidades do candidato.
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

    (
        seniority_level,
        exp_mode,
        exp_min_years,
        exp_pref_years,
        _exp_summary,
        required_techs_tuple,
        desirable_techs_tuple,
    ) = resolve_opportunity_seniority_and_experience(opportunity)

    category = target_category
    if category is None:
        if seniority_level == SeniorityLevel.INTERNSHIP.value:
            category = OpportunityType.INTERNSHIP.value
        elif seniority_level in {
            SeniorityLevel.JUNIOR.value,
            SeniorityLevel.ENTRY_LEVEL.value,
        }:
            category = OpportunityType.JUNIOR.value
        elif opportunity.employment_type == EmploymentType.FREELANCE.value:
            category = OpportunityType.FREELANCE.value
        elif opportunity.opportunity_type in {
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

    # 3. Contrato e bloqueio CLT
    contract_compatibility = "unknown"
    if opportunity.employment_type == EmploymentType.UNKNOWN.value:
        uncertainty_notes.append("Tipo de contrato não informado pela fonte original.")
    elif category == OpportunityType.JUNIOR.value:
        jr_prefs = prefs["junior_developer"]
        contract_blocked = False
        if jr_prefs.get("block_clt", False) and (
            opportunity.employment_type == EmploymentType.CLT.value
        ):
            exclusions.append(
                "Regra block_clt ativa: oportunidades classificadas como CLT são excluídas."
            )
            contract_blocked = True

        accepted = jr_prefs.get("accepted_contract_types") or []
        if accepted:
            normalized_accepted = {_normalize_contract_label(item) for item in accepted}
            if opportunity.employment_type not in normalized_accepted:
                exclusions.append(
                    f"Contrato '{opportunity.employment_type}' fora das modalidades aceitas ({', '.join(accepted)})."
                )
                contract_blocked = True
            elif not contract_blocked:
                inclusions.append(
                    f"Modalidade contratual aceita ({opportunity.employment_type})."
                )
        contract_compatibility = "incompatible" if contract_blocked else "compatible"
    else:
        if (
            prefs["junior_developer"].get("block_clt", False)
            and opportunity.employment_type == EmploymentType.CLT.value
        ):
            exclusions.append(
                "Regra block_clt ativa: oportunidades classificadas como CLT são excluídas."
            )
            contract_compatibility = "incompatible"
        else:
            inclusions.append(f"Contrato informado: {opportunity.employment_type}.")
            contract_compatibility = "compatible"

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

    if opportunity.employment_type == EmploymentType.FREELANCE.value or category == OpportunityType.FREELANCE.value:
        scopes = [s.lower() for s in (prefs["freelance"].get("scopes") or [])]
        if not prefs["freelance"].get("enabled", True):
            exclusions.append("Categoria Freelancers desabilitada nas preferências do usuário.")
        elif scopes and geo_status == "eligible":
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

    # 7. Senioridade, Experiência e Habilidades Técnicas do Candidato
    (
        confirmed_target_years,
        _total_work_years,
        ceiling_rank,
        candidate_tokens,
        _has_student_status,
        has_explicit_skills,
        _has_practical_projects,
    ) = _estimate_candidate_profile_stage(
        profile, prefs, skills, experiences, educations, projects
    )

    seniority_compat, sen_inc, sen_exc, sen_unc = _evaluate_seniority_dimension(
        seniority_level, ceiling_rank, confirmed_target_years, prefs
    )
    inclusions.extend(sen_inc)
    exclusions.extend(sen_exc)
    uncertainty_notes.extend(sen_unc)

    exp_compat, exp_inc, exp_exc, exp_unc = _evaluate_experience_dimension(
        exp_mode,
        exp_min_years,
        exp_pref_years,
        seniority_level,
        confirmed_target_years,
    )
    inclusions.extend(exp_inc)
    exclusions.extend(exp_exc)
    uncertainty_notes.extend(exp_unc)

    # 8. Tecnologias prioritárias (preferências) separadas de requisitos obrigatórios (requisitos da vaga)
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

    required_techs = list(required_techs_tuple)
    desirable_techs = list(desirable_techs_tuple)
    matched_required: list[str] = []
    missing_required: list[str] = []

    if required_techs:
        for req_tech in required_techs:
            if _skill_matches_tech(req_tech, candidate_tokens):
                matched_required.append(req_tech)
            else:
                missing_required.append(req_tech)

    matched_skills: list[str] = list(matched_required)
    for tag in list(opportunity.technologies or []) + desirable_techs:
        if _skill_matches_tech(tag, candidate_tokens) and tag not in matched_skills:
            matched_skills.append(tag)

    technical_compatibility = "unknown"
    if area_compatibility == "incompatible":
        technical_compatibility = "incompatible"
    elif required_techs:
        if not candidate_tokens and not has_explicit_skills:
            technical_compatibility = "unknown"
            uncertainty_notes.append(
                f"A vaga exige {', '.join(required_techs[:4])}; preencha habilidades no perfil para validar aderência técnica."
            )
        elif not missing_required:
            technical_compatibility = "compatible"
            inclusions.append(
                f"Requisitos técnicos obrigatórios atendidos pelo perfil: {', '.join(matched_required[:5])}."
            )
        elif len(matched_required) == 0 or (len(matched_required) < len(required_techs) / 2):
            technical_compatibility = "incompatible"
            exclusions.append(
                f"Requisito técnico obrigatório não identificado no perfil: {', '.join(missing_required[:5])}."
            )
        else:
            technical_compatibility = "potential"
            uncertainty_notes.append(
                f"Atende parcialmente aos requisitos obrigatórios; revisar: {', '.join(missing_required[:4])}."
            )
    else:
        # Sem requisitos técnicos obrigatórios extraídos da descrição: tags nunca viram bloqueio
        if matched_skills or matched_priorities:
            technical_compatibility = "compatible"
        elif opportunity.technologies:
            technical_compatibility = "potential"
            uncertainty_notes.append(
                "Sem requisito técnico obrigatório explícito; validar afinidade com as tecnologias listadas."
            )
        else:
            technical_compatibility = "unknown"

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

    # 9. Consolidação das 6 dimensões em overall_compatibility e eligible
    has_hard_exclusion = (
        len(exclusions) > 0
        or area_compatibility != "compatible"
        or seniority_compat == "incompatible"
        or exp_compat == "incompatible"
        or technical_compatibility == "incompatible"
        or contract_compatibility == "incompatible"
        or geo_status == "excluded"
    )
    has_uncertainty_or_potential = (
        geo_status == "unknown"
        or seniority_compat in {"potential", "unknown"}
        or exp_compat in {"potential", "unknown"}
        or technical_compatibility in {"potential", "unknown"}
        or contract_compatibility == "unknown"
        or opp_status in {"unknown", "unconfirmed", "source_unavailable"}
    )

    if has_hard_exclusion:
        overall_compatibility = "incompatible"
        eligible = False
    elif has_uncertainty_or_potential:
        overall_compatibility = "potential"
        eligible = True
    else:
        overall_compatibility = "compatible"
        eligible = True

    return OpportunityMatchEvaluation(
        eligible=eligible,
        overall_compatibility=overall_compatibility,
        geographic_eligibility=geo_status,
        area_compatibility=area_compatibility,
        contract_compatibility=contract_compatibility,
        seniority_compatibility=seniority_compat,
        experience_compatibility=exp_compat,
        technical_compatibility=technical_compatibility,
        matched_areas=matched_areas,
        matched_technologies=matched_priorities if area_compatibility == "compatible" else [],
        matched_skills=matched_skills if area_compatibility == "compatible" else [],
        required_technologies=required_techs,
        missing_required_technologies=missing_required,
        desirable_technologies=desirable_techs,
        missing_priority_technologies=missing_priorities[:5] if not matched_priorities else [],
        uncertainty_notes=list(dict.fromkeys(uncertainty_notes)),
        inclusion_reasons=list(dict.fromkeys(inclusions)),
        exclusion_reasons=list(dict.fromkeys(exclusions)),
    )

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from app.models.profile import (
    Education,
    EducationStatus,
    ExperienceType,
    Language,
    LanguageProficiency,
    ProfessionalProfile,
    ProfessionalProject,
    Skill,
    SkillProficiency,
    WorkExperience,
)
from app.schemas.material import (
    ContactInclusionOptions,
    ResumeEducationItem,
    ResumeExperienceItem,
    ResumeHeaderSection,
    ResumeLanguageItem,
    ResumeLinkItem,
    ResumeManualNoteItem,
    ResumeProjectItem,
    ResumeSkillItem,
    ResumeStructuredContent,
    ResumeSummarySection,
    ResumeTargetAlignmentSection,
    TargetLanguage,
)
from app.services.materials.fact_selector import AuthorizedFactBundle
from app.services.opportunities.sanitization import (
    sanitize_external_html_text,
    sanitize_plain_text,
    validate_safe_external_url,
)

_EDUCATION_STATUS_LABELS: dict[str, dict[str, str]] = {
    EducationStatus.IN_PROGRESS.value: {"pt-BR": "Em andamento", "en": "In Progress"},
    EducationStatus.COMPLETED.value: {"pt-BR": "Concluído", "en": "Completed"},
    EducationStatus.PAUSED.value: {"pt-BR": "Trancado / Pausado", "en": "Paused"},
    EducationStatus.PLANNED.value: {"pt-BR": "Planejado", "en": "Planned"},
}

_SKILL_PROFICIENCY_LABELS: dict[str, dict[str, str]] = {
    SkillProficiency.EXPERT.value: {"pt-BR": "Especialista", "en": "Expert"},
    SkillProficiency.ADVANCED.value: {"pt-BR": "Avançado", "en": "Advanced"},
    SkillProficiency.INTERMEDIATE.value: {"pt-BR": "Intermediário", "en": "Intermediate"},
    SkillProficiency.BASIC.value: {"pt-BR": "Básico", "en": "Basic"},
    SkillProficiency.BEGINNER.value: {"pt-BR": "Iniciante", "en": "Beginner"},
}

_LANGUAGE_PROFICIENCY_LABELS: dict[str, dict[str, str]] = {
    LanguageProficiency.NATIVE.value: {"pt-BR": "Nativo", "en": "Native"},
    LanguageProficiency.FLUENT.value: {"pt-BR": "Fluente", "en": "Fluent"},
    LanguageProficiency.ADVANCED.value: {"pt-BR": "Avançado", "en": "Advanced"},
    LanguageProficiency.INTERMEDIATE.value: {"pt-BR": "Intermediário", "en": "Intermediate"},
    LanguageProficiency.BASIC.value: {"pt-BR": "Básico", "en": "Basic"},
}

_EXPERIENCE_TYPE_LABELS: dict[str, dict[str, str]] = {
    ExperienceType.INTERNSHIP.value: {"pt-BR": "Estágio", "en": "Internship"},
    ExperienceType.JUNIOR.value: {"pt-BR": "Desenvolvedor Júnior", "en": "Junior Role"},
    ExperienceType.FREELANCE.value: {"pt-BR": "Freelance", "en": "Freelance"},
    ExperienceType.PJ.value: {"pt-BR": "Pessoa Jurídica (PJ)", "en": "Contractor (PJ)"},
    ExperienceType.CLT.value: {"pt-BR": "CLT", "en": "Full-time (CLT)"},
    ExperienceType.ACADEMIC.value: {"pt-BR": "Projeto / Pesquisa Acadêmica", "en": "Academic"},
    ExperienceType.OTHER.value: {"pt-BR": "Outra Atuação", "en": "Other Experience"},
}


def _format_period(
    start_date: Any,
    end_date: Any,
    is_current: bool,
    language: TargetLanguage,
) -> str | None:
    start_str = start_date.strftime("%m/%Y") if start_date else None
    if is_current:
        end_str = "Present" if language == "en" else "Atual"
    elif end_date:
        end_str = end_date.strftime("%m/%Y")
    else:
        end_str = None

    if start_str and end_str:
        return f"{start_str} – {end_str}"
    return start_str or end_str


def _safe_link(label: str, raw_url: str | None) -> ResumeLinkItem | None:
    if not raw_url or not raw_url.strip():
        return None
    try:
        safe_url = validate_safe_external_url(raw_url, allow_localhost=False)
    except ValueError:
        return None
    return ResumeLinkItem(label=label, url=safe_url)


def _build_header(
    profile: ProfessionalProfile | None,
    contact_options: ContactInclusionOptions,
    contact_location_label: str | None,
) -> ResumeHeaderSection:
    if profile is None:
        return ResumeHeaderSection(
            full_name=None,
            professional_title=None,
            location_text=None,
            email=None,
            phone=None,
            links=[],
            source_fact_keys=[],
            provenance="confirmed_fact",
        )

    links: list[ResumeLinkItem] = []
    if contact_options.include_links:
        for label, raw_url in [
            ("LinkedIn", profile.linkedin_url),
            ("GitHub", profile.github_url),
            ("Portfolio", profile.portfolio_url),
        ]:
            item = _safe_link(label, raw_url)
            if item is not None:
                links.append(item)

    return ResumeHeaderSection(
        full_name=sanitize_plain_text(profile.full_name, max_length=200),
        professional_title=sanitize_plain_text(profile.professional_title, max_length=200),
        location_text=contact_location_label if contact_options.include_location else None,
        email=sanitize_plain_text(profile.professional_email, max_length=255)
        if contact_options.include_email
        else None,
        phone=sanitize_plain_text(profile.phone, max_length=50)
        if contact_options.include_phone
        else None,
        links=links,
        source_fact_keys=[f"profile:{profile.id}"],
        provenance="confirmed_fact",
    )


def _build_summary(
    bundle: AuthorizedFactBundle,
    language: TargetLanguage,
) -> ResumeSummarySection | None:
    source_keys: list[str] = []
    clauses: list[str] = []

    profile = bundle.profile
    if profile is not None:
        source_keys.append(f"profile:{profile.id}")
        if profile.professional_summary and profile.professional_summary.strip():
            cleaned_summary = sanitize_external_html_text(
                profile.professional_summary, max_length=1500
            )
            if cleaned_summary:
                clauses.append(cleaned_summary)
        else:
            title_or_obj = sanitize_plain_text(
                profile.professional_title,
                max_length=250,
            )
            if title_or_obj:
                if language == "en":
                    clauses.append(f"Profile focus: {title_or_obj}.")
                else:
                    clauses.append(f"Atuação e objetivo profissional: {title_or_obj}.")

    # Complemento determinístico curto apenas quando não houver resumo completo ou para alinhar evidências confirmadas
    matched_skills: list[str] = []
    for skill in bundle.skills:
        fact_key = f"skill:{skill.id}"
        if bundle.matched_req_map.get(fact_key):
            matched_skills.append(skill.name)
            source_keys.append(fact_key)
    top_skills = matched_skills[:6] if matched_skills else [s.name for s in bundle.skills[:6]]
    if not matched_skills:
        for skill in bundle.skills[:6]:
            source_keys.append(f"skill:{skill.id}")

    if top_skills and not clauses:
        skills_joined = ", ".join(top_skills)
        if language == "en":
            clauses.append(f"Confirmed technical skills: {skills_joined}.")
        else:
            clauses.append(f"Competências técnicas confirmadas: {skills_joined}.")

    if not clauses and bundle.educations:
        edu = bundle.educations[0]
        source_keys.append(f"education:{edu.id}")
        status_label = _EDUCATION_STATUS_LABELS.get(edu.education_status, {}).get(
            language, edu.education_status
        )
        if language == "en":
            clauses.append(f"Academic background in {edu.course} ({edu.institution} — {status_label}).")
        else:
            clauses.append(f"Formação em {edu.course} ({edu.institution} — {status_label}).")

    if not clauses and bundle.experiences:
        exp = bundle.experiences[0]
        source_keys.append(f"experience:{exp.id}")
        if language == "en":
            clauses.append(f"Experience as {exp.role} at {exp.company}.")
        else:
            clauses.append(f"Experiência como {exp.role} em {exp.company}.")

    if not clauses and bundle.projects:
        proj = bundle.projects[0]
        source_keys.append(f"project:{proj.id}")
        if language == "en":
            clauses.append(f"Confirmed practical work including project {proj.name}.")
        else:
            clauses.append(f"Atuação prática comprovada no projeto {proj.name}.")

    if not clauses:
        return None

    dedup_keys = list(dict.fromkeys(source_keys))[:50]
    text_joined = " ".join(clauses).strip()
    return ResumeSummarySection(
        text=text_joined[:3000],
        source_fact_keys=dedup_keys,
        provenance="confirmed_fact",
    )


def _build_target_alignment(
    bundle: AuthorizedFactBundle,
    language: TargetLanguage,
) -> ResumeTargetAlignmentSection | None:
    ctx = bundle.opportunity_context
    if not ctx.title and not ctx.all_technologies:
        return None

    confirmed_matched: list[str] = []
    source_keys: list[str] = []
    seen_req: set[str] = set()

    for fact_ref in bundle.used_facts:
        if fact_ref.matched_requirements:
            source_keys.append(fact_ref.fact_key)
            for req_name in fact_ref.matched_requirements:
                if req_name.lower() not in seen_req:
                    seen_req.add(req_name.lower())
                    confirmed_matched.append(req_name)

    has_target_exp = any(exp.eligible_as_target_role for exp in bundle.experiences)
    note_parts: list[str] = []
    if confirmed_matched:
        joined = ", ".join(confirmed_matched[:10])
        if language == "en":
            note_parts.append(f"Confirmed evidence aligned with requirements: {joined}.")
        else:
            note_parts.append(f"Evidências confirmadas aderentes aos requisitos: {joined}.")
    if not has_target_exp and bundle.projects:
        if language == "en":
            note_parts.append(
                "Supporting background built from confirmed projects, education, and technical skills."
            )
        else:
            note_parts.append(
                "Base sustentada por projetos, formação e competências técnicas confirmadas."
            )

    target_role = ctx.title or ("Target Role" if language == "en" else "Oportunidade-alvo")
    return ResumeTargetAlignmentSection(
        target_role=target_role,
        company_name=ctx.company_name,
        highlighted_requirements=confirmed_matched[:20],
        alignment_note=" ".join(note_parts) if note_parts else None,
        source_fact_keys=list(dict.fromkeys(source_keys))[:50],
        provenance="confirmed_fact",
    )


def _serialize_snapshot(
    bundle: AuthorizedFactBundle,
    language: TargetLanguage,
) -> dict[str, Any]:
    """Snapshot estrito sem email/telefone/endereço completo."""
    facts: dict[str, dict[str, Any]] = {}

    if bundle.profile is not None:
        p = bundle.profile
        facts[f"profile:{p.id}"] = {
            "entity_type": "profile",
            "entity_id": str(p.id),
            "confirmed_at": p.confirmed_at.isoformat() if p.confirmed_at else None,
            "full_name": sanitize_plain_text(p.full_name, max_length=200),
            "professional_title": sanitize_plain_text(p.professional_title, max_length=200),
            "city": sanitize_plain_text(p.city, max_length=120),
            "state": sanitize_plain_text(p.state, max_length=120),
            "country": sanitize_plain_text(p.country, max_length=120),
            "has_email": bool(p.professional_email),
            "has_phone": bool(p.phone),
            "links_count": sum(
                1 for u in [p.linkedin_url, p.github_url, p.portfolio_url] if u and u.strip()
            ),
        }

    for exp in bundle.experiences:
        facts[f"experience:{exp.id}"] = {
            "entity_type": "experience",
            "entity_id": str(exp.id),
            "confirmed_at": exp.confirmed_at.isoformat() if exp.confirmed_at else None,
            "company": exp.company,
            "role": exp.role,
            "experience_type": exp.experience_type,
            "eligible_as_target_role": exp.eligible_as_target_role,
            "period_label": _format_period(exp.start_date, exp.end_date, exp.is_current, language),
            "technologies": list(exp.technologies or [])[:30],
        }

    for proj in bundle.projects:
        facts[f"project:{proj.id}"] = {
            "entity_type": "project",
            "entity_id": str(proj.id),
            "confirmed_at": proj.confirmed_at.isoformat() if proj.confirmed_at else None,
            "name": proj.name,
            "role": proj.role,
            "technologies": list(proj.technologies or [])[:30],
            "has_verified_results": bool(proj.verified_results),
        }

    for edu in bundle.educations:
        facts[f"education:{edu.id}"] = {
            "entity_type": "education",
            "entity_id": str(edu.id),
            "confirmed_at": edu.confirmed_at.isoformat() if edu.confirmed_at else None,
            "institution": edu.institution,
            "course": edu.course,
            "education_status": edu.education_status,
            "current_semester": edu.current_semester,
        }

    for skill in bundle.skills:
        facts[f"skill:{skill.id}"] = {
            "entity_type": "skill",
            "entity_id": str(skill.id),
            "confirmed_at": skill.confirmed_at.isoformat() if skill.confirmed_at else None,
            "name": skill.name,
            "category": skill.category,
            "proficiency_level": skill.proficiency_level,
        }

    for lang in bundle.languages:
        facts[f"language:{lang.id}"] = {
            "entity_type": "language",
            "entity_id": str(lang.id),
            "confirmed_at": lang.confirmed_at.isoformat() if lang.confirmed_at else None,
            "language_name": lang.language_name,
            "proficiency_level": lang.proficiency_level,
            "cefr_level": lang.cefr_level,
        }

    return {
        "schema_version": 1,
        "captured_at": datetime.now(UTC).isoformat(),
        "opportunity_context": bundle.opportunity_context.model_dump(mode="json"),
        "facts": facts,
    }


def compose_deterministic_resume(
    bundle: AuthorizedFactBundle,
    *,
    target_language: TargetLanguage,
    contact_options: ContactInclusionOptions,
    user_instructions: str | None = None,
) -> tuple[ResumeStructuredContent, dict[str, Any]]:
    """Compõe currículo estruturado exclusivamente com fatos confirmados."""
    if not bundle.can_generate:
        raise ValueError(
            "; ".join(bundle.blocking_reasons)
            or "Não há fatos substantivos confirmados suficientes para gerar currículo."
        )

    header = _build_header(
        bundle.profile,
        contact_options,
        bundle.contact_preview.location_label,
    )
    summary = _build_summary(bundle, target_language)
    target_alignment = _build_target_alignment(bundle, target_language)

    experiences: list[ResumeExperienceItem] = []
    for exp in bundle.experiences:
        experiences.append(
            ResumeExperienceItem(
                entity_id=str(exp.id),
                company=exp.company,
                role=exp.role,
                period_label=_format_period(exp.start_date, exp.end_date, exp.is_current, target_language),
                description=exp.description,
                technologies=list(exp.technologies or [])[:30],
                experience_type=exp.experience_type,
                eligible_as_target_role=exp.eligible_as_target_role,
                source_fact_keys=[f"experience:{exp.id}"],
                provenance="confirmed_fact",
            )
        )

    projects: list[ResumeProjectItem] = []
    for proj in bundle.projects:
        proj_links: list[ResumeLinkItem] = []
        raw_links = proj.links if isinstance(proj.links, dict) else {}
        for link_label, raw_url in raw_links.items():
            clean_label = sanitize_plain_text(str(link_label), max_length=60) or "Link"
            item = _safe_link(clean_label, str(raw_url) if raw_url else None)
            if item is not None:
                proj_links.append(item)

        projects.append(
            ResumeProjectItem(
                entity_id=str(proj.id),
                name=proj.name,
                role=proj.role,
                description=proj.description,
                technologies=list(proj.technologies or [])[:30],
                links=proj_links,
                verified_results=proj.verified_results,
                source_fact_keys=[f"project:{proj.id}"],
                provenance="confirmed_fact",
            )
        )

    educations: list[ResumeEducationItem] = []
    for edu in bundle.educations:
        status_label = _EDUCATION_STATUS_LABELS.get(edu.education_status, {}).get(
            target_language, edu.education_status
        )
        educations.append(
            ResumeEducationItem(
                entity_id=str(edu.id),
                institution=edu.institution,
                course=edu.course,
                field_of_study=edu.field_of_study,
                education_status=edu.education_status,
                status_label=status_label,
                current_semester=edu.current_semester,
                period_label=_format_period(
                    edu.start_date,
                    edu.expected_graduation_date,
                    False,
                    target_language,
                ),
                source_fact_keys=[f"education:{edu.id}"],
                provenance="confirmed_fact",
            )
        )

    skills: list[ResumeSkillItem] = []
    for skill in bundle.skills:
        prof_label = _SKILL_PROFICIENCY_LABELS.get(skill.proficiency_level, {}).get(
            target_language, skill.proficiency_level
        )
        skills.append(
            ResumeSkillItem(
                entity_id=str(skill.id),
                name=skill.name,
                category=skill.category,
                proficiency_level=skill.proficiency_level,
                proficiency_label=prof_label,
                notes=skill.notes,
                source_fact_keys=[f"skill:{skill.id}"],
                provenance="confirmed_fact",
            )
        )

    languages: list[ResumeLanguageItem] = []
    for lang in bundle.languages:
        prof_label = _LANGUAGE_PROFICIENCY_LABELS.get(lang.proficiency_level, {}).get(
            target_language, lang.proficiency_level
        )
        languages.append(
            ResumeLanguageItem(
                entity_id=str(lang.id),
                language_name=lang.language_name,
                proficiency_level=lang.proficiency_level,
                proficiency_label=prof_label,
                cefr_level=lang.cefr_level,
                source_fact_keys=[f"language:{lang.id}"],
                provenance="confirmed_fact",
            )
        )

    # Instruções opcionais ficam registradas na versão sem inventar fatos nem contaminar seções confirmadas
    _ = user_instructions

    structured = ResumeStructuredContent(
        schema_version=1,
        language=target_language,
        header=header,
        summary=summary,
        target_alignment=target_alignment,
        experiences=experiences,
        projects=projects,
        education=educations,
        skills=skills,
        languages=languages,
        manual_notes=[],
        has_unverified_manual_edits=False,
    )
    snapshot = _serialize_snapshot(bundle, target_language)
    return structured, snapshot


def _validate_section_fact_keys(
    keys: list[str],
    expected_prefix: str,
    snapshot_facts: dict[str, Any],
) -> list[str]:
    for key in keys:
        if ":" in key and not key.startswith(f"{expected_prefix}:"):
            raise ValueError(
                f"Referência de fato inválida para esta seção ('{key}'); esperado prefixo '{expected_prefix}:'."
            )
    return [key for key in keys if key in snapshot_facts and key.startswith(f"{expected_prefix}:")]


def _reconcile_list_items(
    previous_items: list[Any],
    edited_items: list[Any],
    expected_prefix: str,
    snapshot_facts: dict[str, Any],
    comparable_fields: tuple[str, ...],
) -> list[Any]:
    prev_by_entity: dict[str, Any] = {}
    for item in previous_items:
        if item.entity_id:
            prev_by_entity[item.entity_id] = item

    reconciled: list[Any] = []
    for item in edited_items:
        valid_keys = _validate_section_fact_keys(item.source_fact_keys, expected_prefix, snapshot_facts)
        fact_key = f"{expected_prefix}:{item.entity_id}" if item.entity_id else None
        has_snapshot_backing = bool(fact_key and fact_key in snapshot_facts)

        if not has_snapshot_backing:
            reconciled.append(
                item.model_copy(
                    update={
                        "entity_id": None,
                        "source_fact_keys": [],
                        "provenance": "user_authored",
                    }
                )
            )
            continue

        prev_item = prev_by_entity.get(item.entity_id)
        if (
            prev_item is not None
            and prev_item.provenance == "confirmed_fact"
            and all(getattr(item, f) == getattr(prev_item, f) for f in comparable_fields)
        ):
            reconciled.append(
                item.model_copy(
                    update={
                        "source_fact_keys": valid_keys or [fact_key],
                        "provenance": "confirmed_fact",
                    }
                )
            )
        else:
            reconciled.append(
                item.model_copy(
                    update={
                        "source_fact_keys": valid_keys or [fact_key],
                        "provenance": "manual_edit",
                    }
                )
            )
    return reconciled


def reconcile_edited_structured_content(
    previous: ResumeStructuredContent,
    edited: ResumeStructuredContent,
    snapshot: dict[str, Any],
) -> ResumeStructuredContent:
    """Impede forja de proveniência confirmada e preserva separação estrita entre tipos de entidade."""
    snapshot_facts: dict[str, Any] = dict(snapshot.get("facts") or {})

    # Header
    header_keys = _validate_section_fact_keys(
        edited.header.source_fact_keys, "profile", snapshot_facts
    )
    prev_header_fields = (
        previous.header.full_name,
        previous.header.professional_title,
        previous.header.location_text,
        previous.header.email,
        previous.header.phone,
        [l.model_dump() for l in previous.header.links],
    )
    new_header_fields = (
        edited.header.full_name,
        edited.header.professional_title,
        edited.header.location_text,
        edited.header.email,
        edited.header.phone,
        [l.model_dump() for l in edited.header.links],
    )
    if (
        previous.header.provenance == "confirmed_fact"
        and previous.header.source_fact_keys
        and all(k in snapshot_facts for k in previous.header.source_fact_keys)
        and new_header_fields == prev_header_fields
    ):
        reconciled_header = edited.header.model_copy(
            update={"source_fact_keys": previous.header.source_fact_keys, "provenance": "confirmed_fact"}
        )
    elif header_keys:
        reconciled_header = edited.header.model_copy(
            update={"source_fact_keys": header_keys, "provenance": "manual_edit"}
        )
    else:
        reconciled_header = edited.header.model_copy(
            update={"source_fact_keys": [], "provenance": "user_authored"}
        )

    # Summary
    reconciled_summary: ResumeSummarySection | None = None
    if edited.summary is not None:
        valid_sum_keys = [k for k in edited.summary.source_fact_keys if k in snapshot_facts]
        if (
            previous.summary is not None
            and previous.summary.provenance == "confirmed_fact"
            and edited.summary.text == previous.summary.text
            and previous.summary.source_fact_keys
        ):
            reconciled_summary = edited.summary.model_copy(
                update={
                    "source_fact_keys": previous.summary.source_fact_keys,
                    "provenance": "confirmed_fact",
                }
            )
        elif valid_sum_keys:
            reconciled_summary = edited.summary.model_copy(
                update={"source_fact_keys": valid_sum_keys, "provenance": "manual_edit"}
            )
        else:
            reconciled_summary = edited.summary.model_copy(
                update={"source_fact_keys": [], "provenance": "user_authored"}
            )

    # Target alignment
    reconciled_alignment: ResumeTargetAlignmentSection | None = None
    if edited.target_alignment is not None:
        valid_align_keys = [k for k in edited.target_alignment.source_fact_keys if k in snapshot_facts]
        if (
            previous.target_alignment is not None
            and previous.target_alignment.provenance == "confirmed_fact"
            and (
                edited.target_alignment.target_role,
                edited.target_alignment.company_name,
                edited.target_alignment.highlighted_requirements,
                edited.target_alignment.alignment_note,
            )
            == (
                previous.target_alignment.target_role,
                previous.target_alignment.company_name,
                previous.target_alignment.highlighted_requirements,
                previous.target_alignment.alignment_note,
            )
        ):
            reconciled_alignment = edited.target_alignment.model_copy(
                update={
                    "source_fact_keys": previous.target_alignment.source_fact_keys,
                    "provenance": "confirmed_fact",
                }
            )
        else:
            reconciled_alignment = edited.target_alignment.model_copy(
                update={
                    "source_fact_keys": valid_align_keys,
                    "provenance": "manual_edit" if valid_align_keys else "user_authored",
                }
            )

    reconciled_experiences = _reconcile_list_items(
        previous.experiences,
        edited.experiences,
        "experience",
        snapshot_facts,
        ("company", "role", "period_label", "description", "technologies", "experience_type", "eligible_as_target_role"),
    )
    reconciled_projects = _reconcile_list_items(
        previous.projects,
        edited.projects,
        "project",
        snapshot_facts,
        ("name", "role", "description", "technologies", "links", "verified_results"),
    )
    reconciled_educations = _reconcile_list_items(
        previous.education,
        edited.education,
        "education",
        snapshot_facts,
        ("institution", "course", "field_of_study", "education_status", "status_label", "current_semester", "period_label"),
    )
    reconciled_skills = _reconcile_list_items(
        previous.skills,
        edited.skills,
        "skill",
        snapshot_facts,
        ("name", "category", "proficiency_level", "proficiency_label", "notes"),
    )
    reconciled_languages = _reconcile_list_items(
        previous.languages,
        edited.languages,
        "language",
        snapshot_facts,
        ("language_name", "proficiency_level", "proficiency_label", "cefr_level"),
    )

    reconciled_notes: list[ResumeManualNoteItem] = []
    for note in edited.manual_notes:
        reconciled_notes.append(
            note.model_copy(
                update={
                    "id": note.id or str(uuid.uuid4()),
                    "source_fact_keys": [],
                    "provenance": "user_authored",
                }
            )
        )

    has_manual_edits = any(
        [
            reconciled_header.provenance != "confirmed_fact",
            reconciled_summary is not None and reconciled_summary.provenance != "confirmed_fact",
            reconciled_alignment is not None and reconciled_alignment.provenance != "confirmed_fact",
            any(item.provenance != "confirmed_fact" for item in reconciled_experiences),
            any(item.provenance != "confirmed_fact" for item in reconciled_projects),
            any(item.provenance != "confirmed_fact" for item in reconciled_educations),
            any(item.provenance != "confirmed_fact" for item in reconciled_skills),
            any(item.provenance != "confirmed_fact" for item in reconciled_languages),
            len(reconciled_notes) > 0,
        ]
    )

    return ResumeStructuredContent(
        schema_version=1,
        language=edited.language,
        header=reconciled_header,
        summary=reconciled_summary,
        target_alignment=reconciled_alignment,
        experiences=reconciled_experiences,
        projects=reconciled_projects,
        education=reconciled_educations,
        skills=reconciled_skills,
        languages=reconciled_languages,
        manual_notes=reconciled_notes,
        has_unverified_manual_edits=has_manual_edits,
    )


def render_material_markdown(
    content: ResumeStructuredContent,
    language: TargetLanguage | None = None,
) -> str:
    """Renderiza Markdown limpo e determinístico exclusivamente a partir de structured_content."""
    lang: TargetLanguage = language or content.language
    lines: list[str] = []

    h = content.header
    heading_name = h.full_name or ("Candidate Resume" if lang == "en" else "Currículo Profissional")
    lines.append(f"# {heading_name}")
    if h.professional_title:
        lines.append(f"**{h.professional_title}**")

    contact_parts: list[str] = []
    if h.location_text:
        contact_parts.append(h.location_text)
    if h.email:
        contact_parts.append(h.email)
    if h.phone:
        contact_parts.append(h.phone)
    for link in h.links:
        contact_parts.append(f"[{link.label}]({link.url})")
    if contact_parts:
        lines.append(" | ".join(contact_parts))
    lines.append("")

    if content.target_alignment:
        ta = content.target_alignment
        lines.append(f"## {'Target Role' if lang == 'en' else 'Direcionamento para a Vaga'}")
        role_line = f"- **{ta.target_role}**"
        if ta.company_name:
            role_line += f" — {ta.company_name}"
        lines.append(role_line)
        if ta.highlighted_requirements:
            req_title = "Matched confirmed evidence" if lang == "en" else "Requisitos cobertos por fatos confirmados"
            lines.append(f"- {req_title}: {', '.join(ta.highlighted_requirements)}")
        if ta.alignment_note:
            lines.append(f"- {ta.alignment_note}")
        lines.append("")

    if content.summary:
        lines.append(f"## {'Professional Summary' if lang == 'en' else 'Resumo Profissional'}")
        lines.append(content.summary.text)
        lines.append("")

    if content.experiences:
        lines.append(f"## {'Professional Experience' if lang == 'en' else 'Experiência Profissional'}")
        for exp in content.experiences:
            exp_type_lbl = _EXPERIENCE_TYPE_LABELS.get(exp.experience_type, {}).get(
                lang, exp.experience_type
            )
            header_line = f"### {exp.role} — {exp.company}"
            lines.append(header_line)
            meta_parts = [p for p in [exp.period_label, exp_type_lbl] if p]
            if meta_parts:
                lines.append(f"*{' · '.join(meta_parts)}*")
            if exp.description:
                lines.append(exp.description)
            if exp.technologies:
                tech_lbl = "Technologies" if lang == "en" else "Tecnologias"
                lines.append(f"- **{tech_lbl}:** {', '.join(exp.technologies)}")
            lines.append("")

    if content.projects:
        lines.append(f"## {'Projects' if lang == 'en' else 'Projetos'}")
        for proj in content.projects:
            title = f"### {proj.name}"
            if proj.role:
                title += f" ({proj.role})"
            lines.append(title)
            if proj.description:
                lines.append(proj.description)
            if proj.verified_results:
                res_lbl = "Verified results" if lang == "en" else "Resultados verificados"
                lines.append(f"- **{res_lbl}:** {proj.verified_results}")
            if proj.technologies:
                tech_lbl = "Technologies" if lang == "en" else "Tecnologias"
                lines.append(f"- **{tech_lbl}:** {', '.join(proj.technologies)}")
            if proj.links:
                link_strs = [f"[{lk.label}]({lk.url})" for lk in proj.links]
                lines.append(f"- **Links:** {' · '.join(link_strs)}")
            lines.append("")

    if content.education:
        lines.append(f"## {'Education' if lang == 'en' else 'Formação Acadêmica'}")
        for edu in content.education:
            title = f"- **{edu.course}** — {edu.institution} ({edu.status_label})"
            extras = [p for p in [edu.current_semester, edu.period_label, edu.field_of_study] if p]
            if extras:
                title += f" · {' · '.join(extras)}"
            lines.append(title)
        lines.append("")

    if content.skills:
        lines.append(f"## {'Technical Skills' if lang == 'en' else 'Habilidades Técnicas'}")
        grouped: dict[str, list[ResumeSkillItem]] = {}
        for skill in content.skills:
            grouped.setdefault(skill.category, []).append(skill)
        for category, items in grouped.items():
            formatted = ", ".join(f"{it.name} ({it.proficiency_label})" for it in items)
            lines.append(f"- **{category}:** {formatted}")
        lines.append("")

    if content.languages:
        lines.append(f"## {'Languages' if lang == 'en' else 'Idiomas'}")
        for lang_item in content.languages:
            cefr = f" · {lang_item.cefr_level}" if lang_item.cefr_level else ""
            lines.append(f"- **{lang_item.language_name}:** {lang_item.proficiency_label}{cefr}")
        lines.append("")

    if content.manual_notes:
        lines.append(f"## {'Additional Notes' if lang == 'en' else 'Notas Adicionais'}")
        for note in content.manual_notes:
            lines.append(f"### {note.title}")
            lines.append(note.content)
            lines.append("")

    return "\n".join(lines).strip() + "\n"


def render_material_plain_text(
    content: ResumeStructuredContent,
    language: TargetLanguage | None = None,
) -> str:
    """Renderiza texto simples limpo a partir do structured_content."""
    markdown = render_material_markdown(content, language=language)
    plain_lines: list[str] = []
    for raw_line in markdown.splitlines():
        line = raw_line.lstrip("# ").replace("**", "")
        if line.startswith("*") and line.endswith("*") and len(line) > 2:
            line = line[1:-1]
        plain_lines.append(line)
    return "\n".join(plain_lines).strip() + "\n"

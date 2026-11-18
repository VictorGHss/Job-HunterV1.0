from __future__ import annotations

import re
import uuid
from typing import Any

from app.models.profile import EducationStatus, LanguageProficiency, SkillProficiency
from app.schemas.material import (
    BlockProvenance,
    ContactInclusionOptions,
    MaterialTypeValue,
    OpportunityContextInfo,
    PendingUserInputField,
    ResumeHeaderSection,
    ResumeManualNoteItem,
    TargetLanguage,
    WritingEvidenceBlock,
    WritingTextBlock,
)
from app.services.materials.fact_selector import AuthorizedFactBundle
from app.services.materials.resume_composer import (
    _build_header,
    _format_period,
    _serialize_snapshot,
)
from app.services.opportunities.sanitization import sanitize_plain_text

_MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")

EDUCATION_STATUS_PROSE: dict[str, dict[str, str]] = {
    EducationStatus.IN_PROGRESS.value: {"pt-BR": "em andamento", "en": "in progress"},
    EducationStatus.COMPLETED.value: {"pt-BR": "concluída", "en": "completed"},
    EducationStatus.PAUSED.value: {"pt-BR": "pausada/trancada", "en": "paused"},
    EducationStatus.PLANNED.value: {"pt-BR": "planejada", "en": "planned"},
}

SKILL_LEVEL_PROSE: dict[str, dict[str, str]] = {
    SkillProficiency.EXPERT.value: {"pt-BR": "especialista", "en": "expert"},
    SkillProficiency.ADVANCED.value: {"pt-BR": "avançado", "en": "advanced"},
    SkillProficiency.INTERMEDIATE.value: {"pt-BR": "intermediário", "en": "intermediate"},
    SkillProficiency.BASIC.value: {"pt-BR": "básico", "en": "basic"},
    SkillProficiency.BEGINNER.value: {"pt-BR": "iniciante", "en": "beginner"},
}

LANGUAGE_LEVEL_PROSE: dict[str, dict[str, str]] = {
    LanguageProficiency.NATIVE.value: {"pt-BR": "nativo", "en": "native"},
    LanguageProficiency.FLUENT.value: {"pt-BR": "fluente", "en": "fluent"},
    LanguageProficiency.ADVANCED.value: {"pt-BR": "avançado", "en": "advanced"},
    LanguageProficiency.INTERMEDIATE.value: {"pt-BR": "intermediário", "en": "intermediate"},
    LanguageProficiency.BASIC.value: {"pt-BR": "básico", "en": "basic"},
}


def determine_compatible_material_types(
    ctx: OpportunityContextInfo,
) -> list[MaterialTypeValue]:
    """Ordena e prioriza os tipos de material mais adequados ao contexto da vaga."""
    is_freelance = (
        ctx.employment_type == "freelance" or ctx.opportunity_type == "freelance"
    )
    if is_freelance:
        return [
            "freelance_proposal",
            "resume",
            "recruiter_message",
            "cover_letter",
            "application_answers",
        ]
    return [
        "resume",
        "cover_letter",
        "recruiter_message",
        "application_answers",
    ]


def build_snapshot_for_bundle(
    bundle: AuthorizedFactBundle,
    target_language: TargetLanguage,
) -> dict[str, Any]:
    return _serialize_snapshot(bundle, target_language)


def build_controlled_header(
    bundle: AuthorizedFactBundle,
    contact_options: ContactInclusionOptions,
) -> ResumeHeaderSection:
    return _build_header(
        bundle.profile,
        contact_options,
        bundle.contact_preview.location_label,
    )


def collect_matched_skills(bundle: AuthorizedFactBundle) -> list[tuple[str, str]]:
    """Retorna [(skill_name, fact_key)] priorizando skills que dão match com a vaga."""
    matched: list[tuple[str, str]] = []
    others: list[tuple[str, str]] = []
    for sk in bundle.skills:
        fk = f"skill:{sk.id}"
        if bundle.matched_req_map.get(fk):
            matched.append((sk.name, fk))
        else:
            others.append((sk.name, fk))
    return matched + others


def format_evidence_blocks(
    bundle: AuthorizedFactBundle,
    language: TargetLanguage,
    *,
    max_items: int = 3,
    prefer_projects: bool = False,
) -> tuple[list[WritingEvidenceBlock], list[str]]:
    """Seleciona experiências e projetos confirmados relevantes mantendo natureza distinta."""
    blocks: list[WritingEvidenceBlock] = []
    used_keys: list[str] = []

    exp_candidates = [
        (
            bundle.matched_req_map.get(f"experience:{exp.id}", []),
            exp,
        )
        for exp in bundle.experiences
    ]
    proj_candidates = [
        (
            bundle.matched_req_map.get(f"project:{proj.id}", []),
            proj,
        )
        for proj in bundle.projects
    ]

    def _add_project(matched: list[str], proj: Any) -> None:
        fk = f"project:{proj.id}"
        techs = ", ".join((proj.technologies or [])[:5])
        parts: list[str] = []
        if language == "en":
            header = f"Project {proj.name}"
            if proj.role:
                header += f" ({proj.role})"
            parts.append(header + ".")
            if proj.description:
                parts.append(proj.description.strip())
            if techs:
                parts.append(f"Confirmed technologies: {techs}.")
            if proj.verified_results:
                parts.append(f"Verified results: {proj.verified_results.strip()}")
        else:
            header = f"Projeto {proj.name}"
            if proj.role:
                header += f" ({proj.role})"
            parts.append(header + ".")
            if proj.description:
                parts.append(proj.description.strip())
            if techs:
                parts.append(f"Tecnologias confirmadas: {techs}.")
            if proj.verified_results:
                parts.append(f"Resultados verificados: {proj.verified_results.strip()}")

        blocks.append(
            WritingEvidenceBlock(
                entity_id=str(proj.id),
                entity_type="project",
                title=f"{proj.name}" + (f" — {proj.role}" if proj.role else ""),
                summary_text=" ".join(parts)[:3800],
                matched_requirements=list(matched),
                source_fact_keys=[fk],
                provenance="confirmed_fact",
            )
        )
        used_keys.append(fk)

    def _add_experience(matched: list[str], exp: Any) -> None:
        fk = f"experience:{exp.id}"
        period = _format_period(exp.start_date, exp.end_date, exp.is_current, language)
        techs = ", ".join((exp.technologies or [])[:5])
        parts: list[str] = []
        if language == "en":
            if exp.eligible_as_target_role:
                intro = f"Work experience as {exp.role} at {exp.company}"
            else:
                intro = f"Complementary work experience as {exp.role} at {exp.company}"
            if period:
                intro += f" ({period})"
            parts.append(intro + ".")
            if exp.description:
                parts.append(exp.description.strip())
            if techs:
                parts.append(f"Technologies used: {techs}.")
        else:
            if exp.eligible_as_target_role:
                intro = f"Experiência profissional como {exp.role} em {exp.company}"
            else:
                intro = f"Experiência profissional complementar como {exp.role} em {exp.company}"
            if period:
                intro += f" ({period})"
            parts.append(intro + ".")
            if exp.description:
                parts.append(exp.description.strip())
            if techs:
                parts.append(f"Tecnologias utilizadas: {techs}.")

        blocks.append(
            WritingEvidenceBlock(
                entity_id=str(exp.id),
                entity_type="experience",
                title=f"{exp.role} — {exp.company}" + (f" ({period})" if period else ""),
                summary_text=" ".join(parts)[:3800],
                matched_requirements=list(matched),
                source_fact_keys=[fk],
                provenance="confirmed_fact",
            )
        )
        used_keys.append(fk)

    if prefer_projects:
        for matched, proj in proj_candidates:
            if len(blocks) >= max_items:
                break
            _add_project(matched, proj)
        for matched, exp in exp_candidates:
            if len(blocks) >= max_items:
                break
            if matched or exp.eligible_as_target_role or len(blocks) == 0:
                _add_experience(matched, exp)
    else:
        # Prioriza experiências elegíveis ou com match, mas inclui projetos confirmados relevantes sem misturar
        eligible_exps = [row for row in exp_candidates if row[1].eligible_as_target_role or row[0]]
        secondary_exps = [row for row in exp_candidates if not (row[1].eligible_as_target_role or row[0])]
        for matched, exp in eligible_exps:
            if len(blocks) >= max_items:
                break
            _add_experience(matched, exp)
        for matched, proj in proj_candidates:
            if len(blocks) >= max_items:
                break
            _add_project(matched, proj)
        for matched, exp in secondary_exps:
            if len(blocks) >= max_items:
                break
            _add_experience(matched, exp)

    return blocks, list(dict.fromkeys(used_keys))


def education_prose_snippet(bundle: AuthorizedFactBundle, language: TargetLanguage) -> tuple[str | None, list[str]]:
    if not bundle.educations:
        return None, []
    edu = bundle.educations[0]
    status_word = EDUCATION_STATUS_PROSE.get(edu.education_status, {}).get(
        language, edu.education_status
    )
    sem = f" ({edu.current_semester})" if edu.current_semester else ""
    if language == "en":
        text = f"academic background in {edu.course} at {edu.institution} ({status_word}{sem})"
    else:
        text = f"formação acadêmica em {edu.course} na instituição {edu.institution} ({status_word}{sem})"
    return text, [f"education:{edu.id}"]


def languages_prose_snippet(bundle: AuthorizedFactBundle, language: TargetLanguage) -> tuple[str | None, list[str]]:
    if not bundle.languages:
        return None, []
    items: list[str] = []
    keys: list[str] = []
    for lang in bundle.languages[:4]:
        lvl = LANGUAGE_LEVEL_PROSE.get(lang.proficiency_level, {}).get(
            language, lang.proficiency_level
        )
        cefr = f"/{lang.cefr_level}" if lang.cefr_level else ""
        items.append(f"{lang.language_name} ({lvl}{cefr})")
        keys.append(f"language:{lang.id}")
    return ", ".join(items), keys


def safe_candidate_display_name(bundle: AuthorizedFactBundle) -> str | None:
    if bundle.profile and bundle.profile.full_name:
        return sanitize_plain_text(bundle.profile.full_name, max_length=150)
    return None


def validate_strict_fact_keys(
    keys: list[str],
    snapshot_facts: dict[str, Any],
    *,
    expected_prefix: str | None = None,
) -> list[str]:
    """Rejeita referências de origem inexistentes ou incompatíveis com o tipo de entidade."""
    cleaned: list[str] = []
    for key in keys:
        if expected_prefix and (":" not in key or not key.startswith(f"{expected_prefix}:")):
            raise ValueError(
                f"Referência de fato '{key}' incompatível; esperado prefixo '{expected_prefix}:'."
            )
        if key not in snapshot_facts:
            raise ValueError(
                f"Referência de fato inexistente ou não confirmada: '{key}'."
            )
        cleaned.append(key)
    return list(dict.fromkeys(cleaned))


def reconcile_writing_header(
    previous: ResumeHeaderSection,
    edited: ResumeHeaderSection,
    snapshot_facts: dict[str, Any],
) -> ResumeHeaderSection:
    valid_keys = validate_strict_fact_keys(
        edited.source_fact_keys,
        snapshot_facts,
        expected_prefix="profile",
    )
    prev_tuple = (
        previous.full_name,
        previous.professional_title,
        previous.location_text,
        previous.email,
        previous.phone,
        [lk.model_dump() for lk in previous.links],
    )
    new_tuple = (
        edited.full_name,
        edited.professional_title,
        edited.location_text,
        edited.email,
        edited.phone,
        [lk.model_dump() for lk in edited.links],
    )
    if (
        previous.provenance == "confirmed_fact"
        and previous.source_fact_keys
        and all(k in snapshot_facts for k in previous.source_fact_keys)
        and new_tuple == prev_tuple
    ):
        return edited.model_copy(
            update={"source_fact_keys": previous.source_fact_keys, "provenance": "confirmed_fact"}
        )
    if valid_keys:
        return edited.model_copy(
            update={"source_fact_keys": valid_keys, "provenance": "manual_edit"}
        )
    return edited.model_copy(update={"source_fact_keys": [], "provenance": "user_authored"})


def reconcile_text_block(
    previous: WritingTextBlock | None,
    edited: WritingTextBlock | None,
    snapshot_facts: dict[str, Any],
) -> WritingTextBlock | None:
    if edited is None:
        return None
    valid_keys = validate_strict_fact_keys(edited.source_fact_keys, snapshot_facts)
    if (
        previous is not None
        and previous.provenance == "confirmed_fact"
        and edited.text == previous.text
        and previous.source_fact_keys
        and all(k in snapshot_facts for k in previous.source_fact_keys)
    ):
        return edited.model_copy(
            update={
                "source_fact_keys": previous.source_fact_keys,
                "provenance": "confirmed_fact",
            }
        )
    provenance: BlockProvenance = "manual_edit" if valid_keys else "user_authored"
    return edited.model_copy(
        update={
            "source_fact_keys": valid_keys,
            "provenance": provenance,
        }
    )


def reconcile_evidence_blocks(
    previous_items: list[WritingEvidenceBlock],
    edited_items: list[WritingEvidenceBlock],
    snapshot_facts: dict[str, Any],
) -> list[WritingEvidenceBlock]:
    prev_by_entity: dict[str, WritingEvidenceBlock] = {
        item.entity_id: item for item in previous_items if item.entity_id
    }
    result: list[WritingEvidenceBlock] = []
    for item in edited_items:
        prefix = item.entity_type if item.entity_type else None
        valid_keys = validate_strict_fact_keys(
            item.source_fact_keys,
            snapshot_facts,
            expected_prefix=prefix,
        )
        expected_key = (
            f"{item.entity_type}:{item.entity_id}"
            if item.entity_id and item.entity_type
            else None
        )
        if expected_key and expected_key not in snapshot_facts:
            raise ValueError(
                f"Referência de fato inexistente ou não confirmada: '{expected_key}'."
            )

        has_snapshot = bool(expected_key and expected_key in snapshot_facts)
        if not has_snapshot:
            if valid_keys:
                raise ValueError(
                    "Bloco autoral sem entity_id não pode reivindicar referências de fato confirmado."
                )
            result.append(
                item.model_copy(
                    update={
                        "entity_id": None,
                        "source_fact_keys": [],
                        "provenance": "user_authored",
                    }
                )
            )
            continue

        prev = prev_by_entity.get(item.entity_id or "")
        if (
            prev is not None
            and prev.provenance == "confirmed_fact"
            and (
                item.title,
                item.summary_text,
                item.entity_type,
                item.matched_requirements,
            )
            == (
                prev.title,
                prev.summary_text,
                prev.entity_type,
                prev.matched_requirements,
            )
        ):
            result.append(
                item.model_copy(
                    update={
                        "source_fact_keys": valid_keys or [expected_key],
                        "provenance": "confirmed_fact",
                    }
                )
            )
        else:
            result.append(
                item.model_copy(
                    update={
                        "source_fact_keys": valid_keys or [expected_key],
                        "provenance": "manual_edit",
                    }
                )
            )
    return result


def reconcile_manual_notes(notes: list[ResumeManualNoteItem]) -> list[ResumeManualNoteItem]:
    return [
        note.model_copy(
            update={
                "id": note.id or str(uuid.uuid4()),
                "source_fact_keys": [],
                "provenance": "user_authored",
            }
        )
        for note in notes
    ]


def reconcile_pending_fields(
    previous_fields: list[PendingUserInputField],
    edited_fields: list[PendingUserInputField],
) -> list[PendingUserInputField]:
    """Preserva obrigatoriedade definida pelo servidor nos campos de sistema."""
    prev_required_map = {f.field_id: f.required for f in previous_fields}
    reconciled: list[PendingUserInputField] = []
    seen_ids: set[str] = set()
    for field in edited_fields:
        if field.field_id in seen_ids:
            continue
        seen_ids.add(field.field_id)
        required_flag = prev_required_map.get(field.field_id, field.required)
        has_val = bool(field.user_value and field.user_value.strip())
        reconciled.append(
            field.model_copy(
                update={
                    "required": required_flag,
                    "user_value": field.user_value.strip() if has_val else None,
                    "status": "provided" if has_val else "pending",
                }
            )
        )
    # Garante que nenhum campo obrigatório gerado pelo sistema seja deletado silenciosamente
    for prev_field in previous_fields:
        if prev_field.required and prev_field.field_id not in seen_ids:
            reconciled.append(prev_field)
    return reconciled


def markdown_to_plain_text(markdown: str) -> str:
    plain_lines: list[str] = []
    for raw_line in markdown.splitlines():
        line = _MARKDOWN_LINK_RE.sub(r"\1 (\2)", raw_line)
        line = line.lstrip("# ").replace("**", "")
        if line.startswith("*") and line.endswith("*") and len(line) > 2:
            line = line[1:-1]
        plain_lines.append(line)
    return "\n".join(plain_lines).strip() + "\n"

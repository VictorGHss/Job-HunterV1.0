from __future__ import annotations

from typing import Any

from app.schemas.material import (
    ContactInclusionOptions,
    RecruiterMessageStructuredContent,
    TargetLanguage,
    WritingGenerationOptions,
    WritingTextBlock,
)
from app.services.materials.fact_selector import AuthorizedFactBundle
from app.services.materials.writing_common import (
    build_controlled_header,
    build_snapshot_for_bundle,
    collect_matched_skills,
    format_evidence_blocks,
    markdown_to_plain_text,
    reconcile_manual_notes,
    reconcile_text_block,
    safe_candidate_display_name,
)


def _compute_char_count(content: RecruiterMessageStructuredContent) -> int:
    text = render_recruiter_message_plain_text(content, language=content.language).strip()
    return len(text)


def compose_recruiter_message(
    bundle: AuthorizedFactBundle,
    *,
    target_language: TargetLanguage,
    contact_options: ContactInclusionOptions,
    writing_options: WritingGenerationOptions | None = None,
    user_instructions: str | None = None,
) -> tuple[RecruiterMessageStructuredContent, dict[str, Any]]:
    """Compõe mensagem curta e direta para recrutador usando somente fatos confirmados."""
    if not bundle.can_generate:
        raise ValueError(
            "; ".join(bundle.blocking_reasons)
            or "Não há fatos substantivos confirmados suficientes para gerar a mensagem."
        )

    _ = user_instructions
    opts = writing_options or WritingGenerationOptions()
    header = build_controlled_header(bundle, contact_options)
    ctx = bundle.opportunity_context
    role_title = ctx.title
    company_name = ctx.company_name

    profile_keys = [f"profile:{bundle.profile.id}"] if bundle.profile else []
    if opts.contact_name:
        greeting_block = WritingTextBlock(
            text=f"Hi {opts.contact_name}," if target_language == "en" else f"Olá, {opts.contact_name},",
            source_fact_keys=[],
            provenance="user_authored",
        )
    else:
        greeting_block = WritingTextBlock(
            text="Hello," if target_language == "en" else "Olá,",
            source_fact_keys=profile_keys,
            provenance="confirmed_fact" if profile_keys else "user_authored",
        )

    # Assunto recomendado para e-mail ou título de contato
    subject_block: WritingTextBlock | None = None
    if opts.channel == "email":
        if role_title and company_name:
            subj = (
                f"Application for {role_title} — {company_name}"
                if target_language == "en"
                else f"Candidatura: {role_title} — {company_name}"
            )
        elif role_title:
            subj = (
                f"Application for {role_title}"
                if target_language == "en"
                else f"Candidatura: {role_title}"
            )
        else:
            subj = (
                "Professional Profile Introduction"
                if target_language == "en"
                else "Apresentação Profissional"
            )
        subject_block = WritingTextBlock(
            text=subj,
            source_fact_keys=profile_keys,
            provenance="confirmed_fact" if profile_keys else "user_authored",
        )

    # Corpo conciso com melhor evidência confirmada e competências correspondentes
    matched_skills = collect_matched_skills(bundle)
    top_skills = [name for name, _ in matched_skills[:3]]
    skill_keys = [fk for _, fk in matched_skills[:3]]

    evidence_blocks, ev_keys = format_evidence_blocks(
        bundle,
        target_language,
        max_items=1,
        prefer_projects=False,
    )
    body_keys: list[str] = [*profile_keys, *skill_keys, *ev_keys]

    sentences: list[str] = []
    if target_language == "en":
        if role_title and company_name:
            sentences.append(
                f"I am reaching out regarding the {role_title} opportunity at {company_name}."
            )
        elif role_title:
            sentences.append(
                f"I am reaching out regarding the {role_title} opportunity."
            )
        elif company_name:
            sentences.append(
                f"I would like to share my verified profile for relevant technical roles at {company_name}."
            )
        else:
            sentences.append(
                "I would like to introduce my verified technical profile for relevant opportunities."
            )

        if evidence_blocks:
            ev = evidence_blocks[0]
            if ev.entity_type == "project":
                sentences.append(f"I highlight my confirmed work on {ev.title}.")
            else:
                sentences.append(f"My verified background includes {ev.title}.")
        if top_skills:
            sentences.append(f"Core confirmed skills: {', '.join(top_skills)}.")
        if opts.contact_context:
            sentences.append(opts.contact_context)
    else:
        if role_title and company_name:
            sentences.append(
                f"Entro em contato sobre a vaga de {role_title} em {company_name}."
            )
        elif role_title:
            sentences.append(
                f"Entro em contato sobre a vaga de {role_title}."
            )
        elif company_name:
            sentences.append(
                f"Compartilho brevemente meu perfil confirmado para oportunidades técnicas em {company_name}."
            )
        else:
            sentences.append(
                "Compartilho brevemente meu perfil profissional confirmado para oportunidades técnicas compatíveis."
            )

        if evidence_blocks:
            ev = evidence_blocks[0]
            if ev.entity_type == "project":
                sentences.append(f"Destaco a atuação confirmada no {ev.title}.")
            else:
                sentences.append(f"Tenho experiência confirmada como {ev.title}.")
        if top_skills:
            sentences.append(f"Principais competências confirmadas: {', '.join(top_skills)}.")
        if opts.contact_context:
            sentences.append(opts.contact_context)

    body_provenance = "manual_edit" if opts.contact_context else "confirmed_fact"
    body_block = WritingTextBlock(
        text=" ".join(sentences),
        source_fact_keys=list(dict.fromkeys(body_keys)),
        provenance=body_provenance,  # type: ignore[arg-type]
    )

    # Assinatura respeitando ContactInclusionOptions
    candidate_name = safe_candidate_display_name(bundle)
    sign_parts: list[str] = [
        "Best regards," if target_language == "en" else "Atenciosamente,"
    ]
    if candidate_name:
        sign_parts.append(candidate_name)
    contact_line_bits: list[str] = []
    if header.email:
        contact_line_bits.append(header.email)
    if header.phone:
        contact_line_bits.append(header.phone)
    for lk in header.links[:2]:
        contact_line_bits.append(f"{lk.label}: {lk.url}")
    if contact_line_bits:
        sign_parts.append(" | ".join(contact_line_bits))

    sign_block = WritingTextBlock(
        text="\n".join(sign_parts),
        source_fact_keys=profile_keys if candidate_name or contact_line_bits else [],
        provenance="confirmed_fact" if (candidate_name or contact_line_bits) and profile_keys else "user_authored",
    )

    has_manual = any(
        b.provenance != "confirmed_fact"
        for b in [greeting_block, body_block, sign_block]
    )
    structured = RecruiterMessageStructuredContent(
        schema_version=1,
        material_type="recruiter_message",
        language=target_language,
        channel=opts.channel,
        subject=subject_block,
        greeting=greeting_block,
        body=body_block,
        sign_off=sign_block,
        character_count=0,
        manual_notes=[],
        has_unverified_manual_edits=has_manual,
    )
    structured = structured.model_copy(
        update={"character_count": _compute_char_count(structured)}
    )
    snapshot = build_snapshot_for_bundle(bundle, target_language)
    return structured, snapshot


def reconcile_recruiter_message(
    previous: RecruiterMessageStructuredContent,
    edited: RecruiterMessageStructuredContent,
    snapshot: dict[str, Any],
) -> RecruiterMessageStructuredContent:
    snapshot_facts: dict[str, Any] = dict(snapshot.get("facts") or {})
    subject = reconcile_text_block(previous.subject, edited.subject, snapshot_facts)
    greeting = reconcile_text_block(previous.greeting, edited.greeting, snapshot_facts)
    body = reconcile_text_block(previous.body, edited.body, snapshot_facts)
    sign_off = reconcile_text_block(previous.sign_off, edited.sign_off, snapshot_facts)
    notes = reconcile_manual_notes(edited.manual_notes)

    assert greeting is not None and body is not None and sign_off is not None
    has_manual = any(
        [
            subject is not None and subject.provenance != "confirmed_fact",
            greeting.provenance != "confirmed_fact",
            body.provenance != "confirmed_fact",
            sign_off.provenance != "confirmed_fact",
            len(notes) > 0,
        ]
    )
    reconciled = RecruiterMessageStructuredContent(
        schema_version=1,
        material_type="recruiter_message",
        language=edited.language,
        channel=edited.channel,
        subject=subject,
        greeting=greeting,
        body=body,
        sign_off=sign_off,
        character_count=0,
        manual_notes=notes,
        has_unverified_manual_edits=has_manual,
    )
    return reconciled.model_copy(
        update={"character_count": _compute_char_count(reconciled)}
    )


def render_recruiter_message_markdown(
    content: RecruiterMessageStructuredContent,
    language: TargetLanguage | None = None,
) -> str:
    lang: TargetLanguage = language or content.language
    lines: list[str] = []
    if content.subject:
        subj_label = "Subject" if lang == "en" else "Assunto"
        lines.append(f"**{subj_label}:** {content.subject.text}")
        lines.append("")
    lines.append(content.greeting.text)
    lines.append("")
    lines.append(content.body.text)
    lines.append("")
    if content.manual_notes:
        for note in content.manual_notes:
            lines.append(f"- **{note.title}:** {note.content}")
        lines.append("")
    lines.append(content.sign_off.text)
    return "\n".join(lines).strip() + "\n"


def render_recruiter_message_plain_text(
    content: RecruiterMessageStructuredContent,
    language: TargetLanguage | None = None,
) -> str:
    return markdown_to_plain_text(render_recruiter_message_markdown(content, language=language))

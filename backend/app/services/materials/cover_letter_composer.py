from __future__ import annotations

from typing import Any

from app.schemas.material import (
    ContactInclusionOptions,
    CoverLetterStructuredContent,
    TargetLanguage,
    WritingEvidenceBlock,
    WritingGenerationOptions,
    WritingTextBlock,
)
from app.services.materials.fact_selector import AuthorizedFactBundle
from app.services.materials.writing_common import (
    build_controlled_header,
    build_snapshot_for_bundle,
    collect_matched_skills,
    education_prose_snippet,
    format_evidence_blocks,
    languages_prose_snippet,
    markdown_to_plain_text,
    reconcile_evidence_blocks,
    reconcile_manual_notes,
    reconcile_text_block,
    reconcile_writing_header,
    safe_candidate_display_name,
)


def compose_cover_letter(
    bundle: AuthorizedFactBundle,
    *,
    target_language: TargetLanguage,
    contact_options: ContactInclusionOptions,
    writing_options: WritingGenerationOptions | None = None,
    user_instructions: str | None = None,
) -> tuple[CoverLetterStructuredContent, dict[str, Any]]:
    """Compõe carta de apresentação determinística usando exclusivamente fatos confirmados."""
    if not bundle.can_generate:
        raise ValueError(
            "; ".join(bundle.blocking_reasons)
            or "Não há fatos substantivos confirmados suficientes para gerar a carta."
        )

    _ = user_instructions
    opts = writing_options or WritingGenerationOptions()
    header = build_controlled_header(bundle, contact_options)
    ctx = bundle.opportunity_context
    role_title = ctx.title
    company_name = ctx.company_name

    # Destinatário e saudação sem inventar nomes de recrutadores
    recipient_keys = [f"profile:{bundle.profile.id}"] if bundle.profile else []
    if opts.contact_name:
        recipient_text = (
            f"Attn: {opts.contact_name}" + (f" — {company_name}" if company_name else "")
            if target_language == "en"
            else f"Aos cuidados de {opts.contact_name}" + (f" — {company_name}" if company_name else "")
        )
        greeting_text = (
            f"Dear {opts.contact_name},"
            if target_language == "en"
            else f"Prezado(a) {opts.contact_name},"
        )
        greeting_provenance = "user_authored"
        recipient_provenance = "user_authored"
    else:
        if company_name:
            recipient_text = (
                f"To the Hiring Team at {company_name}"
                if target_language == "en"
                else f"À equipe de seleção de {company_name}"
            )
        else:
            recipient_text = (
                "To the Hiring Team"
                if target_language == "en"
                else "À equipe de seleção"
            )
        greeting_text = "Dear Hiring Team," if target_language == "en" else "Prezados(as),"
        greeting_provenance = "confirmed_fact" if recipient_keys else "user_authored"
        recipient_provenance = "confirmed_fact" if recipient_keys else "user_authored"

    recipient_block = WritingTextBlock(
        text=recipient_text,
        source_fact_keys=recipient_keys if recipient_provenance == "confirmed_fact" else [],
        provenance=recipient_provenance,  # type: ignore[arg-type]
    )
    greeting_block = WritingTextBlock(
        text=greeting_text,
        source_fact_keys=recipient_keys if greeting_provenance == "confirmed_fact" else [],
        provenance=greeting_provenance,  # type: ignore[arg-type]
    )

    # Abertura neutra e factual (sem inventar admiração/sentimento não declarado)
    opening_keys: list[str] = []
    if bundle.profile:
        opening_keys.append(f"profile:{bundle.profile.id}")
    edu_snippet, edu_keys = education_prose_snippet(bundle, target_language)
    opening_keys.extend(edu_keys)

    matched_skills = collect_matched_skills(bundle)
    top_skills_names = [name for name, _ in matched_skills[:5]]
    for _, fk in matched_skills[:5]:
        opening_keys.append(fk)

    prof_title = (
        bundle.profile.professional_title.strip()
        if bundle.profile and bundle.profile.professional_title
        else None
    )

    opening_sentences: list[str] = []
    if target_language == "en":
        if role_title and company_name:
            opening_sentences.append(
                f"I am submitting my application for the {role_title} position at {company_name}."
            )
        elif role_title:
            opening_sentences.append(
                f"I am submitting my application for the {role_title} position."
            )
        elif company_name:
            opening_sentences.append(
                f"I am submitting my professional profile for consideration at {company_name}."
            )
        else:
            opening_sentences.append(
                "I am submitting my professional profile for technical opportunities aligned with my verified background."
            )

        bg_bits: list[str] = []
        if prof_title:
            bg_bits.append(f"my confirmed focus in {prof_title}")
        if edu_snippet:
            bg_bits.append(edu_snippet)
        if top_skills_names:
            bg_bits.append(f"practical experience with {', '.join(top_skills_names)}")
        if bg_bits:
            opening_sentences.append(
                f"My documented background combines {', '.join(bg_bits)}."
            )
    else:
        if role_title and company_name:
            opening_sentences.append(
                f"Apresento minha candidatura para a oportunidade de {role_title} em {company_name}."
            )
        elif role_title:
            opening_sentences.append(
                f"Apresento minha candidatura para a oportunidade de {role_title}."
            )
        elif company_name:
            opening_sentences.append(
                f"Apresento meu histórico profissional confirmado para avaliação em {company_name}."
            )
        else:
            opening_sentences.append(
                "Apresento meu perfil profissional para oportunidades compatíveis com minha trajetória confirmada."
            )

        bg_bits = []
        if prof_title:
            bg_bits.append(f"atuação voltada a {prof_title}")
        if edu_snippet:
            bg_bits.append(edu_snippet)
        if top_skills_names:
            bg_bits.append(f"domínio confirmado em {', '.join(top_skills_names)}")
        if bg_bits:
            opening_sentences.append(
                f"Minha base comprovada reúne {'; '.join(bg_bits)}."
            )

    opening_block = WritingTextBlock(
        text=" ".join(opening_sentences),
        source_fact_keys=list(dict.fromkeys(opening_keys)),
        provenance="confirmed_fact",
    )

    # Destaques de experiências e projetos relevantes sem repetir currículo inteiro
    relevance_highlights: list[WritingEvidenceBlock]
    evidence_blocks, _ev_keys = format_evidence_blocks(
        bundle,
        target_language,
        max_items=3,
        prefer_projects=False,
    )
    relevance_highlights = evidence_blocks

    # Alinhamento objetivo aos requisitos da oportunidade
    alignment_keys: list[str] = []
    confirmed_matched_reqs: list[str] = []
    seen_req: set[str] = set()
    for fact_ref in bundle.used_facts:
        if fact_ref.matched_requirements:
            alignment_keys.append(fact_ref.fact_key)
            for req in fact_ref.matched_requirements:
                if req.lower() not in seen_req:
                    seen_req.add(req.lower())
                    confirmed_matched_reqs.append(req)

    lang_snippet, lang_keys = languages_prose_snippet(bundle, target_language)
    alignment_parts: list[str] = []
    if confirmed_matched_reqs:
        req_joined = ", ".join(confirmed_matched_reqs[:8])
        if target_language == "en":
            alignment_parts.append(
                f"In relation to the role requirements, my confirmed background directly covers {req_joined}."
            )
        else:
            alignment_parts.append(
                f"Em relação aos requisitos da vaga, minhas evidências confirmadas cobrem diretamente {req_joined}."
            )
    elif top_skills_names:
        if target_language == "en":
            alignment_parts.append(
                f"Among my verified technical competencies, I highlight {', '.join(top_skills_names)}."
            )
        else:
            alignment_parts.append(
                f"Entre as competências técnicas confirmadas no meu perfil, destaco {', '.join(top_skills_names)}."
            )
        alignment_keys.extend(fk for _, fk in matched_skills[:5])

    if lang_snippet:
        alignment_keys.extend(lang_keys)
        if target_language == "en":
            alignment_parts.append(f"Confirmed languages: {lang_snippet}.")
        else:
            alignment_parts.append(f"Idiomas confirmados: {lang_snippet}.")

    opportunity_alignment: WritingTextBlock | None = None
    if alignment_parts:
        opportunity_alignment = WritingTextBlock(
            text=" ".join(alignment_parts),
            source_fact_keys=list(dict.fromkeys(alignment_keys)),
            provenance="confirmed_fact",
        )

    # Fechamento neutro sem prometer disponibilidade não informada
    candidate_name = safe_candidate_display_name(bundle)
    closing_keys = [f"profile:{bundle.profile.id}"] if bundle.profile and candidate_name else []
    if target_language == "en":
        closing_msg = "Thank you for reviewing my application. I remain available to share further details about the verified experiences and projects listed above."
        if candidate_name:
            closing_msg += f"\n\nSincerely,\n{candidate_name}"
        else:
            closing_msg += "\n\nSincerely,"
    else:
        closing_msg = "Agradeço pela atenção à minha candidatura e coloco-me à disposição para detalhar as experiências e projetos confirmados acima durante o processo seletivo."
        if candidate_name:
            closing_msg += f"\n\nAtenciosamente,\n{candidate_name}"
        else:
            closing_msg += "\n\nAtenciosamente,"

    closing_block = WritingTextBlock(
        text=closing_msg,
        source_fact_keys=closing_keys,
        provenance="confirmed_fact" if closing_keys else "user_authored",
    )

    has_manual = any(
        b.provenance != "confirmed_fact"
        for b in [recipient_block, greeting_block, closing_block]
    )

    structured = CoverLetterStructuredContent(
        schema_version=1,
        material_type="cover_letter",
        language=target_language,
        header=header,
        recipient_line=recipient_block,
        greeting=greeting_block,
        opening=opening_block,
        relevance_highlights=relevance_highlights,
        opportunity_alignment=opportunity_alignment,
        closing=closing_block,
        manual_notes=[],
        has_unverified_manual_edits=has_manual,
    )
    snapshot = build_snapshot_for_bundle(bundle, target_language)
    return structured, snapshot


def reconcile_cover_letter(
    previous: CoverLetterStructuredContent,
    edited: CoverLetterStructuredContent,
    snapshot: dict[str, Any],
) -> CoverLetterStructuredContent:
    snapshot_facts: dict[str, Any] = dict(snapshot.get("facts") or {})
    header = reconcile_writing_header(previous.header, edited.header, snapshot_facts)
    recipient = reconcile_text_block(previous.recipient_line, edited.recipient_line, snapshot_facts)
    greeting = reconcile_text_block(previous.greeting, edited.greeting, snapshot_facts)
    opening = reconcile_text_block(previous.opening, edited.opening, snapshot_facts)
    highlights = reconcile_evidence_blocks(
        previous.relevance_highlights, edited.relevance_highlights, snapshot_facts
    )
    alignment = reconcile_text_block(
        previous.opportunity_alignment, edited.opportunity_alignment, snapshot_facts
    )
    closing = reconcile_text_block(previous.closing, edited.closing, snapshot_facts)
    notes = reconcile_manual_notes(edited.manual_notes)

    assert recipient is not None and greeting is not None and opening is not None and closing is not None
    has_manual = any(
        [
            header.provenance != "confirmed_fact",
            recipient.provenance != "confirmed_fact",
            greeting.provenance != "confirmed_fact",
            opening.provenance != "confirmed_fact",
            any(item.provenance != "confirmed_fact" for item in highlights),
            alignment is not None and alignment.provenance != "confirmed_fact",
            closing.provenance != "confirmed_fact",
            len(notes) > 0,
        ]
    )
    return CoverLetterStructuredContent(
        schema_version=1,
        material_type="cover_letter",
        language=edited.language,
        header=header,
        recipient_line=recipient,
        greeting=greeting,
        opening=opening,
        relevance_highlights=highlights,
        opportunity_alignment=alignment,
        closing=closing,
        manual_notes=notes,
        has_unverified_manual_edits=has_manual,
    )


def render_cover_letter_markdown(
    content: CoverLetterStructuredContent,
    language: TargetLanguage | None = None,
) -> str:
    lang: TargetLanguage = language or content.language
    lines: list[str] = []

    h = content.header
    title_name = h.full_name or ("Cover Letter" if lang == "en" else "Carta de Apresentação")
    lines.append(f"# {title_name}")
    if h.professional_title:
        lines.append(f"**{h.professional_title}**")
    contact_parts = [p for p in [h.location_text, h.email, h.phone] if p]
    for lk in h.links:
        contact_parts.append(f"[{lk.label}]({lk.url})")
    if contact_parts:
        lines.append(" | ".join(contact_parts))
    lines.append("")

    lines.append(content.recipient_line.text)
    lines.append("")
    lines.append(content.greeting.text)
    lines.append("")
    lines.append(content.opening.text)
    lines.append("")

    if content.relevance_highlights:
        heading = (
            "Relevant Experience and Projects"
            if lang == "en"
            else "Experiências e Projetos Relevantes"
        )
        lines.append(f"## {heading}")
        for item in content.relevance_highlights:
            lines.append(f"- **{item.title}:** {item.summary_text}")
        lines.append("")

    if content.opportunity_alignment:
        lines.append(content.opportunity_alignment.text)
        lines.append("")

    if content.manual_notes:
        lines.append(f"## {'Additional Notes' if lang == 'en' else 'Notas Adicionais'}")
        for note in content.manual_notes:
            lines.append(f"- **{note.title}:** {note.content}")
        lines.append("")

    lines.append(content.closing.text)
    return "\n".join(lines).strip() + "\n"


def render_cover_letter_plain_text(
    content: CoverLetterStructuredContent,
    language: TargetLanguage | None = None,
) -> str:
    return markdown_to_plain_text(render_cover_letter_markdown(content, language=language))

from __future__ import annotations

from typing import Any

from app.schemas.material import (
    ContactInclusionOptions,
    FreelanceInputsPayload,
    FreelanceProposalStructuredContent,
    PendingUserInputField,
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
    reconcile_evidence_blocks,
    reconcile_manual_notes,
    reconcile_pending_fields,
    reconcile_text_block,
    reconcile_writing_header,
    safe_candidate_display_name,
)


def build_freelance_pending_fields(
    language: TargetLanguage,
    inputs: FreelanceInputsPayload | None = None,
) -> list[PendingUserInputField]:
    """Cria campos estruturados para informações que jamais podem ser presumidas."""
    data = inputs or FreelanceInputsPayload()
    if language == "en":
        specs = [
            (
                "availability",
                "Availability / Weekly Capacity",
                "When can you start and how many hours per week can you allocate?",
                True,
                data.availability,
            ),
            (
                "estimated_delivery",
                "Estimated Delivery Timeline",
                "What delivery estimate or milestones would you like to propose?",
                True,
                data.estimated_delivery,
            ),
            (
                "budget_or_price",
                "Budget / Rate",
                "What fixed price, range, or hourly rate will you quote?",
                True,
                data.budget_or_price,
            ),
            (
                "scope_clarifications",
                "Scope Clarifications",
                "Are there scope questions or boundaries to clarify with the client?",
                False,
                data.scope_clarifications,
            ),
            (
                "additional_requirements",
                "Client Prerequisites",
                "What access, repositories, APIs, or assets do you need from the client?",
                False,
                data.additional_requirements,
            ),
        ]
    else:
        specs = [
            (
                "availability",
                "Disponibilidade / Início",
                "Qual sua disponibilidade real de início e dedicação horária?",
                True,
                data.availability,
            ),
            (
                "estimated_delivery",
                "Prazo Estimado de Entrega",
                "Qual prazo estimado ou cronograma de entregas você pretende propor?",
                True,
                data.estimated_delivery,
            ),
            (
                "budget_or_price",
                "Valor / Orçamento",
                "Qual valor fechado, faixa ou valor por hora deseja apresentar?",
                True,
                data.budget_or_price,
            ),
            (
                "scope_clarifications",
                "Dúvidas de Escopo",
                "Quais definições de escopo precisam de alinhamento prévio com o cliente?",
                False,
                data.scope_clarifications,
            ),
            (
                "additional_requirements",
                "Pré-requisitos Técnicos do Cliente",
                "Quais acessos, ambientes, credenciais ou insumos dependem do contratante?",
                False,
                data.additional_requirements,
            ),
        ]

    return [
        PendingUserInputField(
            field_id=field_id,
            label=label,
            question=question,
            required=required,
            user_value=raw_val,
        )
        for field_id, label, question, required, raw_val in specs
    ]


def _render_alignment_block_text(
    pending_fields: list[PendingUserInputField],
    language: TargetLanguage,
) -> str:
    provided = [f for f in pending_fields if f.status == "provided" and f.user_value]
    pending = [f for f in pending_fields if f.status == "pending"]

    lines: list[str] = []
    if provided:
        for field in provided:
            lines.append(f"- {field.label}: {field.user_value}")
    if pending:
        pending_labels = ", ".join(f.label for f in pending)
        if language == "en":
            lines.append(
                f"To be finalized directly with the client prior to kick-off: {pending_labels}."
            )
        else:
            lines.append(
                f"Pontos a alinhar diretamente antes do início da execução: {pending_labels}."
            )
    if not lines:
        return (
            "Execution parameters confirmed."
            if language == "en"
            else "Condições comerciais e operacionais definidas."
        )
    return "\n".join(lines)


def compose_freelance_proposal(
    bundle: AuthorizedFactBundle,
    *,
    target_language: TargetLanguage,
    contact_options: ContactInclusionOptions,
    writing_options: WritingGenerationOptions | None = None,
    user_instructions: str | None = None,
) -> tuple[FreelanceProposalStructuredContent, dict[str, Any]]:
    """Compõe proposta freelance sem inventar preço, prazo, disponibilidade ou garantias."""
    if not bundle.can_generate:
        raise ValueError(
            "; ".join(bundle.blocking_reasons)
            or "Não há fatos substantivos confirmados suficientes para gerar a proposta."
        )

    _ = user_instructions
    opts = writing_options or WritingGenerationOptions()
    header = build_controlled_header(bundle, contact_options)
    ctx = bundle.opportunity_context
    project_title = ctx.title
    client_name = ctx.company_name

    # 1. Apresentação estritamente factual
    intro_keys = [f"profile:{bundle.profile.id}"] if bundle.profile else []
    candidate_name = safe_candidate_display_name(bundle)
    prof_title = (
        bundle.profile.professional_title.strip()
        if bundle.profile and bundle.profile.professional_title
        else None
    )
    if target_language == "en":
        intro_parts: list[str] = []
        if candidate_name and prof_title:
            intro_parts.append(f"Hello, I am {candidate_name} ({prof_title}).")
        elif candidate_name:
            intro_parts.append(f"Hello, I am {candidate_name}.")
        elif prof_title:
            intro_parts.append(f"Hello, I work in {prof_title}.")
        else:
            intro_parts.append("Hello, I am submitting a proposal grounded in verified technical work.")
        if project_title and client_name:
            intro_parts.append(
                f"Below is an objective proposal for '{project_title}' ({client_name})."
            )
        elif project_title:
            intro_parts.append(f"Below is an objective proposal for '{project_title}'.")
    else:
        intro_parts = []
        if candidate_name and prof_title:
            intro_parts.append(f"Olá, sou {candidate_name} ({prof_title}).")
        elif candidate_name:
            intro_parts.append(f"Olá, sou {candidate_name}.")
        elif prof_title:
            intro_parts.append(f"Olá, atuo com foco em {prof_title}.")
        else:
            intro_parts.append(
                "Olá, apresento uma proposta técnica baseada exclusivamente em entregas reais confirmadas."
            )
        if project_title and client_name:
            intro_parts.append(
                f"Segue minha proposta estruturada para o projeto '{project_title}' ({client_name})."
            )
        elif project_title:
            intro_parts.append(
                f"Segue minha proposta estruturada para a demanda '{project_title}'."
            )

    introduction = WritingTextBlock(
        text=" ".join(intro_parts),
        source_fact_keys=intro_keys,
        provenance="confirmed_fact" if intro_keys else "user_authored",
    )

    # 2. Entendimento do projeto sintetizado APENAS de metadados sanitizados (anti prompt-injection)
    req_techs = ctx.required_technologies or ctx.all_technologies
    tech_list_str = ", ".join(req_techs[:8]) if req_techs else None
    if target_language == "en":
        u_parts = []
        if project_title:
            u_parts.append(f"Target scope identified: {project_title}.")
        else:
            u_parts.append("Freelance technical delivery scope.")
        if tech_list_str:
            u_parts.append(f"Technical requirements noted in the brief: {tech_list_str}.")
        else:
            u_parts.append("Technical details and acceptance criteria should be confirmed before execution.")
    else:
        u_parts = []
        if project_title:
            u_parts.append(f"Demanda identificada: {project_title}.")
        else:
            u_parts.append("Escopo de prestação de serviço técnico.")
        if tech_list_str:
            u_parts.append(f"Requisitos e tecnologias citados na oportunidade: {tech_list_str}.")
        else:
            u_parts.append("Critérios técnicos detalhados dependem de alinhamento inicial de escopo.")

    project_understanding = WritingTextBlock(
        text=" ".join(u_parts),
        source_fact_keys=[],
        provenance="confirmed_fact",
    )

    # 3. Projetos e experiências confirmados (prioriza projetos reais para freelance)
    relevant_evidence, ev_keys = format_evidence_blocks(
        bundle,
        target_language,
        max_items=3,
        prefer_projects=True,
    )

    # 4. Abordagem técnica sugerida sem inventar stack não confirmada, prazos ou garantias
    matched_skills = collect_matched_skills(bundle)
    confirmed_matched_techs = [
        name for name, fk in matched_skills if bundle.matched_req_map.get(fk)
    ][:6]
    fallback_techs = [name for name, _ in matched_skills[:5]]
    used_techs = confirmed_matched_techs or fallback_techs
    approach_keys = [fk for _, fk in matched_skills[:6]] + ev_keys

    if target_language == "en":
        app_parts = [
            "Suggested execution structure: (1) initial review of requirements, data contracts, and access dependencies; "
            "(2) incremental implementation with automated verification; (3) technical documentation and handoff."
        ]
        if used_techs:
            app_parts.append(f"Confirmed technologies available in my background: {', '.join(used_techs)}.")
    else:
        app_parts = [
            "Abordagem técnica sugerida: (1) validação inicial de requisitos, fluxos e acessos necessários; "
            "(2) implementação incremental com testes automatizados; (3) entrega documentada e validação conjunta."
        ]
        if used_techs:
            app_parts.append(f"Tecnologias confirmadas no meu perfil aplicáveis à demanda: {', '.join(used_techs)}.")

    suggested_approach = WritingTextBlock(
        text=" ".join(app_parts),
        source_fact_keys=list(dict.fromkeys(approach_keys)),
        provenance="confirmed_fact",
    )

    # 5. Informações comerciais/prazo/disponibilidade nunca inventadas -> campos estruturados pendentes
    pending_fields = build_freelance_pending_fields(target_language, opts.freelance_inputs)
    has_provided_inputs = any(f.status == "provided" for f in pending_fields)
    alignment_points = WritingTextBlock(
        text=_render_alignment_block_text(pending_fields, target_language),
        source_fact_keys=[],
        provenance="user_authored" if has_provided_inputs else "confirmed_fact",
    )

    # 6. Encerramento profissional
    closing_text = (
        "Thank you for considering this proposal. Once we align on scope, timeline, and commercial terms, we can confirm the next steps."
        if target_language == "en"
        else "Agradeço pela consideração. Assim que alinharmos escopo, prazo e condições comerciais, confirmamos os próximos passos."
    )
    if candidate_name:
        closing_text += f"\n\n{candidate_name}"
    closing = WritingTextBlock(
        text=closing_text,
        source_fact_keys=intro_keys if candidate_name else [],
        provenance="confirmed_fact" if (candidate_name and intro_keys) else "user_authored",
    )

    has_manual = any(
        b.provenance != "confirmed_fact"
        for b in [introduction, alignment_points, closing]
    )
    structured = FreelanceProposalStructuredContent(
        schema_version=1,
        material_type="freelance_proposal",
        language=target_language,
        header=header,
        introduction=introduction,
        project_understanding=project_understanding,
        relevant_evidence=relevant_evidence,
        suggested_approach=suggested_approach,
        alignment_points=alignment_points,
        pending_fields=pending_fields,
        closing=closing,
        manual_notes=[],
        has_unverified_manual_edits=has_manual,
    )
    snapshot = build_snapshot_for_bundle(bundle, target_language)
    return structured, snapshot


def reconcile_freelance_proposal(
    previous: FreelanceProposalStructuredContent,
    edited: FreelanceProposalStructuredContent,
    snapshot: dict[str, Any],
) -> FreelanceProposalStructuredContent:
    snapshot_facts: dict[str, Any] = dict(snapshot.get("facts") or {})
    header = reconcile_writing_header(previous.header, edited.header, snapshot_facts)
    introduction = reconcile_text_block(previous.introduction, edited.introduction, snapshot_facts)
    understanding = reconcile_text_block(
        previous.project_understanding, edited.project_understanding, snapshot_facts
    )
    evidence = reconcile_evidence_blocks(
        previous.relevant_evidence, edited.relevant_evidence, snapshot_facts
    )
    approach = reconcile_text_block(
        previous.suggested_approach, edited.suggested_approach, snapshot_facts
    )
    pending_fields = reconcile_pending_fields(previous.pending_fields, edited.pending_fields)

    # Se usuário preencheu pending_fields e não alterou manualmente alignment_points, atualiza automaticamente
    if edited.alignment_points.text == previous.alignment_points.text:
        has_provided = any(f.status == "provided" for f in pending_fields)
        alignment_points = WritingTextBlock(
            text=_render_alignment_block_text(pending_fields, edited.language),
            source_fact_keys=[],
            provenance="user_authored" if has_provided else "confirmed_fact",
        )
    else:
        alignment_points = reconcile_text_block(
            previous.alignment_points, edited.alignment_points, snapshot_facts
        )

    closing = reconcile_text_block(previous.closing, edited.closing, snapshot_facts)
    notes = reconcile_manual_notes(edited.manual_notes)

    assert (
        introduction is not None
        and understanding is not None
        and approach is not None
        and alignment_points is not None
        and closing is not None
    )
    has_manual = any(
        [
            header.provenance != "confirmed_fact",
            introduction.provenance != "confirmed_fact",
            understanding.provenance != "confirmed_fact",
            any(ev.provenance != "confirmed_fact" for ev in evidence),
            approach.provenance != "confirmed_fact",
            alignment_points.provenance != "confirmed_fact",
            closing.provenance != "confirmed_fact",
            len(notes) > 0,
        ]
    )
    return FreelanceProposalStructuredContent(
        schema_version=1,
        material_type="freelance_proposal",
        language=edited.language,
        header=header,
        introduction=introduction,
        project_understanding=understanding,
        relevant_evidence=evidence,
        suggested_approach=approach,
        alignment_points=alignment_points,
        pending_fields=pending_fields,
        closing=closing,
        manual_notes=notes,
        has_unverified_manual_edits=has_manual,
    )


def render_freelance_proposal_markdown(
    content: FreelanceProposalStructuredContent,
    language: TargetLanguage | None = None,
) -> str:
    lang: TargetLanguage = language or content.language
    lines: list[str] = []

    h = content.header
    title_name = h.full_name or ("Freelance Proposal" if lang == "en" else "Proposta Freelance")
    lines.append(f"# {title_name}")
    if h.professional_title:
        lines.append(f"**{h.professional_title}**")
    contact_parts = [p for p in [h.location_text, h.email, h.phone] if p]
    for lk in h.links:
        contact_parts.append(f"[{lk.label}]({lk.url})")
    if contact_parts:
        lines.append(" | ".join(contact_parts))
    lines.append("")

    lines.append(f"## {'Introduction' if lang == 'en' else 'Apresentação'}")
    lines.append(content.introduction.text)
    lines.append("")

    lines.append(f"## {'Project Understanding' if lang == 'en' else 'Entendimento do Projeto'}")
    lines.append(content.project_understanding.text)
    lines.append("")

    if content.relevant_evidence:
        lines.append(
            f"## {'Relevant Experience and Projects' if lang == 'en' else 'Experiência e Projetos Relevantes'}"
        )
        for ev in content.relevant_evidence:
            lines.append(f"- **{ev.title}:** {ev.summary_text}")
        lines.append("")

    lines.append(f"## {'Suggested Technical Approach' if lang == 'en' else 'Abordagem Técnica Sugerida'}")
    lines.append(content.suggested_approach.text)
    lines.append("")

    lines.append(f"## {'Alignment Points & Commercial Terms' if lang == 'en' else 'Pontos de Alinhamento e Condições'}")
    lines.append(content.alignment_points.text)
    lines.append("")

    if content.manual_notes:
        lines.append(f"## {'Additional Notes' if lang == 'en' else 'Notas Adicionais'}")
        for note in content.manual_notes:
            lines.append(f"- **{note.title}:** {note.content}")
        lines.append("")

    lines.append(content.closing.text)
    return "\n".join(lines).strip() + "\n"


def render_freelance_proposal_plain_text(
    content: FreelanceProposalStructuredContent,
    language: TargetLanguage | None = None,
) -> str:
    return markdown_to_plain_text(render_freelance_proposal_markdown(content, language=language))

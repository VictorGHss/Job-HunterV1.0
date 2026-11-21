from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.schemas.material import (
    AnyMaterialStructuredContent,
    ApplicationAnswersStructuredContent,
    CoverLetterStructuredContent,
    FreelanceProposalStructuredContent,
    RecruiterMessageStructuredContent,
    ResumeStructuredContent,
)
from app.services.materials.ai.ai_schemas import (
    AIMaterialEnhanceOutput,
    AIMaterialTypeLiteral,
    AISuggestionItem,
    parse_and_validate_slot_for_material,
)
from app.services.materials.ai.contracts import AIOverlayConflictError
from app.services.materials.recruiter_message_composer import (
    render_recruiter_message_plain_text,
)


@dataclass(frozen=True, slots=True)
class EligibleSlotInfo:
    """Metadados de um slot elegível para aprimoramento assistido por IA."""

    slot_id: str
    current_text: str
    current_provenance: str
    current_source_fact_keys: tuple[str, ...]
    required_fact_key: str | None = None
    question_text: str | None = None


@dataclass(frozen=True, slots=True)
class SlotEligibilityResolution:
    """Resultado determinístico da inspeção de elegibilidade de slots."""

    eligible_slots: tuple[EligibleSlotInfo, ...]
    preserved_user_authored_slot_ids: tuple[str, ...]
    preserved_manual_edit_slot_ids: tuple[str, ...]

    def as_map(self) -> dict[str, EligibleSlotInfo]:
        return {item.slot_id: item for item in self.eligible_slots}


@dataclass(frozen=True, slots=True)
class OverlayMergeResult:
    """Resultado imutável da aplicação All-or-Nothing do ControlledOverlayMerger."""

    merged_content: AnyMaterialStructuredContent
    applied_slot_ids: tuple[str, ...]
    preserved_user_authored_slot_ids: tuple[str, ...]
    preserved_manual_edit_slot_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _InspectedSlot:
    slot_id: str
    current_text: str
    provenance: str
    source_fact_keys: tuple[str, ...]
    required_fact_key: str | None = None
    question_text: str | None = None
    answer_status: str | None = None
    requires_user_input: bool = False


class ControlledOverlayMerger:
    """Merger determinístico de sugestões de IA sobre structured_content dos 5 materiais.

    Invariantes garantidas:
    - Opera exclusivamente sobre cópia profunda (``model_copy(deep=True)``) sem mutar ``source_content``.
    - Protege estritamente blocos ``user_authored`` e ``pending_fields``.
    - Implementa Política 2 para ``manual_edit``: protegido em modo automático (``target_slot_ids=None``)
      e permitido apenas quando explicitamente listado em ``target_slot_ids`` (exceto em
      ``application_answers``, onde apenas ``answered_from_facts`` + ``confirmed_fact`` são elegíveis).
    - Validação All-or-Nothing: qualquer slot inválido, protegido ou sem entidade correspondente
      aborta a operação inteira sem aplicar alterações parciais.
    """

    @staticmethod
    def _inspect_all_addressable_slots(
        material_type: AIMaterialTypeLiteral,
        source_content: AnyMaterialStructuredContent,
    ) -> dict[str, _InspectedSlot]:
        slots: dict[str, _InspectedSlot] = {}

        if material_type == "resume":
            if not isinstance(source_content, ResumeStructuredContent):
                raise AIOverlayConflictError(
                    "Conteúdo estruturado incompatível com currículo.",
                    reason_code="type_mismatch",
                )
            if source_content.summary is not None:
                slots["summary"] = _InspectedSlot(
                    slot_id="summary",
                    current_text=source_content.summary.text,
                    provenance=source_content.summary.provenance,
                    source_fact_keys=tuple(source_content.summary.source_fact_keys),
                )
            if source_content.target_alignment is not None:
                slots["target_alignment"] = _InspectedSlot(
                    slot_id="target_alignment",
                    current_text=source_content.target_alignment.alignment_note or "",
                    provenance=source_content.target_alignment.provenance,
                    source_fact_keys=tuple(source_content.target_alignment.source_fact_keys),
                )
            for exp in source_content.experiences:
                if exp.entity_id:
                    slot_id = f"experience_highlight:{exp.entity_id}"
                    slots[slot_id] = _InspectedSlot(
                        slot_id=slot_id,
                        current_text=exp.description or "",
                        provenance=exp.provenance,
                        source_fact_keys=tuple(exp.source_fact_keys),
                        required_fact_key=f"experience:{exp.entity_id}",
                    )
            for proj in source_content.projects:
                if proj.entity_id:
                    slot_id = f"project_highlight:{proj.entity_id}"
                    slots[slot_id] = _InspectedSlot(
                        slot_id=slot_id,
                        current_text=proj.description or "",
                        provenance=proj.provenance,
                        source_fact_keys=tuple(proj.source_fact_keys),
                        required_fact_key=f"project:{proj.entity_id}",
                    )
            return slots

        if material_type == "cover_letter":
            if not isinstance(source_content, CoverLetterStructuredContent):
                raise AIOverlayConflictError(
                    "Conteúdo estruturado incompatível com carta de apresentação.",
                    reason_code="type_mismatch",
                )
            slots["opening"] = _InspectedSlot(
                slot_id="opening",
                current_text=source_content.opening.text,
                provenance=source_content.opening.provenance,
                source_fact_keys=tuple(source_content.opening.source_fact_keys),
            )
            if source_content.opportunity_alignment is not None:
                slots["opportunity_alignment"] = _InspectedSlot(
                    slot_id="opportunity_alignment",
                    current_text=source_content.opportunity_alignment.text,
                    provenance=source_content.opportunity_alignment.provenance,
                    source_fact_keys=tuple(source_content.opportunity_alignment.source_fact_keys),
                )
            slots["closing"] = _InspectedSlot(
                slot_id="closing",
                current_text=source_content.closing.text,
                provenance=source_content.closing.provenance,
                source_fact_keys=tuple(source_content.closing.source_fact_keys),
            )
            for ev in source_content.relevance_highlights:
                if ev.entity_type in ("experience", "project") and ev.entity_id:
                    slot_id = f"relevance_highlight:{ev.entity_type}:{ev.entity_id}"
                    slots[slot_id] = _InspectedSlot(
                        slot_id=slot_id,
                        current_text=ev.summary_text,
                        provenance=ev.provenance,
                        source_fact_keys=tuple(ev.source_fact_keys),
                        required_fact_key=f"{ev.entity_type}:{ev.entity_id}",
                    )
            return slots

        if material_type == "recruiter_message":
            if not isinstance(source_content, RecruiterMessageStructuredContent):
                raise AIOverlayConflictError(
                    "Conteúdo estruturado incompatível com mensagem para recrutador.",
                    reason_code="type_mismatch",
                )
            if source_content.subject is not None:
                slots["subject"] = _InspectedSlot(
                    slot_id="subject",
                    current_text=source_content.subject.text,
                    provenance=source_content.subject.provenance,
                    source_fact_keys=tuple(source_content.subject.source_fact_keys),
                )
            for static_id in ("body", "sign_off"):
                blk = getattr(source_content, static_id)
                slots[static_id] = _InspectedSlot(
                    slot_id=static_id,
                    current_text=blk.text,
                    provenance=blk.provenance,
                    source_fact_keys=tuple(blk.source_fact_keys),
                )
            return slots

        if material_type == "freelance_proposal":
            if not isinstance(source_content, FreelanceProposalStructuredContent):
                raise AIOverlayConflictError(
                    "Conteúdo estruturado incompatível com proposta freelance.",
                    reason_code="type_mismatch",
                )
            for static_id in (
                "introduction",
                "project_understanding",
                "suggested_approach",
                "alignment_points",
                "closing",
            ):
                blk = getattr(source_content, static_id)
                slots[static_id] = _InspectedSlot(
                    slot_id=static_id,
                    current_text=blk.text,
                    provenance=blk.provenance,
                    source_fact_keys=tuple(blk.source_fact_keys),
                )
            for ev in source_content.relevant_evidence:
                if ev.entity_type in ("experience", "project") and ev.entity_id:
                    slot_id = f"relevant_evidence:{ev.entity_type}:{ev.entity_id}"
                    slots[slot_id] = _InspectedSlot(
                        slot_id=slot_id,
                        current_text=ev.summary_text,
                        provenance=ev.provenance,
                        source_fact_keys=tuple(ev.source_fact_keys),
                        required_fact_key=f"{ev.entity_type}:{ev.entity_id}",
                    )
            return slots

        if material_type == "application_answers":
            if not isinstance(source_content, ApplicationAnswersStructuredContent):
                raise AIOverlayConflictError(
                    "Conteúdo estruturado incompatível com respostas de candidatura.",
                    reason_code="type_mismatch",
                )
            for item in source_content.items:
                slot_id = f"answer:{item.question_id}"
                slots[slot_id] = _InspectedSlot(
                    slot_id=slot_id,
                    current_text=item.answer_text or "",
                    provenance=item.provenance,
                    source_fact_keys=tuple(item.source_fact_keys),
                    question_text=item.question,
                    answer_status=item.status,
                    requires_user_input=bool(item.requires_user_input),
                )
            return slots

        raise AIOverlayConflictError(
            f"Tipo de material não suportado para overlay de IA: '{material_type}'.",
            reason_code="unsupported_material_type",
        )

    @classmethod
    def resolve_eligible_slots(
        cls,
        *,
        material_type: AIMaterialTypeLiteral,
        source_content: AnyMaterialStructuredContent,
        target_slot_ids: Sequence[str] | None = None,
    ) -> SlotEligibilityResolution:
        """Resolve os slots elegíveis aplicando proteção de user_authored e Política 2 de manual_edit."""
        inspected_map = cls._inspect_all_addressable_slots(material_type, source_content)

        explicit_targets: list[str] | None = None
        if target_slot_ids is not None:
            explicit_targets = []
            for raw_slot in target_slot_ids:
                try:
                    parsed = parse_and_validate_slot_for_material(material_type, raw_slot)
                except ValueError as exc:
                    raise AIOverlayConflictError(
                        str(exc),
                        slot_id=raw_slot.strip(),
                        reason_code="invalid_slot_for_material",
                    ) from exc
                if parsed.slot_id not in inspected_map:
                    raise AIOverlayConflictError(
                        f"O slot solicitado '{parsed.slot_id}' não existe na versão de origem.",
                        slot_id=parsed.slot_id,
                        reason_code="slot_target_not_found",
                    )
                if parsed.slot_id not in explicit_targets:
                    explicit_targets.append(parsed.slot_id)

        explicit_set = set(explicit_targets) if explicit_targets is not None else None
        eligible: list[EligibleSlotInfo] = []
        preserved_user_authored: list[str] = []
        preserved_manual_edit: list[str] = []

        for slot_id, slot in inspected_map.items():
            is_explicitly_requested = explicit_set is not None and slot_id in explicit_set

            if material_type == "application_answers":
                is_answer_eligible = (
                    slot.answer_status == "answered_from_facts"
                    and slot.provenance == "confirmed_fact"
                    and not slot.requires_user_input
                    and bool(slot.current_text.strip())
                )
                if not is_answer_eligible:
                    if is_explicitly_requested:
                        raise AIOverlayConflictError(
                            f"A resposta '{slot_id}' é protegida (autoria do usuário, edição manual ou pendente de input) e não pode ser sobrescrita pela IA.",
                            slot_id=slot_id,
                            reason_code="protected_application_answer",
                        )
                    if slot.provenance == "manual_edit":
                        preserved_manual_edit.append(slot_id)
                    else:
                        preserved_user_authored.append(slot_id)
                    continue

                if explicit_set is None or is_explicitly_requested:
                    eligible.append(
                        EligibleSlotInfo(
                            slot_id=slot.slot_id,
                            current_text=slot.current_text,
                            current_provenance=slot.provenance,
                            current_source_fact_keys=slot.source_fact_keys,
                            required_fact_key=slot.required_fact_key,
                            question_text=slot.question_text,
                        )
                    )
                continue

            # Demais materiais: resume, cover_letter, recruiter_message, freelance_proposal
            if slot.provenance == "user_authored":
                if is_explicitly_requested:
                    raise AIOverlayConflictError(
                        f"O bloco '{slot_id}' possui autoria direta do usuário (user_authored) e não pode ser sobrescrito pela IA.",
                        slot_id=slot_id,
                        reason_code="protected_user_authored_slot",
                    )
                preserved_user_authored.append(slot_id)
                continue

            if slot.provenance == "manual_edit":
                if explicit_set is None:
                    # Modo automático: preserva manual_edit
                    preserved_manual_edit.append(slot_id)
                    continue
                if not is_explicitly_requested:
                    preserved_manual_edit.append(slot_id)
                    continue
                # Modo explícito com slot listado em target_slot_ids: permitido pela Política 2

            if explicit_set is None or is_explicitly_requested:
                eligible.append(
                    EligibleSlotInfo(
                        slot_id=slot.slot_id,
                        current_text=slot.current_text,
                        current_provenance=slot.provenance,
                        current_source_fact_keys=slot.source_fact_keys,
                        required_fact_key=slot.required_fact_key,
                        question_text=slot.question_text,
                    )
                )

        if not eligible:
            raise AIOverlayConflictError(
                "Nenhum slot elegível disponível para aprimoramento por IA nesta versão.",
                reason_code="no_eligible_slots",
            )

        return SlotEligibilityResolution(
            eligible_slots=tuple(eligible),
            preserved_user_authored_slot_ids=tuple(preserved_user_authored),
            preserved_manual_edit_slot_ids=tuple(preserved_manual_edit),
        )

    @classmethod
    def apply_overlay(
        cls,
        *,
        material_type: AIMaterialTypeLiteral,
        source_content: AnyMaterialStructuredContent,
        ai_output: AIMaterialEnhanceOutput,
        target_slot_ids: Sequence[str] | None = None,
    ) -> OverlayMergeResult:
        """Aplica sugestões validadas de IA de forma All-or-Nothing sobre cópia profunda de source_content."""
        if ai_output.material_type != material_type:
            raise AIOverlayConflictError(
                f"Tipo de material da resposta da IA ('{ai_output.material_type}') diverge do material ('{material_type}').",
                reason_code="material_type_mismatch",
            )

        resolution = cls.resolve_eligible_slots(
            material_type=material_type,
            source_content=source_content,
            target_slot_ids=target_slot_ids,
        )
        eligible_map = resolution.as_map()

        # Fase 1: Validação All-or-Nothing antes de qualquer mutação na cópia
        for suggestion in ai_output.suggestions:
            if suggestion.slot_id not in eligible_map:
                raise AIOverlayConflictError(
                    f"Sugestão retornada para slot não elegível ou não solicitado: '{suggestion.slot_id}'.",
                    slot_id=suggestion.slot_id,
                    reason_code="ineligible_or_unrequested_slot",
                )
            slot_info = eligible_map[suggestion.slot_id]
            if (
                slot_info.required_fact_key is not None
                and slot_info.required_fact_key not in suggestion.cited_fact_keys
            ):
                raise AIOverlayConflictError(
                    f"O slot parametrizado '{suggestion.slot_id}' exige citação de '{slot_info.required_fact_key}'.",
                    slot_id=suggestion.slot_id,
                    reason_code="missing_entity_fact_citation",
                )

        # Fase 2: Aplicação em cópia profunda (source_content original permanece intacto)
        cloned = source_content.model_copy(deep=True)
        applied_ids: list[str] = []

        for suggestion in ai_output.suggestions:
            cls._apply_single_suggestion(
                material_type=material_type,
                cloned_content=cloned,
                suggestion=suggestion,
            )
            applied_ids.append(suggestion.slot_id)

        if isinstance(cloned, RecruiterMessageStructuredContent):
            plain = render_recruiter_message_plain_text(cloned, language=cloned.language).strip()
            cloned.character_count = len(plain)

        # Fase 3: Revalidação estrutural Pydantic do modelo resultante
        validated_clone = cloned.__class__.model_validate(cloned.model_dump(mode="python"))

        return OverlayMergeResult(
            merged_content=validated_clone,
            applied_slot_ids=tuple(applied_ids),
            preserved_user_authored_slot_ids=resolution.preserved_user_authored_slot_ids,
            preserved_manual_edit_slot_ids=resolution.preserved_manual_edit_slot_ids,
        )

    @staticmethod
    def _apply_single_suggestion(
        *,
        material_type: AIMaterialTypeLiteral,
        cloned_content: AnyMaterialStructuredContent,
        suggestion: AISuggestionItem,
    ) -> None:
        slot_id = suggestion.slot_id
        text = suggestion.suggested_text.strip()
        cited = list(suggestion.cited_fact_keys)

        if material_type == "resume":
            assert isinstance(cloned_content, ResumeStructuredContent)
            if slot_id == "summary" and cloned_content.summary is not None:
                cloned_content.summary.text = text[:3000]
                cloned_content.summary.provenance = "confirmed_fact"
                cloned_content.summary.source_fact_keys = cited
                return
            if slot_id == "target_alignment" and cloned_content.target_alignment is not None:
                cloned_content.target_alignment.alignment_note = text[:1000]
                cloned_content.target_alignment.provenance = "confirmed_fact"
                cloned_content.target_alignment.source_fact_keys = cited
                return
            if slot_id.startswith("experience_highlight:"):
                target_id = slot_id.split(":", 1)[1]
                for exp in cloned_content.experiences:
                    if exp.entity_id == target_id:
                        exp.description = text[:4000]
                        exp.provenance = "confirmed_fact"
                        exp.source_fact_keys = cited
                        return
            if slot_id.startswith("project_highlight:"):
                target_id = slot_id.split(":", 1)[1]
                for proj in cloned_content.projects:
                    if proj.entity_id == target_id:
                        proj.description = text[:4000]
                        proj.provenance = "confirmed_fact"
                        proj.source_fact_keys = cited
                        return
            raise AIOverlayConflictError(
                f"Slot '{slot_id}' não encontrado no currículo.",
                slot_id=slot_id,
                reason_code="slot_target_not_found",
            )

        if material_type == "cover_letter":
            assert isinstance(cloned_content, CoverLetterStructuredContent)
            if slot_id in ("opening", "opportunity_alignment", "closing"):
                blk = getattr(cloned_content, slot_id)
                if blk is None:
                    raise AIOverlayConflictError(
                        f"O slot '{slot_id}' não está ativo nesta carta.",
                        slot_id=slot_id,
                        reason_code="slot_target_not_found",
                    )
                blk.text = text
                blk.provenance = "confirmed_fact"
                blk.source_fact_keys = cited
                return
            if slot_id.startswith("relevance_highlight:"):
                _, entity_type, target_id = slot_id.split(":", 2)
                for ev in cloned_content.relevance_highlights:
                    if ev.entity_type == entity_type and ev.entity_id == target_id:
                        ev.summary_text = text
                        ev.provenance = "confirmed_fact"
                        ev.source_fact_keys = cited
                        return
            raise AIOverlayConflictError(
                f"Slot '{slot_id}' não encontrado na carta de apresentação.",
                slot_id=slot_id,
                reason_code="slot_target_not_found",
            )

        if material_type == "recruiter_message":
            assert isinstance(cloned_content, RecruiterMessageStructuredContent)
            if slot_id == "subject":
                if cloned_content.subject is None:
                    raise AIOverlayConflictError(
                        "O slot 'subject' não está ativo nesta mensagem.",
                        slot_id=slot_id,
                        reason_code="slot_target_not_found",
                    )
                cloned_content.subject.text = text[:300]
                cloned_content.subject.provenance = "confirmed_fact"
                cloned_content.subject.source_fact_keys = cited
                return
            if slot_id in ("body", "sign_off"):
                blk = getattr(cloned_content, slot_id)
                blk.text = text
                blk.provenance = "confirmed_fact"
                blk.source_fact_keys = cited
                return
            raise AIOverlayConflictError(
                f"Slot '{slot_id}' não encontrado na mensagem para recrutador.",
                slot_id=slot_id,
                reason_code="slot_target_not_found",
            )

        if material_type == "freelance_proposal":
            assert isinstance(cloned_content, FreelanceProposalStructuredContent)
            if slot_id in (
                "introduction",
                "project_understanding",
                "suggested_approach",
                "alignment_points",
                "closing",
            ):
                blk = getattr(cloned_content, slot_id)
                blk.text = text
                blk.provenance = "confirmed_fact"
                blk.source_fact_keys = cited
                return
            if slot_id.startswith("relevant_evidence:"):
                _, entity_type, target_id = slot_id.split(":", 2)
                for ev in cloned_content.relevant_evidence:
                    if ev.entity_type == entity_type and ev.entity_id == target_id:
                        ev.summary_text = text
                        ev.provenance = "confirmed_fact"
                        ev.source_fact_keys = cited
                        return
            raise AIOverlayConflictError(
                f"Slot '{slot_id}' não encontrado na proposta freelance.",
                slot_id=slot_id,
                reason_code="slot_target_not_found",
            )

        if material_type == "application_answers":
            assert isinstance(cloned_content, ApplicationAnswersStructuredContent)
            if slot_id.startswith("answer:"):
                target_qid = slot_id.split(":", 1)[1]
                for item in cloned_content.items:
                    if item.question_id == target_qid:
                        item.answer_text = text
                        item.provenance = "confirmed_fact"
                        item.status = "answered_from_facts"
                        item.requires_user_input = False
                        item.source_fact_keys = cited
                        return
            raise AIOverlayConflictError(
                f"Slot '{slot_id}' não encontrado nas respostas de candidatura.",
                slot_id=slot_id,
                reason_code="slot_target_not_found",
            )

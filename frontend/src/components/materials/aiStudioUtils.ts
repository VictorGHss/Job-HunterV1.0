import { ApiError } from "@/lib/api";
import type {
  AnyMaterialStructuredContent,
  ApplicationAnswersStructuredContent,
  CoverLetterStructuredContent,
  FreelanceProposalStructuredContent,
  MaterialAIOverlayMetadata,
  MaterialBlockProvenance,
  MaterialSnapshotFactItem,
  MaterialTypeValue,
  RecruiterMessageStructuredContent,
  ResumeStructuredContent,
} from "@/types/api";

export interface ExtractedMaterialSlot {
  slotId: string;
  label: string;
  subtitle: string | null;
  text: string;
  provenance: MaterialBlockProvenance;
  sourceFactKeys: string[];
  autoEligible: boolean;
  manualSelectable: boolean;
  protectionReason: string | null;
}

export type SlotDiffStatus =
  | "modified"
  | "added"
  | "removed"
  | "preserved_user_authored"
  | "preserved_manual_edit"
  | "unchanged";

export interface StructuredSlotDiffItem {
  slotId: string;
  label: string;
  subtitle: string | null;
  status: SlotDiffStatus;
  beforeText: string | null;
  afterText: string | null;
  beforeProvenance: MaterialBlockProvenance | null;
  afterProvenance: MaterialBlockProvenance;
  sourceFactKeys: string[];
  isAppliedByAi: boolean;
}

export interface AIErrorPresentation {
  title: string;
  description: string;
  errorCodeBadge: string | null;
  retryAfterLabel: string | null;
  canReloadMaterial: boolean;
  severity: "warning" | "destructive";
}

const ENTITY_TYPE_LABELS: Record<string, string> = {
  profile: "Perfil",
  experience: "Experiência",
  project: "Projeto",
  education: "Formação",
  skill: "Habilidade",
  language: "Idioma",
};

export function hasVisibleText(value: string | null | undefined): boolean {
  return Boolean(value && value.trim().length > 0);
}

export function extractMaterialSlots(
  materialType: MaterialTypeValue | string,
  content: AnyMaterialStructuredContent
): ExtractedMaterialSlot[] {
  const slots: ExtractedMaterialSlot[] = [];

  const buildSlot = (params: {
    slotId: string;
    label: string;
    subtitle?: string | null;
    text: string | null | undefined;
    provenance: MaterialBlockProvenance;
    sourceFactKeys: string[];
    isApplicationAnswer?: boolean;
    answerStatus?: string;
    requiresUserInput?: boolean;
  }): ExtractedMaterialSlot => {
    const cleanText = params.text ?? "";
    const visible = hasVisibleText(cleanText);

    if (params.isApplicationAnswer) {
      const eligible =
        visible &&
        params.answerStatus === "answered_from_facts" &&
        !params.requiresUserInput &&
        params.provenance === "confirmed_fact";
      let protectionReason: string | null = null;
      if (!eligible) {
        if (params.requiresUserInput || params.answerStatus === "needs_user_input") {
          protectionReason =
            "Protegido: pergunta exige resposta manual do usuário (needs_user_input).";
        } else if (params.provenance === "user_authored") {
          protectionReason =
            "Protegido: conteúdo autoral do usuário (user_authored) nunca é sobrescrito pela IA.";
        } else {
          protectionReason =
            "Protegido: apenas respostas geradas diretamente de fatos confirmados são elegíveis.";
        }
      }
      return {
        slotId: params.slotId,
        label: params.label,
        subtitle: params.subtitle ?? null,
        text: cleanText,
        provenance: params.provenance,
        sourceFactKeys: params.sourceFactKeys,
        autoEligible: eligible,
        manualSelectable: eligible,
        protectionReason,
      };
    }

    if (params.provenance === "user_authored") {
      return {
        slotId: params.slotId,
        label: params.label,
        subtitle: params.subtitle ?? null,
        text: cleanText,
        provenance: params.provenance,
        sourceFactKeys: params.sourceFactKeys,
        autoEligible: false,
        manualSelectable: false,
        protectionReason:
          "Protegido: bloco autoral do usuário (user_authored) é sempre preservado.",
      };
    }

    if (!visible) {
      return {
        slotId: params.slotId,
        label: params.label,
        subtitle: params.subtitle ?? null,
        text: cleanText,
        provenance: params.provenance,
        sourceFactKeys: params.sourceFactKeys,
        autoEligible: false,
        manualSelectable: false,
        protectionReason: "Slot sem texto base disponível para aprimoramento.",
      };
    }

    if (params.provenance === "manual_edit") {
      return {
        slotId: params.slotId,
        label: params.label,
        subtitle: params.subtitle ?? null,
        text: cleanText,
        provenance: params.provenance,
        sourceFactKeys: params.sourceFactKeys,
        autoEligible: false,
        manualSelectable: true,
        protectionReason:
          "Política 2: edição manual preservada por padrão; marque explicitamente para autorizar o aprimoramento por IA.",
      };
    }

    return {
      slotId: params.slotId,
      label: params.label,
      subtitle: params.subtitle ?? null,
      text: cleanText,
      provenance: params.provenance,
      sourceFactKeys: params.sourceFactKeys,
      autoEligible: true,
      manualSelectable: true,
      protectionReason: null,
    };
  };

  if (materialType === "resume") {
    const resume = content as ResumeStructuredContent;
    if (resume.summary) {
      slots.push(
        buildSlot({
          slotId: "summary",
          label: "Resumo Profissional",
          text: resume.summary.text,
          provenance: resume.summary.provenance,
          sourceFactKeys: resume.summary.source_fact_keys || [],
        })
      );
    }
    if (resume.target_alignment) {
      slots.push(
        buildSlot({
          slotId: "target_alignment",
          label: "Alinhamento com a Vaga",
          subtitle: resume.target_alignment.target_role || null,
          text: resume.target_alignment.alignment_note,
          provenance: resume.target_alignment.provenance,
          sourceFactKeys: resume.target_alignment.source_fact_keys || [],
        })
      );
    }
    for (const exp of resume.experiences || []) {
      if (exp.entity_id) {
        slots.push(
          buildSlot({
            slotId: `experience_highlight:${exp.entity_id}`,
            label: `Experiência: ${exp.role} — ${exp.company}`,
            subtitle: exp.period_label || exp.experience_type,
            text: exp.description,
            provenance: exp.provenance,
            sourceFactKeys: exp.source_fact_keys || [],
          })
        );
      }
    }
    for (const proj of resume.projects || []) {
      if (proj.entity_id) {
        slots.push(
          buildSlot({
            slotId: `project_highlight:${proj.entity_id}`,
            label: `Projeto: ${proj.name}`,
            subtitle: proj.role || null,
            text: proj.description,
            provenance: proj.provenance,
            sourceFactKeys: proj.source_fact_keys || [],
          })
        );
      }
    }
    return slots;
  }

  if (materialType === "cover_letter") {
    const cl = content as CoverLetterStructuredContent;
    slots.push(
      buildSlot({
        slotId: "opening",
        label: "Apresentação Inicial",
        text: cl.opening.text,
        provenance: cl.opening.provenance,
        sourceFactKeys: cl.opening.source_fact_keys || [],
      })
    );
    for (const ev of cl.relevance_highlights || []) {
      if ((ev.entity_type === "experience" || ev.entity_type === "project") && ev.entity_id) {
        slots.push(
          buildSlot({
            slotId: `relevance_highlight:${ev.entity_type}:${ev.entity_id}`,
            label: `Destaque (${ENTITY_TYPE_LABELS[ev.entity_type] || ev.entity_type}): ${ev.title}`,
            text: ev.summary_text,
            provenance: ev.provenance,
            sourceFactKeys: ev.source_fact_keys || [],
          })
        );
      }
    }
    if (cl.opportunity_alignment) {
      slots.push(
        buildSlot({
          slotId: "opportunity_alignment",
          label: "Relação com os Requisitos da Vaga",
          text: cl.opportunity_alignment.text,
          provenance: cl.opportunity_alignment.provenance,
          sourceFactKeys: cl.opportunity_alignment.source_fact_keys || [],
        })
      );
    }
    slots.push(
      buildSlot({
        slotId: "closing",
        label: "Encerramento",
        text: cl.closing.text,
        provenance: cl.closing.provenance,
        sourceFactKeys: cl.closing.source_fact_keys || [],
      })
    );
    return slots;
  }

  if (materialType === "recruiter_message") {
    const rm = content as RecruiterMessageStructuredContent;
    if (rm.subject) {
      slots.push(
        buildSlot({
          slotId: "subject",
          label: "Assunto Sugerido",
          text: rm.subject.text,
          provenance: rm.subject.provenance,
          sourceFactKeys: rm.subject.source_fact_keys || [],
        })
      );
    }
    slots.push(
      buildSlot({
        slotId: "body",
        label: "Mensagem Principal",
        subtitle: `Canal: ${rm.channel}`,
        text: rm.body.text,
        provenance: rm.body.provenance,
        sourceFactKeys: rm.body.source_fact_keys || [],
      }),
      buildSlot({
        slotId: "sign_off",
        label: "Assinatura e Contatos",
        text: rm.sign_off.text,
        provenance: rm.sign_off.provenance,
        sourceFactKeys: rm.sign_off.source_fact_keys || [],
      })
    );
    return slots;
  }

  if (materialType === "freelance_proposal") {
    const fp = content as FreelanceProposalStructuredContent;
    slots.push(
      buildSlot({
        slotId: "introduction",
        label: "Apresentação",
        text: fp.introduction.text,
        provenance: fp.introduction.provenance,
        sourceFactKeys: fp.introduction.source_fact_keys || [],
      }),
      buildSlot({
        slotId: "project_understanding",
        label: "Entendimento do Projeto",
        text: fp.project_understanding.text,
        provenance: fp.project_understanding.provenance,
        sourceFactKeys: fp.project_understanding.source_fact_keys || [],
      })
    );
    for (const ev of fp.relevant_evidence || []) {
      if ((ev.entity_type === "experience" || ev.entity_type === "project") && ev.entity_id) {
        slots.push(
          buildSlot({
            slotId: `relevant_evidence:${ev.entity_type}:${ev.entity_id}`,
            label: `Evidência (${ENTITY_TYPE_LABELS[ev.entity_type] || ev.entity_type}): ${ev.title}`,
            text: ev.summary_text,
            provenance: ev.provenance,
            sourceFactKeys: ev.source_fact_keys || [],
          })
        );
      }
    }
    slots.push(
      buildSlot({
        slotId: "suggested_approach",
        label: "Abordagem Técnica Sugerida",
        text: fp.suggested_approach.text,
        provenance: fp.suggested_approach.provenance,
        sourceFactKeys: fp.suggested_approach.source_fact_keys || [],
      }),
      buildSlot({
        slotId: "alignment_points",
        label: "Pontos de Alinhamento & Condições",
        text: fp.alignment_points.text,
        provenance: fp.alignment_points.provenance,
        sourceFactKeys: fp.alignment_points.source_fact_keys || [],
      }),
      buildSlot({
        slotId: "closing",
        label: "Encerramento",
        text: fp.closing.text,
        provenance: fp.closing.provenance,
        sourceFactKeys: fp.closing.source_fact_keys || [],
      })
    );
    return slots;
  }

  if (materialType === "application_answers") {
    const aa = content as ApplicationAnswersStructuredContent;
    (aa.items || []).forEach((item, index) => {
      slots.push(
        buildSlot({
          slotId: `answer:${item.question_id}`,
          label: `Pergunta ${index + 1}: ${item.question}`,
          subtitle: `Tipo: ${item.question_kind}`,
          text: item.answer_text,
          provenance: item.provenance,
          sourceFactKeys: item.source_fact_keys || [],
          isApplicationAnswer: true,
          answerStatus: item.status,
          requiresUserInput: item.requires_user_input,
        })
      );
    });
    return slots;
  }

  return slots;
}

export function buildStructuredSlotDiffs(
  materialType: MaterialTypeValue | string,
  parentContent: AnyMaterialStructuredContent | null,
  currentContent: AnyMaterialStructuredContent,
  aiOverlay: MaterialAIOverlayMetadata | null,
  currentOrigin: string
): StructuredSlotDiffItem[] {
  const parentSlots = parentContent
    ? extractMaterialSlots(materialType, parentContent)
    : [];
  const currentSlots = extractMaterialSlots(materialType, currentContent);

  const parentMap = new Map<string, ExtractedMaterialSlot>();
  for (const s of parentSlots) {
    parentMap.set(s.slotId, s);
  }
  const currentMap = new Map<string, ExtractedMaterialSlot>();
  for (const s of currentSlots) {
    currentMap.set(s.slotId, s);
  }

  const appliedSet = new Set(aiOverlay?.applied_slot_ids || []);
  const preservedUserSet = new Set(
    aiOverlay?.preserved_user_authored_slot_ids || []
  );
  const preservedManualSet = new Set(
    aiOverlay?.preserved_manual_edit_slot_ids || []
  );

  const orderedSlotIds: string[] = [];
  const seen = new Set<string>();
  for (const s of currentSlots) {
    orderedSlotIds.push(s.slotId);
    seen.add(s.slotId);
  }
  for (const s of parentSlots) {
    if (!seen.has(s.slotId)) {
      orderedSlotIds.push(s.slotId);
      seen.add(s.slotId);
    }
  }

  const diffs: StructuredSlotDiffItem[] = [];

  for (const slotId of orderedSlotIds) {
    const before = parentMap.get(slotId) || null;
    const after = currentMap.get(slotId) || null;

    if (after && !before) {
      const hasAfter = hasVisibleText(after.text);
      diffs.push({
        slotId,
        label: after.label,
        subtitle: after.subtitle,
        status: parentContent && hasAfter ? "added" : "unchanged",
        beforeText: null,
        afterText: after.text,
        beforeProvenance: null,
        afterProvenance: after.provenance,
        sourceFactKeys: after.sourceFactKeys,
        isAppliedByAi:
          appliedSet.has(slotId) ||
          (currentOrigin === "ai_assisted" && Boolean(parentContent) && hasAfter),
      });
      continue;
    }

    if (before && !after) {
      diffs.push({
        slotId,
        label: before.label,
        subtitle: before.subtitle,
        status: "removed",
        beforeText: before.text,
        afterText: null,
        beforeProvenance: before.provenance,
        afterProvenance: before.provenance,
        sourceFactKeys: before.sourceFactKeys,
        isAppliedByAi: false,
      });
      continue;
    }

    if (before && after) {
      const beforeNorm = (before.text || "").trim();
      const afterNorm = (after.text || "").trim();
      const isTextDifferent = beforeNorm !== afterNorm;
      const isApplied =
        appliedSet.has(slotId) ||
        (currentOrigin === "ai_assisted" && isTextDifferent);

      let status: SlotDiffStatus = "unchanged";
      if (!beforeNorm && afterNorm) {
        status = "added";
      } else if (beforeNorm && !afterNorm) {
        status = "removed";
      } else if (isTextDifferent || appliedSet.has(slotId)) {
        status = "modified";
      } else if (
        preservedUserSet.has(slotId) ||
        after.provenance === "user_authored"
      ) {
        status = "preserved_user_authored";
      } else if (
        preservedManualSet.has(slotId) ||
        after.provenance === "manual_edit"
      ) {
        status = "preserved_manual_edit";
      } else {
        status = "unchanged";
      }

      diffs.push({
        slotId,
        label: after.label,
        subtitle: after.subtitle,
        status,
        beforeText: before.text,
        afterText: after.text,
        beforeProvenance: before.provenance,
        afterProvenance: after.provenance,
        sourceFactKeys: after.sourceFactKeys,
        isAppliedByAi: isApplied,
      });
    }
  }

  return diffs;
}

export function resolveFactReferenceDisplay(
  factKey: string,
  snapshot: Record<string, unknown> | null | undefined
): {
  factKey: string;
  entityTypeLabel: string;
  title: string;
  detail: string | null;
} {
  const prefix = factKey.includes(":") ? factKey.split(":")[0] : "";
  const entityTypeLabel = ENTITY_TYPE_LABELS[prefix] || "Fato confirmado";

  const rawFacts = snapshot && typeof snapshot === "object" ? snapshot.facts : null;
  let factObj: Record<string, unknown> | null = null;

  if (rawFacts && typeof rawFacts === "object" && !Array.isArray(rawFacts)) {
    const candidate = (rawFacts as Record<string, unknown>)[factKey];
    if (candidate && typeof candidate === "object") {
      factObj = candidate as Record<string, unknown>;
    }
  } else if (Array.isArray(rawFacts)) {
    const found = (rawFacts as MaterialSnapshotFactItem[]).find(
      (item) => item && item.fact_key === factKey
    );
    if (found && typeof found === "object") {
      factObj = found as unknown as Record<string, unknown>;
    }
  }

  if (!factObj) {
    return {
      factKey,
      entityTypeLabel,
      title: factKey,
      detail: null,
    };
  }

  const str = (key: string): string | null => {
    const val = factObj?.[key];
    return typeof val === "string" && val.trim() ? val.trim() : null;
  };

  const label = str("label");
  const role = str("role");
  const company = str("company");
  const name = str("name");
  const profTitle = str("professional_title");
  const fullName = str("full_name");
  const course = str("course");
  const institution = str("institution");
  const langName = str("language_name");
  const summary = str("summary");
  const periodLabel = str("period_label");

  let title = factKey;
  if (label) {
    title = label;
  } else if (role && company) {
    title = `${role} — ${company}`;
  } else if (name) {
    title = role ? `${name} (${role})` : name;
  } else if (profTitle) {
    title = fullName ? `${fullName} · ${profTitle}` : profTitle;
  } else if (course) {
    title = institution ? `${course} — ${institution}` : course;
  } else if (langName) {
    title = langName;
  }

  const detail = summary || periodLabel || null;

  return {
    factKey,
    entityTypeLabel,
    title,
    detail,
  };
}

function formatRetryAfterFriendly(seconds: number | null): string | null {
  if (!seconds || seconds <= 0) return null;
  if (seconds < 60) {
    return `Tempo estimado de espera: ${seconds} segundo(s).`;
  }
  const minutes = Math.ceil(seconds / 60);
  return `Tempo estimado de espera: cerca de ${minutes} minuto(s) (${seconds}s).`;
}

export function formatAIErrorPresentation(error: unknown): AIErrorPresentation {
  if (error instanceof ApiError) {
    const code = (error.errorCode || "").toLowerCase();
    const retryAfterLabel = formatRetryAfterFriendly(error.retryAfterSeconds);

    if (error.status === 429 || code.startsWith("quota_exceeded")) {
      const scopePart = code.includes(":") ? code.split(":")[1] : "";
      const scopeLabel =
        scopePart === "global_daily"
          ? "limite diário global da instância"
          : scopePart === "user_daily"
            ? "limite diário da sua conta"
            : scopePart === "user_burst"
              ? "limite de requisições por janela curta"
              : "limite de uso de IA";
      return {
        title: `Quota de IA atingida (${scopeLabel})`,
        description:
          error.message ||
          "O limite de aprimoramentos por IA foi atingido no momento. Aguarde antes de enviar uma nova solicitação.",
        errorCodeBadge: error.errorCode || "quota_exceeded",
        retryAfterLabel,
        canReloadMaterial: false,
        severity: "warning",
      };
    }

    if (code === "ai_disabled" || code === "ai_misconfigured") {
      return {
        title: "Aprimoramento por IA indisponível nesta instância",
        description:
          error.message ||
          "O serviço de aprimoramento assistido por IA está desabilitado ou não configurado. Você pode continuar editando, derivando e aprovando versões manualmente.",
        errorCodeBadge: error.errorCode,
        retryAfterLabel: null,
        canReloadMaterial: false,
        severity: "warning",
      };
    }

    if (code === "circuit_open" || error.status === 503) {
      return {
        title: "Proteção contra falhas ativa (Circuit Breaker)",
        description:
          error.message ||
          "O serviço de IA entrou temporariamente em modo de proteção após instabilidades do provedor. Suas versões existentes permanecem íntegras.",
        errorCodeBadge: error.errorCode || "circuit_open",
        retryAfterLabel,
        canReloadMaterial: false,
        severity: "warning",
      };
    }

    if (code === "stale_source_version") {
      return {
        title: "Versão de origem desatualizada ou alterada concorrentemente",
        description:
          error.message ||
          "Uma versão mais recente deste material foi criada ou o estado do material mudou. Recarregue o material para trabalhar sobre a versão ativa atual.",
        errorCodeBadge: "stale_source_version",
        retryAfterLabel: null,
        canReloadMaterial: true,
        severity: "warning",
      };
    }

    if (code === "review_state_conflict" || error.status === 409) {
      return {
        title: "Conflito de estado da versão",
        description:
          error.message ||
          "Esta versão já foi aprovada, rejeitada, vinculada a uma candidatura ou não permite mais esta operação. Recarregue o material para sincronizar o estado atual.",
        errorCodeBadge: error.errorCode || "review_state_conflict",
        retryAfterLabel: null,
        canReloadMaterial: true,
        severity: "warning",
      };
    }

    if (code === "grounding_rejected" || code === "overlay_conflict" || error.status === 422) {
      return {
        title:
          code === "grounding_rejected"
            ? "Sugestão bloqueada pelo validador factual (Grounding Gate)"
            : "Validação estruturada não concluída",
        description:
          error.message ||
          "A sugestão retornada pela IA não atendeu às regras estritas de fidelidade factual ou elegibilidade de slots e foi descartada com segurança.",
        errorCodeBadge: error.errorCode || "validation_rejected",
        retryAfterLabel: null,
        canReloadMaterial: false,
        severity: "destructive",
      };
    }

    if (code === "provider_timeout" || error.status === 504) {
      return {
        title: "Tempo limite do provedor de IA excedido",
        description:
          error.message ||
          "O provedor de IA demorou mais que o limite permitido para responder. Nenhuma alteração parcial foi aplicada; tente novamente.",
        errorCodeBadge: error.errorCode || "provider_timeout",
        retryAfterLabel,
        canReloadMaterial: false,
        severity: "warning",
      };
    }

    if (
      code === "malformed_output" ||
      code === "provider_error" ||
      error.status === 502
    ) {
      return {
        title: "Falha temporária na resposta do provedor de IA",
        description:
          error.message ||
          "O provedor de IA retornou uma resposta inválida ou indisponível. Sua versão original foi preservada integralmente.",
        errorCodeBadge: error.errorCode || "provider_error",
        retryAfterLabel,
        canReloadMaterial: false,
        severity: "destructive",
      };
    }

    return {
      title: `Não foi possível concluir a operação (HTTP ${error.status})`,
      description: error.message || "Ocorreu um erro ao processar sua solicitação.",
      errorCodeBadge: error.errorCode,
      retryAfterLabel,
      canReloadMaterial: error.status === 409,
      severity: "destructive",
    };
  }

  return {
    title: "Falha de comunicação ou erro inesperado",
    description:
      error instanceof Error && error.message
        ? error.message
        : "Não foi possível comunicar com o servidor. Verifique sua conexão e tente novamente.",
    errorCodeBadge: null,
    retryAfterLabel: null,
    canReloadMaterial: false,
    severity: "destructive",
  };
}

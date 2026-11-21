import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  Check,
  CheckCircle2,
  Copy,
  Download,
  FileCheck2,
  FileText,
  GitBranch,
  History,
  Link2,
  Lock,
  Plus,
  RefreshCw,
  ShieldAlert,
  Sparkles,
  Trash2,
  Unlink2,
  X,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input, Label } from "@/components/ui/input";
import { api } from "@/lib/api";
import { DocumentPreviewCard } from "@/components/materials/DocumentPreviewCard";
import {
  formatAIErrorPresentation,
  type AIErrorPresentation,
} from "@/components/materials/aiStudioUtils";
import { MaterialAIStudioPanel } from "@/components/materials/MaterialAIStudioPanel";
import {
  ApplicationAnswersEditor,
  CoverLetterEditor,
  FreelanceProposalEditor,
  RecruiterMessageEditor,
} from "@/components/materials/MaterialTypeEditors";
import type {
  AnyMaterialStructuredContent,
  ApplicationAnswersStructuredContent,
  ContactInclusionOptions,
  CoverLetterStructuredContent,
  DocumentDownloadFormat,
  DocumentTemplateId,
  FreelanceProposalStructuredContent,
  MaterialAIEnhancePayload,
  MaterialBlockProvenance,
  MaterialDetailResponse,
  MaterialExportFormat,
  MaterialPreAnalysisResponse,
  MaterialTargetLanguage,
  MaterialTypeValue,
  MaterialVersionItem,
  ProfileConfirmBatchPayload,
  RecruiterChannel,
  RecruiterMessageStructuredContent,
  ResumeExperienceItem,
  ResumeManualNoteItem,
  ResumeProjectItem,
  ResumeStructuredContent,
  UnconfirmedWarningItem,
} from "@/types/api";

interface MaterialWorkspaceModalProps {
  open: boolean;
  onClose: () => void;
  opportunityId?: string | null;
  applicationId?: string | null;
  targetTitle?: string | null;
  initialMaterialId?: string | null;
  onMaterialChanged?: () => void;
  onNavigateProfile?: () => void;
}

type WorkspacePanelTab = "editor" | "ai_studio" | "preview" | "history";

const DEFAULT_CONTACT_OPTIONS: ContactInclusionOptions = {
  include_email: true,
  include_phone: false,
  include_location: true,
  include_links: true,
};

const PROVENANCE_META: Record<
  MaterialBlockProvenance,
  { label: string; variant: "default" | "secondary" | "outline" }
> = {
  confirmed_fact: { label: "Fato confirmado", variant: "secondary" },
  manual_edit: { label: "Editado manualmente", variant: "outline" },
  user_authored: { label: "Autoral (manual)", variant: "outline" },
};

const ORIGIN_LABELS: Record<string, string> = {
  generated: "Gerado",
  manual_edit: "Editado",
  regenerated: "Regenerado",
  derived: "Derivado",
  ai_assisted: "IA assistida",
};

const ENTITY_TYPE_LABELS: Record<string, string> = {
  profile: "Perfil",
  experience: "Experiência",
  project: "Projeto",
  education: "Formação",
  skill: "Habilidade",
  language: "Idioma",
};

const MATERIAL_TYPE_OPTIONS: Array<{
  value: MaterialTypeValue;
  label: string;
  shortLabel: string;
  ctaLabel: string;
  description: string;
}> = [
  {
    value: "resume",
    label: "Currículo Direcionado",
    shortLabel: "Currículo",
    ctaLabel: "Gerar Currículo Direcionado",
    description: "Seções estruturadas com fatos confirmados.",
  },
  {
    value: "cover_letter",
    label: "Carta de Apresentação",
    shortLabel: "Carta",
    ctaLabel: "Gerar Carta de Apresentação",
    description: "Apresentação objetiva conectando trajetória e requisitos.",
  },
  {
    value: "recruiter_message",
    label: "Mensagem para Recrutador",
    shortLabel: "Mensagem",
    ctaLabel: "Gerar Mensagem para Recrutador",
    description: "Texto curto e direto para LinkedIn, e-mail ou formulário.",
  },
  {
    value: "freelance_proposal",
    label: "Proposta Freelance",
    shortLabel: "Proposta",
    ctaLabel: "Gerar Proposta Freelance",
    description: "Escopo técnico e evidências sem presumir preço ou prazo.",
  },
  {
    value: "application_answers",
    label: "Respostas de Candidatura",
    shortLabel: "Respostas",
    ctaLabel: "Gerar Respostas de Candidatura",
    description: "Responde perguntas da vaga com rastreabilidade ou solicita sua entrada.",
  },
];

const MATERIAL_TYPE_SHORT_LABELS: Record<string, string> = {
  resume: "Currículo",
  cover_letter: "Carta de Apresentação",
  recruiter_message: "Mensagem",
  freelance_proposal: "Proposta Freelance",
  application_answers: "Respostas",
};

function formatDateTimePtBr(iso: string | null | undefined): string {
  if (!iso) return "—";
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return iso;
  return parsed.toLocaleString("pt-BR");
}

function warningSelectionKey(item: UnconfirmedWarningItem): string {
  return `${item.entity_type}:${item.entity_id}`;
}

export const MaterialWorkspaceModal: React.FC<MaterialWorkspaceModalProps> = ({
  open,
  onClose,
  opportunityId = null,
  applicationId = null,
  targetTitle = null,
  initialMaterialId = null,
  onMaterialChanged,
  onNavigateProfile,
}) => {
  const [selectedMaterialType, setSelectedMaterialType] =
    useState<MaterialTypeValue>("resume");
  const [targetLanguage, setTargetLanguage] =
    useState<MaterialTargetLanguage>("pt-BR");
  const [contactOptions, setContactOptions] = useState<ContactInclusionOptions>(
    DEFAULT_CONTACT_OPTIONS
  );
  const [customTitle, setCustomTitle] = useState("");
  const [userInstructions, setUserInstructions] = useState("");

  // Opções contextuais (Subfase 04.2)
  const [recruiterChannel, setRecruiterChannel] =
    useState<RecruiterChannel>("linkedin");
  const [contactName, setContactName] = useState("");
  const [contactContext, setContactContext] = useState("");
  const [freelanceAvailability, setFreelanceAvailability] = useState("");
  const [freelanceDelivery, setFreelanceDelivery] = useState("");
  const [freelanceBudget, setFreelanceBudget] = useState("");
  const [freelanceScopeNotes, setFreelanceScopeNotes] = useState("");
  const [questionDrafts, setQuestionDrafts] = useState<string[]>([""]);

  const [preAnalysis, setPreAnalysis] =
    useState<MaterialPreAnalysisResponse | null>(null);
  const [preLoading, setPreLoading] = useState(false);
  const [selectedBatchKeys, setSelectedBatchKeys] = useState<string[]>([]);
  const [confirmingBatch, setConfirmingBatch] = useState(false);

  const [material, setMaterial] = useState<MaterialDetailResponse | null>(null);
  const [activeVersionId, setActiveVersionId] = useState<string | null>(null);
  const [draftContent, setDraftContent] =
    useState<AnyMaterialStructuredContent | null>(null);
  const [panelTab, setPanelTab] = useState<WorkspacePanelTab>("editor");

  const [busyAction, setBusyAction] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [copiedFormat, setCopiedFormat] =
    useState<MaterialExportFormat | null>(null);
  const [selectedTemplate, setSelectedTemplate] =
    useState<DocumentTemplateId>("classic_ats");
  const [previewMode, setPreviewMode] = useState<"document" | "markdown">(
    "document"
  );
  const [downloadingFormat, setDownloadingFormat] =
    useState<DocumentDownloadFormat | null>(null);
  const [aiEnhancing, setAiEnhancing] = useState(false);
  const [aiError, setAiError] = useState<AIErrorPresentation | null>(null);
  const [isDerivingEditMode, setIsDerivingEditMode] = useState(false);

  const isMountedRef = useRef(true);
  const isOpenRef = useRef(open);
  const activeMaterialIdRef = useRef<string | null>(material?.id ?? null);
  const aiEnhanceRequestIdRef = useRef(0);

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
      aiEnhanceRequestIdRef.current += 1;
    };
  }, []);

  useEffect(() => {
    isOpenRef.current = open;
    if (!open) {
      aiEnhanceRequestIdRef.current += 1;
      setAiEnhancing(false);
      setBusyAction(false);
    }
  }, [open]);

  useEffect(() => {
    activeMaterialIdRef.current = material?.id ?? null;
  }, [material?.id]);

  const buildWritingOptionsPayload = useCallback(() => {
    const cleanedQuestions = questionDrafts
      .map((q) => q.trim())
      .filter((q) => q.length >= 3);
    return {
      channel: recruiterChannel,
      contact_name: contactName.trim() || null,
      contact_context: contactContext.trim() || null,
      freelance_inputs: {
        availability: freelanceAvailability.trim() || null,
        estimated_delivery: freelanceDelivery.trim() || null,
        budget_or_price: freelanceBudget.trim() || null,
        scope_clarifications: freelanceScopeNotes.trim() || null,
      },
      questions: cleanedQuestions,
    };
  }, [
    contactContext,
    contactName,
    freelanceAvailability,
    freelanceBudget,
    freelanceDelivery,
    freelanceScopeNotes,
    questionDrafts,
    recruiterChannel,
  ]);

  const loadPreAnalysis = useCallback(
    async (
      lang: MaterialTargetLanguage,
      opts: ContactInclusionOptions,
      matType: MaterialTypeValue = selectedMaterialType
    ) => {
      setPreLoading(true);
      setErrorMsg(null);
      try {
        const res = await api.materials.preAnalyze({
          opportunity_id: opportunityId || null,
          application_id: applicationId || null,
          ...(matType !== "resume"
            ? {
                material_type: matType,
                writing_options: buildWritingOptionsPayload(),
              }
            : {}),
          target_language: lang,
          contact_options: opts,
        });
        setPreAnalysis(res);
      } catch (err) {
        setErrorMsg(
          err instanceof Error
            ? err.message
            : "Não foi possível analisar os fatos confirmados do perfil."
        );
      } finally {
        setPreLoading(false);
      }
    },
    [
      applicationId,
      buildWritingOptionsPayload,
      opportunityId,
      selectedMaterialType,
    ]
  );

  const loadExistingMaterial = useCallback(async (matId: string) => {
    aiEnhanceRequestIdRef.current += 1;
    setAiEnhancing(false);
    setBusyAction(true);
    setErrorMsg(null);
    setAiError(null);
    setIsDerivingEditMode(false);
    try {
      const detail = await api.materials.get(matId);
      if (!isMountedRef.current || !isOpenRef.current) return;
      setMaterial(detail);
      const preferred =
        (detail.latest_active_version_id
          ? detail.versions.find((v) => v.id === detail.latest_active_version_id)
          : null) ||
        detail.versions.find((v) => !v.is_rejected) ||
        detail.versions[0] ||
        null;
      setActiveVersionId(preferred?.id || null);
      setDraftContent(preferred ? preferred.structured_content : null);
      if (detail.target_language === "en" || detail.target_language === "pt-BR") {
        setTargetLanguage(detail.target_language);
      }
    } catch (err) {
      if (!isMountedRef.current || !isOpenRef.current) return;
      setErrorMsg(
        err instanceof Error
          ? err.message
          : "Não foi possível carregar o material selecionado."
      );
    } finally {
      if (isMountedRef.current && isOpenRef.current) {
        setBusyAction(false);
      }
    }
  }, []);

  useEffect(() => {
    if (!open) return;
    setErrorMsg(null);
    setSuccessMsg(null);
    setSelectedBatchKeys([]);
    setCopiedFormat(null);
    if (initialMaterialId) {
      setPreAnalysis(null);
      void loadExistingMaterial(initialMaterialId);
    } else {
      setMaterial(null);
      setActiveVersionId(null);
      setDraftContent(null);
      setCustomTitle("");
      setUserInstructions("");
      setContactName("");
      setContactContext("");
      setFreelanceAvailability("");
      setFreelanceDelivery("");
      setFreelanceBudget("");
      setFreelanceScopeNotes("");
      setQuestionDrafts([""]);
      void loadPreAnalysis(targetLanguage, contactOptions, selectedMaterialType);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    open,
    initialMaterialId,
    loadExistingMaterial,
    targetLanguage,
    contactOptions,
    selectedMaterialType,
  ]);

  const latestActiveVersion: MaterialVersionItem | null = useMemo(() => {
    if (!material || material.versions.length === 0) return null;
    if (material.latest_active_version_id) {
      const matched = material.versions.find(
        (v) => v.id === material.latest_active_version_id
      );
      if (matched) return matched;
    }
    return (
      material.versions.find((v) => !v.is_rejected) || material.versions[0]
    );
  }, [material]);

  const activeVersion: MaterialVersionItem | null = useMemo(() => {
    if (!material || material.versions.length === 0) return null;
    if (activeVersionId) {
      return (
        material.versions.find((v) => v.id === activeVersionId) ||
        latestActiveVersion ||
        material.versions[0]
      );
    }
    return latestActiveVersion || material.versions[0];
  }, [activeVersionId, latestActiveVersion, material]);

  useEffect(() => {
    if (activeVersion) {
      setDraftContent(activeVersion.structured_content);
      setIsDerivingEditMode(false);
    }
  }, [activeVersion]);

  const activeLinkForCurrentApp = useMemo(() => {
    if (!material || !applicationId) return null;
    return (
      material.links.find(
        (lk) => lk.application_id === applicationId && lk.is_active
      ) || null
    );
  }, [applicationId, material]);

  if (!open) return null;

  const pendingConfirmItems = (preAnalysis?.unconfirmed_warnings || []).filter(
    (item) => item.can_batch_confirm
  );
  const draftItems = (preAnalysis?.unconfirmed_warnings || []).filter(
    (item) => !item.can_batch_confirm
  );

  const toggleBatchItem = (item: UnconfirmedWarningItem) => {
    const key = warningSelectionKey(item);
    setSelectedBatchKeys((prev) =>
      prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]
    );
  };

  const handleConfirmSelectedBatch = async () => {
    if (selectedBatchKeys.length === 0) return;
    setConfirmingBatch(true);
    setErrorMsg(null);
    setSuccessMsg(null);
    try {
      const payload: ProfileConfirmBatchPayload = {
        profile_confirmed: false,
        experience_ids: [],
        education_ids: [],
        skill_ids: [],
        language_ids: [],
        project_ids: [],
      };
      for (const item of pendingConfirmItems) {
        if (!selectedBatchKeys.includes(warningSelectionKey(item))) continue;
        if (item.entity_type === "profile") payload.profile_confirmed = true;
        if (item.entity_type === "experience")
          payload.experience_ids?.push(item.entity_id);
        if (item.entity_type === "education")
          payload.education_ids?.push(item.entity_id);
        if (item.entity_type === "skill")
          payload.skill_ids?.push(item.entity_id);
        if (item.entity_type === "language")
          payload.language_ids?.push(item.entity_id);
        if (item.entity_type === "project")
          payload.project_ids?.push(item.entity_id);
      }

      const result = await api.profileConfirmBatch(payload);
      setSelectedBatchKeys([]);
      setSuccessMsg(
        `${result.total_confirmed} item(ns) confirmado(s) no seu Perfil. Pré-análise atualizada.`
      );
      await loadPreAnalysis(targetLanguage, contactOptions, selectedMaterialType);
    } catch (err) {
      setErrorMsg(
        err instanceof Error
          ? err.message
          : "Falha ao confirmar os itens selecionados em lote."
      );
    } finally {
      setConfirmingBatch(false);
    }
  };

  const handleGenerateMaterial = async () => {
    setBusyAction(true);
    setErrorMsg(null);
    setSuccessMsg(null);
    try {
      const created = await api.materials.create({
        opportunity_id: opportunityId || null,
        application_id: applicationId || null,
        ...(selectedMaterialType !== "resume"
          ? {
              material_type: selectedMaterialType,
              writing_options: buildWritingOptionsPayload(),
            }
          : {}),
        title: customTitle.trim() ? customTitle.trim() : null,
        target_language: targetLanguage,
        contact_options: contactOptions,
        user_instructions: userInstructions.trim()
          ? userInstructions.trim()
          : null,
      });
      setMaterial(created);
      const latest = created.versions[0] || null;
      setActiveVersionId(latest?.id || null);
      setDraftContent(latest?.structured_content || null);
      setPanelTab("editor");
      setSuccessMsg(
        selectedMaterialType === "resume"
          ? "Currículo determinístico gerado exclusivamente com fatos confirmados."
          : `${MATERIAL_TYPE_SHORT_LABELS[selectedMaterialType] || "Material"} gerado(a) exclusivamente com fatos confirmados.`
      );
      onMaterialChanged?.();
    } catch (err) {
      setErrorMsg(
        err instanceof Error
          ? err.message
          : "Não foi possível gerar o material."
      );
    } finally {
      setBusyAction(false);
    }
  };

  const handleSaveDraft = async () => {
    if (!material || !activeVersion || !draftContent) return;
    setBusyAction(true);
    setErrorMsg(null);
    setSuccessMsg(null);
    try {
      const updated = await api.materials.updateVersion(
        material.id,
        activeVersion.id,
        {
          structured_content: draftContent,
        }
      );
      setMaterial(updated);
      setSuccessMsg("Alterações salvas na versão atual.");
      onMaterialChanged?.();
    } catch (err) {
      setErrorMsg(
        err instanceof Error
          ? err.message
          : "Não foi possível salvar a edição."
      );
    } finally {
      setBusyAction(false);
    }
  };

  const handleDeriveVersion = async () => {
    if (!material || !activeVersion) return;
    setBusyAction(true);
    setErrorMsg(null);
    setSuccessMsg(null);
    try {
      const updated = await api.materials.deriveVersion(
        material.id,
        activeVersion.id,
        {}
      );
      setMaterial(updated);
      const newest = updated.versions[0];
      if (newest) setActiveVersionId(newest.id);
      setPanelTab("editor");
      setSuccessMsg(
        `Versão v${newest?.version_number || ""} derivada e aberta para edição.`
      );
      onMaterialChanged?.();
    } catch (err) {
      setErrorMsg(
        err instanceof Error
          ? err.message
          : "Falha ao derivar nova versão."
      );
    } finally {
      setBusyAction(false);
    }
  };

  const handleRegenerate = async () => {
    if (!material) return;
    setBusyAction(true);
    setErrorMsg(null);
    setSuccessMsg(null);
    try {
      const updated = await api.materials.regenerate(material.id, {
        target_language: targetLanguage,
        contact_options: contactOptions,
        user_instructions: userInstructions.trim() || null,
      });
      setMaterial(updated);
      const newest = updated.versions[0];
      if (newest) setActiveVersionId(newest.id);
      setPanelTab("preview");
      setSuccessMsg(
        `Nova versão v${newest?.version_number || ""} regenerada a partir dos fatos confirmados atuais.`
      );
      onMaterialChanged?.();
    } catch (err) {
      setErrorMsg(
        err instanceof Error
          ? err.message
          : "Falha ao regenerar currículo a partir do perfil."
      );
    } finally {
      setBusyAction(false);
    }
  };

  const handleApproveVersion = async () => {
    if (!material || !activeVersion || activeVersion.is_rejected) return;
    setBusyAction(true);
    setErrorMsg(null);
    setAiError(null);
    setSuccessMsg(null);
    try {
      const updated = await api.materials.approveVersion(
        material.id,
        activeVersion.id
      );
      setMaterial(updated);
      setIsDerivingEditMode(false);
      setSuccessMsg(
        `Versão v${activeVersion.version_number} aprovada e bloqueada contra mutações.`
      );
      onMaterialChanged?.();
    } catch (err) {
      const formatted = formatAIErrorPresentation(err);
      setAiError(formatted);
      setErrorMsg(
        err instanceof Error ? err.message : "Falha ao aprovar versão."
      );
    } finally {
      setBusyAction(false);
    }
  };

  const handleRunAiEnhance = async (payload: MaterialAIEnhancePayload) => {
    if (!material || !activeVersion || busyAction || aiEnhancing) return;
    const requestId = ++aiEnhanceRequestIdRef.current;
    const requestedMaterialId = material.id;
    const isStaleRequest = () =>
      !isMountedRef.current ||
      !isOpenRef.current ||
      aiEnhanceRequestIdRef.current !== requestId ||
      activeMaterialIdRef.current !== requestedMaterialId;

    setAiEnhancing(true);
    setBusyAction(true);
    setErrorMsg(null);
    setAiError(null);
    setSuccessMsg(null);
    try {
      const updated = await api.materials.aiEnhanceVersion(
        material.id,
        activeVersion.id,
        payload
      );
      if (isStaleRequest()) return;
      setMaterial(updated);
      const newest = updated.versions[0] || null;
      if (newest) {
        setActiveVersionId(newest.id);
        setDraftContent(newest.structured_content);
      }
      setIsDerivingEditMode(false);
      setPanelTab("ai_studio");
      setSuccessMsg(
        `Sugestão de IA v${newest?.version_number || ""} gerada como rascunho não aprovado. Revise a comparação estruturada e escolha uma decisão humana.`
      );
      onMaterialChanged?.();
    } catch (err) {
      if (isStaleRequest()) return;
      const formatted = formatAIErrorPresentation(err);
      setAiError(formatted);
      setErrorMsg(formatted.description);
    } finally {
      if (!isStaleRequest()) {
        setAiEnhancing(false);
        setBusyAction(false);
      }
    }
  };

  const handleRejectAiVersion = async () => {
    if (!material || !activeVersion || busyAction) return;
    setBusyAction(true);
    setErrorMsg(null);
    setAiError(null);
    setSuccessMsg(null);
    try {
      const rejectedVerNum = activeVersion.version_number;
      const updated = await api.materials.rejectAiVersion(
        material.id,
        activeVersion.id
      );
      setMaterial(updated);
      const restored =
        (updated.latest_active_version_id
          ? updated.versions.find(
              (v) => v.id === updated.latest_active_version_id
            )
          : null) ||
        updated.versions.find((v) => !v.is_rejected) ||
        updated.versions[0] ||
        null;
      setActiveVersionId(restored?.id || null);
      setDraftContent(restored ? restored.structured_content : null);
      setIsDerivingEditMode(false);
      setSuccessMsg(
        `Sugestão de IA v${rejectedVerNum} rejeitada e mantida no histórico como rejeitada. A versão ativa voltou para v${restored?.version_number || ""}.`
      );
      onMaterialChanged?.();
    } catch (err) {
      const formatted = formatAIErrorPresentation(err);
      setAiError(formatted);
      setErrorMsg(formatted.description);
    } finally {
      setBusyAction(false);
    }
  };

  const handleStartDeriveEdit = () => {
    if (!activeVersion || activeVersion.is_rejected) return;
    setDraftContent(activeVersion.structured_content);
    setIsDerivingEditMode(true);
    setPanelTab("editor");
    setSuccessMsg(
      `Modo de edição derivada ativado a partir da sugestão v${activeVersion.version_number}. Edite os blocos desejados e clique em "Salvar versão derivada".`
    );
  };

  const handleCancelDeriveEdit = () => {
    if (activeVersion) {
      setDraftContent(activeVersion.structured_content);
    }
    setIsDerivingEditMode(false);
    setSuccessMsg(null);
  };

  const handleSaveDerivedFromAi = async () => {
    if (!material || !activeVersion || !draftContent || busyAction) return;
    setBusyAction(true);
    setErrorMsg(null);
    setAiError(null);
    setSuccessMsg(null);
    try {
      const updated = await api.materials.deriveVersion(
        material.id,
        activeVersion.id,
        {
          structured_content: draftContent,
        }
      );
      setMaterial(updated);
      const newest = updated.versions[0] || null;
      if (newest) {
        setActiveVersionId(newest.id);
        setDraftContent(newest.structured_content);
      }
      setIsDerivingEditMode(false);
      setPanelTab("editor");
      setSuccessMsg(
        `Versão v${newest?.version_number || ""} salva como versão derivada editável a partir da sugestão v${activeVersion.version_number}.`
      );
      onMaterialChanged?.();
    } catch (err) {
      const formatted = formatAIErrorPresentation(err);
      setAiError(formatted);
      setErrorMsg(formatted.description);
    } finally {
      setBusyAction(false);
    }
  };

  const handleReloadCurrentMaterial = async () => {
    if (!material) return;
    await loadExistingMaterial(material.id);
  };

  const handleLinkToApplication = async () => {
    if (!material || !activeVersion || !applicationId) return;
    setBusyAction(true);
    setErrorMsg(null);
    setSuccessMsg(null);
    try {
      const updated = await api.materials.link(material.id, {
        application_id: applicationId,
        version_id: activeVersion.id,
      });
      setMaterial(updated);
      setSuccessMsg(
        `Versão v${activeVersion.version_number} vinculada a esta candidatura.`
      );
      onMaterialChanged?.();
    } catch (err) {
      setErrorMsg(
        err instanceof Error
          ? err.message
          : "Falha ao vincular versão à candidatura."
      );
    } finally {
      setBusyAction(false);
    }
  };

  const handleUnlinkFromApplication = async () => {
    if (!material || !applicationId) return;
    setBusyAction(true);
    setErrorMsg(null);
    setSuccessMsg(null);
    try {
      const updated = await api.materials.unlink(material.id, {
        application_id: applicationId,
      });
      setMaterial(updated);
      setSuccessMsg(
        "Vínculo desativado nesta candidatura (histórico mantido)."
      );
      onMaterialChanged?.();
    } catch (err) {
      setErrorMsg(
        err instanceof Error ? err.message : "Falha ao desvincular material."
      );
    } finally {
      setBusyAction(false);
    }
  };

  const handleCopyExport = async (fmt: MaterialExportFormat) => {
    if (!material || !activeVersion || activeVersion.is_rejected) return;
    setBusyAction(true);
    setErrorMsg(null);
    try {
      const exported = await api.materials.exportVersion(
        material.id,
        activeVersion.id,
        fmt
      );
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(exported.content);
      }
      setCopiedFormat(fmt);
      setTimeout(() => setCopiedFormat(null), 2500);
    } catch (err) {
      setErrorMsg(
        err instanceof Error ? err.message : "Falha ao exportar conteúdo."
      );
    } finally {
      setBusyAction(false);
    }
  };

  const handleDownloadBinary = async (fmt: DocumentDownloadFormat) => {
    if (!material || !activeVersion || activeVersion.is_rejected) return;
    if (activeVersion.has_blocking_pending_fields) return;
    setDownloadingFormat(fmt);
    setErrorMsg(null);
    setSuccessMsg(null);
    try {
      const result = await api.materials.downloadVersion(
        material.id,
        activeVersion.id,
        {
          format: fmt,
          template: selectedTemplate,
          allow_draft: !activeVersion.is_approved,
        }
      );
      setSuccessMsg(`Download concluído: ${result.filename}`);
    } catch (err) {
      setErrorMsg(
        err instanceof Error
          ? err.message
          : `Falha ao baixar arquivo ${fmt.toUpperCase()}.`
      );
    } finally {
      setDownloadingFormat(null);
    }
  };

  const updateExperienceItem = (
    idx: number,
    patch: Partial<ResumeExperienceItem>
  ) => {
    if (!draftContent || "material_type" in draftContent) return;
    const next = [...draftContent.experiences];
    next[idx] = { ...next[idx], ...patch, provenance: "manual_edit" };
    setDraftContent({ ...draftContent, experiences: next });
  };

  const updateProjectItem = (
    idx: number,
    patch: Partial<ResumeProjectItem>
  ) => {
    if (!draftContent || "material_type" in draftContent) return;
    const next = [...draftContent.projects];
    next[idx] = { ...next[idx], ...patch, provenance: "manual_edit" };
    setDraftContent({ ...draftContent, projects: next });
  };

  const addManualNote = () => {
    if (!draftContent || "material_type" in draftContent) return;
    const newNote: ResumeManualNoteItem = {
      id: `note-${Date.now()}`,
      title: "Observação adicional",
      content: "Inclua aqui detalhes autorais verificados por você.",
      source_fact_keys: [],
      provenance: "user_authored",
    };
    setDraftContent({
      ...draftContent,
      manual_notes: [...draftContent.manual_notes, newNote],
    });
  };

  const resumeDraft =
    draftContent && !("material_type" in draftContent)
      ? (draftContent as ResumeStructuredContent)
      : null;

  const canEditDraft = Boolean(
    activeVersion &&
      !activeVersion.is_rejected &&
      (activeVersion.is_mutable || isDerivingEditMode)
  );

  const selectedTypeMeta =
    MATERIAL_TYPE_OPTIONS.find((opt) => opt.value === selectedMaterialType) ||
    MATERIAL_TYPE_OPTIONS[0];
  const validQuestionsCount = questionDrafts.filter(
    (q) => q.trim().length >= 3
  ).length;
  const missingRequiredQuestions =
    selectedMaterialType === "application_answers" && validQuestionsCount === 0;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 p-2 backdrop-blur-sm sm:p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Estúdio de Materiais e Candidaturas"
    >
      <div className="relative flex max-h-[92vh] w-full max-w-5xl flex-col overflow-hidden rounded-2xl border border-border bg-card shadow-2xl">
        {/* Cabeçalho */}
        <div className="flex flex-wrap items-start justify-between gap-3 border-b border-border bg-muted/30 px-4 py-3.5 sm:px-6">
          <div className="space-y-1">
            <div className="flex flex-wrap items-center gap-2">
              <FileText className="h-5 w-5 text-primary" />
              <h2 className="text-base font-bold text-foreground sm:text-lg">
                {material ? material.title : "Estúdio de Materiais para Candidatura"}
              </h2>
              <Badge variant="outline" className="text-[11px]">
                {MATERIAL_TYPE_SHORT_LABELS[
                  material?.material_type || selectedMaterialType
                ] || "Material"}
              </Badge>
              <Badge variant="secondary" className="text-[11px]">
                Fatos confirmados · Revisão humana
              </Badge>
            </div>
            <p className="text-xs text-muted-foreground">
              {targetTitle ||
                material?.opportunity_title ||
                "Baseado exclusivamente em fatos confirmados no seu Perfil."}
            </p>
          </div>

          <div className="flex items-center gap-2">
            {material && !initialMaterialId && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => {
                  aiEnhanceRequestIdRef.current += 1;
                  setAiEnhancing(false);
                  setMaterial(null);
                  setActiveVersionId(null);
                  void loadPreAnalysis(
                    targetLanguage,
                    contactOptions,
                    selectedMaterialType
                  );
                }}
              >
                Nova geração
              </Button>
            )}
            <Button
              type="button"
              variant="ghost"
              size="icon"
              onClick={onClose}
              aria-label="Fechar janela de material"
            >
              <X className="h-4 w-4" />
            </Button>
          </div>
        </div>

        {/* Corpo com rolagem */}
        <div className="flex-1 space-y-4 overflow-y-auto p-4 sm:p-6">
          {errorMsg && (
            <div className="flex items-start gap-2 rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-xs text-destructive">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{errorMsg}</span>
            </div>
          )}
          {successMsg && (
            <div className="flex items-start gap-2 rounded-lg border border-emerald-500/40 bg-emerald-500/10 p-3 text-xs text-emerald-700 dark:text-emerald-300">
              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{successMsg}</span>
            </div>
          )}

          {/* MODO 1: PRÉ-ANÁLISE E GERAÇÃO */}
          {!material && (
            <div className="space-y-4">
              {/* Seletor de Tipo de Material (Subfase 04.2) */}
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm">
                    Tipo de Material e Configurações
                  </CardTitle>
                  <CardDescription className="text-xs">
                    Escolha o formato desejado, o idioma de saída e os dados
                    contextuais. Fatos não confirmados nunca são inventados.
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="space-y-1.5">
                    <Label>Tipo de material</Label>
                    <div
                      role="radiogroup"
                      aria-label="Selecionar tipo de material"
                      className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3"
                    >
                      {MATERIAL_TYPE_OPTIONS.map((opt) => {
                        const isSelected = selectedMaterialType === opt.value;
                        const compatibleList =
                          preAnalysis?.compatible_material_types || [
                            "resume",
                            "cover_letter",
                            "recruiter_message",
                            "application_answers",
                          ];
                        const isRecommended = compatibleList.includes(opt.value);
                        return (
                          <button
                            key={opt.value}
                            type="button"
                            role="radio"
                            aria-checked={isSelected}
                            onClick={() => setSelectedMaterialType(opt.value)}
                            className={`flex flex-col items-start gap-1 rounded-xl border p-3 text-left text-xs transition-colors ${
                              isSelected
                                ? "border-primary bg-primary/10 text-foreground"
                                : "border-border bg-background text-muted-foreground hover:text-foreground"
                            }`}
                          >
                            <div className="flex w-full flex-wrap items-center justify-between gap-1">
                              <span className="font-semibold text-foreground">
                                {opt.label}
                              </span>
                              <Badge
                                variant={isRecommended ? "secondary" : "outline"}
                                className="text-[10px]"
                              >
                                {isRecommended ? "Recomendado" : "Sob solicitação"}
                              </Badge>
                            </div>
                            <span className="text-[11px] leading-snug">
                              {opt.description}
                            </span>
                          </button>
                        );
                      })}
                    </div>
                  </div>

                  <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                    <div className="space-y-1.5">
                      <Label htmlFor="mat-lang">Idioma do material</Label>
                      <div className="flex gap-2">
                        {(["pt-BR", "en"] as MaterialTargetLanguage[]).map(
                          (langOption) => (
                            <Button
                              key={langOption}
                              type="button"
                              size="sm"
                              variant={
                                targetLanguage === langOption
                                  ? "default"
                                  : "outline"
                              }
                              onClick={() => setTargetLanguage(langOption)}
                            >
                              {langOption === "pt-BR"
                                ? "Português (pt-BR)"
                                : "English (en)"}
                            </Button>
                          )
                        )}
                      </div>
                    </div>

                    <div className="space-y-1.5">
                      <Label htmlFor="mat-title">
                        Título interno (opcional)
                      </Label>
                      <Input
                        id="mat-title"
                        value={customTitle}
                        onChange={(e) => setCustomTitle(e.target.value)}
                        placeholder="Ex: Currículo Backend Python v1"
                      />
                    </div>
                  </div>

                  <div className="space-y-2">
                    <Label>Contatos incluídos no cabeçalho</Label>
                    <div className="flex flex-wrap gap-3 text-xs">
                      <label className="inline-flex items-center gap-1.5">
                        <input
                          type="checkbox"
                          checked={contactOptions.include_email}
                          onChange={(e) =>
                            setContactOptions((prev) => ({
                              ...prev,
                              include_email: e.target.checked,
                            }))
                          }
                        />
                        E-mail profissional
                      </label>
                      <label className="inline-flex items-center gap-1.5">
                        <input
                          type="checkbox"
                          checked={contactOptions.include_phone}
                          onChange={(e) =>
                            setContactOptions((prev) => ({
                              ...prev,
                              include_phone: e.target.checked,
                            }))
                          }
                        />
                        Telefone
                      </label>
                      <label className="inline-flex items-center gap-1.5">
                        <input
                          type="checkbox"
                          checked={contactOptions.include_location}
                          onChange={(e) =>
                            setContactOptions((prev) => ({
                              ...prev,
                              include_location: e.target.checked,
                            }))
                          }
                        />
                        Cidade/Estado/País
                      </label>
                      <label className="inline-flex items-center gap-1.5">
                        <input
                          type="checkbox"
                          checked={contactOptions.include_links}
                          onChange={(e) =>
                            setContactOptions((prev) => ({
                              ...prev,
                              include_links: e.target.checked,
                            }))
                          }
                        />
                        Links (LinkedIn, GitHub, Portfólio)
                      </label>
                    </div>
                  </div>

                  <div className="space-y-1.5">
                    <Label htmlFor="mat-instructions">
                      Notas ou foco opcional desta geração
                    </Label>
                    <Input
                      id="mat-instructions"
                      value={userInstructions}
                      onChange={(e) => setUserInstructions(e.target.value)}
                      placeholder="Ex: Priorizar projetos em FastAPI e formação em andamento"
                    />
                  </div>

                  {/* Opções contextuais por tipo de material (Subfase 04.2) */}
                  {(selectedMaterialType === "cover_letter" ||
                    selectedMaterialType === "recruiter_message") && (
                    <div className="space-y-3 rounded-xl border border-border bg-muted/20 p-3">
                      <div className="text-xs font-semibold text-foreground">
                        Detalhes opcionais de contato (não inventados caso fiquem vazios)
                      </div>
                      {selectedMaterialType === "recruiter_message" && (
                        <div className="space-y-1.5">
                          <Label>Canal da mensagem</Label>
                          <div className="flex flex-wrap gap-2">
                            {(
                              [
                                { value: "linkedin", label: "LinkedIn" },
                                { value: "email", label: "E-mail" },
                                { value: "contact_form", label: "Formulário" },
                              ] as Array<{ value: RecruiterChannel; label: string }>
                            ).map((ch) => (
                              <Button
                                key={ch.value}
                                type="button"
                                size="sm"
                                variant={
                                  recruiterChannel === ch.value
                                    ? "default"
                                    : "outline"
                                }
                                onClick={() => setRecruiterChannel(ch.value)}
                              >
                                {ch.label}
                              </Button>
                            ))}
                          </div>
                        </div>
                      )}
                      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                        <div className="space-y-1">
                          <Label htmlFor="mat-contact-name">
                            Nome do contato / recrutador (opcional)
                          </Label>
                          <Input
                            id="mat-contact-name"
                            value={contactName}
                            onChange={(e) => setContactName(e.target.value)}
                            placeholder="Deixe vazio para saudação neutra"
                          />
                        </div>
                        {selectedMaterialType === "recruiter_message" && (
                          <div className="space-y-1">
                            <Label htmlFor="mat-contact-ctx">
                              Contexto do contato (opcional)
                            </Label>
                            <Input
                              id="mat-contact-ctx"
                              value={contactContext}
                              onChange={(e) => setContactContext(e.target.value)}
                              placeholder="Ex: Candidatei-me via plataforma X ontem"
                            />
                          </div>
                        )}
                      </div>
                    </div>
                  )}

                  {selectedMaterialType === "freelance_proposal" && (
                    <div className="space-y-3 rounded-xl border border-border bg-muted/20 p-3">
                      <div className="text-xs font-semibold text-foreground">
                        Condições reais de execução (deixe em branco se quiser preencher depois antes de aprovar)
                      </div>
                      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                        <div className="space-y-1">
                          <Label htmlFor="mat-fl-avail">Disponibilidade</Label>
                          <Input
                            id="mat-fl-avail"
                            value={freelanceAvailability}
                            onChange={(e) =>
                              setFreelanceAvailability(e.target.value)
                            }
                            placeholder="Ex: 20h semanais a partir de segunda"
                          />
                        </div>
                        <div className="space-y-1">
                          <Label htmlFor="mat-fl-deliv">Prazo estimado</Label>
                          <Input
                            id="mat-fl-deliv"
                            value={freelanceDelivery}
                            onChange={(e) =>
                              setFreelanceDelivery(e.target.value)
                            }
                            placeholder="Ex: 15 dias corridos"
                          />
                        </div>
                        <div className="space-y-1">
                          <Label htmlFor="mat-fl-budget">Valor / Orçamento</Label>
                          <Input
                            id="mat-fl-budget"
                            value={freelanceBudget}
                            onChange={(e) => setFreelanceBudget(e.target.value)}
                            placeholder="Ex: R$ 2.500 fechado ou R$ 80/h"
                          />
                        </div>
                        <div className="space-y-1">
                          <Label htmlFor="mat-fl-scope">
                            Esclarecimentos de escopo (opcional)
                          </Label>
                          <Input
                            id="mat-fl-scope"
                            value={freelanceScopeNotes}
                            onChange={(e) =>
                              setFreelanceScopeNotes(e.target.value)
                            }
                            placeholder="Ex: Confirmação do endpoint de webhook"
                          />
                        </div>
                      </div>
                    </div>
                  )}

                  {selectedMaterialType === "application_answers" && (
                    <div className="space-y-3 rounded-xl border border-border bg-muted/20 p-3">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div>
                          <div className="text-xs font-semibold text-foreground">
                            Perguntas do formulário da candidatura ({validQuestionsCount} válida(s))
                          </div>
                          <p className="text-[11px] text-muted-foreground">
                            Perguntas sem evidência confirmada no Perfil ou de cunho pessoal solicitarão sua resposta antes da aprovação.
                          </p>
                        </div>
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          onClick={() =>
                            setQuestionDrafts((prev) => [...prev, ""])
                          }
                        >
                          <Plus className="mr-1.5 h-3.5 w-3.5" />
                          Adicionar pergunta
                        </Button>
                      </div>
                      <div className="space-y-2">
                        {questionDrafts.map((qVal, idx) => (
                          <div key={idx} className="flex items-center gap-2">
                            <Input
                              aria-label={`Pergunta ${idx + 1}`}
                              value={qVal}
                              onChange={(e) => {
                                const next = [...questionDrafts];
                                next[idx] = e.target.value;
                                setQuestionDrafts(next);
                              }}
                              placeholder="Ex: Você já trabalhou com APIs REST? / Qual sua pretensão salarial?"
                            />
                            {questionDrafts.length > 1 && (
                              <Button
                                type="button"
                                size="icon"
                                variant="ghost"
                                aria-label={`Remover pergunta ${idx + 1}`}
                                onClick={() =>
                                  setQuestionDrafts((prev) =>
                                    prev.filter((_, i) => i !== idx)
                                  )
                                }
                              >
                                <Trash2 className="h-3.5 w-3.5" />
                              </Button>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>

              {preLoading && (
                <div className="rounded-xl border border-border p-6 text-center text-xs text-muted-foreground">
                  Analisando fatos confirmados, pendências e lacunas em relação à
                  vaga...
                </div>
              )}

              {preAnalysis && !preLoading && (
                <>
                  {/* Bloqueio por falta de fatos substantivos */}
                  {!preAnalysis.can_generate && (
                    <div className="space-y-2 rounded-xl border border-amber-500/40 bg-amber-500/10 p-4 text-xs text-amber-800 dark:text-amber-200">
                      <div className="flex items-center gap-2 font-semibold">
                        <ShieldAlert className="h-4 w-4" />
                        Geração bloqueada por integridade factual
                      </div>
                      <ul className="list-disc space-y-1 pl-5">
                        {preAnalysis.blocking_reasons.map((reason, idx) => (
                          <li key={idx}>{reason}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* Resumo dos fatos confirmados */}
                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm">
                        Fatos Confirmados Disponíveis
                      </CardTitle>
                      <CardDescription className="text-xs">
                        Apenas registros com status <strong>confirmado</strong>{" "}
                        entram no currículo gerado.
                      </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-3">
                      <div className="flex flex-wrap gap-2 text-xs">
                        <Badge variant="secondary">
                          Perfil:{" "}
                          {preAnalysis.contact_preview.profile_confirmed
                            ? "Confirmado"
                            : "Não confirmado"}
                        </Badge>
                        <Badge variant="secondary">
                          Experiências: {preAnalysis.confirmed_counts.experiences ?? 0}
                        </Badge>
                        <Badge variant="secondary">
                          Projetos: {preAnalysis.confirmed_counts.projects ?? 0}
                        </Badge>
                        <Badge variant="secondary">
                          Formações: {preAnalysis.confirmed_counts.educations ?? 0}
                        </Badge>
                        <Badge variant="secondary">
                          Habilidades: {preAnalysis.confirmed_counts.skills ?? 0}
                        </Badge>
                        <Badge variant="secondary">
                          Idiomas: {preAnalysis.confirmed_counts.languages ?? 0}
                        </Badge>
                      </div>

                      {preAnalysis.missing_requirements.length > 0 && (
                        <div className="space-y-1.5 rounded-lg border border-border bg-muted/20 p-3">
                          <div className="text-xs font-semibold text-foreground">
                            Requisitos da vaga sem evidência confirmada
                          </div>
                          <ul className="space-y-1 text-xs text-muted-foreground">
                            {preAnalysis.missing_requirements.map((gap, i) => (
                              <li key={i} className="flex flex-wrap items-center gap-1.5">
                                <Badge variant="outline" className="text-[10px]">
                                  {gap.requirement}
                                </Badge>
                                <span>{gap.note}</span>
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </CardContent>
                  </Card>

                  {/* Itens aguardando confirmação com seleção explícita */}
                  {(pendingConfirmItems.length > 0 || draftItems.length > 0) && (
                    <Card>
                      <CardHeader className="pb-2">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div>
                            <CardTitle className="text-sm">
                              Itens do Perfil Ainda Não Confirmados
                            </CardTitle>
                            <CardDescription className="text-xs">
                              Marque manualmente apenas os fatos que você revisou e
                              confirma como verdadeiros (nenhum item vem
                              pré-selecionado).
                            </CardDescription>
                          </div>

                          {pendingConfirmItems.length > 0 && (
                            <Button
                              type="button"
                              size="sm"
                              variant="default"
                              disabled={
                                selectedBatchKeys.length === 0 || confirmingBatch
                              }
                              onClick={handleConfirmSelectedBatch}
                            >
                              <Check className="mr-1.5 h-3.5 w-3.5" />
                              {confirmingBatch
                                ? "Confirmando..."
                                : `Confirmar selecionados (${selectedBatchKeys.length})`}
                            </Button>
                          )}
                        </div>
                      </CardHeader>
                      <CardContent className="space-y-3">
                        {pendingConfirmItems.length > 0 && (
                          <div className="max-h-60 space-y-2 overflow-y-auto pr-1">
                            {pendingConfirmItems.map((item) => {
                              const key = warningSelectionKey(item);
                              const checked = selectedBatchKeys.includes(key);
                              return (
                                <label
                                  key={key}
                                  className="flex cursor-pointer items-start gap-2.5 rounded-lg border border-border bg-background p-2.5 text-xs hover:bg-muted/30"
                                >
                                  <input
                                    type="checkbox"
                                    className="mt-0.5"
                                    checked={checked}
                                    onChange={() => toggleBatchItem(item)}
                                  />
                                  <div className="min-w-0 flex-1 space-y-0.5">
                                    <div className="flex flex-wrap items-center gap-1.5">
                                      <Badge variant="outline" className="text-[10px]">
                                        {ENTITY_TYPE_LABELS[item.entity_type] ||
                                          item.entity_type}
                                      </Badge>
                                      <span className="font-semibold text-foreground">
                                        {item.label}
                                      </span>
                                      {item.matched_requirements.length > 0 && (
                                        <Badge variant="secondary" className="text-[10px]">
                                          Relevante:{" "}
                                          {item.matched_requirements.join(", ")}
                                        </Badge>
                                      )}
                                    </div>
                                    <p className="text-muted-foreground">
                                      {item.summary} · {item.reason}
                                    </p>
                                  </div>
                                </label>
                              );
                            })}
                          </div>
                        )}

                        {draftItems.length > 0 && (
                          <div className="space-y-2 rounded-lg border border-dashed border-border p-3 text-xs">
                            <div className="flex flex-wrap items-center justify-between gap-2">
                              <span className="font-medium text-muted-foreground">
                                Itens em rascunho (exigem edição/confirmação na aba
                                Perfil)
                              </span>
                              {onNavigateProfile && (
                                <Button
                                  type="button"
                                  size="sm"
                                  variant="outline"
                                  onClick={() => {
                                    onClose();
                                    onNavigateProfile();
                                  }}
                                >
                                  Abrir Perfil
                                </Button>
                              )}
                            </div>
                            <ul className="space-y-1 text-muted-foreground">
                              {draftItems.map((item) => (
                                <li key={warningSelectionKey(item)}>
                                  •{" "}
                                  <strong>
                                    {ENTITY_TYPE_LABELS[item.entity_type] ||
                                      item.entity_type}
                                    :
                                  </strong>{" "}
                                  {item.label} ({item.summary})
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}
                      </CardContent>
                    </Card>
                  )}

                  <div className="flex flex-wrap justify-end gap-2">
                    <Button type="button" variant="outline" onClick={onClose}>
                      Cancelar
                    </Button>
                    <Button
                      type="button"
                      disabled={
                        !preAnalysis.can_generate ||
                        busyAction ||
                        missingRequiredQuestions
                      }
                      onClick={handleGenerateMaterial}
                    >
                      <Sparkles className="mr-1.5 h-4 w-4" />
                      {busyAction ? "Gerando..." : selectedTypeMeta.ctaLabel}
                    </Button>
                  </div>
                </>
              )}
            </div>
          )}

          {/* MODO 2: EDITOR, AI STUDIO, PREVIEW, HISTÓRICO, APROVAÇÃO E VÍNCULO */}
          {material && activeVersion && draftContent && (
            <div className="space-y-4">
              {/* Barra de versões */}
              <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-border bg-muted/20 p-3">
                <div className="flex flex-wrap items-center gap-1.5">
                  {material.versions.map((ver) => {
                    const isSelected = ver.id === activeVersion.id;
                    return (
                      <button
                        key={ver.id}
                        type="button"
                        onClick={() => setActiveVersionId(ver.id)}
                        className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs font-medium transition-colors ${
                          isSelected
                            ? "border-primary bg-primary text-primary-foreground"
                            : ver.is_rejected
                              ? "border-destructive/40 bg-destructive/5 text-muted-foreground hover:bg-destructive/10"
                              : "border-border bg-background text-foreground hover:bg-muted/40"
                        }`}
                      >
                        <span>v{ver.version_number}</span>
                        <span className="opacity-80">
                          {ORIGIN_LABELS[ver.origin] || ver.origin}
                        </span>
                        {ver.is_rejected && (
                          <span className="rounded bg-destructive/20 px-1 py-0.2 text-[10px] font-semibold">
                            Rejeitada
                          </span>
                        )}
                        {ver.is_approved && <Lock className="h-3 w-3" />}
                      </button>
                    );
                  })}
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  <Button
                    type="button"
                    size="sm"
                    variant={panelTab === "ai_studio" ? "default" : "outline"}
                    disabled={busyAction}
                    onClick={() => setPanelTab("ai_studio")}
                  >
                    <Sparkles className="mr-1.5 h-3.5 w-3.5" />
                    {activeVersion.origin === "ai_assisted" &&
                    !activeVersion.is_approved &&
                    !activeVersion.is_rejected
                      ? "Revisar sugestão IA"
                      : "AI Studio"}
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    disabled={busyAction}
                    onClick={handleRegenerate}
                  >
                    <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
                    Regenerar do Perfil
                  </Button>
                  {!activeVersion.is_mutable && !activeVersion.is_rejected && (
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      disabled={busyAction}
                      onClick={handleDeriveVersion}
                    >
                      <GitBranch className="mr-1.5 h-3.5 w-3.5" />
                      Criar versão derivada para editar
                    </Button>
                  )}
                  {!activeVersion.is_approved && !activeVersion.is_rejected && (
                    <Button
                      type="button"
                      size="sm"
                      disabled={
                        busyAction ||
                        Boolean(activeVersion.has_blocking_pending_fields)
                      }
                      onClick={handleApproveVersion}
                    >
                      <CheckCircle2 className="mr-1.5 h-3.5 w-3.5" />
                      Aprovar versão
                    </Button>
                  )}
                  {applicationId &&
                    activeVersion.is_approved &&
                    !activeVersion.is_rejected && (
                      <Button
                        type="button"
                        size="sm"
                        variant={
                          activeLinkForCurrentApp?.version_id ===
                          activeVersion.id
                            ? "secondary"
                            : "default"
                        }
                        disabled={busyAction}
                        onClick={handleLinkToApplication}
                      >
                        <Link2 className="mr-1.5 h-3.5 w-3.5" />
                        {activeLinkForCurrentApp?.version_id ===
                        activeVersion.id
                          ? "Versão ativa na candidatura"
                          : "Vincular à candidatura"}
                      </Button>
                    )}
                  {applicationId && activeLinkForCurrentApp && (
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      disabled={busyAction}
                      onClick={handleUnlinkFromApplication}
                    >
                      <Unlink2 className="mr-1.5 h-3.5 w-3.5" />
                      Desvincular
                    </Button>
                  )}
                </div>
              </div>

              {/* Banner de versão rejeitada (bloqueia ações incompatíveis) */}
              {activeVersion.is_rejected && (
                <div
                  role="status"
                  className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-destructive/50 bg-destructive/10 p-3 text-xs text-destructive"
                >
                  <span>
                    <strong>
                      Versão v{activeVersion.version_number} rejeitada:
                    </strong>{" "}
                    esta sugestão gerada por IA foi rejeitada pelo usuário e é
                    mantida apenas para auditoria no histórico. Aprovação,
                    edição, derivação, exportação e vinculação estão bloqueadas.
                  </span>
                  {latestActiveVersion &&
                    latestActiveVersion.id !== activeVersion.id && (
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        onClick={() => setActiveVersionId(latestActiveVersion.id)}
                      >
                        Voltar para versão ativa (v
                        {latestActiveVersion.version_number})
                      </Button>
                    )}
                </div>
              )}

              {/* Barra de decisão humana quando visualizando sugestão IA fora da aba AI Studio */}
              {activeVersion.origin === "ai_assisted" &&
                !activeVersion.is_approved &&
                !activeVersion.is_rejected &&
                panelTab !== "ai_studio" && (
                  <div className="flex flex-col gap-2.5 rounded-xl border border-primary/50 bg-primary/5 p-3 text-xs sm:flex-row sm:flex-wrap sm:items-center sm:justify-between">
                    <div className="space-y-0.5">
                      <div className="flex flex-wrap items-center gap-1.5 font-semibold text-foreground">
                        <Sparkles className="h-4 w-4 text-primary" />
                        <span>
                          Sugestão de IA (v{activeVersion.version_number}) —
                          Rascunho não aprovado (exige revisão humana)
                        </span>
                      </div>
                      <p className="text-muted-foreground">
                        {isDerivingEditMode
                          ? "Modo de edição derivada ativo: edite os campos abaixo e clique em 'Salvar versão derivada' para consolidar sem alterar a sugestão original da IA."
                          : "Inspecione a comparação estruturada no AI Studio ou escolha aprovar, editar como versão derivada ou rejeitar."}
                      </p>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        onClick={() => setPanelTab("ai_studio")}
                      >
                        Ver comparação estruturada
                      </Button>
                      <Button
                        type="button"
                        size="sm"
                        disabled={
                          busyAction ||
                          Boolean(activeVersion.has_blocking_pending_fields)
                        }
                        onClick={handleApproveVersion}
                      >
                        <CheckCircle2 className="mr-1.5 h-3.5 w-3.5" />
                        Aprovar sugestão
                      </Button>
                      {!isDerivingEditMode ? (
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          disabled={busyAction}
                          onClick={handleStartDeriveEdit}
                        >
                          Editar como versão derivada
                        </Button>
                      ) : (
                        <>
                          <Button
                            type="button"
                            size="sm"
                            variant="default"
                            disabled={busyAction}
                            onClick={handleSaveDerivedFromAi}
                          >
                            <FileCheck2 className="mr-1.5 h-3.5 w-3.5" />
                            Salvar versão derivada
                          </Button>
                          <Button
                            type="button"
                            size="sm"
                            variant="ghost"
                            disabled={busyAction}
                            onClick={handleCancelDeriveEdit}
                          >
                            Cancelar edição derivada
                          </Button>
                        </>
                      )}
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        className="border-destructive/50 text-destructive hover:bg-destructive/10"
                        disabled={busyAction}
                        onClick={handleRejectAiVersion}
                      >
                        Rejeitar sugestão
                      </Button>
                    </div>
                  </div>
                )}

              {/* Aviso de pendências obrigatórias antes de aprovar (Subfase 04.2) */}
              {activeVersion.has_blocking_pending_fields &&
                !activeVersion.is_approved &&
                !activeVersion.is_rejected && (
                  <div className="flex items-start gap-2 rounded-lg border border-amber-500/50 bg-amber-500/10 p-3 text-xs text-amber-800 dark:text-amber-200">
                    <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" />
                    <span>
                      Há{" "}
                      <strong>
                        {activeVersion.pending_requirements_count || 1}
                      </strong>{" "}
                      informação(ões) obrigatória(s) pendente(s). Preencha-as no
                      editor e clique em{" "}
                      <strong>
                        {isDerivingEditMode
                          ? "Salvar versão derivada"
                          : "Salvar rascunho"}
                      </strong>{" "}
                      para liberar a aprovação.
                    </span>
                  </div>
                )}

              {/* Aviso de edição manual ou imutabilidade */}
              {draftContent.has_unverified_manual_edits &&
                !activeVersion.is_approved &&
                !activeVersion.is_rejected && (
                  <div className="flex items-start gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-xs text-amber-800 dark:text-amber-200">
                    <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                    <span>
                      Este rascunho contém alterações manuais ainda não confirmadas
                      no Perfil. Ao aprovar, você confirma que o conteúdo deste
                      material é exato.
                    </span>
                  </div>
                )}

              {!activeVersion.is_mutable &&
                !activeVersion.is_rejected &&
                !isDerivingEditMode && (
                  <div className="flex items-start gap-2 rounded-lg border border-border bg-muted/40 p-3 text-xs text-muted-foreground">
                    <Lock className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                    <span>
                      Versão v{activeVersion.version_number} está{" "}
                      {activeVersion.is_approved ? "aprovada" : "somente leitura"} e
                      não pode ser sobrescrita diretamente. Use{" "}
                      <strong>
                        {activeVersion.origin === "ai_assisted" &&
                        !activeVersion.is_approved
                          ? "Editar como versão derivada"
                          : "Criar versão derivada"}
                      </strong>{" "}
                      ou <strong>Regenerar do Perfil</strong> para criar um novo
                      rascunho editável.
                    </span>
                  </div>
                )}

              {/* Subabas: Editor Estruturado | AI Studio & Comparação | Pré-visualização | Histórico & Lacunas */}
              <div className="flex flex-wrap gap-1.5 border-b border-border pb-2">
                {[
                  { id: "editor" as const, label: "Editor Estruturado" },
                  {
                    id: "ai_studio" as const,
                    label: "AI Studio & Comparação",
                  },
                  {
                    id: "preview" as const,
                    label: "Pré-visualização & Exportação",
                  },
                  {
                    id: "history" as const,
                    label: "Histórico, Fatos & Lacunas",
                  },
                ].map((tab) => (
                  <button
                    key={tab.id}
                    type="button"
                    onClick={() => setPanelTab(tab.id)}
                    className={`rounded-lg border px-3 py-1.5 text-xs font-medium ${
                      panelTab === tab.id
                        ? "border-primary bg-primary text-primary-foreground"
                        : "border-border bg-background text-muted-foreground hover:text-foreground"
                    }`}
                  >
                    {tab.label}
                  </button>
                ))}
              </div>

              {/* TAB AI STUDIO & COMPARAÇÃO */}
              {panelTab === "ai_studio" && (
                <MaterialAIStudioPanel
                  material={material}
                  activeVersion={activeVersion}
                  latestActiveVersion={latestActiveVersion}
                  busyAction={busyAction}
                  aiEnhancing={aiEnhancing}
                  aiError={aiError}
                  isDerivingEditMode={isDerivingEditMode}
                  onDismissAiError={() => setAiError(null)}
                  onReloadMaterial={handleReloadCurrentMaterial}
                  onSelectVersion={(ver) => setActiveVersionId(ver.id)}
                  onRunAiEnhance={handleRunAiEnhance}
                  onApproveVersion={handleApproveVersion}
                  onStartDeriveEdit={handleStartDeriveEdit}
                  onSaveDerivedVersion={handleSaveDerivedFromAi}
                  onCancelDeriveEdit={handleCancelDeriveEdit}
                  onRejectAiVersion={handleRejectAiVersion}
                />
              )}

              {/* TAB EDITOR */}
              {panelTab === "editor" && (
                <div className="space-y-4">
                  {"material_type" in draftContent &&
                    draftContent.material_type === "cover_letter" && (
                      <CoverLetterEditor
                        content={draftContent as CoverLetterStructuredContent}
                        isMutable={canEditDraft}
                        onChange={(next) => setDraftContent(next)}
                      />
                    )}

                  {"material_type" in draftContent &&
                    draftContent.material_type === "recruiter_message" && (
                      <RecruiterMessageEditor
                        content={draftContent as RecruiterMessageStructuredContent}
                        isMutable={canEditDraft}
                        onChange={(next) => setDraftContent(next)}
                      />
                    )}

                  {"material_type" in draftContent &&
                    draftContent.material_type === "freelance_proposal" && (
                      <FreelanceProposalEditor
                        content={draftContent as FreelanceProposalStructuredContent}
                        isMutable={canEditDraft}
                        onChange={(next) => setDraftContent(next)}
                      />
                    )}

                  {"material_type" in draftContent &&
                    draftContent.material_type === "application_answers" && (
                      <ApplicationAnswersEditor
                        content={
                          draftContent as ApplicationAnswersStructuredContent
                        }
                        isMutable={canEditDraft}
                        onChange={(next) => setDraftContent(next)}
                      />
                    )}

                  {resumeDraft && (
                    <>
                      {/* Cabeçalho */}
                      <Card>
                        <CardHeader className="pb-2">
                          <div className="flex items-center justify-between gap-2">
                            <CardTitle className="text-sm">Cabeçalho</CardTitle>
                            <Badge
                              variant={
                                PROVENANCE_META[resumeDraft.header.provenance].variant
                              }
                              className="text-[10px]"
                            >
                              {PROVENANCE_META[resumeDraft.header.provenance].label}
                            </Badge>
                          </div>
                        </CardHeader>
                        <CardContent className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                          <div className="space-y-1">
                            <Label htmlFor="ed-fullname">Nome completo</Label>
                            <Input
                              id="ed-fullname"
                              disabled={!canEditDraft}
                              value={resumeDraft.header.full_name || ""}
                              onChange={(e) =>
                                setDraftContent({
                                  ...resumeDraft,
                                  header: {
                                    ...resumeDraft.header,
                                    full_name: e.target.value || null,
                                    provenance: "manual_edit",
                                  },
                                })
                              }
                            />
                          </div>
                          <div className="space-y-1">
                            <Label htmlFor="ed-title">Título profissional</Label>
                            <Input
                              id="ed-title"
                              disabled={!canEditDraft}
                              value={resumeDraft.header.professional_title || ""}
                              onChange={(e) =>
                                setDraftContent({
                                  ...resumeDraft,
                                  header: {
                                    ...resumeDraft.header,
                                    professional_title: e.target.value || null,
                                    provenance: "manual_edit",
                                  },
                                })
                              }
                            />
                          </div>
                          <div className="space-y-1">
                            <Label htmlFor="ed-loc">Localização</Label>
                            <Input
                              id="ed-loc"
                              disabled={!canEditDraft}
                              value={resumeDraft.header.location_text || ""}
                              onChange={(e) =>
                                setDraftContent({
                                  ...resumeDraft,
                                  header: {
                                    ...resumeDraft.header,
                                    location_text: e.target.value || null,
                                    provenance: "manual_edit",
                                  },
                                })
                              }
                            />
                          </div>
                          <div className="space-y-1">
                            <Label htmlFor="ed-email">E-mail de contato</Label>
                            <Input
                              id="ed-email"
                              disabled={!canEditDraft}
                              value={resumeDraft.header.email || ""}
                              onChange={(e) =>
                                setDraftContent({
                                  ...resumeDraft,
                                  header: {
                                    ...resumeDraft.header,
                                    email: e.target.value || null,
                                    provenance: "manual_edit",
                                  },
                                })
                              }
                            />
                          </div>
                        </CardContent>
                      </Card>

                      {/* Resumo */}
                      {resumeDraft.summary && (
                        <Card>
                          <CardHeader className="pb-2">
                            <div className="flex items-center justify-between gap-2">
                              <CardTitle className="text-sm">
                                Resumo Profissional
                              </CardTitle>
                              <Badge
                                variant={
                                  PROVENANCE_META[resumeDraft.summary.provenance]
                                    .variant
                                }
                                className="text-[10px]"
                              >
                                {
                                  PROVENANCE_META[resumeDraft.summary.provenance]
                                    .label
                                }
                              </Badge>
                            </div>
                          </CardHeader>
                          <CardContent>
                            <textarea
                              rows={3}
                              disabled={!canEditDraft}
                              value={resumeDraft.summary.text}
                              onChange={(e) =>
                                setDraftContent({
                                  ...resumeDraft,
                                  summary: resumeDraft.summary
                                    ? {
                                        ...resumeDraft.summary,
                                        text: e.target.value,
                                        provenance: "manual_edit",
                                      }
                                    : null,
                                })
                              }
                              className="w-full rounded-md border border-input bg-background px-3 py-2 text-xs text-foreground"
                            />
                          </CardContent>
                        </Card>
                      )}

                      {/* Experiências (estritamente separadas de projetos) */}
                      <Card>
                        <CardHeader className="pb-2">
                          <CardTitle className="text-sm">
                            Experiência Profissional ({resumeDraft.experiences.length})
                          </CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-3">
                          {resumeDraft.experiences.length === 0 ? (
                            <p className="text-xs text-muted-foreground">
                              Nenhuma experiência profissional confirmada incluída.
                            </p>
                          ) : (
                            resumeDraft.experiences.map((exp, idx) => (
                              <div
                                key={`${exp.entity_id || "manual"}-${idx}`}
                                className="space-y-2 rounded-lg border border-border p-3"
                              >
                                <div className="flex flex-wrap items-center justify-between gap-2">
                                  <div className="flex flex-wrap items-center gap-1.5">
                                    <Badge variant="secondary" className="text-[10px]">
                                      {exp.experience_type}
                                    </Badge>
                                    <Badge
                                      variant={
                                        exp.eligible_as_target_role
                                          ? "default"
                                          : "outline"
                                      }
                                      className="text-[10px]"
                                    >
                                      {exp.eligible_as_target_role
                                        ? "Elegível como atuação-alvo"
                                        : "Experiência complementar"}
                                    </Badge>
                                  </div>
                                  <Badge
                                    variant={
                                      PROVENANCE_META[exp.provenance].variant
                                    }
                                    className="text-[10px]"
                                  >
                                    {PROVENANCE_META[exp.provenance].label}
                                  </Badge>
                                </div>
                                <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                                  <Input
                                    aria-label={`Cargo da experiência ${idx + 1}`}
                                    disabled={!canEditDraft}
                                    value={exp.role}
                                    onChange={(e) =>
                                      updateExperienceItem(idx, {
                                        role: e.target.value,
                                      })
                                    }
                                  />
                                  <Input
                                    aria-label={`Empresa da experiência ${idx + 1}`}
                                    disabled={!canEditDraft}
                                    value={exp.company}
                                    onChange={(e) =>
                                      updateExperienceItem(idx, {
                                        company: e.target.value,
                                      })
                                    }
                                  />
                                </div>
                                <textarea
                                  rows={2}
                                  aria-label={`Descrição da experiência ${idx + 1}`}
                                  disabled={!canEditDraft}
                                  value={exp.description || ""}
                                  onChange={(e) =>
                                    updateExperienceItem(idx, {
                                      description: e.target.value || null,
                                    })
                                  }
                                  className="w-full rounded-md border border-input bg-background px-3 py-2 text-xs"
                                />
                              </div>
                            ))
                          )}
                        </CardContent>
                      </Card>

                      {/* Projetos (seção própria, jamais fundida em experiências) */}
                      <Card>
                        <CardHeader className="pb-2">
                          <CardTitle className="text-sm">
                            Projetos ({resumeDraft.projects.length})
                          </CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-3">
                          {resumeDraft.projects.length === 0 ? (
                            <p className="text-xs text-muted-foreground">
                              Nenhum projeto confirmado incluído.
                            </p>
                          ) : (
                            resumeDraft.projects.map((proj, idx) => (
                              <div
                                key={`${proj.entity_id || "manual-proj"}-${idx}`}
                                className="space-y-2 rounded-lg border border-border p-3"
                              >
                                <div className="flex items-center justify-between gap-2">
                                  <span className="text-xs font-semibold">
                                    {proj.name}
                                  </span>
                                  <Badge
                                    variant={
                                      PROVENANCE_META[proj.provenance].variant
                                    }
                                    className="text-[10px]"
                                  >
                                    {PROVENANCE_META[proj.provenance].label}
                                  </Badge>
                                </div>
                                <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                                  <Input
                                    aria-label={`Nome do projeto ${idx + 1}`}
                                    disabled={!canEditDraft}
                                    value={proj.name}
                                    onChange={(e) =>
                                      updateProjectItem(idx, {
                                        name: e.target.value,
                                      })
                                    }
                                  />
                                  <Input
                                    aria-label={`Papel no projeto ${idx + 1}`}
                                    disabled={!canEditDraft}
                                    value={proj.role || ""}
                                    placeholder="Papel / atuação"
                                    onChange={(e) =>
                                      updateProjectItem(idx, {
                                        role: e.target.value || null,
                                      })
                                    }
                                  />
                                </div>
                                <textarea
                                  rows={2}
                                  aria-label={`Descrição do projeto ${idx + 1}`}
                                  disabled={!canEditDraft}
                                  value={proj.description || ""}
                                  onChange={(e) =>
                                    updateProjectItem(idx, {
                                      description: e.target.value || null,
                                    })
                                  }
                                  className="w-full rounded-md border border-input bg-background px-3 py-2 text-xs"
                                />
                              </div>
                            ))
                          )}
                        </CardContent>
                      </Card>

                      {/* Formação, Habilidades e Idiomas */}
                      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
                        <Card>
                          <CardHeader className="pb-2">
                            <CardTitle className="text-xs font-semibold">
                              Formação Acadêmica ({resumeDraft.education.length})
                            </CardTitle>
                          </CardHeader>
                          <CardContent className="space-y-1.5 text-xs">
                            {resumeDraft.education.map((edu, idx) => (
                              <div
                                key={`${edu.entity_id || idx}`}
                                className="rounded border border-border p-2"
                              >
                                <div className="font-semibold">{edu.course}</div>
                                <div className="text-muted-foreground">
                                  {edu.institution} · {edu.status_label}
                                  {edu.current_semester
                                    ? ` (${edu.current_semester})`
                                    : ""}
                                </div>
                              </div>
                            ))}
                          </CardContent>
                        </Card>

                        <Card>
                          <CardHeader className="pb-2">
                            <CardTitle className="text-xs font-semibold">
                              Habilidades ({resumeDraft.skills.length})
                            </CardTitle>
                          </CardHeader>
                          <CardContent className="flex flex-wrap gap-1.5 text-xs">
                            {resumeDraft.skills.map((skill, idx) => (
                              <Badge key={`${skill.entity_id || idx}`} variant="secondary">
                                {skill.name} · {skill.proficiency_label}
                              </Badge>
                            ))}
                          </CardContent>
                        </Card>

                        <Card>
                          <CardHeader className="pb-2">
                            <CardTitle className="text-xs font-semibold">
                              Idiomas ({resumeDraft.languages.length})
                            </CardTitle>
                          </CardHeader>
                          <CardContent className="space-y-1.5 text-xs">
                            {resumeDraft.languages.map((lang, idx) => (
                              <div key={`${lang.entity_id || idx}`}>
                                <strong>{lang.language_name}:</strong>{" "}
                                {lang.proficiency_label}
                                {lang.cefr_level ? ` (${lang.cefr_level})` : ""}
                              </div>
                            ))}
                          </CardContent>
                        </Card>
                      </div>

                      {/* Blocos manuais adicionais */}
                      <Card>
                        <CardHeader className="pb-2">
                          <div className="flex items-center justify-between gap-2">
                            <CardTitle className="text-sm">
                              Notas Adicionais do Usuário (
                              {resumeDraft.manual_notes.length})
                            </CardTitle>
                            {canEditDraft && (
                              <Button
                                type="button"
                                size="sm"
                                variant="outline"
                                onClick={addManualNote}
                              >
                                <Plus className="mr-1.5 h-3.5 w-3.5" />
                                Adicionar nota manual
                              </Button>
                            )}
                          </div>
                        </CardHeader>
                        <CardContent className="space-y-2">
                          {resumeDraft.manual_notes.map((note, idx) => (
                            <div
                              key={note.id}
                              className="space-y-2 rounded-lg border border-border p-3"
                            >
                              <div className="flex items-center justify-between gap-2">
                                <Input
                                  disabled={!canEditDraft}
                                  value={note.title}
                                  onChange={(e) => {
                                    const next = [...resumeDraft.manual_notes];
                                    next[idx] = { ...next[idx], title: e.target.value };
                                    setDraftContent({
                                      ...resumeDraft,
                                      manual_notes: next,
                                    });
                                  }}
                                />
                                {canEditDraft && (
                                  <Button
                                    type="button"
                                    size="icon"
                                    variant="ghost"
                                    onClick={() => {
                                      const next = resumeDraft.manual_notes.filter(
                                        (_, i) => i !== idx
                                      );
                                      setDraftContent({
                                        ...resumeDraft,
                                        manual_notes: next,
                                      });
                                    }}
                                    aria-label="Remover nota"
                                  >
                                    <Trash2 className="h-3.5 w-3.5" />
                                  </Button>
                                )}
                              </div>
                              <textarea
                                rows={2}
                                disabled={!canEditDraft}
                                value={note.content}
                                onChange={(e) => {
                                  const next = [...resumeDraft.manual_notes];
                                  next[idx] = {
                                    ...next[idx],
                                    content: e.target.value,
                                  };
                                  setDraftContent({
                                    ...resumeDraft,
                                    manual_notes: next,
                                  });
                                }}
                                className="w-full rounded-md border border-input bg-background px-3 py-2 text-xs"
                              />
                            </div>
                          ))}
                        </CardContent>
                      </Card>
                    </>
                  )}

                  {activeVersion.is_mutable && !activeVersion.is_rejected && (
                    <div className="flex justify-end gap-2">
                      <Button
                        type="button"
                        disabled={busyAction}
                        onClick={handleSaveDraft}
                      >
                        <FileCheck2 className="mr-1.5 h-4 w-4" />
                        {busyAction ? "Salvando..." : "Salvar rascunho"}
                      </Button>
                    </div>
                  )}

                  {isDerivingEditMode && !activeVersion.is_rejected && (
                    <div className="flex flex-wrap justify-end gap-2">
                      <Button
                        type="button"
                        variant="outline"
                        disabled={busyAction}
                        onClick={handleCancelDeriveEdit}
                      >
                        Cancelar edição derivada
                      </Button>
                      <Button
                        type="button"
                        disabled={busyAction}
                        onClick={handleSaveDerivedFromAi}
                      >
                        <FileCheck2 className="mr-1.5 h-4 w-4" />
                        {busyAction ? "Salvando..." : "Salvar versão derivada"}
                      </Button>
                    </div>
                  )}
                </div>
              )}

              {/* TAB PREVIEW & EXPORT */}
              {panelTab === "preview" && (() => {
                const preferPlainCopy =
                  material.material_type === "recruiter_message" ||
                  material.material_type === "application_answers";
                const hasBlocking = Boolean(
                  activeVersion.has_blocking_pending_fields
                );
                const isRejected = Boolean(activeVersion.is_rejected);
                const isDraftMode = !activeVersion.is_approved;
                const downloadDisabled =
                  busyAction ||
                  downloadingFormat !== null ||
                  hasBlocking ||
                  isRejected;

                return (
                  <Card>
                    <CardHeader className="space-y-3 pb-3">
                      <div className="flex flex-wrap items-start justify-between gap-2">
                        <div>
                          <CardTitle className="text-sm">
                            Pré-visualização & Exportação (v{activeVersion.version_number})
                          </CardTitle>
                          <CardDescription className="text-xs">
                            Exportação em PDF e DOCX gerada exclusivamente a partir da versão estruturada v{activeVersion.version_number}.
                          </CardDescription>
                        </div>
                        <div className="flex flex-wrap gap-2">
                          <Button
                            type="button"
                            size="sm"
                            variant={preferPlainCopy ? "default" : "outline"}
                            disabled={busyAction || isRejected}
                            onClick={() => handleCopyExport("text")}
                          >
                            <Copy className="mr-1.5 h-3.5 w-3.5" />
                            {copiedFormat === "text"
                              ? "Texto copiado!"
                              : "Copiar Texto Simples"}
                          </Button>
                          <Button
                            type="button"
                            size="sm"
                            variant="outline"
                            disabled={busyAction || isRejected}
                            onClick={() => handleCopyExport("markdown")}
                          >
                            <Copy className="mr-1.5 h-3.5 w-3.5" />
                            {copiedFormat === "markdown"
                              ? "Markdown copiado!"
                              : "Copiar Markdown"}
                          </Button>
                        </div>
                      </div>

                      {/* Controles de template, visualização e downloads PDF/DOCX */}
                      <div className="flex flex-col gap-3 rounded-xl border border-border bg-muted/20 p-3 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-xs font-medium text-foreground">
                            Template:
                          </span>
                          <div
                            role="group"
                            aria-label="Selecionar template documental"
                            className="inline-flex rounded-lg border border-border bg-background p-0.5"
                          >
                            {(
                              [
                                { id: "classic_ats", label: "Classic ATS" },
                                { id: "modern_minimal", label: "Modern Minimalist" },
                              ] as Array<{ id: DocumentTemplateId; label: string }>
                            ).map((tpl) => (
                              <button
                                key={tpl.id}
                                type="button"
                                aria-pressed={selectedTemplate === tpl.id}
                                onClick={() => setSelectedTemplate(tpl.id)}
                                className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                                  selectedTemplate === tpl.id
                                    ? "bg-primary text-primary-foreground"
                                    : "text-muted-foreground hover:text-foreground"
                                }`}
                              >
                                {tpl.label}
                              </button>
                            ))}
                          </div>

                          <div
                            role="group"
                            aria-label="Alternar visualização"
                            className="inline-flex rounded-lg border border-border bg-background p-0.5"
                          >
                            <button
                              type="button"
                              aria-pressed={previewMode === "document"}
                              onClick={() => setPreviewMode("document")}
                              className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                                previewMode === "document"
                                  ? "bg-secondary text-secondary-foreground"
                                  : "text-muted-foreground hover:text-foreground"
                              }`}
                            >
                              Preview Documental
                            </button>
                            <button
                              type="button"
                              aria-pressed={previewMode === "markdown"}
                              onClick={() => setPreviewMode("markdown")}
                              className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                                previewMode === "markdown"
                                  ? "bg-secondary text-secondary-foreground"
                                  : "text-muted-foreground hover:text-foreground"
                              }`}
                            >
                              Markdown
                            </button>
                          </div>
                        </div>

                        <div className="flex flex-wrap gap-2">
                          <Button
                            type="button"
                            size="sm"
                            variant={preferPlainCopy ? "outline" : "default"}
                            disabled={downloadDisabled}
                            onClick={() => handleDownloadBinary("pdf")}
                          >
                            <Download className="mr-1.5 h-3.5 w-3.5" />
                            {downloadingFormat === "pdf"
                              ? "Baixando PDF..."
                              : isDraftMode
                                ? "Baixar PDF (Rascunho)"
                                : "Baixar PDF"}
                          </Button>
                          <Button
                            type="button"
                            size="sm"
                            variant="outline"
                            disabled={downloadDisabled}
                            onClick={() => handleDownloadBinary("docx")}
                          >
                            <Download className="mr-1.5 h-3.5 w-3.5" />
                            {downloadingFormat === "docx"
                              ? "Baixando DOCX..."
                              : isDraftMode
                                ? "Baixar DOCX (Rascunho)"
                                : "Baixar DOCX"}
                          </Button>
                        </div>
                      </div>

                      {isRejected ? (
                        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-3 text-xs text-destructive">
                          Exportação e aprovação bloqueadas: esta versão foi rejeitada e permanece no histórico apenas para auditoria.
                        </div>
                      ) : hasBlocking ? (
                        <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-amber-500/50 bg-amber-500/10 p-3 text-xs text-amber-800 dark:text-amber-200">
                          <span>
                            Downloads PDF/DOCX bloqueados: há{" "}
                            <strong>
                              {activeVersion.pending_requirements_count || 1}
                            </strong>{" "}
                            pendência(s) obrigatória(s). Preencha no editor e salve o rascunho para liberar a exportação.
                          </span>
                          <Button
                            type="button"
                            size="sm"
                            variant="outline"
                            onClick={() => setPanelTab("editor")}
                          >
                            Ir para o Editor
                          </Button>
                        </div>
                      ) : isDraftMode ? (
                        <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-xs text-amber-800 dark:text-amber-200">
                          <span>
                            Versão ainda não aprovada: os arquivos baixados incluirão aviso e marcação de <strong>RASCUNHO NÃO APROVADO</strong> em todas as páginas.
                          </span>
                          <Button
                            type="button"
                            size="sm"
                            disabled={busyAction}
                            onClick={handleApproveVersion}
                          >
                            <CheckCircle2 className="mr-1.5 h-3.5 w-3.5" />
                            Aprovar para versão final
                          </Button>
                        </div>
                      ) : null}
                    </CardHeader>

                    <CardContent>
                      {previewMode === "document" ? (
                        <DocumentPreviewCard
                          content={draftContent}
                          template={selectedTemplate}
                          isDraft={isDraftMode}
                        />
                      ) : (
                        <pre className="max-h-[55vh] overflow-auto whitespace-pre-wrap break-words rounded-xl border border-border bg-muted/20 p-4 font-mono text-xs leading-relaxed text-foreground">
                          {activeVersion.rendered_markdown}
                        </pre>
                      )}
                    </CardContent>
                  </Card>
                );
              })()}

              {/* TAB HISTÓRICO & LACUNAS */}
              {panelTab === "history" && (
                <div className="space-y-4">
                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="flex items-center gap-2 text-sm">
                        <History className="h-4 w-4 text-primary" />
                        Histórico de Versões ({material.versions.length})
                      </CardTitle>
                      <CardDescription className="text-xs">
                        Tipo:{" "}
                        {MATERIAL_TYPE_SHORT_LABELS[material.material_type] ||
                          material.material_type}{" "}
                        · Contexto:{" "}
                        {material.opportunity_title || "Perfil geral"}
                      </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-2 text-xs">
                      {material.versions.map((ver) => (
                        <div
                          key={ver.id}
                          className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border p-2.5"
                        >
                          <div className="space-y-0.5">
                            <div className="flex flex-wrap items-center gap-1.5">
                              <span className="font-semibold">
                                v{ver.version_number}
                              </span>
                              <Badge variant="outline" className="text-[10px]">
                                {ORIGIN_LABELS[ver.origin] || ver.origin}
                              </Badge>
                              {ver.has_blocking_pending_fields && (
                                <Badge variant="outline" className="text-[10px]">
                                  {ver.pending_requirements_count} pendência(s)
                                </Badge>
                              )}
                            </div>
                            <div className="text-muted-foreground">
                              Criada em {formatDateTimePtBr(ver.created_at)}
                              {ver.approved_at
                                ? ` · Aprovada em ${formatDateTimePtBr(ver.approved_at)}`
                                : ""}
                              {ver.rejected_at
                                ? ` · Rejeitada em ${formatDateTimePtBr(ver.rejected_at)}`
                                : ""}
                            </div>
                          </div>
                          <Badge
                            variant={
                              ver.is_rejected
                                ? "outline"
                                : ver.is_approved
                                  ? "default"
                                  : "secondary"
                            }
                            className={
                              ver.is_rejected
                                ? "border-destructive/50 text-destructive"
                                : undefined
                            }
                          >
                            {ver.is_rejected
                              ? "Rejeitada"
                              : ver.is_approved
                                ? "Aprovada"
                                : ver.origin === "ai_assisted"
                                  ? "Sugestão IA (Rascunho)"
                                  : "Rascunho"}
                          </Badge>
                        </div>
                      ))}
                    </CardContent>
                  </Card>

                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="flex items-center gap-2 text-sm">
                        <History className="h-4 w-4 text-primary" />
                        Vínculos com Candidaturas ({material.links.length})
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-2 text-xs">
                      {material.links.length === 0 ? (
                        <p className="text-muted-foreground">
                          Este material ainda não foi vinculado a nenhuma
                          candidatura.
                        </p>
                      ) : (
                        material.links.map((lk) => (
                          <div
                            key={lk.id}
                            className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border p-2.5"
                          >
                            <div>
                              <span className="font-semibold">
                                {lk.application_role_title || "Candidatura"}
                              </span>
                              {lk.application_company_name
                                ? ` — ${lk.application_company_name}`
                                : ""}
                              <div className="text-muted-foreground">
                                Versão v{lk.version_number} · Vinculado em{" "}
                                {formatDateTimePtBr(lk.linked_at)}
                              </div>
                            </div>
                            <Badge variant={lk.is_active ? "default" : "outline"}>
                              {lk.is_active
                                ? "Ativo"
                                : `Desvinculado (${formatDateTimePtBr(lk.unlinked_at)})`}
                            </Badge>
                          </div>
                        ))
                      )}
                    </CardContent>
                  </Card>

                  {activeVersion.missing_requirements.length > 0 && (
                    <Card>
                      <CardHeader className="pb-2">
                        <CardTitle className="text-sm">
                          Lacunas Identificadas na Geração
                        </CardTitle>
                      </CardHeader>
                      <CardContent className="space-y-1.5 text-xs text-muted-foreground">
                        {activeVersion.missing_requirements.map((gap, i) => (
                          <div key={i}>
                            • <strong>{gap.requirement}:</strong> {gap.note}
                          </div>
                        ))}
                      </CardContent>
                    </Card>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

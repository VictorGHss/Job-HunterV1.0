import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  Check,
  CheckCircle2,
  Copy,
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
import type {
  ContactInclusionOptions,
  MaterialBlockProvenance,
  MaterialDetailResponse,
  MaterialExportFormat,
  MaterialPreAnalysisResponse,
  MaterialTargetLanguage,
  MaterialVersionItem,
  ProfileConfirmBatchPayload,
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

type WorkspacePanelTab = "editor" | "preview" | "history";

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
};

const ENTITY_TYPE_LABELS: Record<string, string> = {
  profile: "Perfil",
  experience: "Experiência",
  project: "Projeto",
  education: "Formação",
  skill: "Habilidade",
  language: "Idioma",
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
  const [targetLanguage, setTargetLanguage] =
    useState<MaterialTargetLanguage>("pt-BR");
  const [contactOptions, setContactOptions] = useState<ContactInclusionOptions>(
    DEFAULT_CONTACT_OPTIONS
  );
  const [customTitle, setCustomTitle] = useState("");
  const [userInstructions, setUserInstructions] = useState("");

  const [preAnalysis, setPreAnalysis] =
    useState<MaterialPreAnalysisResponse | null>(null);
  const [preLoading, setPreLoading] = useState(false);
  const [selectedBatchKeys, setSelectedBatchKeys] = useState<string[]>([]);
  const [confirmingBatch, setConfirmingBatch] = useState(false);

  const [material, setMaterial] = useState<MaterialDetailResponse | null>(null);
  const [activeVersionId, setActiveVersionId] = useState<string | null>(null);
  const [draftContent, setDraftContent] =
    useState<ResumeStructuredContent | null>(null);
  const [panelTab, setPanelTab] = useState<WorkspacePanelTab>("editor");

  const [busyAction, setBusyAction] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [copiedFormat, setCopiedFormat] =
    useState<MaterialExportFormat | null>(null);

  const loadPreAnalysis = useCallback(
    async (lang: MaterialTargetLanguage, opts: ContactInclusionOptions) => {
      setPreLoading(true);
      setErrorMsg(null);
      try {
        const res = await api.materials.preAnalyze({
          opportunity_id: opportunityId || null,
          application_id: applicationId || null,
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
    [applicationId, opportunityId]
  );

  const loadExistingMaterial = useCallback(async (matId: string) => {
    setBusyAction(true);
    setErrorMsg(null);
    try {
      const detail = await api.materials.get(matId);
      setMaterial(detail);
      const latest = detail.versions[0] || null;
      setActiveVersionId(latest?.id || null);
      setDraftContent(latest ? latest.structured_content : null);
      if (detail.target_language === "en" || detail.target_language === "pt-BR") {
        setTargetLanguage(detail.target_language);
      }
    } catch (err) {
      setErrorMsg(
        err instanceof Error
          ? err.message
          : "Não foi possível carregar o material selecionado."
      );
    } finally {
      setBusyAction(false);
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
      void loadPreAnalysis(targetLanguage, contactOptions);
    }
  }, [
    open,
    initialMaterialId,
    loadExistingMaterial,
    loadPreAnalysis,
    targetLanguage,
    contactOptions,
  ]);

  const activeVersion: MaterialVersionItem | null = useMemo(() => {
    if (!material || material.versions.length === 0) return null;
    if (activeVersionId) {
      return (
        material.versions.find((v) => v.id === activeVersionId) ||
        material.versions[0]
      );
    }
    return material.versions[0];
  }, [activeVersionId, material]);

  useEffect(() => {
    if (activeVersion) {
      setDraftContent(activeVersion.structured_content);
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
      await loadPreAnalysis(targetLanguage, contactOptions);
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
        "Currículo determinístico gerado exclusivamente com fatos confirmados."
      );
      onMaterialChanged?.();
    } catch (err) {
      setErrorMsg(
        err instanceof Error
          ? err.message
          : "Não foi possível gerar o currículo."
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
    if (!material || !activeVersion) return;
    setBusyAction(true);
    setErrorMsg(null);
    setSuccessMsg(null);
    try {
      const updated = await api.materials.approveVersion(
        material.id,
        activeVersion.id
      );
      setMaterial(updated);
      setSuccessMsg(
        `Versão v${activeVersion.version_number} aprovada e bloqueada contra mutações.`
      );
      onMaterialChanged?.();
    } catch (err) {
      setErrorMsg(
        err instanceof Error ? err.message : "Falha ao aprovar versão."
      );
    } finally {
      setBusyAction(false);
    }
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
    if (!material || !activeVersion) return;
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

  const updateExperienceItem = (
    idx: number,
    patch: Partial<ResumeExperienceItem>
  ) => {
    if (!draftContent) return;
    const next = [...draftContent.experiences];
    next[idx] = { ...next[idx], ...patch, provenance: "manual_edit" };
    setDraftContent({ ...draftContent, experiences: next });
  };

  const updateProjectItem = (
    idx: number,
    patch: Partial<ResumeProjectItem>
  ) => {
    if (!draftContent) return;
    const next = [...draftContent.projects];
    next[idx] = { ...next[idx], ...patch, provenance: "manual_edit" };
    setDraftContent({ ...draftContent, projects: next });
  };

  const addManualNote = () => {
    if (!draftContent) return;
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

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 p-2 backdrop-blur-sm sm:p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Estúdio de Currículo Direcionado"
    >
      <div className="relative flex max-h-[92vh] w-full max-w-5xl flex-col overflow-hidden rounded-2xl border border-border bg-card shadow-2xl">
        {/* Cabeçalho */}
        <div className="flex flex-wrap items-start justify-between gap-3 border-b border-border bg-muted/30 px-4 py-3.5 sm:px-6">
          <div className="space-y-1">
            <div className="flex flex-wrap items-center gap-2">
              <FileText className="h-5 w-5 text-primary" />
              <h2 className="text-base font-bold text-foreground sm:text-lg">
                {material ? material.title : "Currículo Direcionado Determinístico"}
              </h2>
              <Badge variant="secondary" className="text-[11px]">
                Fase 04.1 · Sem IA
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
                  setMaterial(null);
                  setActiveVersionId(null);
                  void loadPreAnalysis(targetLanguage, contactOptions);
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
              {/* Configurações */}
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm">
                    Configuração do Currículo
                  </CardTitle>
                  <CardDescription className="text-xs">
                    Escolha o idioma de geração e quais informações de contato
                    confirmadas entram no cabeçalho.
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                    <div className="space-y-1.5">
                      <Label htmlFor="mat-lang">Idioma do currículo</Label>
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
                      disabled={!preAnalysis.can_generate || busyAction}
                      onClick={handleGenerateMaterial}
                    >
                      <Sparkles className="mr-1.5 h-4 w-4" />
                      {busyAction
                        ? "Gerando..."
                        : "Gerar Currículo Direcionado"}
                    </Button>
                  </div>
                </>
              )}
            </div>
          )}

          {/* MODO 2: EDITOR, PREVIEW, HISTÓRICO, APROVAÇÃO E VÍNCULO */}
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
                            : "border-border bg-background text-foreground hover:bg-muted/40"
                        }`}
                      >
                        <span>v{ver.version_number}</span>
                        <span className="opacity-80">
                          {ORIGIN_LABELS[ver.origin] || ver.origin}
                        </span>
                        {ver.is_approved && <Lock className="h-3 w-3" />}
                      </button>
                    );
                  })}
                </div>

                <div className="flex flex-wrap items-center gap-2">
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
                  {!activeVersion.is_mutable && (
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
                  {!activeVersion.is_approved && (
                    <Button
                      type="button"
                      size="sm"
                      disabled={busyAction}
                      onClick={handleApproveVersion}
                    >
                      <CheckCircle2 className="mr-1.5 h-3.5 w-3.5" />
                      Aprovar versão
                    </Button>
                  )}
                  {applicationId && activeVersion.is_approved && (
                    <Button
                      type="button"
                      size="sm"
                      variant={
                        activeLinkForCurrentApp?.version_id === activeVersion.id
                          ? "secondary"
                          : "default"
                      }
                      disabled={busyAction}
                      onClick={handleLinkToApplication}
                    >
                      <Link2 className="mr-1.5 h-3.5 w-3.5" />
                      {activeLinkForCurrentApp?.version_id === activeVersion.id
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

              {/* Aviso de edição manual ou imutabilidade */}
              {draftContent.has_unverified_manual_edits &&
                !activeVersion.is_approved && (
                  <div className="flex items-start gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-xs text-amber-800 dark:text-amber-200">
                    <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                    <span>
                      Este rascunho contém alterações manuais ainda não confirmadas
                      no Perfil. Ao aprovar, você confirma que o conteúdo deste
                      currículo é exato.
                    </span>
                  </div>
                )}

              {!activeVersion.is_mutable && (
                <div className="flex items-start gap-2 rounded-lg border border-border bg-muted/40 p-3 text-xs text-muted-foreground">
                  <Lock className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                  <span>
                    Versão v{activeVersion.version_number} está{" "}
                    {activeVersion.is_approved ? "aprovada" : "somente leitura"} e
                    não pode ser sobrescrita diretamente. Use{" "}
                    <strong>Criar versão derivada</strong> ou{" "}
                    <strong>Regenerar do Perfil</strong> para criar um novo
                    rascunho editável.
                  </span>
                </div>
              )}

              {/* Subabas: Editor Estruturado | Pré-visualização | Histórico & Lacunas */}
              <div className="flex flex-wrap gap-1.5 border-b border-border pb-2">
                {[
                  { id: "editor" as const, label: "Editor Estruturado" },
                  { id: "preview" as const, label: "Pré-visualização & Exportação" },
                  { id: "history" as const, label: "Histórico, Fatos & Lacunas" },
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

              {/* TAB EDITOR */}
              {panelTab === "editor" && (
                <div className="space-y-4">
                  {/* Cabeçalho */}
                  <Card>
                    <CardHeader className="pb-2">
                      <div className="flex items-center justify-between gap-2">
                        <CardTitle className="text-sm">Cabeçalho</CardTitle>
                        <Badge
                          variant={
                            PROVENANCE_META[draftContent.header.provenance].variant
                          }
                          className="text-[10px]"
                        >
                          {PROVENANCE_META[draftContent.header.provenance].label}
                        </Badge>
                      </div>
                    </CardHeader>
                    <CardContent className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                      <div className="space-y-1">
                        <Label htmlFor="ed-fullname">Nome completo</Label>
                        <Input
                          id="ed-fullname"
                          disabled={!activeVersion.is_mutable}
                          value={draftContent.header.full_name || ""}
                          onChange={(e) =>
                            setDraftContent({
                              ...draftContent,
                              header: {
                                ...draftContent.header,
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
                          disabled={!activeVersion.is_mutable}
                          value={draftContent.header.professional_title || ""}
                          onChange={(e) =>
                            setDraftContent({
                              ...draftContent,
                              header: {
                                ...draftContent.header,
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
                          disabled={!activeVersion.is_mutable}
                          value={draftContent.header.location_text || ""}
                          onChange={(e) =>
                            setDraftContent({
                              ...draftContent,
                              header: {
                                ...draftContent.header,
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
                          disabled={!activeVersion.is_mutable}
                          value={draftContent.header.email || ""}
                          onChange={(e) =>
                            setDraftContent({
                              ...draftContent,
                              header: {
                                ...draftContent.header,
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
                  {draftContent.summary && (
                    <Card>
                      <CardHeader className="pb-2">
                        <div className="flex items-center justify-between gap-2">
                          <CardTitle className="text-sm">
                            Resumo Profissional
                          </CardTitle>
                          <Badge
                            variant={
                              PROVENANCE_META[draftContent.summary.provenance]
                                .variant
                            }
                            className="text-[10px]"
                          >
                            {
                              PROVENANCE_META[draftContent.summary.provenance]
                                .label
                            }
                          </Badge>
                        </div>
                      </CardHeader>
                      <CardContent>
                        <textarea
                          rows={3}
                          disabled={!activeVersion.is_mutable}
                          value={draftContent.summary.text}
                          onChange={(e) =>
                            setDraftContent({
                              ...draftContent,
                              summary: draftContent.summary
                                ? {
                                    ...draftContent.summary,
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
                        Experiência Profissional ({draftContent.experiences.length})
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-3">
                      {draftContent.experiences.length === 0 ? (
                        <p className="text-xs text-muted-foreground">
                          Nenhuma experiência profissional confirmada incluída.
                        </p>
                      ) : (
                        draftContent.experiences.map((exp, idx) => (
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
                                disabled={!activeVersion.is_mutable}
                                value={exp.role}
                                onChange={(e) =>
                                  updateExperienceItem(idx, {
                                    role: e.target.value,
                                  })
                                }
                              />
                              <Input
                                aria-label={`Empresa da experiência ${idx + 1}`}
                                disabled={!activeVersion.is_mutable}
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
                              disabled={!activeVersion.is_mutable}
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
                        Projetos ({draftContent.projects.length})
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-3">
                      {draftContent.projects.length === 0 ? (
                        <p className="text-xs text-muted-foreground">
                          Nenhum projeto confirmado incluído.
                        </p>
                      ) : (
                        draftContent.projects.map((proj, idx) => (
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
                                disabled={!activeVersion.is_mutable}
                                value={proj.name}
                                onChange={(e) =>
                                  updateProjectItem(idx, {
                                    name: e.target.value,
                                  })
                                }
                              />
                              <Input
                                aria-label={`Papel no projeto ${idx + 1}`}
                                disabled={!activeVersion.is_mutable}
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
                              disabled={!activeVersion.is_mutable}
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

                  {/* Formação, Habilidades e Idiomas (preservação explícita) */}
                  <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
                    <Card>
                      <CardHeader className="pb-2">
                        <CardTitle className="text-xs font-semibold">
                          Formação Acadêmica ({draftContent.education.length})
                        </CardTitle>
                      </CardHeader>
                      <CardContent className="space-y-1.5 text-xs">
                        {draftContent.education.map((edu, idx) => (
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
                          Habilidades ({draftContent.skills.length})
                        </CardTitle>
                      </CardHeader>
                      <CardContent className="flex flex-wrap gap-1.5 text-xs">
                        {draftContent.skills.map((skill, idx) => (
                          <Badge key={`${skill.entity_id || idx}`} variant="secondary">
                            {skill.name} · {skill.proficiency_label}
                          </Badge>
                        ))}
                      </CardContent>
                    </Card>

                    <Card>
                      <CardHeader className="pb-2">
                        <CardTitle className="text-xs font-semibold">
                          Idiomas ({draftContent.languages.length})
                        </CardTitle>
                      </CardHeader>
                      <CardContent className="space-y-1.5 text-xs">
                        {draftContent.languages.map((lang, idx) => (
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
                          {draftContent.manual_notes.length})
                        </CardTitle>
                        {activeVersion.is_mutable && (
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
                      {draftContent.manual_notes.map((note, idx) => (
                        <div
                          key={note.id}
                          className="space-y-2 rounded-lg border border-border p-3"
                        >
                          <div className="flex items-center justify-between gap-2">
                            <Input
                              disabled={!activeVersion.is_mutable}
                              value={note.title}
                              onChange={(e) => {
                                const next = [...draftContent.manual_notes];
                                next[idx] = { ...next[idx], title: e.target.value };
                                setDraftContent({
                                  ...draftContent,
                                  manual_notes: next,
                                });
                              }}
                            />
                            {activeVersion.is_mutable && (
                              <Button
                                type="button"
                                size="icon"
                                variant="ghost"
                                onClick={() => {
                                  const next = draftContent.manual_notes.filter(
                                    (_, i) => i !== idx
                                  );
                                  setDraftContent({
                                    ...draftContent,
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
                            disabled={!activeVersion.is_mutable}
                            value={note.content}
                            onChange={(e) => {
                              const next = [...draftContent.manual_notes];
                              next[idx] = {
                                ...next[idx],
                                content: e.target.value,
                              };
                              setDraftContent({
                                ...draftContent,
                                manual_notes: next,
                              });
                            }}
                            className="w-full rounded-md border border-input bg-background px-3 py-2 text-xs"
                          />
                        </div>
                      ))}
                    </CardContent>
                  </Card>

                  {activeVersion.is_mutable && (
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
                </div>
              )}

              {/* TAB PREVIEW & EXPORT */}
              {panelTab === "preview" && (
                <Card>
                  <CardHeader className="pb-2">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div>
                        <CardTitle className="text-sm">
                          Pré-visualização Final (v{activeVersion.version_number})
                        </CardTitle>
                        <CardDescription className="text-xs">
                          Renderização pura derivada do conteúdo estruturado
                          canônico.
                        </CardDescription>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          disabled={busyAction}
                          onClick={() => handleCopyExport("markdown")}
                        >
                          <Copy className="mr-1.5 h-3.5 w-3.5" />
                          {copiedFormat === "markdown"
                            ? "Markdown copiado!"
                            : "Copiar Markdown"}
                        </Button>
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          disabled={busyAction}
                          onClick={() => handleCopyExport("text")}
                        >
                          <Copy className="mr-1.5 h-3.5 w-3.5" />
                          {copiedFormat === "text"
                            ? "Texto copiado!"
                            : "Copiar Texto Simples"}
                        </Button>
                      </div>
                    </div>
                  </CardHeader>
                  <CardContent>
                    <pre className="max-h-[55vh] overflow-auto whitespace-pre-wrap break-words rounded-xl border border-border bg-muted/20 p-4 font-mono text-xs leading-relaxed text-foreground">
                      {activeVersion.rendered_markdown}
                    </pre>
                  </CardContent>
                </Card>
              )}

              {/* TAB HISTÓRICO & LACUNAS */}
              {panelTab === "history" && (
                <div className="space-y-4">
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

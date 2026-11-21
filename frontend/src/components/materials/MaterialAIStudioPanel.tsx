import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Edit3,
  FileCheck2,
  GitCompare,
  Lock,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  XCircle,
} from "lucide-react";

import {
  buildStructuredSlotDiffs,
  extractMaterialSlots,
  hasVisibleText,
  resolveFactReferenceDisplay,
  type AIErrorPresentation,
} from "@/components/materials/aiStudioUtils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Label } from "@/components/ui/input";
import type {
  MaterialAIEnhancePayload,
  MaterialAIOverlayMetadata,
  MaterialBlockProvenance,
  MaterialDetailResponse,
  MaterialVersionItem,
} from "@/types/api";

const PROVENANCE_LABELS: Record<
  MaterialBlockProvenance,
  { label: string; variant: "default" | "secondary" | "outline" }
> = {
  confirmed_fact: { label: "Fato confirmado", variant: "secondary" },
  manual_edit: { label: "Editado manualmente", variant: "outline" },
  user_authored: { label: "Autoral (usuário)", variant: "outline" },
};

const ORIGIN_LABELS: Record<string, string> = {
  generated: "Gerada de fatos confirmados",
  manual_edit: "Edição manual",
  regenerated: "Regenerada do perfil",
  derived: "Derivada de versão",
  ai_assisted: "IA assistida",
};

const MATERIAL_TYPE_LABELS: Record<string, string> = {
  resume: "Currículo Direcionado",
  cover_letter: "Carta de Apresentação",
  recruiter_message: "Mensagem para Recrutador",
  freelance_proposal: "Proposta Freelance",
  application_answers: "Respostas de Candidatura",
};

interface MaterialAIStudioPanelProps {
  material: MaterialDetailResponse;
  activeVersion: MaterialVersionItem;
  latestActiveVersion: MaterialVersionItem | null;
  busyAction: boolean;
  aiEnhancing: boolean;
  aiError: AIErrorPresentation | null;
  isDerivingEditMode: boolean;
  onDismissAiError: () => void;
  onReloadMaterial: () => void;
  onSelectVersion: (version: MaterialVersionItem) => void;
  onRunAiEnhance: (payload: MaterialAIEnhancePayload) => void;
  onApproveVersion: () => void;
  onStartDeriveEdit: () => void;
  onSaveDerivedVersion: () => void;
  onCancelDeriveEdit: () => void;
  onRejectAiVersion: () => void;
}

export function MaterialAIStudioPanel({
  material,
  activeVersion,
  latestActiveVersion,
  busyAction,
  aiEnhancing,
  aiError,
  isDerivingEditMode,
  onDismissAiError,
  onReloadMaterial,
  onSelectVersion,
  onRunAiEnhance,
  onApproveVersion,
  onStartDeriveEdit,
  onSaveDerivedVersion,
  onCancelDeriveEdit,
  onRejectAiVersion,
}: MaterialAIStudioPanelProps) {
  const [selectionMode, setSelectionMode] = useState<"auto" | "manual">("auto");
  const [selectedSlotIds, setSelectedSlotIds] = useState<string[]>([]);
  const [aiInstructions, setAiInstructions] = useState<string>(
    activeVersion.user_instructions || ""
  );
  const [diffFilter, setDiffFilter] = useState<"all" | "changed" | "preserved">(
    "all"
  );

  const currentSlots = useMemo(
    () =>
      extractMaterialSlots(
        material.material_type,
        activeVersion.structured_content
      ),
    [material.material_type, activeVersion.structured_content]
  );

  const autoEligibleSlots = useMemo(
    () => currentSlots.filter((s) => s.autoEligible),
    [currentSlots]
  );

  const manualSelectableSlots = useMemo(
    () => currentSlots.filter((s) => s.manualSelectable),
    [currentSlots]
  );

  useEffect(() => {
    setSelectedSlotIds(
      currentSlots.filter((s) => s.autoEligible).map((s) => s.slotId)
    );
  }, [activeVersion.id, currentSlots]);

  const parentVersion = useMemo(() => {
    if (!activeVersion.parent_version_id) return null;
    return (
      material.versions.find((v) => v.id === activeVersion.parent_version_id) ||
      null
    );
  }, [material.versions, activeVersion.parent_version_id]);

  const aiOverlay = useMemo<MaterialAIOverlayMetadata | null>(() => {
    const raw = activeVersion.source_facts_snapshot?.ai_overlay;
    if (raw && typeof raw === "object") {
      return raw as MaterialAIOverlayMetadata;
    }
    return null;
  }, [activeVersion.source_facts_snapshot]);

  const slotDiffs = useMemo(
    () =>
      buildStructuredSlotDiffs(
        material.material_type,
        parentVersion ? parentVersion.structured_content : null,
        activeVersion.structured_content,
        aiOverlay,
        activeVersion.origin
      ),
    [
      material.material_type,
      parentVersion,
      activeVersion.structured_content,
      aiOverlay,
      activeVersion.origin,
    ]
  );

  const filteredDiffs = useMemo(() => {
    if (diffFilter === "changed") {
      return slotDiffs.filter(
        (d) =>
          d.status === "modified" ||
          d.status === "added" ||
          d.status === "removed"
      );
    }
    if (diffFilter === "preserved") {
      return slotDiffs.filter(
        (d) =>
          d.status === "preserved_user_authored" ||
          d.status === "preserved_manual_edit" ||
          d.status === "unchanged"
      );
    }
    return slotDiffs;
  }, [slotDiffs, diffFilter]);

  const diffStats = useMemo(() => {
    let changedCount = 0;
    let preservedUserCount = 0;
    let preservedManualCount = 0;
    let unchangedFactCount = 0;
    const allFactKeys = new Set<string>();

    for (const d of slotDiffs) {
      for (const fk of d.sourceFactKeys) {
        allFactKeys.add(fk);
      }
      if (
        d.status === "modified" ||
        d.status === "added" ||
        d.status === "removed"
      ) {
        changedCount += 1;
      } else if (d.status === "preserved_user_authored") {
        preservedUserCount += 1;
      } else if (d.status === "preserved_manual_edit") {
        preservedManualCount += 1;
      } else {
        unchangedFactCount += 1;
      }
    }

    return {
      changedCount,
      preservedUserCount,
      preservedManualCount,
      unchangedFactCount,
      totalCitedFacts: allFactKeys.size,
      allFactKeys: Array.from(allFactKeys),
    };
  }, [slotDiffs]);

  const isLatestActive =
    !activeVersion.is_rejected &&
    (latestActiveVersion === null ||
      activeVersion.id === latestActiveVersion.id);

  const isUnapprovedAiSuggestion =
    activeVersion.origin === "ai_assisted" &&
    !activeVersion.is_approved &&
    !activeVersion.is_rejected;

  const effectiveTargetSlotsCount =
    selectionMode === "auto"
      ? autoEligibleSlots.length
      : selectedSlotIds.length;

  const canSubmitAiEnhance =
    !busyAction &&
    !aiEnhancing &&
    !activeVersion.is_rejected &&
    isLatestActive &&
    effectiveTargetSlotsCount > 0 &&
    aiInstructions.length <= 1500;

  const handleToggleSlot = (slotId: string) => {
    setSelectedSlotIds((prev) =>
      prev.includes(slotId)
        ? prev.filter((id) => id !== slotId)
        : [...prev, slotId]
    );
  };

  const handleTriggerEnhance = () => {
    if (!canSubmitAiEnhance) return;
    const payload: MaterialAIEnhancePayload = {
      target_slot_ids: selectionMode === "manual" ? selectedSlotIds : null,
      user_instructions: aiInstructions.trim() ? aiInstructions.trim() : null,
    };
    onRunAiEnhance(payload);
  };

  return (
    <div className="space-y-4" data-testid="ai-studio-panel">
      {/* Alerta categorizado de erros de IA (X-AI-Error-Code / Retry-After) */}
      {aiError && (
        <div
          role="alert"
          className={`rounded-xl border p-3.5 text-xs ${
            aiError.severity === "destructive"
              ? "border-destructive/50 bg-destructive/10 text-destructive"
              : "border-amber-500/50 bg-amber-500/10 text-amber-900 dark:text-amber-200"
          }`}
        >
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div className="space-y-1">
              <div className="flex flex-wrap items-center gap-2 font-semibold">
                <AlertTriangle className="h-4 w-4 shrink-0" />
                <span>{aiError.title}</span>
                {aiError.errorCodeBadge && (
                  <Badge variant="outline" className="font-mono text-[10px]">
                    {aiError.errorCodeBadge}
                  </Badge>
                )}
              </div>
              <p className="leading-relaxed">{aiError.description}</p>
              {aiError.retryAfterLabel && (
                <p className="font-medium">{aiError.retryAfterLabel}</p>
              )}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {aiError.canReloadMaterial && (
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  disabled={busyAction}
                  onClick={onReloadMaterial}
                >
                  <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
                  Recarregar material
                </Button>
              )}
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={onDismissAiError}
              >
                Fechar aviso
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* SEÇÃO 1: Banner de Revisão e Decisão Humana quando a versão atual é ai_assisted */}
      {activeVersion.origin === "ai_assisted" && (
        <Card
          className={
            activeVersion.is_rejected
              ? "border-destructive/40 bg-destructive/5"
              : activeVersion.is_approved
                ? "border-emerald-500/40 bg-emerald-500/5"
                : "border-primary/50 bg-primary/5"
          }
        >
          <CardHeader className="pb-2">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div className="space-y-1">
                <div className="flex flex-wrap items-center gap-2">
                  <Sparkles className="h-4 w-4 text-primary" />
                  <CardTitle className="text-sm">
                    {activeVersion.is_rejected
                      ? `Sugestão de IA Rejeitada (v${activeVersion.version_number})`
                      : activeVersion.is_approved
                        ? `Sugestão de IA Aprovada (v${activeVersion.version_number})`
                        : `Revisão Humana Obrigatória — Sugestão de IA (v${activeVersion.version_number})`}
                  </CardTitle>
                  <Badge
                    variant={
                      activeVersion.is_rejected
                        ? "outline"
                        : activeVersion.is_approved
                          ? "default"
                          : "secondary"
                    }
                  >
                    {activeVersion.is_rejected
                      ? "Rejeitada"
                      : activeVersion.is_approved
                        ? "Aprovada"
                        : "Sugestão não aprovada"}
                  </Badge>
                </div>
                <CardDescription className="text-xs">
                  {activeVersion.is_rejected ? (
                    <>
                      Esta sugestão gerada por IA foi rejeitada pelo usuário e permanece no histórico apenas para rastreabilidade. Nenhuma aprovação, edição, derivação, exportação ou vinculação é permitida sobre versão rejeitada.
                    </>
                  ) : activeVersion.is_approved ? (
                    <>
                      Esta versão assistida por IA foi revisada e aprovada pelo usuário. Ela é imutável e está pronta para exportação ou vinculação à candidatura.
                    </>
                  ) : (
                    <>
                      Esta versão <strong>ainda não está aprovada</strong>. Compare as alterações estruturadas em relação à versão de origem{" "}
                      {parentVersion
                        ? `v${parentVersion.version_number}`
                        : "anterior"}
                      , verifique as referências factuais citadas e escolha uma decisão humana abaixo.
                    </>
                  )}
                </CardDescription>
              </div>
            </div>
          </CardHeader>

          {isUnapprovedAiSuggestion && (
            <CardContent className="space-y-3 pt-1">
              {activeVersion.has_blocking_pending_fields && (
                <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-2.5 text-xs text-amber-900 dark:text-amber-200">
                  <strong>Aprovação direta bloqueada:</strong> esta versão possui{" "}
                  <strong>
                    {activeVersion.pending_requirements_count || 1}
                  </strong>{" "}
                  campo(s) obrigatório(s) pendente(s) do usuário. Use{" "}
                  <strong>Editar como versão derivada</strong> para preencher as informações pendentes antes de aprovar.
                </div>
              )}

              <div className="flex flex-wrap items-center gap-2">
                <Button
                  type="button"
                  size="sm"
                  disabled={
                    busyAction ||
                    Boolean(activeVersion.has_blocking_pending_fields)
                  }
                  onClick={onApproveVersion}
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
                    onClick={onStartDeriveEdit}
                  >
                    <Edit3 className="mr-1.5 h-3.5 w-3.5" />
                    Editar como versão derivada
                  </Button>
                ) : (
                  <>
                    <Button
                      type="button"
                      size="sm"
                      variant="default"
                      disabled={busyAction}
                      onClick={onSaveDerivedVersion}
                    >
                      <FileCheck2 className="mr-1.5 h-3.5 w-3.5" />
                      Salvar versão derivada
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      disabled={busyAction}
                      onClick={onCancelDeriveEdit}
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
                  onClick={onRejectAiVersion}
                >
                  <XCircle className="mr-1.5 h-3.5 w-3.5" />
                  Rejeitar sugestão
                </Button>
              </div>
            </CardContent>
          )}
        </Card>
      )}

      {/* SEÇÃO 2: Comparação Estruturada entre Versões & Proveniência / Fatos Citados */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div>
              <CardTitle className="flex items-center gap-2 text-sm">
                <GitCompare className="h-4 w-4 text-primary" />
                Comparação Estruturada & Proveniência Factual (
                {parentVersion
                  ? `v${parentVersion.version_number} → v${activeVersion.version_number}`
                  : `v${activeVersion.version_number}`}
                )
              </CardTitle>
              <CardDescription className="text-xs">
                {parentVersion ? (
                  <>
                    Comparação campo a campo entre a versão de origem{" "}
                    <strong>
                      v{parentVersion.version_number} (
                      {ORIGIN_LABELS[parentVersion.origin] ||
                        parentVersion.origin}
                      )
                    </strong>{" "}
                    e a versão selecionada{" "}
                    <strong>
                      v{activeVersion.version_number} (
                      {ORIGIN_LABELS[activeVersion.origin] ||
                        activeVersion.origin}
                      )
                    </strong>
                    .
                  </>
                ) : (
                  <>
                    Inspeção estruturada de slots, proveniência dos blocos e fatos confirmados citados na versão{" "}
                    <strong>v{activeVersion.version_number}</strong>.
                  </>
                )}
              </CardDescription>
            </div>

            {/* Resumo estatístico da comparação e proveniência */}
            <div className="flex flex-wrap items-center gap-1.5 text-xs">
              <Badge variant="default" className="text-[10px]">
                {diffStats.changedCount} slot(s) alterado(s)
              </Badge>
              <Badge variant="secondary" className="text-[10px]">
                {diffStats.unchangedFactCount} fato(s) inalterado(s)
              </Badge>
              {diffStats.preservedManualCount > 0 && (
                <Badge variant="outline" className="text-[10px]">
                  {diffStats.preservedManualCount} edição(ões) manual(is) preservada(s)
                </Badge>
              )}
              {diffStats.preservedUserCount > 0 && (
                <Badge variant="outline" className="text-[10px]">
                  {diffStats.preservedUserCount} bloco(s) autoral(is) protegido(s)
                </Badge>
              )}
              <Badge variant="outline" className="text-[10px]">
                {diffStats.totalCitedFacts} fato(s) confirmado(s) citado(s)
              </Badge>
            </div>
          </div>

          {/* Legenda clara de proveniência e filtro de visualização */}
          <div className="mt-2 flex flex-col gap-2 rounded-lg border border-border bg-muted/20 p-2.5 text-xs sm:flex-row sm:flex-wrap sm:items-center sm:justify-between">
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="font-medium text-muted-foreground">
                Proveniência:
              </span>
              <Badge variant="secondary" className="text-[10px]">
                Fato confirmado
              </Badge>
              <Badge variant="outline" className="text-[10px]">
                Editado manualmente
              </Badge>
              <Badge variant="outline" className="text-[10px]">
                Autoral (usuário)
              </Badge>
              <Badge variant="default" className="text-[10px]">
                Aprimorado por IA
              </Badge>
            </div>

            <div
              role="group"
              aria-label="Filtrar slots na comparação estruturada"
              className="inline-flex rounded-lg border border-border bg-background p-0.5"
            >
              {(
                [
                  { id: "all", label: `Todos (${slotDiffs.length})` },
                  {
                    id: "changed",
                    label: `Alterados (${diffStats.changedCount})`,
                  },
                  {
                    id: "preserved",
                    label: `Preservados (${
                      slotDiffs.length - diffStats.changedCount
                    })`,
                  },
                ] as const
              ).map((tab) => (
                <button
                  key={tab.id}
                  type="button"
                  aria-pressed={diffFilter === tab.id}
                  onClick={() => setDiffFilter(tab.id)}
                  className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                    diffFilter === tab.id
                      ? "bg-primary text-primary-foreground"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>
          </div>
        </CardHeader>

        <CardContent className="space-y-3">
          {filteredDiffs.length === 0 ? (
            <p className="rounded-lg border border-dashed border-border p-4 text-center text-xs text-muted-foreground">
              Nenhum slot corresponde ao filtro selecionado.
            </p>
          ) : (
            filteredDiffs.map((item) => {
              const provMeta =
                PROVENANCE_LABELS[item.afterProvenance] ||
                PROVENANCE_LABELS.user_authored;

              const statusBadge = (() => {
                switch (item.status) {
                  case "modified":
                    return {
                      label: item.isAppliedByAi
                        ? "Alterado pela IA"
                        : "Alterado",
                      variant: "default" as const,
                    };
                  case "added":
                    return {
                      label: "Adicionado",
                      variant: "default" as const,
                    };
                  case "removed":
                    return {
                      label: "Removido",
                      variant: "outline" as const,
                    };
                  case "preserved_user_authored":
                    return {
                      label: "Preservado (Autoral)",
                      variant: "outline" as const,
                    };
                  case "preserved_manual_edit":
                    return {
                      label: "Preservado (Edição manual)",
                      variant: "outline" as const,
                    };
                  default:
                    return {
                      label: parentVersion ? "Inalterado" : "Slot atual",
                      variant: "secondary" as const,
                    };
                }
              })();

              return (
                <div
                  key={item.slotId}
                  data-testid={`slot-diff-${item.slotId}`}
                  className={`space-y-2.5 rounded-xl border p-3 text-xs ${
                    item.status === "modified" || item.status === "added"
                      ? "border-primary/40 bg-primary/5"
                      : "border-border bg-card"
                  }`}
                >
                  {/* Cabeçalho do Slot com label, slot_id técnico, diff status e proveniência */}
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="font-semibold text-foreground">
                        {item.label}
                      </span>
                      <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
                        {item.slotId}
                      </code>
                      {item.subtitle && (
                        <span className="text-[11px] text-muted-foreground">
                          ({item.subtitle})
                        </span>
                      )}
                    </div>

                    <div className="flex flex-wrap items-center gap-1.5">
                      <Badge variant={statusBadge.variant} className="text-[10px]">
                        {statusBadge.label}
                      </Badge>
                      <Badge variant={provMeta.variant} className="text-[10px]">
                        {provMeta.label}
                      </Badge>
                      {item.isAppliedByAi && (
                        <Badge variant="default" className="text-[10px]">
                          Sugestão IA
                        </Badge>
                      )}
                    </div>
                  </div>

                  {/* Blocos Antes (Versão pai) vs Depois (Versão atual / Sugestão IA) */}
                  {parentVersion ? (
                    <div className="grid grid-cols-1 gap-2.5 md:grid-cols-2">
                      <div className="space-y-1 rounded-lg border border-border bg-background/80 p-2.5">
                        <div className="flex items-center justify-between text-[11px] font-medium text-muted-foreground">
                          <span>
                            Antes (v{parentVersion.version_number} ·{" "}
                            {ORIGIN_LABELS[parentVersion.origin] ||
                              parentVersion.origin}
                            )
                          </span>
                          {item.beforeProvenance && (
                            <span>
                              {PROVENANCE_LABELS[item.beforeProvenance]?.label}
                            </span>
                          )}
                        </div>
                        <p className="whitespace-pre-wrap break-words leading-relaxed text-muted-foreground">
                          {hasVisibleText(item.beforeText)
                            ? item.beforeText
                            : "— Sem conteúdo na versão anterior —"}
                        </p>
                      </div>

                      <div
                        className={`space-y-1 rounded-lg border p-2.5 ${
                          item.status === "modified" || item.status === "added"
                            ? "border-primary/40 bg-background"
                            : "border-border bg-background/80"
                        }`}
                      >
                        <div className="flex items-center justify-between text-[11px] font-medium text-foreground">
                          <span className="flex items-center gap-1">
                            <ArrowRight className="h-3 w-3 text-primary" />
                            Depois (v{activeVersion.version_number} ·{" "}
                            {activeVersion.is_approved
                              ? "Aprovada"
                              : activeVersion.origin === "ai_assisted"
                                ? "Sugestão não aprovada"
                                : "Rascunho"}
                            )
                          </span>
                          <span>{provMeta.label}</span>
                        </div>
                        <p className="whitespace-pre-wrap break-words leading-relaxed text-foreground">
                          {hasVisibleText(item.afterText)
                            ? item.afterText
                            : "— Removido / Vazio —"}
                        </p>
                      </div>
                    </div>
                  ) : (
                    <div className="rounded-lg border border-border bg-background p-2.5">
                      <p className="whitespace-pre-wrap break-words leading-relaxed text-foreground">
                        {hasVisibleText(item.afterText)
                          ? item.afterText
                          : "— Sem texto preenchido neste slot —"}
                      </p>
                    </div>
                  )}

                  {/* Referências Factuais Citadas (source_fact_keys) contextualizadas por slot */}
                  <div className="flex flex-wrap items-center gap-1.5 pt-0.5">
                    <span className="text-[11px] font-medium text-muted-foreground">
                      Referências factuais citadas:
                    </span>
                    {item.sourceFactKeys.length === 0 ? (
                      <span className="text-[11px] text-muted-foreground">
                        Nenhuma citação factual direta (bloco estrutural ou autoral)
                      </span>
                    ) : (
                      item.sourceFactKeys.map((factKey) => {
                        const resolved = resolveFactReferenceDisplay(
                          factKey,
                          activeVersion.source_facts_snapshot
                        );
                        return (
                          <span
                            key={factKey}
                            title={
                              resolved.detail
                                ? `${resolved.title} — ${resolved.detail} (${resolved.factKey})`
                                : `${resolved.title} (${resolved.factKey})`
                            }
                            className="inline-flex items-center gap-1 rounded-md border border-border bg-muted/40 px-2 py-0.5 text-[11px] text-foreground"
                          >
                            <ShieldCheck className="h-3 w-3 text-emerald-600 dark:text-emerald-400" />
                            <strong>{resolved.entityTypeLabel}:</strong>{" "}
                            <span>{resolved.title}</span>
                            {resolved.title !== resolved.factKey && (
                              <code className="font-mono text-[10px] text-muted-foreground">
                                ({resolved.factKey})
                              </code>
                            )}
                          </span>
                        );
                      })
                    )}
                  </div>
                </div>
              );
            })
          )}
        </CardContent>
      </Card>

      {/* SEÇÃO 3: Solicitar Novo Aprimoramento Assistido por IA */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div>
              <CardTitle className="flex items-center gap-2 text-sm">
                <Sparkles className="h-4 w-4 text-primary" />
                AI Studio — Solicitar Aprimoramento Assistido por IA
              </CardTitle>
              <CardDescription className="text-xs">
                Material:{" "}
                <strong>
                  {MATERIAL_TYPE_LABELS[material.material_type] ||
                    material.material_type}
                </strong>{" "}
                · Versão de origem selecionada:{" "}
                <strong>
                  v{activeVersion.version_number} (
                  {ORIGIN_LABELS[activeVersion.origin] || activeVersion.origin})
                </strong>{" "}
                · Estado:{" "}
                <strong>
                  {activeVersion.is_rejected
                    ? "Rejeitada"
                    : activeVersion.is_approved
                      ? "Aprovada"
                      : "Rascunho não aprovado"}
                </strong>
              </CardDescription>
            </div>
            <Badge variant="outline" className="text-[10px]">
              Gera sugestão não aprovada (revisão humana obrigatória)
            </Badge>
          </div>
        </CardHeader>

        <CardContent className="space-y-4 text-xs">
          {/* Aviso de governança e imutabilidade */}
          <div className="rounded-lg border border-border bg-muted/20 p-3 text-muted-foreground">
            O aprimoramento por IA nunca modifica a versão{" "}
            <strong>v{activeVersion.version_number}</strong> in-place: o backend
            cria uma nova versão imutável <code>ai_assisted</code> como{" "}
            <strong>sugestão não aprovada</strong>, preservando fatos
            confirmados, blocos autorais (<code>user_authored</code>) e campos
            comerciais/pessoais pendentes (<code>pending_fields</code>).
          </div>

          {/* Restrições de elegibilidade de versão definidas pelo backend */}
          {activeVersion.is_rejected ? (
            <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-destructive">
              <span>
                <strong>Versão rejeitada:</strong> a versão v
                {activeVersion.version_number} foi rejeitada e não pode servir
                de base para novo aprimoramento por IA.
              </span>
              {latestActiveVersion && (
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() => onSelectVersion(latestActiveVersion)}
                >
                  Ir para versão ativa (v{latestActiveVersion.version_number})
                </Button>
              )}
            </div>
          ) : !isLatestActive && latestActiveVersion ? (
            <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-amber-900 dark:text-amber-200">
              <span>
                <strong>Versão histórica selecionada:</strong> apenas a versão
                ativa mais recente (
                <strong>v{latestActiveVersion.version_number}</strong>) pode
                receber novo aprimoramento por IA.
              </span>
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => onSelectVersion(latestActiveVersion)}
              >
                Selecionar versão ativa (v{latestActiveVersion.version_number})
              </Button>
            </div>
          ) : null}

          {/* Modo de seleção de slots (Automático vs Seleção Explícita com Política 2) */}
          <div className="space-y-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <Label className="text-xs font-semibold">
                Escopo de slots para aprimoramento
              </Label>
              <div
                role="group"
                aria-label="Modo de seleção de slots para IA"
                className="inline-flex rounded-lg border border-border bg-background p-0.5"
              >
                <button
                  type="button"
                  aria-pressed={selectionMode === "auto"}
                  onClick={() => setSelectionMode("auto")}
                  className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                    selectionMode === "auto"
                      ? "bg-primary text-primary-foreground"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  Automático ({autoEligibleSlots.length} elegíveis)
                </button>
                <button
                  type="button"
                  aria-pressed={selectionMode === "manual"}
                  onClick={() => setSelectionMode("manual")}
                  className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                    selectionMode === "manual"
                      ? "bg-primary text-primary-foreground"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  Seleção manual de slots ({selectedSlotIds.length}/
                  {manualSelectableSlots.length})
                </button>
              </div>
            </div>

            {selectionMode === "auto" ? (
              <p className="text-muted-foreground">
                No modo automático, apenas os{" "}
                <strong>{autoEligibleSlots.length}</strong> slot(s) de origem{" "}
                <code>confirmed_fact</code> são enviados para redação assistida.
                Blocos editados manualmente (<code>manual_edit</code>) e
                autorais (<code>user_authored</code>) permanecem intocados.
              </p>
            ) : (
              <div className="space-y-2 rounded-lg border border-border p-3">
                <p className="text-muted-foreground">
                  Selecione quais slots deseja aprimorar. Slots editados
                  manualmente (<code>manual_edit</code>) podem ser incluídos
                  explicitamente (Política 2). Slots autorais (
                  <code>user_authored</code>) e perguntas pendentes permanecem
                  bloqueados para proteção de autoria.
                </p>
                <div className="space-y-1.5">
                  {currentSlots.map((slot) => {
                    const checked = selectedSlotIds.includes(slot.slotId);
                    const provMeta =
                      PROVENANCE_LABELS[slot.provenance] ||
                      PROVENANCE_LABELS.user_authored;
                    return (
                      <label
                        key={slot.slotId}
                        className={`flex flex-wrap items-start justify-between gap-2 rounded-md border p-2 ${
                          !slot.manualSelectable
                            ? "cursor-not-allowed border-border/60 bg-muted/30 opacity-75"
                            : checked
                              ? "cursor-pointer border-primary/50 bg-primary/5"
                              : "cursor-pointer border-border bg-background"
                        }`}
                      >
                        <div className="flex items-start gap-2">
                          <input
                            type="checkbox"
                            aria-label={`Selecionar slot ${slot.label} (${slot.slotId})`}
                            disabled={
                              !slot.manualSelectable ||
                              busyAction ||
                              aiEnhancing
                            }
                            checked={slot.manualSelectable && checked}
                            onChange={() => handleToggleSlot(slot.slotId)}
                            className="mt-0.5 h-3.5 w-3.5"
                          />
                          <div className="space-y-0.5">
                            <div className="flex flex-wrap items-center gap-1.5">
                              <span className="font-medium text-foreground">
                                {slot.label}
                              </span>
                              <code className="rounded bg-muted px-1 py-0.5 font-mono text-[10px] text-muted-foreground">
                                {slot.slotId}
                              </code>
                            </div>
                            {slot.protectionReason && (
                              <p className="flex items-center gap-1 text-[11px] text-muted-foreground">
                                {!slot.manualSelectable && (
                                  <Lock className="h-3 w-3 shrink-0" />
                                )}
                                <span>{slot.protectionReason}</span>
                              </p>
                            )}
                          </div>
                        </div>

                        <div className="flex items-center gap-1.5">
                          <Badge variant={provMeta.variant} className="text-[10px]">
                            {provMeta.label}
                          </Badge>
                        </div>
                      </label>
                    );
                  })}
                </div>
              </div>
            )}
          </div>

          {/* Instruções opcionais para o aprimoramento por IA */}
          <div className="space-y-1.5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <Label htmlFor="ai-studio-instructions" className="text-xs font-semibold">
                Instruções opcionais para o aprimoramento (estilo, concisão ou foco)
              </Label>
              <span className="text-[11px] text-muted-foreground">
                {aiInstructions.length}/1500 caracteres
              </span>
            </div>
            <textarea
              id="ai-studio-instructions"
              rows={2}
              maxLength={1500}
              disabled={busyAction || aiEnhancing || activeVersion.is_rejected || !isLatestActive}
              value={aiInstructions}
              onChange={(e) => setAiInstructions(e.target.value)}
              placeholder="Ex.: Destaque resultados técnicos em Python e mantenha tom objetivo para leitura rápida."
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-xs text-foreground"
            />
            <p className="text-[11px] text-muted-foreground">
              As instruções orientam apenas redação e priorização visual; o Grounding Gate bloqueia qualquer adição de fatos, empresas, métricas ou tecnologias não confirmadas no perfil.
            </p>
          </div>

          {effectiveTargetSlotsCount === 0 && (
            <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-2.5 text-amber-900 dark:text-amber-200">
              {selectionMode === "auto" && manualSelectableSlots.length > 0 ? (
                <>
                  Nenhum slot está elegível no modo automático porque os blocos foram editados manualmente (<code>manual_edit</code>). Alterne para{" "}
                  <strong>Seleção manual de slots</strong> acima caso deseje autorizar o aprimoramento desses blocos (Política 2).
                </>
              ) : (
                <>
                  Selecione ao menos um slot elegível para iniciar o aprimoramento assistido por IA.
                </>
              )}
            </div>
          )}

          <div className="flex flex-wrap items-center justify-end gap-2">
            <Button
              type="button"
              disabled={!canSubmitAiEnhance}
              onClick={handleTriggerEnhance}
            >
              <Sparkles className="mr-1.5 h-4 w-4" />
              {aiEnhancing
                ? "Processando aprimoramento com IA..."
                : `Aprimorar com IA (gerar sugestão a partir de v${activeVersion.version_number})`}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

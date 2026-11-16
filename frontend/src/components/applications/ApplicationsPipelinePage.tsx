import React, { useCallback, useEffect, useState } from "react";
import {
  Archive,
  CalendarClock,
  CheckCircle2,
  ClipboardCheck,
  Clock,
  ExternalLink,
  FileCheck2,
  History,
  Kanban,
  Loader2,
  MapPin,
  Plus,
  RefreshCw,
  Search,
  Send,
  ShieldAlert,
  Trash2,
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
import { Input, Label, Textarea } from "@/components/ui/input";
import { ApiError, api } from "@/lib/api";
import type {
  ApplicationCreatePayload,
  ApplicationItem,
  ApplicationKanbanResponse,
  ApplicationStatus,
  EmploymentType,
  SeniorityLevel,
  WorkMode,
} from "@/types/api";

interface ApplicationsPipelinePageProps {
  initialApplicationId?: string | null;
  onClearInitialApplication?: () => void;
  onNavigateProfile?: () => void;
}

const ALL_STATUS_OPTIONS: Array<{ value: ApplicationStatus; label: string }> = [
  { value: "interested", label: "Interesse" },
  { value: "preparing", label: "Preparação" },
  { value: "applied", label: "Candidatura enviada" },
  { value: "assessment", label: "Teste técnico" },
  { value: "interview", label: "Entrevista" },
  { value: "offer", label: "Proposta" },
  { value: "accepted", label: "Aprovado" },
  { value: "rejected", label: "Rejeitado" },
  { value: "withdrawn", label: "Desistência" },
];

const WORK_MODE_LABELS: Record<WorkMode, string> = {
  remote: "Remoto",
  hybrid: "Híbrido",
  onsite: "Presencial",
  unknown: "Modelo não informado",
};

const EMPLOYMENT_LABELS: Record<EmploymentType, string> = {
  internship: "Estágio",
  clt: "CLT",
  pj: "PJ",
  freelance: "Freelance",
  temporary: "Temporário",
  other: "Outro",
  unknown: "Contrato não informado",
};

const SENIORITY_LABELS: Record<SeniorityLevel, string> = {
  internship: "Estágio",
  entry_level: "Início de carreira",
  junior: "Júnior",
  mid_level: "Pleno",
  senior: "Sênior",
  staff_principal: "Staff / Principal",
  management: "Liderança / Gestão",
  unknown: "Não informada",
};

function formatDateTimePtBr(iso: string | null | undefined): string {
  if (!iso) return "Não informada";
  try {
    return new Date(iso).toLocaleDateString("pt-BR", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
    });
  } catch {
    return iso;
  }
}

function formatHistoryDateTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString("pt-BR", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function toInputDateValue(iso: string | null | undefined): string {
  if (!iso) return "";
  try {
    const dt = new Date(iso);
    if (Number.isNaN(dt.getTime())) return "";
    return dt.toISOString().slice(0, 10);
  } catch {
    return "";
  }
}

function fromInputDateValue(raw: string): string | null {
  const trimmed = raw.trim();
  if (!trimmed) return null;
  return `${trimmed}T12:00:00Z`;
}

function statusBadgeVariant(
  status: ApplicationStatus
): "default" | "secondary" | "outline" | "success" | "warning" {
  if (status === "accepted" || status === "offer") return "success";
  if (status === "assessment" || status === "interview") return "warning";
  if (status === "applied" || status === "preparing") return "default";
  return "secondary";
}

export const ApplicationsPipelinePage: React.FC<ApplicationsPipelinePageProps> = ({
  initialApplicationId = null,
  onClearInitialApplication,
  onNavigateProfile,
}) => {
  const [kanban, setKanban] = useState<ApplicationKanbanResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [searchText, setSearchText] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [busyCardId, setBusyCardId] = useState<string | null>(null);
  const [showClosedSection, setShowClosedSection] = useState(true);
  const [mobileStage, setMobileStage] = useState<ApplicationStatus>("interested");

  const [selectedApp, setSelectedApp] = useState<ApplicationItem | null>(null);
  const [detailSaving, setDetailSaving] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [confirmHistoryDeleteId, setConfirmHistoryDeleteId] = useState<string | null>(null);

  // Campos editáveis no painel de detalhes
  const [editNextAction, setEditNextAction] = useState("");
  const [editNextDue, setEditNextDue] = useState("");
  const [editAppliedAt, setEditAppliedAt] = useState("");
  const [editInterviewAt, setEditInterviewAt] = useState("");
  const [editAssessmentDue, setEditAssessmentDue] = useState("");
  const [editExpectedReturn, setEditExpectedReturn] = useState("");
  const [editSummary, setEditSummary] = useState("");
  const [editNotes, setEditNotes] = useState("");
  const [moveTargetStatus, setMoveTargetStatus] =
    useState<ApplicationStatus>("interested");
  const [moveNote, setMoveNote] = useState("");

  // Modal de criação manual
  const [manualOpen, setManualOpen] = useState(false);
  const [manualSubmitting, setManualSubmitting] = useState(false);
  const [manualError, setManualError] = useState<string | null>(null);
  const [manualRole, setManualRole] = useState("");
  const [manualCompany, setManualCompany] = useState("");
  const [manualSourceUrl, setManualSourceUrl] = useState("");
  const [manualApplyUrl, setManualApplyUrl] = useState("");
  const [manualLocation, setManualLocation] = useState("Brasil");
  const [manualEmployment, setManualEmployment] = useState<EmploymentType>("pj");
  const [manualWorkMode, setManualWorkMode] = useState<WorkMode>("remote");
  const [manualSeniority, setManualSeniority] = useState<SeniorityLevel>("junior");
  const [manualStatus, setManualStatus] = useState<ApplicationStatus>("interested");
  const [manualAppliedAt, setManualAppliedAt] = useState("");
  const [manualNextAction, setManualNextAction] = useState("");
  const [manualNextDue, setManualNextDue] = useState("");
  const [manualNotes, setManualNotes] = useState("");

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedSearch(searchText), 250);
    return () => window.clearTimeout(timer);
  }, [searchText]);

  const loadKanban = useCallback(async () => {
    setLoading(true);
    setErrorMessage(null);
    try {
      const res = await api.applications.kanban(debouncedSearch || undefined);
      setKanban(res);
    } catch (err) {
      setErrorMessage(
        err instanceof ApiError
          ? err.message
          : "Não foi possível carregar o pipeline de candidaturas."
      );
    } finally {
      setLoading(false);
    }
  }, [debouncedSearch]);

  useEffect(() => {
    loadKanban();
  }, [loadKanban]);

  const hydrateDetailEditor = useCallback((item: ApplicationItem) => {
    setSelectedApp(item);
    setEditNextAction(item.next_action || "");
    setEditNextDue(toInputDateValue(item.next_action_due_at));
    setEditAppliedAt(toInputDateValue(item.applied_at));
    setEditInterviewAt(toInputDateValue(item.interview_at));
    setEditAssessmentDue(toInputDateValue(item.assessment_deadline_at));
    setEditExpectedReturn(toInputDateValue(item.expected_response_at));
    setEditSummary(item.personal_summary || "");
    setEditNotes(item.notes || "");
    setMoveTargetStatus(item.status);
    setMoveNote("");
    setDetailError(null);
    setConfirmHistoryDeleteId(null);
  }, []);

  useEffect(() => {
    if (!initialApplicationId) return;
    api.applications
      .get(initialApplicationId)
      .then((item) => {
        hydrateDetailEditor(item);
      })
      .catch(() => {
        /* Ignora se o usuário fechou ou excluiu antes de abrir */
      })
      .finally(() => {
        onClearInitialApplication?.();
      });
  }, [initialApplicationId, hydrateDetailEditor, onClearInitialApplication]);

  async function handleQuickStatusChange(
    item: ApplicationItem,
    nextStatus: ApplicationStatus
  ) {
    if (nextStatus === item.status) return;
    const previousKanban = kanban;
    setBusyCardId(item.id);
    setErrorMessage(null);

    // Atualização otimista com reversão imediata se a API falhar
    if (kanban) {
      const nextLabel =
        ALL_STATUS_OPTIONS.find((o) => o.value === nextStatus)?.label ||
        nextStatus;
      const isNextClosed = ["accepted", "rejected", "withdrawn"].includes(
        nextStatus
      );
      const optimisticItem: ApplicationItem = {
        ...item,
        status: nextStatus,
        status_label: nextLabel,
        is_closed: isNextClosed,
      };
      setKanban({
        ...kanban,
        columns: kanban.columns.map((col) => {
          const filtered = col.items.filter((c) => c.id !== item.id);
          if (col.status === nextStatus) {
            return {
              ...col,
              items: [optimisticItem, ...filtered],
              count: filtered.length + 1,
            };
          }
          return { ...col, items: filtered, count: filtered.length };
        }),
        closed_items: isNextClosed
          ? [
              optimisticItem,
              ...kanban.closed_items.filter((c) => c.id !== item.id),
            ]
          : kanban.closed_items.filter((c) => c.id !== item.id),
      });
    }

    try {
      const updated = await api.applications.changeStatus(item.id, {
        status: nextStatus,
      });
      await loadKanban();
      if (selectedApp?.id === item.id) {
        hydrateDetailEditor(updated);
      }
    } catch (err) {
      if (previousKanban) {
        setKanban(previousKanban);
      }
      setErrorMessage(
        err instanceof ApiError
          ? err.message
          : "Não foi possível movimentar a candidatura de etapa."
      );
    } finally {
      setBusyCardId(null);
    }
  }

  async function handleSaveDetails(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedApp) return;
    setDetailSaving(true);
    setDetailError(null);
    try {
      let updated = await api.applications.update(selectedApp.id, {
        next_action: editNextAction.trim() || null,
        next_action_due_at: fromInputDateValue(editNextDue),
        applied_at: fromInputDateValue(editAppliedAt),
        interview_at: fromInputDateValue(editInterviewAt),
        assessment_deadline_at: fromInputDateValue(editAssessmentDue),
        expected_response_at: fromInputDateValue(editExpectedReturn),
        personal_summary: editSummary.trim() || null,
        notes: editNotes.trim() || null,
      });
      if (moveTargetStatus !== selectedApp.status || moveNote.trim()) {
        updated = await api.applications.changeStatus(selectedApp.id, {
          status: moveTargetStatus,
          note: moveNote.trim() || null,
        });
      }
      hydrateDetailEditor(updated);
      await loadKanban();
    } catch (err) {
      setDetailError(
        err instanceof ApiError
          ? err.message
          : "Não foi possível salvar as alterações da candidatura."
      );
    } finally {
      setDetailSaving(false);
    }
  }

  async function handleDeleteSelected(forceHistoryDeletion = false) {
    if (!selectedApp) return;
    setDetailSaving(true);
    setDetailError(null);
    try {
      await api.applications.remove(selectedApp.id, forceHistoryDeletion);
      setSelectedApp(null);
      setConfirmHistoryDeleteId(null);
      await loadKanban();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409 && !forceHistoryDeletion) {
        setConfirmHistoryDeleteId(selectedApp.id);
        setDetailError(err.message);
      } else {
        setDetailError(
          err instanceof ApiError
            ? err.message
            : "Não foi possível excluir a candidatura."
        );
      }
    } finally {
      setDetailSaving(false);
    }
  }

  async function handleCreateManual(e: React.FormEvent) {
    e.preventDefault();
    setManualError(null);
    if (manualRole.trim().length < 2) {
      setManualError("Informe o título do cargo com pelo menos 2 caracteres.");
      return;
    }

    const payload: ApplicationCreatePayload = {
      role_title: manualRole.trim(),
      company_name: manualCompany.trim() || null,
      source_url: manualSourceUrl.trim() || null,
      application_url: manualApplyUrl.trim() || null,
      location_text: manualLocation.trim() || null,
      employment_type: manualEmployment,
      work_mode: manualWorkMode,
      seniority_level: manualSeniority,
      status: manualStatus,
      applied_at: fromInputDateValue(manualAppliedAt),
      next_action: manualNextAction.trim() || null,
      next_action_due_at: fromInputDateValue(manualNextDue),
      notes: manualNotes.trim() || null,
    };

    setManualSubmitting(true);
    try {
      const created = await api.applications.create(payload);
      setManualOpen(false);
      setManualRole("");
      setManualCompany("");
      setManualSourceUrl("");
      setManualApplyUrl("");
      setManualAppliedAt("");
      setManualNextAction("");
      setManualNextDue("");
      setManualNotes("");
      await loadKanban();
      hydrateDetailEditor(created);
    } catch (err) {
      setManualError(
        err instanceof ApiError
          ? err.message
          : "Não foi possível registrar a candidatura manual."
      );
    } finally {
      setManualSubmitting(false);
    }
  }

  const indicators = kanban?.indicators;

  return (
    <div className="space-y-6">
      {/* Cabeçalho da seção */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-1">
          <div className="flex items-center gap-2 text-xs font-semibold text-primary">
            <Kanban className="h-4 w-4" />
            Pipeline Supervisionado de Processos Seletivos
          </div>
          <h2 className="text-2xl font-bold tracking-tight">Candidaturas</h2>
          <p className="text-sm text-muted-foreground">
            Organize etapas do interesse ao desfecho, registre prazos e preserve o
            histórico privado de cada candidatura. Nenhum envio ocorre automaticamente.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={loadKanban}
            disabled={loading}
          >
            <RefreshCw className="mr-1.5 h-4 w-4" />
            Atualizar
          </Button>
          <Button
            type="button"
            size="sm"
            onClick={() => {
              setManualError(null);
              setManualOpen(true);
            }}
          >
            <Plus className="mr-1.5 h-4 w-4" />
            Nova Candidatura Manual
          </Button>
        </div>
      </div>

      {/* Indicadores reais do usuário */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        <Card>
          <CardContent className="flex flex-col gap-1 p-4">
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>Candidaturas ativas</span>
              <Kanban className="h-4 w-4 text-primary" />
            </div>
            <span className="text-2xl font-bold">
              {indicators?.active_count ?? 0}
            </span>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="flex flex-col gap-1 p-4">
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>Enviadas</span>
              <Send className="h-4 w-4 text-primary" />
            </div>
            <span className="text-2xl font-bold">
              {indicators?.applied_count ?? 0}
            </span>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="flex flex-col gap-1 p-4">
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>Testes pendentes</span>
              <ClipboardCheck className="h-4 w-4 text-amber-500" />
            </div>
            <span className="text-2xl font-bold">
              {indicators?.assessment_count ?? 0}
            </span>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="flex flex-col gap-1 p-4">
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>Em entrevista</span>
              <CalendarClock className="h-4 w-4 text-amber-500" />
            </div>
            <span className="text-2xl font-bold">
              {indicators?.interview_count ?? 0}
            </span>
          </CardContent>
        </Card>

        <Card className="col-span-2 sm:col-span-1">
          <CardContent className="flex flex-col gap-1 p-4">
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>Propostas</span>
              <CheckCircle2 className="h-4 w-4 text-emerald-500" />
            </div>
            <span className="text-2xl font-bold">
              {indicators?.offer_count ?? 0}
            </span>
          </CardContent>
        </Card>
      </div>

      {/* Resumo de desfechos encerrados & busca */}
      <Card>
        <CardContent className="flex flex-col gap-3 p-4 md:flex-row md:items-center md:justify-between">
          <div className="relative flex-1 max-w-md">
            <Search className="pointer-events-none absolute top-3 left-3 h-4 w-4 text-muted-foreground" />
            <Input
              aria-label="Buscar candidaturas"
              className="pl-9"
              value={searchText}
              onChange={(e) => setSearchText(e.target.value)}
              placeholder="Filtrar por cargo, empresa, fonte ou próxima ação..."
            />
          </div>

          <div className="flex flex-wrap items-center gap-2 text-xs">
            <Badge variant="success">
              Aprovadas: {indicators?.accepted_count ?? 0}
            </Badge>
            <Badge variant="outline">
              Rejeitadas: {indicators?.rejected_count ?? 0}
            </Badge>
            <Badge variant="secondary">
              Desistências: {indicators?.withdrawn_count ?? 0}
            </Badge>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => setShowClosedSection((v) => !v)}
            >
              <Archive className="mr-1.5 h-3.5 w-3.5" />
              {showClosedSection
                ? "Ocultar encerradas"
                : `Ver encerradas (${indicators?.closed_count ?? 0})`}
            </Button>
          </div>
        </CardContent>
      </Card>

      {errorMessage && (
        <div className="flex items-center justify-between rounded-xl border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          <span>{errorMessage}</span>
          <Button type="button" variant="outline" size="sm" onClick={loadKanban}>
            Tentar novamente
          </Button>
        </div>
      )}

      {loading ? (
        <Card>
          <CardContent className="flex items-center justify-center gap-2 py-12 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin text-primary" />
            Carregando quadro Kanban de candidaturas...
          </CardContent>
        </Card>
      ) : (
        <>
          {/* Navegação mobile por etapas (< 768px) para evitar rolagem horizontal quebrada */}
          <div className="space-y-3 md:hidden" data-testid="kanban-mobile-view">
            <div className="flex flex-wrap gap-1.5">
              {(kanban?.columns ?? []).map((col) => {
                const activeTab = mobileStage === col.status;
                return (
                  <button
                    key={col.status}
                    type="button"
                    onClick={() => setMobileStage(col.status)}
                    className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors ${
                      activeTab
                        ? "border-primary bg-primary text-primary-foreground"
                        : "border-border bg-card text-muted-foreground hover:text-foreground"
                    }`}
                  >
                    <span>{col.label}</span>
                    <span className="rounded-full bg-background/20 px-1.5 py-0.5 text-[10px]">
                      {col.count}
                    </span>
                  </button>
                );
              })}
            </div>

            {(() => {
              const currentCol = (kanban?.columns ?? []).find(
                (c) => c.status === mobileStage
              );
              if (!currentCol || currentCol.items.length === 0) {
                return (
                  <Card>
                    <CardContent className="p-4 text-center text-xs text-muted-foreground">
                      Sem processos na etapa{" "}
                      <strong>{currentCol?.label || mobileStage}</strong>.
                    </CardContent>
                  </Card>
                );
              }
              return (
                <div className="space-y-2.5">
                  {currentCol.items.map((item) => {
                    const busy = busyCardId === item.id;
                    const isOverdue =
                      item.next_deadline_at != null &&
                      new Date(item.next_deadline_at).getTime() < Date.now();
                    return (
                      <div
                        key={item.id}
                        className="space-y-2.5 rounded-xl border border-border bg-card p-3.5 shadow-xs"
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div>
                            <p className="text-sm font-semibold text-foreground">
                              {item.role_title}
                            </p>
                            <p className="text-xs text-muted-foreground">
                              {item.company_name || "Empresa não informada"}
                            </p>
                          </div>
                          <Badge variant={statusBadgeVariant(item.status)}>
                            {item.status_label}
                          </Badge>
                        </div>

                        {item.next_deadline_at && (
                          <div
                            className={`flex items-start gap-1.5 rounded-md border px-2.5 py-1.5 text-xs ${
                              isOverdue
                                ? "border-destructive/40 bg-destructive/10 text-destructive"
                                : "border-amber-500/30 bg-amber-500/10 text-amber-800 dark:text-amber-300"
                            }`}
                          >
                            <Clock className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                            <span>
                              {isOverdue ? "Prazo vencido • " : ""}
                              {item.next_deadline_label}:{" "}
                              <strong>
                                {formatDateTimePtBr(item.next_deadline_at)}
                              </strong>
                            </span>
                          </div>
                        )}

                        <div className="flex flex-col gap-2 pt-1">
                          <select
                            aria-label={`Mover etapa mobile de ${item.role_title}`}
                            value={item.status}
                            disabled={busy}
                            onChange={(e) =>
                              handleQuickStatusChange(
                                item,
                                e.target.value as ApplicationStatus
                              )
                            }
                            className="h-9 w-full rounded-md border border-input bg-background px-2.5 text-xs text-foreground"
                          >
                            {ALL_STATUS_OPTIONS.map((opt) => (
                              <option key={opt.value} value={opt.value}>
                                {opt.label}
                              </option>
                            ))}
                          </select>
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            onClick={() => hydrateDetailEditor(item)}
                          >
                            Abrir detalhes
                          </Button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              );
            })()}
          </div>

          {/* Quadro Kanban Ativo Desktop (6 etapas separadas das encerradas) */}
          <div className="hidden overflow-x-auto pb-2 md:block">
            <div className="grid min-w-[1020px] grid-cols-6 gap-3">
              {(kanban?.columns ?? []).map((col) => (
                <div
                  key={col.status}
                  data-testid={`kanban-col-${col.status}`}
                  className="flex flex-col rounded-xl border border-border bg-card/70 p-3"
                >
                  <div className="mb-3 flex items-center justify-between gap-2 border-b border-border pb-2">
                    <span className="text-xs font-semibold tracking-tight text-foreground">
                      {col.label}
                    </span>
                    <Badge variant={statusBadgeVariant(col.status)}>
                      {col.count}
                    </Badge>
                  </div>

                  <div className="flex flex-1 flex-col gap-2.5">
                    {col.items.length === 0 ? (
                      <div className="rounded-lg border border-dashed border-border p-3 text-center text-[11px] text-muted-foreground">
                        Sem processos nesta etapa
                      </div>
                    ) : (
                      col.items.map((item) => {
                        const busy = busyCardId === item.id;
                        const isOverdue =
                          item.next_deadline_at != null &&
                          new Date(item.next_deadline_at).getTime() < Date.now();
                        return (
                          <div
                            key={item.id}
                            className="space-y-2.5 rounded-lg border border-border bg-background p-3 shadow-xs transition-colors hover:border-primary/40"
                          >
                            <div className="space-y-1">
                              <p className="text-xs font-semibold leading-snug text-foreground">
                                {item.role_title}
                              </p>
                              <p className="text-[11px] text-muted-foreground">
                                {item.company_name || "Empresa não informada"}
                              </p>
                            </div>

                            <div className="flex flex-wrap items-center gap-1">
                              <Badge variant={statusBadgeVariant(item.status)} className="text-[10px]">
                                {item.status_label}
                              </Badge>
                              {item.source_name && (
                                <Badge variant="outline" className="text-[10px]">
                                  {item.source_name}
                                </Badge>
                              )}
                            </div>

                            {item.next_deadline_at && (
                              <div
                                className={`flex items-start gap-1.5 rounded-md border px-2 py-1 text-[11px] ${
                                  isOverdue
                                    ? "border-destructive/40 bg-destructive/10 text-destructive"
                                    : "border-amber-500/30 bg-amber-500/10 text-amber-800 dark:text-amber-300"
                                }`}
                              >
                                <Clock className="mt-0.5 h-3 w-3 shrink-0" />
                                <span>
                                  {isOverdue ? "Prazo vencido • " : ""}
                                  {item.next_deadline_label}:{" "}
                                  <strong>
                                    {formatDateTimePtBr(item.next_deadline_at)}
                                  </strong>
                                </span>
                              </div>
                            )}

                            {item.next_action && (
                              <p className="line-clamp-2 text-[11px] text-muted-foreground">
                                Próximo passo: {item.next_action}
                              </p>
                            )}

                            <p className="text-[10px] text-muted-foreground">
                              Atualizada: {formatDateTimePtBr(item.updated_at)}
                            </p>

                            <div className="space-y-1.5 border-t border-border pt-2">
                              <select
                                aria-label={`Mover etapa de ${item.role_title}`}
                                value={item.status}
                                disabled={busy}
                                onChange={(e) =>
                                  handleQuickStatusChange(
                                    item,
                                    e.target.value as ApplicationStatus
                                  )
                                }
                                className="h-8 w-full rounded-md border border-input bg-card px-2 text-[11px] text-foreground"
                              >
                                {ALL_STATUS_OPTIONS.map((opt) => (
                                  <option key={opt.value} value={opt.value}>
                                    {opt.label}
                                  </option>
                                ))}
                              </select>
                              <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                className="h-7 w-full text-[11px]"
                                onClick={() => hydrateDetailEditor(item)}
                              >
                                Abrir detalhes
                              </Button>
                            </div>
                          </div>
                        );
                      })
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Seção separada de Processos Encerrados (nunca misturados às colunas ativas) */}
          {showClosedSection && (
            <Card data-testid="closed-applications-section">
              <CardHeader className="pb-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <CardTitle className="flex items-center gap-2 text-base">
                      <Archive className="h-4 w-4 text-muted-foreground" />
                      Candidaturas Encerradas ({kanban?.closed_items.length ?? 0})
                    </CardTitle>
                    <CardDescription>
                      Processos concluídos (`Aprovado`, `Rejeitado` e `Desistência`)
                      preservados com histórico completo sem poluir o quadro ativo.
                    </CardDescription>
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                {!kanban?.closed_items.length ? (
                  <p className="text-xs text-muted-foreground">
                    Nenhuma candidatura encerrada registrada até o momento.
                  </p>
                ) : (
                  <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
                    {kanban.closed_items.map((item) => (
                      <div
                        key={item.id}
                        className="flex flex-col justify-between space-y-3 rounded-lg border border-border bg-muted/30 p-3.5"
                      >
                        <div className="space-y-1.5">
                          <div className="flex items-start justify-between gap-2">
                            <div>
                              <p className="text-sm font-semibold text-foreground">
                                {item.role_title}
                              </p>
                              <p className="text-xs text-muted-foreground">
                                {item.company_name || "Empresa não informada"}
                              </p>
                            </div>
                            <Badge variant={statusBadgeVariant(item.status)}>
                              {item.status_label}
                            </Badge>
                          </div>
                          <p className="text-[11px] text-muted-foreground">
                            Encerrada em:{" "}
                            {formatDateTimePtBr(item.closed_at || item.updated_at)} •{" "}
                            {item.status_history.length} registro(s) no histórico
                          </p>
                        </div>

                        <div className="flex items-center justify-between gap-2">
                          <Button
                            type="button"
                            size="sm"
                            variant="outline"
                            onClick={() => hydrateDetailEditor(item)}
                          >
                            Ver histórico e detalhes
                          </Button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          )}
        </>
      )}

      {/* Aviso compacto de governança do perfil */}
      {onNavigateProfile && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-card p-3.5 text-xs">
          <div className="flex items-center gap-2 text-muted-foreground">
            <FileCheck2 className="h-4 w-4 text-primary shrink-0" />
            <span>
              Acompanhe manualmente quando enviar cada candidatura. Fatos do seu
              currículo seguem governados pelos registros confirmados no Perfil.
            </span>
          </div>
          <Button type="button" variant="outline" size="sm" onClick={onNavigateProfile}>
            Revisar Perfil Central
          </Button>
        </div>
      )}

      {/* Modal de criação manual de candidatura */}
      {manualOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-xs"
          role="dialog"
          aria-modal="true"
          aria-labelledby="new-manual-application-title"
        >
          <div className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-2xl border border-border bg-card p-6 text-card-foreground shadow-xl">
            <div className="mb-4 flex items-start justify-between gap-4">
              <div>
                <h2 id="new-manual-application-title" className="text-lg font-semibold">
                  Registrar Candidatura Manual
                </h2>
                <p className="text-xs text-muted-foreground">
                  Cadastro privado sem necessidade de vínculo com o catálogo externo.
                </p>
              </div>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                onClick={() => setManualOpen(false)}
                aria-label="Fechar modal de nova candidatura"
              >
                <X className="h-4 w-4" />
              </Button>
            </div>

            <form onSubmit={handleCreateManual} className="space-y-4">
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-1 sm:col-span-2">
                  <Label htmlFor="app-manual-role">Cargo *</Label>
                  <Input
                    id="app-manual-role"
                    value={manualRole}
                    onChange={(e) => setManualRole(e.target.value)}
                    placeholder="Ex.: Desenvolvedor Backend Java Júnior"
                    required
                  />
                </div>

                <div className="space-y-1">
                  <Label htmlFor="app-manual-company">Empresa</Label>
                  <Input
                    id="app-manual-company"
                    value={manualCompany}
                    onChange={(e) => setManualCompany(e.target.value)}
                    placeholder="Ex.: Empresa Tech"
                  />
                </div>

                <div className="space-y-1">
                  <Label htmlFor="app-manual-location">Localidade</Label>
                  <Input
                    id="app-manual-location"
                    value={manualLocation}
                    onChange={(e) => setManualLocation(e.target.value)}
                    placeholder="Ex.: Remoto - Brasil"
                  />
                </div>

                <div className="space-y-1">
                  <Label htmlFor="app-manual-status">Etapa inicial</Label>
                  <select
                    id="app-manual-status"
                    value={manualStatus}
                    onChange={(e) => setManualStatus(e.target.value as ApplicationStatus)}
                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                  >
                    {ALL_STATUS_OPTIONS.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="space-y-1">
                  <Label htmlFor="app-manual-applied-at">Data de envio</Label>
                  <Input
                    id="app-manual-applied-at"
                    type="date"
                    value={manualAppliedAt}
                    onChange={(e) => setManualAppliedAt(e.target.value)}
                  />
                </div>

                <div className="space-y-1">
                  <Label htmlFor="app-manual-employment">Regime</Label>
                  <select
                    id="app-manual-employment"
                    value={manualEmployment}
                    onChange={(e) => setManualEmployment(e.target.value as EmploymentType)}
                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                  >
                    {Object.entries(EMPLOYMENT_LABELS).map(([k, v]) => (
                      <option key={k} value={k}>
                        {v}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="space-y-1">
                  <Label htmlFor="app-manual-work-mode">Modalidade</Label>
                  <select
                    id="app-manual-work-mode"
                    value={manualWorkMode}
                    onChange={(e) => setManualWorkMode(e.target.value as WorkMode)}
                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                  >
                    {Object.entries(WORK_MODE_LABELS).map(([k, v]) => (
                      <option key={k} value={k}>
                        {v}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="space-y-1">
                  <Label htmlFor="app-manual-seniority">Senioridade</Label>
                  <select
                    id="app-manual-seniority"
                    value={manualSeniority}
                    onChange={(e) => setManualSeniority(e.target.value as SeniorityLevel)}
                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                  >
                    {Object.entries(SENIORITY_LABELS).map(([k, v]) => (
                      <option key={k} value={k}>
                        {v}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="space-y-1">
                  <Label htmlFor="app-manual-next-due">Prazo da próxima ação</Label>
                  <Input
                    id="app-manual-next-due"
                    type="date"
                    value={manualNextDue}
                    onChange={(e) => setManualNextDue(e.target.value)}
                  />
                </div>

                <div className="space-y-1 sm:col-span-2">
                  <Label htmlFor="app-manual-source-url">URL da publicação</Label>
                  <Input
                    id="app-manual-source-url"
                    type="url"
                    value={manualSourceUrl}
                    onChange={(e) => setManualSourceUrl(e.target.value)}
                    placeholder="https://empresa.com/vagas/backend"
                  />
                </div>

                <div className="space-y-1 sm:col-span-2">
                  <Label htmlFor="app-manual-apply-url">URL da candidatura</Label>
                  <Input
                    id="app-manual-apply-url"
                    type="url"
                    value={manualApplyUrl}
                    onChange={(e) => setManualApplyUrl(e.target.value)}
                    placeholder="https://empresa.com/apply/123"
                  />
                </div>

                <div className="space-y-1 sm:col-span-2">
                  <Label htmlFor="app-manual-next-action">Próxima ação</Label>
                  <Input
                    id="app-manual-next-action"
                    value={manualNextAction}
                    onChange={(e) => setManualNextAction(e.target.value)}
                    placeholder="Ex.: Adaptar currículo focado em Java/Spring e enviar"
                  />
                </div>

                <div className="space-y-1 sm:col-span-2">
                  <Label htmlFor="app-manual-notes">Anotações</Label>
                  <Textarea
                    id="app-manual-notes"
                    rows={3}
                    value={manualNotes}
                    onChange={(e) => setManualNotes(e.target.value)}
                    placeholder="Observações sobre requisitos, recrutador ou preparação."
                  />
                </div>
              </div>

              {manualError && (
                <div className="rounded-lg border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">
                  {manualError}
                </div>
              )}

              <div className="flex justify-end gap-2 pt-2">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setManualOpen(false)}
                >
                  Cancelar
                </Button>
                <Button type="submit" disabled={manualSubmitting}>
                  {manualSubmitting ? "Salvando..." : "Salvar Candidatura"}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal / Painel de Detalhes da Candidatura */}
      {selectedApp && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-xs"
          role="dialog"
          aria-modal="true"
          aria-labelledby="application-detail-title"
        >
          <div className="max-h-[92vh] w-full max-w-3xl overflow-y-auto rounded-2xl border border-border bg-card p-6 text-card-foreground shadow-xl space-y-5">
            <div className="flex items-start justify-between gap-4 border-b border-border pb-4">
              <div className="space-y-1">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant={statusBadgeVariant(selectedApp.status)}>
                    {selectedApp.status_label}
                  </Badge>
                  {selectedApp.source_name && (
                    <Badge variant="outline">{selectedApp.source_name}</Badge>
                  )}
                  <Badge variant="outline">
                    {SENIORITY_LABELS[selectedApp.seniority_level] ||
                      selectedApp.seniority_level}
                  </Badge>
                  <Badge variant="outline">
                    {EMPLOYMENT_LABELS[selectedApp.employment_type] ||
                      selectedApp.employment_type}
                  </Badge>
                  <Badge variant="outline">
                    {WORK_MODE_LABELS[selectedApp.work_mode] ||
                      selectedApp.work_mode}
                  </Badge>
                </div>
                <h2 id="application-detail-title" className="text-xl font-bold">
                  {selectedApp.role_title}
                </h2>
                <p className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                  <span>{selectedApp.company_name || "Empresa não informada"}</span>
                  {selectedApp.location_text && (
                    <>
                      <span>•</span>
                      <span className="inline-flex items-center gap-1">
                        <MapPin className="h-3 w-3" />
                        {selectedApp.location_text}
                      </span>
                    </>
                  )}
                  <span>•</span>
                  <span>Criada: {formatDateTimePtBr(selectedApp.created_at)}</span>
                </p>
              </div>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                onClick={() => setSelectedApp(null)}
                aria-label="Fechar detalhes da candidatura"
              >
                <X className="h-4 w-4" />
              </Button>
            </div>

            {/* Links preservados */}
            {(selectedApp.source_url || selectedApp.application_url) && (
              <div className="flex flex-wrap items-center gap-4 rounded-lg border border-border bg-muted/30 px-3.5 py-2.5 text-xs">
                {selectedApp.source_url && (
                  <a
                    href={selectedApp.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-primary hover:underline"
                  >
                    Publicação original
                    <ExternalLink className="h-3.5 w-3.5" />
                  </a>
                )}
                {selectedApp.application_url && (
                  <a
                    href={selectedApp.application_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-primary hover:underline"
                  >
                    Link de candidatura
                    <ExternalLink className="h-3.5 w-3.5" />
                  </a>
                )}
              </div>
            )}

            <form onSubmit={handleSaveDetails} className="space-y-4">
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-1">
                  <Label htmlFor="detail-status">Etapa atual</Label>
                  <select
                    id="detail-status"
                    value={moveTargetStatus}
                    onChange={(e) =>
                      setMoveTargetStatus(e.target.value as ApplicationStatus)
                    }
                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                  >
                    {ALL_STATUS_OPTIONS.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="space-y-1">
                  <Label htmlFor="detail-move-note">
                    Nota da movimentação (opcional)
                  </Label>
                  <Input
                    id="detail-move-note"
                    value={moveNote}
                    onChange={(e) => setMoveNote(e.target.value)}
                    placeholder="Ex.: Entrevista agendada para sexta"
                  />
                </div>

                <div className="space-y-1">
                  <Label htmlFor="detail-applied-at">Data de candidatura</Label>
                  <Input
                    id="detail-applied-at"
                    type="date"
                    value={editAppliedAt}
                    onChange={(e) => setEditAppliedAt(e.target.value)}
                  />
                </div>

                <div className="space-y-1">
                  <Label htmlFor="detail-interview-at">Data de entrevista</Label>
                  <Input
                    id="detail-interview-at"
                    type="date"
                    value={editInterviewAt}
                    onChange={(e) => setEditInterviewAt(e.target.value)}
                  />
                </div>

                <div className="space-y-1">
                  <Label htmlFor="detail-assessment-due">Prazo de teste técnico</Label>
                  <Input
                    id="detail-assessment-due"
                    type="date"
                    value={editAssessmentDue}
                    onChange={(e) => setEditAssessmentDue(e.target.value)}
                  />
                </div>

                <div className="space-y-1">
                  <Label htmlFor="detail-expected-return">
                    Data prevista de retorno
                  </Label>
                  <Input
                    id="detail-expected-return"
                    type="date"
                    value={editExpectedReturn}
                    onChange={(e) => setEditExpectedReturn(e.target.value)}
                  />
                </div>

                <div className="space-y-1">
                  <Label htmlFor="detail-next-action">Próxima ação</Label>
                  <Input
                    id="detail-next-action"
                    value={editNextAction}
                    onChange={(e) => setEditNextAction(e.target.value)}
                    placeholder="Ex.: Enviar solução do repositório"
                  />
                </div>

                <div className="space-y-1">
                  <Label htmlFor="detail-next-due">Prazo da próxima ação</Label>
                  <Input
                    id="detail-next-due"
                    type="date"
                    value={editNextDue}
                    onChange={(e) => setEditNextDue(e.target.value)}
                  />
                </div>

                <div className="space-y-1 sm:col-span-2">
                  <Label htmlFor="detail-summary">Resumo da oportunidade / processo</Label>
                  <Textarea
                    id="detail-summary"
                    rows={3}
                    value={editSummary}
                    onChange={(e) => setEditSummary(e.target.value)}
                  />
                </div>

                <div className="space-y-1 sm:col-span-2">
                  <Label htmlFor="detail-notes">Anotações privadas</Label>
                  <Textarea
                    id="detail-notes"
                    rows={3}
                    value={editNotes}
                    onChange={(e) => setEditNotes(e.target.value)}
                    placeholder="Registre feedbacks, pontos técnicos e observações pessoais."
                  />
                </div>
              </div>

              {detailError && (
                <div className="flex flex-col gap-2 rounded-lg border border-destructive/40 bg-destructive/10 px-3 py-2.5 text-xs text-destructive">
                  <div className="flex items-start gap-2">
                    <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" />
                    <span>{detailError}</span>
                  </div>
                  {confirmHistoryDeleteId === selectedApp.id && (
                    <div className="flex flex-wrap items-center justify-end gap-2 pt-1">
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        onClick={() => setConfirmHistoryDeleteId(null)}
                      >
                        Manter histórico
                      </Button>
                      <Button
                        type="button"
                        size="sm"
                        className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                        disabled={detailSaving}
                        onClick={() => handleDeleteSelected(true)}
                      >
                        Confirmar exclusão definitiva do processo e histórico
                      </Button>
                    </div>
                  )}
                </div>
              )}

              <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border pt-3">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="text-destructive hover:text-destructive"
                  disabled={detailSaving}
                  onClick={() => handleDeleteSelected(false)}
                >
                  <Trash2 className="mr-1.5 h-4 w-4" />
                  Excluir candidatura
                </Button>

                <div className="flex items-center gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => setSelectedApp(null)}
                  >
                    Fechar
                  </Button>
                  <Button type="submit" disabled={detailSaving}>
                    {detailSaving ? "Salvando..." : "Salvar alterações"}
                  </Button>
                </div>
              </div>
            </form>

            {/* Linha do tempo do histórico */}
            <div className="space-y-2.5 border-t border-border pt-4">
              <h3 className="flex items-center gap-2 text-sm font-semibold">
                <History className="h-4 w-4 text-primary" />
                Histórico de Movimentações ({selectedApp.status_history.length})
              </h3>
              <div className="space-y-2">
                {selectedApp.status_history.map((hist) => (
                  <div
                    key={hist.id}
                    className="flex flex-wrap items-start justify-between gap-2 rounded-lg border border-border bg-muted/30 px-3 py-2 text-xs"
                  >
                    <div className="space-y-0.5">
                      <p className="font-medium text-foreground">
                        {hist.from_status_label
                          ? `${hist.from_status_label} -> ${hist.to_status_label}`
                          : `Início em ${hist.to_status_label}`}
                      </p>
                      {hist.note && (
                        <p className="text-muted-foreground">{hist.note}</p>
                      )}
                    </div>
                    <span className="text-[11px] text-muted-foreground">
                      {formatHistoryDateTime(hist.changed_at)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

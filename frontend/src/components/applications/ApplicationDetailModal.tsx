import React, { useEffect, useState } from "react";
import {
  CalendarClock,
  Check,
  CheckCircle2,
  ClipboardCheck,
  Copy,
  Edit3,
  ExternalLink,
  FileText,
  History,
  Link2,
  Mail,
  MapPin,
  MessageSquareText,
  Plus,
  ShieldAlert,
  Trash2,
  Unlink2,
  Users,
  X,
  XCircle,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input, Label, Textarea } from "@/components/ui/input";
import { ApiError, api } from "@/lib/api";
import { MaterialWorkspaceModal } from "@/components/materials/MaterialWorkspaceModal";
import type {
  ApplicationAssessmentItem,
  ApplicationContactItem,
  ApplicationInterviewItem,
  ApplicationItem,
  ApplicationStatus,
  AssessmentStatus,
  EmploymentType,
  ExternalInteractionType,
  FollowUpTemplateResponse,
  InterviewFormat,
  MaterialSummaryItem,
  SeniorityLevel,
  WorkMode,
} from "@/types/api";
import type { DetailTabKey } from "./ApplicationAgendaView";
import {
  formatLocalDate,
  formatLocalDateTime,
  fromLocalDateTimeInputValue,
  toLocalDateTimeInputValue,
} from "./dateTimeHelpers";

interface ApplicationDetailModalProps {
  selectedApp: ApplicationItem;
  initialTab?: DetailTabKey;
  allStatusOptions: Array<{ value: ApplicationStatus; label: string }>;
  workModeLabels: Record<WorkMode, string>;
  employmentLabels: Record<EmploymentType, string>;
  seniorityLabels: Record<SeniorityLevel, string>;
  onClose: () => void;
  onRefreshApplication: (updated: ApplicationItem) => Promise<void>;
  onDeletedApplication: () => Promise<void>;
  onNavigateProfile?: () => void;
}

const INTERVIEW_FORMAT_OPTIONS: Array<{
  value: InterviewFormat;
  label: string;
}> = [
  { value: "online", label: "Online / Vídeo" },
  { value: "in_person", label: "Presencial" },
  { value: "phone", label: "Telefone" },
];

const INTERACTION_TYPE_OPTIONS: Array<{
  value: ExternalInteractionType;
  label: string;
}> = [
  { value: "email", label: "E-mail" },
  { value: "phone", label: "Telefone / Ligação" },
  { value: "linkedin", label: "LinkedIn" },
  { value: "interview", label: "Entrevista / Conversa" },
  { value: "other", label: "Outro contato externo" },
];

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

export const ApplicationDetailModal: React.FC<ApplicationDetailModalProps> = ({
  selectedApp,
  initialTab = "general",
  allStatusOptions,
  workModeLabels,
  employmentLabels,
  seniorityLabels,
  onClose,
  onRefreshApplication,
  onDeletedApplication,
  onNavigateProfile,
}) => {
  const [activeTab, setActiveTab] = useState<DetailTabKey>(initialTab);
  const [detailSaving, setDetailSaving] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [detailSuccess, setDetailSuccess] = useState<string | null>(null);
  const [confirmHistoryDeleteId, setConfirmHistoryDeleteId] = useState<
    string | null
  >(null);

  // Aba Geral (Fase 03.1 preservada)
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

  // Aba Entrevistas
  const [editingInterviewId, setEditingInterviewId] = useState<string | null>(
    null
  );
  const [ivRoundName, setIvRoundName] = useState("");
  const [ivFormat, setIvFormat] = useState<InterviewFormat>("online");
  const [ivScheduledAt, setIvScheduledAt] = useState("");
  const [ivDuration, setIvDuration] = useState("45");
  const [ivMeetingUrl, setIvMeetingUrl] = useState("");
  const [ivInterviewers, setIvInterviewers] = useState("");
  const [ivNotes, setIvNotes] = useState("");
  const [ivFeedback, setIvFeedback] = useState("");

  // Aba Testes Técnicos
  const [editingAssessmentId, setEditingAssessmentId] = useState<string | null>(
    null
  );
  const [asmtTitle, setAsmtTitle] = useState("");
  const [asmtPlatform, setAsmtPlatform] = useState("");
  const [asmtDescription, setAsmtDescription] = useState("");
  const [asmtInstructionsUrl, setAsmtInstructionsUrl] = useState("");
  const [asmtSubmissionUrl, setAsmtSubmissionUrl] = useState("");
  const [asmtDeadlineAt, setAsmtDeadlineAt] = useState("");
  const [asmtStatus, setAsmtStatus] = useState<AssessmentStatus>("pending");
  const [asmtFeedback, setAsmtFeedback] = useState("");
  const [asmtNotes, setAsmtNotes] = useState("");

  // Aba Contatos
  const [editingContactId, setEditingContactId] = useState<string | null>(null);
  const [ctName, setCtName] = useState("");
  const [ctRole, setCtRole] = useState("");
  const [ctEmail, setCtEmail] = useState("");
  const [ctLinkedin, setCtLinkedin] = useState("");
  const [ctNotes, setCtNotes] = useState("");

  // Aba Acompanhamento / Follow-up
  const [extType, setExtType] = useState<ExternalInteractionType>("email");
  const [extAt, setExtAt] = useState(() =>
    toLocalDateTimeInputValue(new Date().toISOString())
  );
  const [extNote, setExtNote] = useState("");
  const [followUpTemplate, setFollowUpTemplate] =
    useState<FollowUpTemplateResponse | null>(null);
  const [copiedFollowUp, setCopiedFollowUp] = useState(false);

  // Aba Materiais (Fase 04.1)
  const [linkedMaterials, setLinkedMaterials] = useState<MaterialSummaryItem[]>(
    []
  );
  const [availableMaterials, setAvailableMaterials] = useState<
    MaterialSummaryItem[]
  >([]);
  const [materialsLoading, setMaterialsLoading] = useState(false);
  const [materialWorkspaceOpen, setMaterialWorkspaceOpen] = useState(false);
  const [materialWorkspaceId, setMaterialWorkspaceId] = useState<string | null>(
    null
  );

  const loadMaterialsForApp = async () => {
    setMaterialsLoading(true);
    try {
      const [linked, all] = await Promise.all([
        api.materials.list({ application_id: selectedApp.id }),
        api.materials.list(),
      ]);
      setLinkedMaterials(linked);
      const linkedIds = new Set(linked.map((m) => m.id));
      setAvailableMaterials(all.filter((m) => !linkedIds.has(m.id)));
    } catch {
      // Silencioso para não bloquear abas pré-existentes da candidatura caso materiais falhem
    } finally {
      setMaterialsLoading(false);
    }
  };

  useEffect(() => {
    setActiveTab(initialTab);
  }, [initialTab, selectedApp.id]);

  useEffect(() => {
    void loadMaterialsForApp();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedApp.id]);

  useEffect(() => {
    setEditNextAction(selectedApp.next_action || "");
    setEditNextDue(toInputDateValue(selectedApp.next_action_due_at));
    setEditAppliedAt(toInputDateValue(selectedApp.applied_at));
    setEditInterviewAt(toInputDateValue(selectedApp.interview_at));
    setEditAssessmentDue(toInputDateValue(selectedApp.assessment_deadline_at));
    setEditExpectedReturn(toInputDateValue(selectedApp.expected_response_at));
    setEditSummary(selectedApp.personal_summary || "");
    setEditNotes(selectedApp.notes || "");
    setMoveTargetStatus(selectedApp.status);
    setMoveNote("");
    setDetailError(null);
    setConfirmHistoryDeleteId(null);
    setFollowUpTemplate(null);
    setCopiedFollowUp(false);
  }, [selectedApp]);

  const interviews = selectedApp.interviews ?? [];
  const assessments = selectedApp.assessments ?? [];
  const contacts = selectedApp.contacts ?? [];

  async function reloadSelfFromServer(successMsg?: string) {
    const fresh = await api.applications.get(selectedApp.id);
    await onRefreshApplication(fresh);
    if (successMsg) {
      setDetailSuccess(successMsg);
    }
  }

  function resetInterviewForm() {
    setEditingInterviewId(null);
    setIvRoundName("");
    setIvFormat("online");
    setIvScheduledAt("");
    setIvDuration("45");
    setIvMeetingUrl("");
    setIvInterviewers("");
    setIvNotes("");
    setIvFeedback("");
  }

  function startEditInterview(iv: ApplicationInterviewItem) {
    setEditingInterviewId(iv.id);
    setIvRoundName(iv.round_name);
    setIvFormat((iv.interview_format as InterviewFormat) || "online");
    setIvScheduledAt(toLocalDateTimeInputValue(iv.scheduled_at));
    setIvDuration(iv.duration_minutes ? String(iv.duration_minutes) : "");
    setIvMeetingUrl(iv.meeting_url || "");
    setIvInterviewers(iv.interviewers || "");
    setIvNotes(iv.notes || "");
    setIvFeedback(iv.feedback_received || "");
    setDetailError(null);
    setDetailSuccess(null);
  }

  function resetAssessmentForm() {
    setEditingAssessmentId(null);
    setAsmtTitle("");
    setAsmtPlatform("");
    setAsmtDescription("");
    setAsmtInstructionsUrl("");
    setAsmtSubmissionUrl("");
    setAsmtDeadlineAt("");
    setAsmtStatus("pending");
    setAsmtFeedback("");
    setAsmtNotes("");
  }

  function startEditAssessment(asmt: ApplicationAssessmentItem) {
    setEditingAssessmentId(asmt.id);
    setAsmtTitle(asmt.title);
    setAsmtPlatform(asmt.platform || "");
    setAsmtDescription(asmt.description || "");
    setAsmtInstructionsUrl(asmt.instructions_url || "");
    setAsmtSubmissionUrl(asmt.submission_url || "");
    setAsmtDeadlineAt(toLocalDateTimeInputValue(asmt.deadline_at));
    setAsmtStatus((asmt.status as AssessmentStatus) || "pending");
    setAsmtFeedback(asmt.feedback || "");
    setAsmtNotes(asmt.notes || "");
    setDetailError(null);
    setDetailSuccess(null);
  }

  function resetContactForm() {
    setEditingContactId(null);
    setCtName("");
    setCtRole("");
    setCtEmail("");
    setCtLinkedin("");
    setCtNotes("");
  }

  function startEditContact(ct: ApplicationContactItem) {
    setEditingContactId(ct.id);
    setCtName(ct.name);
    setCtRole(ct.role_title || "");
    setCtEmail(ct.email || "");
    setCtLinkedin(ct.linkedin_url || "");
    setCtNotes(ct.notes || "");
    setDetailError(null);
    setDetailSuccess(null);
  }

  async function handleSaveGeneral(e: React.FormEvent) {
    e.preventDefault();
    setDetailSaving(true);
    setDetailError(null);
    setDetailSuccess(null);
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
      await onRefreshApplication(updated);
      setDetailSuccess("Alterações da candidatura salvas.");
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

  async function handleDeleteApplication(forceHistoryDeletion = false) {
    setDetailSaving(true);
    setDetailError(null);
    try {
      await api.applications.remove(selectedApp.id, forceHistoryDeletion);
      await onDeletedApplication();
    } catch (err) {
      if (
        err instanceof ApiError &&
        err.status === 409 &&
        !forceHistoryDeletion
      ) {
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

  async function handleSubmitInterview(e: React.FormEvent) {
    e.preventDefault();
    setDetailError(null);
    setDetailSuccess(null);

    const scheduledIso = fromLocalDateTimeInputValue(ivScheduledAt);
    if (!ivRoundName.trim() || !scheduledIso) {
      setDetailError("Informe o nome da rodada e a data/hora da entrevista.");
      return;
    }

    const parsedDuration = ivDuration.trim() ? Number(ivDuration) : null;
    const payload = {
      round_name: ivRoundName.trim(),
      interview_format: ivFormat,
      scheduled_at: scheduledIso,
      duration_minutes:
        parsedDuration && !Number.isNaN(parsedDuration) ? parsedDuration : null,
      meeting_url: ivMeetingUrl.trim() || null,
      interviewers: ivInterviewers.trim() || null,
      notes: ivNotes.trim() || null,
      feedback_received: ivFeedback.trim() || null,
    };

    setDetailSaving(true);
    try {
      if (editingInterviewId) {
        await api.applications.updateInterview(
          selectedApp.id,
          editingInterviewId,
          payload
        );
        resetInterviewForm();
        await reloadSelfFromServer("Entrevista atualizada/reagendada.");
      } else {
        await api.applications.createInterview(selectedApp.id, payload);
        resetInterviewForm();
        await reloadSelfFromServer("Entrevista registrada com sucesso.");
      }
    } catch (err) {
      setDetailError(
        err instanceof ApiError
          ? err.message
          : "Não foi possível salvar a entrevista."
      );
    } finally {
      setDetailSaving(false);
    }
  }

  async function handleInterviewQuickAction(
    iv: ApplicationInterviewItem,
    status: "completed" | "cancelled"
  ) {
    setDetailSaving(true);
    setDetailError(null);
    setDetailSuccess(null);
    try {
      await api.applications.updateInterview(selectedApp.id, iv.id, {
        status,
        completed_at: status === "completed" ? new Date().toISOString() : null,
      });
      await reloadSelfFromServer(
        status === "completed"
          ? "Entrevista marcada como concluída."
          : "Entrevista cancelada."
      );
    } catch (err) {
      setDetailError(
        err instanceof ApiError
          ? err.message
          : "Não foi possível atualizar o status da entrevista."
      );
    } finally {
      setDetailSaving(false);
    }
  }

  async function handleDeleteInterview(interviewId: string) {
    setDetailSaving(true);
    setDetailError(null);
    setDetailSuccess(null);
    try {
      await api.applications.deleteInterview(selectedApp.id, interviewId);
      if (editingInterviewId === interviewId) {
        resetInterviewForm();
      }
      await reloadSelfFromServer("Entrevista removida.");
    } catch (err) {
      setDetailError(
        err instanceof ApiError
          ? err.message
          : "Não foi possível remover a entrevista."
      );
    } finally {
      setDetailSaving(false);
    }
  }

  async function handleSubmitAssessment(e: React.FormEvent) {
    e.preventDefault();
    setDetailError(null);
    setDetailSuccess(null);

    if (asmtTitle.trim().length < 2) {
      setDetailError("Informe o título do desafio técnico.");
      return;
    }

    const payload = {
      title: asmtTitle.trim(),
      platform: asmtPlatform.trim() || null,
      description: asmtDescription.trim() || null,
      instructions_url: asmtInstructionsUrl.trim() || null,
      submission_url: asmtSubmissionUrl.trim() || null,
      deadline_at: fromLocalDateTimeInputValue(asmtDeadlineAt),
      status: asmtStatus,
      feedback: asmtFeedback.trim() || null,
      notes: asmtNotes.trim() || null,
    };

    setDetailSaving(true);
    try {
      if (editingAssessmentId) {
        await api.applications.updateAssessment(
          selectedApp.id,
          editingAssessmentId,
          payload
        );
        resetAssessmentForm();
        await reloadSelfFromServer("Teste técnico atualizado.");
      } else {
        await api.applications.createAssessment(selectedApp.id, payload);
        resetAssessmentForm();
        await reloadSelfFromServer("Teste técnico cadastrado.");
      }
    } catch (err) {
      setDetailError(
        err instanceof ApiError
          ? err.message
          : "Não foi possível salvar o teste técnico."
      );
    } finally {
      setDetailSaving(false);
    }
  }

  async function handleMarkAssessmentSubmitted(asmt: ApplicationAssessmentItem) {
    setDetailSaving(true);
    setDetailError(null);
    setDetailSuccess(null);
    try {
      await api.applications.updateAssessment(selectedApp.id, asmt.id, {
        status: "submitted",
        submitted_at: new Date().toISOString(),
      });
      await reloadSelfFromServer("Entrega do desafio registrada.");
    } catch (err) {
      setDetailError(
        err instanceof ApiError
          ? err.message
          : "Não foi possível atualizar a entrega do desafio."
      );
    } finally {
      setDetailSaving(false);
    }
  }

  async function handleDeleteAssessment(assessmentId: string) {
    setDetailSaving(true);
    setDetailError(null);
    setDetailSuccess(null);
    try {
      await api.applications.deleteAssessment(selectedApp.id, assessmentId);
      if (editingAssessmentId === assessmentId) {
        resetAssessmentForm();
      }
      await reloadSelfFromServer("Desafio técnico removido.");
    } catch (err) {
      setDetailError(
        err instanceof ApiError
          ? err.message
          : "Não foi possível remover o teste técnico."
      );
    } finally {
      setDetailSaving(false);
    }
  }

  async function handleSubmitContact(e: React.FormEvent) {
    e.preventDefault();
    setDetailError(null);
    setDetailSuccess(null);

    if (ctName.trim().length < 2) {
      setDetailError("Informe o nome do contato.");
      return;
    }

    const payload = {
      name: ctName.trim(),
      role_title: ctRole.trim() || null,
      email: ctEmail.trim() || null,
      linkedin_url: ctLinkedin.trim() || null,
      notes: ctNotes.trim() || null,
    };

    setDetailSaving(true);
    try {
      if (editingContactId) {
        await api.applications.updateContact(
          selectedApp.id,
          editingContactId,
          payload
        );
        resetContactForm();
        await reloadSelfFromServer("Contato atualizado.");
      } else {
        await api.applications.createContact(selectedApp.id, payload);
        resetContactForm();
        await reloadSelfFromServer("Contato adicionado à candidatura.");
      }
    } catch (err) {
      setDetailError(
        err instanceof ApiError
          ? err.message
          : "Não foi possível salvar o contato."
      );
    } finally {
      setDetailSaving(false);
    }
  }

  async function handleDeleteContact(contactId: string) {
    setDetailSaving(true);
    setDetailError(null);
    setDetailSuccess(null);
    try {
      await api.applications.deleteContact(selectedApp.id, contactId);
      if (editingContactId === contactId) {
        resetContactForm();
      }
      await reloadSelfFromServer("Contato removido.");
    } catch (err) {
      setDetailError(
        err instanceof ApiError
          ? err.message
          : "Não foi possível excluir o contato."
      );
    } finally {
      setDetailSaving(false);
    }
  }

  async function handleRecordExternalInteraction(e: React.FormEvent) {
    e.preventDefault();
    setDetailSaving(true);
    setDetailError(null);
    setDetailSuccess(null);
    try {
      const updated = await api.applications.recordExternalInteraction(
        selectedApp.id,
        {
          interaction_type: extType,
          interaction_at:
            fromLocalDateTimeInputValue(extAt) || new Date().toISOString(),
          note: extNote.trim() || null,
        }
      );
      setExtNote("");
      await onRefreshApplication(updated);
      setDetailSuccess("Interação externa registrada.");
    } catch (err) {
      setDetailError(
        err instanceof ApiError
          ? err.message
          : "Não foi possível registrar a interação externa."
      );
    } finally {
      setDetailSaving(false);
    }
  }

  async function handleGenerateFollowUp() {
    setDetailSaving(true);
    setDetailError(null);
    try {
      const tpl = await api.applications.followUpTemplate(selectedApp.id);
      setFollowUpTemplate(tpl);
      setCopiedFollowUp(false);
    } catch (err) {
      setDetailError(
        err instanceof ApiError
          ? err.message
          : "Não foi possível gerar o modelo de follow-up."
      );
    } finally {
      setDetailSaving(false);
    }
  }

  async function handleCopyFollowUp() {
    if (!followUpTemplate) return;
    try {
      if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(followUpTemplate.message);
      }
      setCopiedFollowUp(true);
      window.setTimeout(() => setCopiedFollowUp(false), 3000);
    } catch {
      setDetailError("Não foi possível acessar a área de transferência.");
    }
  }

  const tabs: Array<{ key: DetailTabKey; label: string; count?: number }> = [
    { key: "general", label: "Geral" },
    { key: "interviews", label: "Entrevistas", count: interviews.length },
    { key: "assessments", label: "Testes técnicos", count: assessments.length },
    { key: "contacts", label: "Contatos", count: contacts.length },
    { key: "materials", label: "Materiais", count: linkedMaterials.length },
    { key: "followup", label: "Acompanhamento" },
  ];

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-3 backdrop-blur-xs sm:p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="application-detail-title"
    >
      <div className="max-h-[92vh] w-full max-w-4xl space-y-5 overflow-y-auto rounded-2xl border border-border bg-card p-5 text-card-foreground shadow-xl sm:p-6">
        {/* Cabeçalho */}
        <div className="flex items-start justify-between gap-4 border-b border-border pb-4">
          <div className="min-w-0 space-y-1">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant={statusBadgeVariant(selectedApp.status)}>
                {selectedApp.status_label}
              </Badge>
              {selectedApp.source_name && (
                <Badge variant="outline">{selectedApp.source_name}</Badge>
              )}
              <Badge variant="outline">
                {seniorityLabels[selectedApp.seniority_level] ||
                  selectedApp.seniority_level}
              </Badge>
              <Badge variant="outline">
                {employmentLabels[selectedApp.employment_type] ||
                  selectedApp.employment_type}
              </Badge>
              <Badge variant="outline">
                {workModeLabels[selectedApp.work_mode] ||
                  selectedApp.work_mode}
              </Badge>
            </div>
            <h2
              id="application-detail-title"
              className="break-words text-xl font-bold"
            >
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
              <span>Criada: {formatLocalDate(selectedApp.created_at)}</span>
            </p>
          </div>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            onClick={onClose}
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

        {/* Navegação interna por abas da candidatura */}
        <div
          className="flex flex-wrap gap-1.5 border-b border-border pb-3"
          role="tablist"
          aria-label="Seções da candidatura"
        >
          {tabs.map((tab) => {
            const active = activeTab === tab.key;
            return (
              <button
                key={tab.key}
                type="button"
                role="tab"
                aria-selected={active}
                onClick={() => {
                  setActiveTab(tab.key);
                  setDetailError(null);
                  setDetailSuccess(null);
                }}
                className={`inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors ${
                  active
                    ? "border-primary bg-primary text-primary-foreground"
                    : "border-border bg-background text-muted-foreground hover:text-foreground"
                }`}
              >
                <span>{tab.label}</span>
                {tab.count !== undefined && (
                  <span
                    className={`rounded-full px-1.5 py-0.5 text-[10px] ${
                      active
                        ? "bg-primary-foreground/20 text-primary-foreground"
                        : "bg-muted text-foreground"
                    }`}
                  >
                    {tab.count}
                  </span>
                )}
              </button>
            );
          })}
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
                  onClick={() => handleDeleteApplication(true)}
                >
                  Confirmar exclusão definitiva do processo e histórico
                </Button>
              </div>
            )}
          </div>
        )}

        {detailSuccess && (
          <div className="flex items-center gap-2 rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-700 dark:text-emerald-300">
            <CheckCircle2 className="h-4 w-4 shrink-0" />
            <span>{detailSuccess}</span>
          </div>
        )}

        {/* ABA 1: GERAL */}
        {activeTab === "general" && (
          <div className="space-y-5">
            <form onSubmit={handleSaveGeneral} className="space-y-4">
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
                    {allStatusOptions.map((opt) => (
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
                  <Label htmlFor="detail-assessment-due">
                    Prazo de teste técnico
                  </Label>
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
                  <Label htmlFor="detail-summary">
                    Resumo da oportunidade / processo
                  </Label>
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

              <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border pt-3">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="text-destructive hover:text-destructive"
                  disabled={detailSaving}
                  onClick={() => handleDeleteApplication(false)}
                >
                  <Trash2 className="mr-1.5 h-4 w-4" />
                  Excluir candidatura
                </Button>

                <div className="flex items-center gap-2">
                  <Button type="button" variant="outline" onClick={onClose}>
                    Fechar
                  </Button>
                  <Button type="submit" disabled={detailSaving}>
                    {detailSaving ? "Salvando..." : "Salvar alterações"}
                  </Button>
                </div>
              </div>
            </form>

            {/* Histórico imutável de movimentações */}
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
                          ? hist.from_status === hist.to_status
                            ? `Evento em ${hist.to_status_label}`
                            : `${hist.from_status_label} -> ${hist.to_status_label}`
                          : `Início em ${hist.to_status_label}`}
                      </p>
                      {hist.note && (
                        <p className="text-muted-foreground">{hist.note}</p>
                      )}
                    </div>
                    <span className="text-[11px] text-muted-foreground">
                      {formatLocalDateTime(hist.changed_at)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* ABA 2: ENTREVISTAS */}
        {activeTab === "interviews" && (
          <div className="space-y-5">
            <form
              onSubmit={handleSubmitInterview}
              className="space-y-3 rounded-xl border border-border bg-muted/20 p-4"
            >
              <div className="flex items-center justify-between gap-2">
                <h3 className="flex items-center gap-2 text-sm font-semibold">
                  <CalendarClock className="h-4 w-4 text-primary" />
                  {editingInterviewId
                    ? "Editar / Reagendar Entrevista"
                    : "Agendar Nova Rodada de Entrevista"}
                </h3>
                {editingInterviewId && (
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    onClick={resetInterviewForm}
                  >
                    Cancelar edição
                  </Button>
                )}
              </div>

              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-1">
                  <Label htmlFor="iv-round-name">Nome da rodada *</Label>
                  <Input
                    id="iv-round-name"
                    value={ivRoundName}
                    onChange={(e) => setIvRoundName(e.target.value)}
                    placeholder="Ex.: Triagem RH, Entrevista Técnica, Live Coding"
                    required
                  />
                </div>

                <div className="space-y-1">
                  <Label htmlFor="iv-format">Formato</Label>
                  <select
                    id="iv-format"
                    value={ivFormat}
                    onChange={(e) =>
                      setIvFormat(e.target.value as InterviewFormat)
                    }
                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                  >
                    {INTERVIEW_FORMAT_OPTIONS.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="space-y-1">
                  <Label htmlFor="iv-scheduled-at">Data e hora (local) *</Label>
                  <Input
                    id="iv-scheduled-at"
                    type="datetime-local"
                    value={ivScheduledAt}
                    onChange={(e) => setIvScheduledAt(e.target.value)}
                    required
                  />
                </div>

                <div className="space-y-1">
                  <Label htmlFor="iv-duration">Duração (minutos)</Label>
                  <Input
                    id="iv-duration"
                    type="number"
                    min={5}
                    max={480}
                    value={ivDuration}
                    onChange={(e) => setIvDuration(e.target.value)}
                  />
                </div>

                <div className="space-y-1">
                  <Label htmlFor="iv-interviewers">Participantes</Label>
                  <Input
                    id="iv-interviewers"
                    value={ivInterviewers}
                    onChange={(e) => setIvInterviewers(e.target.value)}
                    placeholder="Ex.: Marina (Tech Lead), João (RH)"
                  />
                </div>

                <div className="space-y-1">
                  <Label htmlFor="iv-meeting-url">Link da reunião</Label>
                  <Input
                    id="iv-meeting-url"
                    type="url"
                    value={ivMeetingUrl}
                    onChange={(e) => setIvMeetingUrl(e.target.value)}
                    placeholder="https://meet.google.com/..."
                  />
                </div>

                <div className="space-y-1">
                  <Label htmlFor="iv-notes">Notas da preparação</Label>
                  <Textarea
                    id="iv-notes"
                    rows={2}
                    value={ivNotes}
                    onChange={(e) => setIvNotes(e.target.value)}
                    placeholder="Tópicos abordados ou perguntas preparadas."
                  />
                </div>

                <div className="space-y-1">
                  <Label htmlFor="iv-feedback">Feedback recebido</Label>
                  <Textarea
                    id="iv-feedback"
                    rows={2}
                    value={ivFeedback}
                    onChange={(e) => setIvFeedback(e.target.value)}
                    placeholder="Impressões ou retornos desta rodada."
                  />
                </div>
              </div>

              <div className="flex justify-end">
                <Button type="submit" size="sm" disabled={detailSaving}>
                  <Plus className="mr-1.5 h-3.5 w-3.5" />
                  {editingInterviewId
                    ? "Salvar reagendamento / edição"
                    : "Salvar entrevista"}
                </Button>
              </div>
            </form>

            <div className="space-y-2.5">
              {interviews.length === 0 ? (
                <p className="rounded-lg border border-dashed border-border p-4 text-center text-xs text-muted-foreground">
                  Nenhuma rodada de entrevista registrada para esta candidatura.
                </p>
              ) : (
                interviews.map((iv) => (
                  <div
                    key={iv.id}
                    className="space-y-2 rounded-xl border border-border bg-background p-3.5 text-xs"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div className="space-y-1">
                        <div className="flex flex-wrap items-center gap-1.5">
                          <span className="text-sm font-semibold text-foreground">
                            {iv.round_name}
                          </span>
                          <Badge
                            variant={
                              iv.status === "completed"
                                ? "success"
                                : iv.status === "cancelled"
                                ? "secondary"
                                : "default"
                            }
                          >
                            {iv.status_label}
                          </Badge>
                          <Badge variant="outline">
                            {iv.interview_format_label}
                          </Badge>
                        </div>
                        <p className="text-muted-foreground">
                          Horário:{" "}
                          <strong>{formatLocalDateTime(iv.scheduled_at)}</strong>
                          {iv.duration_minutes
                            ? ` (${iv.duration_minutes} min)`
                            : ""}
                          {iv.interviewers ? ` • ${iv.interviewers}` : ""}
                        </p>
                        {iv.previous_scheduled_at && (
                          <p className="text-[11px] text-amber-700 dark:text-amber-300">
                            Reagendada (horário anterior:{" "}
                            {formatLocalDateTime(iv.previous_scheduled_at)})
                          </p>
                        )}
                      </div>

                      <div className="flex flex-wrap items-center gap-1.5">
                        {iv.meeting_url && (
                          <a
                            href={iv.meeting_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1 rounded-md border border-border px-2 py-1 text-primary hover:underline"
                          >
                            Reunião
                            <ExternalLink className="h-3 w-3" />
                          </a>
                        )}
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          onClick={() => startEditInterview(iv)}
                        >
                          <Edit3 className="mr-1 h-3 w-3" />
                          Editar / Reagendar
                        </Button>
                        {iv.status === "scheduled" && (
                          <>
                            <Button
                              type="button"
                              size="sm"
                              variant="outline"
                              disabled={detailSaving}
                              onClick={() =>
                                handleInterviewQuickAction(iv, "completed")
                              }
                            >
                              <CheckCircle2 className="mr-1 h-3 w-3 text-emerald-500" />
                              Concluir
                            </Button>
                            <Button
                              type="button"
                              size="sm"
                              variant="ghost"
                              disabled={detailSaving}
                              onClick={() =>
                                handleInterviewQuickAction(iv, "cancelled")
                              }
                            >
                              <XCircle className="mr-1 h-3 w-3" />
                              Cancelar
                            </Button>
                          </>
                        )}
                        <Button
                          type="button"
                          size="sm"
                          variant="ghost"
                          className="text-destructive hover:text-destructive"
                          disabled={detailSaving}
                          onClick={() => handleDeleteInterview(iv.id)}
                          aria-label={`Excluir entrevista ${iv.round_name}`}
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    </div>

                    {iv.notes && (
                      <p className="rounded-md bg-muted/40 p-2 text-muted-foreground">
                        <strong>Notas:</strong> {iv.notes}
                      </p>
                    )}
                    {iv.feedback_received && (
                      <p className="rounded-md bg-primary/5 p-2 text-foreground">
                        <strong>Feedback:</strong> {iv.feedback_received}
                      </p>
                    )}
                  </div>
                ))
              )}
            </div>
          </div>
        )}

        {/* ABA 3: TESTES TÉCNICOS */}
        {activeTab === "assessments" && (
          <div className="space-y-5">
            <form
              onSubmit={handleSubmitAssessment}
              className="space-y-3 rounded-xl border border-border bg-muted/20 p-4"
            >
              <div className="flex items-center justify-between gap-2">
                <h3 className="flex items-center gap-2 text-sm font-semibold">
                  <ClipboardCheck className="h-4 w-4 text-primary" />
                  {editingAssessmentId
                    ? "Editar Teste / Desafio Técnico"
                    : "Cadastrar Desafio Técnico"}
                </h3>
                {editingAssessmentId && (
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    onClick={resetAssessmentForm}
                  >
                    Cancelar edição
                  </Button>
                )}
              </div>

              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-1">
                  <Label htmlFor="asmt-title">Título do desafio *</Label>
                  <Input
                    id="asmt-title"
                    value={asmtTitle}
                    onChange={(e) => setAsmtTitle(e.target.value)}
                    placeholder="Ex.: API REST FastAPI + Docker"
                    required
                  />
                </div>

                <div className="space-y-1">
                  <Label htmlFor="asmt-platform">Plataforma</Label>
                  <Input
                    id="asmt-platform"
                    value={asmtPlatform}
                    onChange={(e) => setAsmtPlatform(e.target.value)}
                    placeholder="Ex.: GitHub, HackerRank, Gupy"
                  />
                </div>

                <div className="space-y-1">
                  <Label htmlFor="asmt-instructions-url">
                    Link das instruções
                  </Label>
                  <Input
                    id="asmt-instructions-url"
                    type="url"
                    value={asmtInstructionsUrl}
                    onChange={(e) => setAsmtInstructionsUrl(e.target.value)}
                    placeholder="https://github.com/empresa/desafio"
                  />
                </div>

                <div className="space-y-1">
                  <Label htmlFor="asmt-submission-url">
                    Link da entrega (seu repositório)
                  </Label>
                  <Input
                    id="asmt-submission-url"
                    type="url"
                    value={asmtSubmissionUrl}
                    onChange={(e) => setAsmtSubmissionUrl(e.target.value)}
                    placeholder="https://github.com/seu-usuario/solucao"
                  />
                </div>

                <div className="space-y-1">
                  <Label htmlFor="asmt-deadline-at">Prazo de entrega (local)</Label>
                  <Input
                    id="asmt-deadline-at"
                    type="datetime-local"
                    value={asmtDeadlineAt}
                    onChange={(e) => setAsmtDeadlineAt(e.target.value)}
                  />
                </div>

                <div className="space-y-1">
                  <Label htmlFor="asmt-status">Status</Label>
                  <select
                    id="asmt-status"
                    value={asmtStatus}
                    onChange={(e) =>
                      setAsmtStatus(e.target.value as AssessmentStatus)
                    }
                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                  >
                    <option value="pending">Pendente</option>
                    <option value="in_progress">Em andamento</option>
                    <option value="submitted">Enviado</option>
                    <option value="feedback_received">Feedback recebido</option>
                    <option value="cancelled">Cancelado</option>
                  </select>
                </div>

                <div className="space-y-1 sm:col-span-2">
                  <Label htmlFor="asmt-description">Descrição e requisitos</Label>
                  <Textarea
                    id="asmt-description"
                    rows={2}
                    value={asmtDescription}
                    onChange={(e) => setAsmtDescription(e.target.value)}
                  />
                </div>

                <div className="space-y-1">
                  <Label htmlFor="asmt-notes">Anotações técnicas</Label>
                  <Textarea
                    id="asmt-notes"
                    rows={2}
                    value={asmtNotes}
                    onChange={(e) => setAsmtNotes(e.target.value)}
                  />
                </div>

                <div className="space-y-1">
                  <Label htmlFor="asmt-feedback">Avaliação / Feedback</Label>
                  <Textarea
                    id="asmt-feedback"
                    rows={2}
                    value={asmtFeedback}
                    onChange={(e) => setAsmtFeedback(e.target.value)}
                  />
                </div>
              </div>

              <div className="flex justify-end">
                <Button type="submit" size="sm" disabled={detailSaving}>
                  <Plus className="mr-1.5 h-3.5 w-3.5" />
                  {editingAssessmentId
                    ? "Atualizar desafio"
                    : "Salvar desafio técnico"}
                </Button>
              </div>
            </form>

            <div className="space-y-2.5">
              {assessments.length === 0 ? (
                <p className="rounded-lg border border-dashed border-border p-4 text-center text-xs text-muted-foreground">
                  Nenhum teste técnico estruturado cadastrado nesta candidatura.
                </p>
              ) : (
                assessments.map((asmt) => (
                  <div
                    key={asmt.id}
                    className="space-y-2 rounded-xl border border-border bg-background p-3.5 text-xs"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div className="space-y-1">
                        <div className="flex flex-wrap items-center gap-1.5">
                          <span className="text-sm font-semibold text-foreground">
                            {asmt.title}
                          </span>
                          <Badge
                            variant={
                              asmt.status === "submitted" ||
                              asmt.status === "feedback_received"
                                ? "success"
                                : asmt.is_overdue
                                ? "outline"
                                : "warning"
                            }
                          >
                            {asmt.status_label}
                          </Badge>
                          {asmt.platform && (
                            <Badge variant="outline">{asmt.platform}</Badge>
                          )}
                          {asmt.is_overdue && (
                            <Badge
                              variant="outline"
                              className="border-destructive/50 text-destructive"
                            >
                              Prazo vencido
                            </Badge>
                          )}
                          {!asmt.is_overdue && asmt.is_due_soon_24h && (
                            <Badge variant="warning">Vence em menos de 24h</Badge>
                          )}
                        </div>
                        <p className="text-muted-foreground">
                          Prazo:{" "}
                          <strong>{formatLocalDateTime(asmt.deadline_at)}</strong>
                          {asmt.submitted_at
                            ? ` • Enviado em: ${formatLocalDateTime(
                                asmt.submitted_at
                              )}`
                            : ""}
                        </p>
                      </div>

                      <div className="flex flex-wrap items-center gap-1.5">
                        {asmt.instructions_url && (
                          <a
                            href={asmt.instructions_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1 rounded-md border border-border px-2 py-1 text-primary hover:underline"
                          >
                            Instruções
                            <ExternalLink className="h-3 w-3" />
                          </a>
                        )}
                        {asmt.submission_url && (
                          <a
                            href={asmt.submission_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1 rounded-md border border-border px-2 py-1 text-primary hover:underline"
                          >
                            Entrega
                            <ExternalLink className="h-3 w-3" />
                          </a>
                        )}
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          onClick={() => startEditAssessment(asmt)}
                        >
                          Editar
                        </Button>
                        {(asmt.status === "pending" ||
                          asmt.status === "in_progress") && (
                          <Button
                            type="button"
                            size="sm"
                            variant="outline"
                            disabled={detailSaving}
                            onClick={() => handleMarkAssessmentSubmitted(asmt)}
                          >
                            Marcar entregue
                          </Button>
                        )}
                        <Button
                          type="button"
                          size="sm"
                          variant="ghost"
                          className="text-destructive hover:text-destructive"
                          disabled={detailSaving}
                          onClick={() => handleDeleteAssessment(asmt.id)}
                          aria-label={`Excluir desafio ${asmt.title}`}
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    </div>

                    {asmt.description && (
                      <p className="text-muted-foreground">{asmt.description}</p>
                    )}
                    {asmt.feedback && (
                      <p className="rounded-md bg-primary/5 p-2 text-foreground">
                        <strong>Feedback:</strong> {asmt.feedback}
                      </p>
                    )}
                  </div>
                ))
              )}
            </div>
          </div>
        )}

        {/* ABA 4: CONTATOS */}
        {activeTab === "contacts" && (
          <div className="space-y-5">
            <form
              onSubmit={handleSubmitContact}
              className="space-y-3 rounded-xl border border-border bg-muted/20 p-4"
            >
              <div className="flex items-center justify-between gap-2">
                <h3 className="flex items-center gap-2 text-sm font-semibold">
                  <Users className="h-4 w-4 text-primary" />
                  {editingContactId
                    ? "Editar Contato do Processo"
                    : "Adicionar Recrutador / Contato"}
                </h3>
                {editingContactId && (
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    onClick={resetContactForm}
                  >
                    Cancelar edição
                  </Button>
                )}
              </div>

              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-1">
                  <Label htmlFor="ct-name">Nome *</Label>
                  <Input
                    id="ct-name"
                    value={ctName}
                    onChange={(e) => setCtName(e.target.value)}
                    placeholder="Ex.: Mariana Souza"
                    required
                  />
                </div>

                <div className="space-y-1">
                  <Label htmlFor="ct-role">Cargo / Papel</Label>
                  <Input
                    id="ct-role"
                    value={ctRole}
                    onChange={(e) => setCtRole(e.target.value)}
                    placeholder="Ex.: Tech Recruiter, Engineering Manager"
                  />
                </div>

                <div className="space-y-1">
                  <Label htmlFor="ct-email">E-mail</Label>
                  <Input
                    id="ct-email"
                    type="email"
                    value={ctEmail}
                    onChange={(e) => setCtEmail(e.target.value)}
                    placeholder="mariana@empresa.com"
                  />
                </div>

                <div className="space-y-1">
                  <Label htmlFor="ct-linkedin">LinkedIn</Label>
                  <Input
                    id="ct-linkedin"
                    type="url"
                    value={ctLinkedin}
                    onChange={(e) => setCtLinkedin(e.target.value)}
                    placeholder="https://www.linkedin.com/in/..."
                  />
                </div>

                <div className="space-y-1 sm:col-span-2">
                  <Label htmlFor="ct-notes">Observações</Label>
                  <Textarea
                    id="ct-notes"
                    rows={2}
                    value={ctNotes}
                    onChange={(e) => setCtNotes(e.target.value)}
                  />
                </div>
              </div>

              <div className="flex justify-end">
                <Button type="submit" size="sm" disabled={detailSaving}>
                  <Plus className="mr-1.5 h-3.5 w-3.5" />
                  {editingContactId ? "Atualizar contato" : "Salvar contato"}
                </Button>
              </div>
            </form>

            <div className="space-y-2.5">
              {contacts.length === 0 ? (
                <p className="rounded-lg border border-dashed border-border p-4 text-center text-xs text-muted-foreground">
                  Nenhum recrutador ou entrevistador cadastrado ainda.
                </p>
              ) : (
                contacts.map((ct) => (
                  <div
                    key={ct.id}
                    className="flex flex-wrap items-start justify-between gap-3 rounded-xl border border-border bg-background p-3.5 text-xs"
                  >
                    <div className="space-y-1">
                      <p className="text-sm font-semibold text-foreground">
                        {ct.name}
                      </p>
                      {ct.role_title && (
                        <p className="text-muted-foreground">{ct.role_title}</p>
                      )}
                      <div className="flex flex-wrap items-center gap-3 pt-1">
                        {ct.email && (
                          <a
                            href={`mailto:${ct.email}`}
                            className="inline-flex items-center gap-1 text-primary hover:underline"
                          >
                            <Mail className="h-3.5 w-3.5" />
                            {ct.email}
                          </a>
                        )}
                        {ct.linkedin_url && (
                          <a
                            href={ct.linkedin_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1 text-primary hover:underline"
                          >
                            LinkedIn
                            <ExternalLink className="h-3 w-3" />
                          </a>
                        )}
                      </div>
                      {ct.notes && (
                        <p className="pt-1 text-muted-foreground">{ct.notes}</p>
                      )}
                    </div>

                    <div className="flex items-center gap-1.5">
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        onClick={() => startEditContact(ct)}
                      >
                        Editar
                      </Button>
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        className="text-destructive hover:text-destructive"
                        disabled={detailSaving}
                        onClick={() => handleDeleteContact(ct.id)}
                        aria-label={`Excluir contato ${ct.name}`}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        )}

        {/* ABA 5: ACOMPANHAMENTO & FOLLOW-UP */}
        {activeTab === "followup" && (
          <div className="space-y-5">
            <div className="rounded-xl border border-border bg-muted/20 p-4 text-xs">
              <p className="font-semibold text-foreground">
                Última interação externa registrada
              </p>
              {selectedApp.last_external_interaction_at ? (
                <div className="mt-1.5 space-y-1 text-muted-foreground">
                  <p>
                    <strong>Data/hora:</strong>{" "}
                    {formatLocalDateTime(
                      selectedApp.last_external_interaction_at
                    )}{" "}
                    • <strong>Canal:</strong>{" "}
                    {selectedApp.last_external_interaction_type_label ||
                      selectedApp.last_external_interaction_type ||
                      "Não informado"}
                  </p>
                  {selectedApp.last_external_interaction_note && (
                    <p>
                      <strong>Registro:</strong>{" "}
                      {selectedApp.last_external_interaction_note}
                    </p>
                  )}
                </div>
              ) : (
                <p className="mt-1 text-muted-foreground">
                  Nenhuma interação externa registrada explicitamente ainda.
                  Edições internas de notas ou contatos não alteram este
                  indicador.
                </p>
              )}
            </div>

            <form
              onSubmit={handleRecordExternalInteraction}
              className="space-y-3 rounded-xl border border-border bg-background p-4"
            >
              <h3 className="text-sm font-semibold">
                Registrar Interação Externa Ocorrida
              </h3>
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-1">
                  <Label htmlFor="ext-type">Canal / Tipo</Label>
                  <select
                    id="ext-type"
                    value={extType}
                    onChange={(e) =>
                      setExtType(e.target.value as ExternalInteractionType)
                    }
                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                  >
                    {INTERACTION_TYPE_OPTIONS.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="space-y-1">
                  <Label htmlFor="ext-at">Data e hora (local)</Label>
                  <Input
                    id="ext-at"
                    type="datetime-local"
                    value={extAt}
                    onChange={(e) => setExtAt(e.target.value)}
                  />
                </div>

                <div className="space-y-1 sm:col-span-2">
                  <Label htmlFor="ext-note">Resumo da conversa / retorno</Label>
                  <Textarea
                    id="ext-note"
                    rows={2}
                    value={extNote}
                    onChange={(e) => setExtNote(e.target.value)}
                    placeholder="Ex.: Recrutadora confirmou análise do desafio até sexta."
                  />
                </div>
              </div>

              <div className="flex justify-end">
                <Button type="submit" size="sm" disabled={detailSaving}>
                  Registrar interação externa
                </Button>
              </div>
            </form>

            {/* Gerador determinístico de Follow-up */}
            <div className="space-y-3 rounded-xl border border-border bg-background p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <h3 className="flex items-center gap-2 text-sm font-semibold">
                    <MessageSquareText className="h-4 w-4 text-primary" />
                    Mensagem Determinística de Follow-up
                  </h3>
                  <p className="text-xs text-muted-foreground">
                    Montada exclusivamente com dados reais salvos na candidatura
                    (sem IA nem envio automático).
                  </p>
                </div>

                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  disabled={detailSaving}
                  onClick={handleGenerateFollowUp}
                >
                  Gerar mensagem
                </Button>
              </div>

              {followUpTemplate && (
                <div className="space-y-3 rounded-lg border border-primary/30 bg-primary/5 p-3.5 text-xs">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="font-semibold text-foreground">
                      Assunto: {followUpTemplate.subject}
                    </span>
                    <Button
                      type="button"
                      size="sm"
                      onClick={handleCopyFollowUp}
                    >
                      {copiedFollowUp ? (
                        <>
                          <Check className="mr-1.5 h-3.5 w-3.5" />
                          Mensagem copiada!
                        </>
                      ) : (
                        <>
                          <Copy className="mr-1.5 h-3.5 w-3.5" />
                          Copiar mensagem
                        </>
                      )}
                    </Button>
                  </div>

                  <pre className="whitespace-pre-wrap break-words rounded-md border border-border bg-background p-3 font-sans text-xs text-foreground">
                    {followUpTemplate.message}
                  </pre>

                  <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-muted-foreground">
                    <span>{followUpTemplate.context_summary}</span>
                    <span>•</span>
                    <span>{followUpTemplate.disclaimer}</span>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* ABA MATERIAIS (FASE 04.1) */}
        {activeTab === "materials" && (
          <div className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-border bg-muted/20 p-4">
              <div>
                <h3 className="flex items-center gap-2 text-sm font-semibold">
                  <FileText className="h-4 w-4 text-primary" />
                  Materiais e Versões Vinculadas
                </h3>
                <p className="text-xs text-muted-foreground">
                  Gere currículos, cartas, mensagens, propostas freelance e
                  respostas determinísticas com fatos confirmados, aprove uma
                  versão e vincule a esta candidatura.
                </p>
              </div>
              <Button
                type="button"
                size="sm"
                onClick={() => {
                  setMaterialWorkspaceId(null);
                  setMaterialWorkspaceOpen(true);
                }}
              >
                <Plus className="mr-1.5 h-3.5 w-3.5" />
                Novo material direcionado
              </Button>
            </div>

            {materialsLoading ? (
              <p className="text-xs text-muted-foreground">
                Carregando materiais vinculados...
              </p>
            ) : (
              <>
                <div className="space-y-2">
                  <h4 className="text-xs font-semibold text-foreground">
                    Vinculados a esta candidatura ({linkedMaterials.length})
                  </h4>
                  {linkedMaterials.length === 0 ? (
                    <div className="rounded-lg border border-dashed border-border p-4 text-xs text-muted-foreground">
                      Nenhum currículo aprovado vinculado a esta candidatura
                      ainda.
                    </div>
                  ) : (
                    linkedMaterials.map((mat) => (
                      <div
                        key={mat.id}
                        className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border bg-background p-3 text-xs"
                      >
                        <div className="space-y-0.5">
                          <div className="flex flex-wrap items-center gap-1.5">
                            <span className="font-semibold text-foreground">
                              {mat.title}
                            </span>
                            <Badge variant="outline">
                              {mat.material_type}
                            </Badge>
                            <Badge variant="secondary">
                              v{mat.latest_version_number}
                            </Badge>
                            {mat.has_approved_version && (
                              <Badge variant="default">Versão aprovada</Badge>
                            )}
                          </div>
                          <div className="text-muted-foreground">
                            Idioma: {mat.target_language} · Atualizado em{" "}
                            {formatLocalDate(mat.updated_at)}
                          </div>
                        </div>
                        <div className="flex flex-wrap gap-2">
                          <Button
                            type="button"
                            size="sm"
                            variant="outline"
                            onClick={() => {
                              setMaterialWorkspaceId(mat.id);
                              setMaterialWorkspaceOpen(true);
                            }}
                          >
                            Abrir / Editar
                          </Button>
                          <Button
                            type="button"
                            size="sm"
                            variant="ghost"
                            disabled={detailSaving}
                            onClick={async () => {
                              setDetailSaving(true);
                              setDetailError(null);
                              try {
                                await api.materials.unlink(mat.id, {
                                  application_id: selectedApp.id,
                                });
                                setDetailSuccess(
                                  "Material desvinculado desta candidatura."
                                );
                                await loadMaterialsForApp();
                              } catch (err) {
                                setDetailError(
                                  err instanceof Error
                                    ? err.message
                                    : "Erro ao desvincular material."
                                );
                              } finally {
                                setDetailSaving(false);
                              }
                            }}
                          >
                            <Unlink2 className="mr-1.5 h-3.5 w-3.5" />
                            Desvincular
                          </Button>
                        </div>
                      </div>
                    ))
                  )}
                </div>

                {availableMaterials.length > 0 && (
                  <div className="space-y-2 pt-2">
                    <h4 className="text-xs font-semibold text-foreground">
                      Outros materiais seus disponíveis ({availableMaterials.length})
                    </h4>
                    {availableMaterials.map((mat) => (
                      <div
                        key={mat.id}
                        className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border bg-muted/20 p-3 text-xs"
                      >
                        <div className="space-y-0.5">
                          <div className="flex flex-wrap items-center gap-1.5">
                            <span className="font-semibold text-foreground">
                              {mat.title}
                            </span>
                            <Badge variant="outline">
                              {mat.material_type}
                            </Badge>
                            <Badge variant="outline">
                              v{mat.latest_version_number}
                            </Badge>
                            {mat.has_approved_version ? (
                              <Badge variant="secondary">Aprovado</Badge>
                            ) : (
                              <Badge variant="outline">Aguardando aprovação</Badge>
                            )}
                          </div>
                        </div>
                        <div className="flex flex-wrap gap-2">
                          <Button
                            type="button"
                            size="sm"
                            variant="outline"
                            onClick={() => {
                              setMaterialWorkspaceId(mat.id);
                              setMaterialWorkspaceOpen(true);
                            }}
                          >
                            <Link2 className="mr-1.5 h-3.5 w-3.5" />
                            Abrir e vincular
                          </Button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </div>

      {materialWorkspaceOpen && (
        <MaterialWorkspaceModal
          open={materialWorkspaceOpen}
          onClose={() => setMaterialWorkspaceOpen(false)}
          opportunityId={selectedApp.opportunity_id || null}
          applicationId={selectedApp.id}
          targetTitle={
            selectedApp.company_name
              ? `${selectedApp.role_title} — ${selectedApp.company_name}`
              : selectedApp.role_title
          }
          initialMaterialId={materialWorkspaceId}
          onMaterialChanged={() => {
            void loadMaterialsForApp();
          }}
          onNavigateProfile={onNavigateProfile}
        />
      )}
    </div>
  );
};

import React, { useState } from "react";
import {
  Check,
  Clock,
  Copy,
  Loader2,
  MailCheck,
  MessageSquareText,
  RefreshCw,
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
import { ApiError, api } from "@/lib/api";
import type {
  FollowUpTemplateResponse,
  StaleApplicationsResponse,
} from "@/types/api";
import type { DetailTabKey } from "./ApplicationAgendaView";
import { formatLocalDateTime } from "./dateTimeHelpers";

interface ApplicationFollowUpViewProps {
  staleData: StaleApplicationsResponse | null;
  loading: boolean;
  error: string | null;
  staleDays: number;
  onChangeStaleDays: (days: number) => void;
  onReload: () => void;
  onOpenApplication: (applicationId: string, tab?: DetailTabKey) => void;
}

export const ApplicationFollowUpView: React.FC<ApplicationFollowUpViewProps> = ({
  staleData,
  loading,
  error,
  staleDays,
  onChangeStaleDays,
  onReload,
  onOpenApplication,
}) => {
  const [busyCopyId, setBusyCopyId] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [previewTemplate, setPreviewTemplate] =
    useState<FollowUpTemplateResponse | null>(null);
  const [copyError, setCopyError] = useState<string | null>(null);

  async function handleGenerateAndCopy(applicationId: string) {
    setBusyCopyId(applicationId);
    setCopyError(null);
    try {
      const tpl = await api.applications.followUpTemplate(applicationId);
      setPreviewTemplate(tpl);
      if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(tpl.message);
      }
      setCopiedId(applicationId);
      window.setTimeout(() => {
        setCopiedId((current) => (current === applicationId ? null : current));
      }, 3000);
    } catch (err) {
      setCopyError(
        err instanceof ApiError
          ? err.message
          : "Não foi possível gerar a mensagem de acompanhamento."
      );
    } finally {
      setBusyCopyId(null);
    }
  }

  return (
    <div className="space-y-4" data-testid="applications-followup-view">
      <Card>
        <CardHeader className="pb-3">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="space-y-1">
              <CardTitle className="flex items-center gap-2 text-base">
                <MessageSquareText className="h-4 w-4 text-primary" />
                Acompanhamento de Processos Sem Interação Registrada
              </CardTitle>
              <CardDescription>
                Processos enviados ou em fase de entrevistas cujo último contato
                externo registrado ultrapassou o intervalo esperado, sem
                entrevistas futuras agendadas. Você decide manualmente se e
                quando enviar um follow-up.
              </CardDescription>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs text-muted-foreground">Critério:</span>
              {[
                { value: 7, label: "Padrão (10d envio / 7d entrevista)" },
                { value: 14, label: "14+ dias" },
                { value: 21, label: "21+ dias" },
              ].map((opt) => (
                <Button
                  key={opt.value}
                  type="button"
                  size="sm"
                  variant={staleDays === opt.value ? "default" : "outline"}
                  onClick={() => onChangeStaleDays(opt.value)}
                >
                  {opt.label}
                </Button>
              ))}
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={onReload}
                disabled={loading}
              >
                <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
                Atualizar
              </Button>
            </div>
          </div>
        </CardHeader>
      </Card>

      {(error || copyError) && (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          <span>{error || copyError}</span>
          {error && (
            <Button type="button" variant="outline" size="sm" onClick={onReload}>
              Tentar novamente
            </Button>
          )}
        </div>
      )}

      {previewTemplate && (
        <Card className="border-primary/40 bg-primary/5">
          <CardHeader className="pb-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <CardTitle className="text-sm">
                Mensagem de follow-up gerada ({previewTemplate.subject})
              </CardTitle>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={() => setPreviewTemplate(null)}
              >
                Fechar prévia
              </Button>
            </div>
            <CardDescription className="text-xs">
              {previewTemplate.context_summary} • {previewTemplate.disclaimer}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            <pre className="whitespace-pre-wrap break-words rounded-lg border border-border bg-background p-3 font-sans text-xs text-foreground">
              {previewTemplate.message}
            </pre>
          </CardContent>
        </Card>
      )}

      {loading ? (
        <Card>
          <CardContent className="flex items-center justify-center gap-2 py-12 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin text-primary" />
            Analisando histórico de interações externas registradas...
          </CardContent>
        </Card>
      ) : !staleData || staleData.items.length === 0 ? (
        <Card>
          <CardContent className="space-y-1.5 py-10 text-center">
            <p className="text-sm font-medium text-foreground">
              Nenhum processo aguardando acompanhamento no critério atual.
            </p>
            <p className="text-xs text-muted-foreground">
              Candidaturas em triagem/preparação, processos encerrados ou vagas
              com entrevista futura agendada não geram alertas aqui.
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {staleData.items.map((item) => {
            const isCopying = busyCopyId === item.application_id;
            const isCopied = copiedId === item.application_id;
            return (
              <Card key={item.application_id}>
                <CardContent className="flex flex-col gap-3 p-4 lg:flex-row lg:items-center lg:justify-between">
                  <div className="min-w-0 space-y-1.5">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant="outline">{item.status_label}</Badge>
                      <Badge variant="secondary">
                        <Clock className="mr-1 h-3 w-3" />
                        {item.days_without_external_interaction} dia(s) sem
                        interação registrada
                      </Badge>
                    </div>

                    <p className="break-words text-sm font-semibold text-foreground">
                      {item.role_title}
                    </p>
                    <p className="break-words text-xs text-muted-foreground">
                      {item.company_name || "Empresa não informada"} •{" "}
                      {item.reference_description}:{" "}
                      <strong>
                        {formatLocalDateTime(
                          item.last_external_interaction_at ||
                            item.reference_timestamp_at
                        )}
                      </strong>
                    </p>
                    <p className="break-words text-xs text-muted-foreground">
                      {item.notice} {item.recommended_follow_up}
                    </p>
                  </div>

                  <div className="flex shrink-0 flex-wrap items-center gap-2">
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      disabled={isCopying}
                      onClick={() => handleGenerateAndCopy(item.application_id)}
                    >
                      {isCopied ? (
                        <>
                          <Check className="mr-1.5 h-3.5 w-3.5 text-emerald-500" />
                          Mensagem copiada!
                        </>
                      ) : (
                        <>
                          <Copy className="mr-1.5 h-3.5 w-3.5" />
                          {isCopying ? "Gerando..." : "Copiar follow-up"}
                        </>
                      )}
                    </Button>

                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      onClick={() =>
                        onOpenApplication(item.application_id, "followup")
                      }
                    >
                      <MailCheck className="mr-1.5 h-3.5 w-3.5" />
                      Registrar interação
                    </Button>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
};

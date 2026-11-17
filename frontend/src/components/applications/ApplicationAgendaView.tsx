import React, { useMemo, useState } from "react";
import {
  AlertTriangle,
  CalendarClock,
  CalendarDays,
  ClipboardCheck,
  Clock,
  ExternalLink,
  ListChecks,
  Loader2,
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
import type { AgendaEventItem, ApplicationAgendaResponse } from "@/types/api";
import {
  formatLocalDayHeading,
  formatLocalTime,
  getLocalDayKey,
  isSameLocalToday,
} from "./dateTimeHelpers";

export type DetailTabKey =
  | "general"
  | "interviews"
  | "assessments"
  | "contacts"
  | "followup";

interface ApplicationAgendaViewProps {
  agenda: ApplicationAgendaResponse | null;
  loading: boolean;
  error: string | null;
  days: number;
  includeOverdue: boolean;
  onChangeDays: (days: number) => void;
  onToggleOverdue: (include: boolean) => void;
  onReload: () => void;
  onOpenApplication: (applicationId: string, tab?: DetailTabKey) => void;
}

const EVENT_TYPE_LABEL: Record<AgendaEventItem["event_type"], string> = {
  interview: "Entrevista",
  assessment: "Teste técnico",
  next_action: "Próxima ação",
  expected_response: "Retorno previsto",
};

function defaultTabForEvent(ev: AgendaEventItem): DetailTabKey {
  if (ev.event_type === "interview") return "interviews";
  if (ev.event_type === "assessment") return "assessments";
  return "general";
}

function eventUrgencyBadge(ev: AgendaEventItem) {
  if (ev.is_overdue) {
    return (
      <Badge variant="outline" className="border-destructive/50 text-destructive">
        Vencido
      </Badge>
    );
  }
  if (ev.is_imminent || isSameLocalToday(ev.scheduled_at)) {
    return (
      <Badge variant="warning">
        {isSameLocalToday(ev.scheduled_at) ? "Hoje" : "Próximas 24h"}
      </Badge>
    );
  }
  return <Badge variant="secondary">{ev.status_label}</Badge>;
}

export const ApplicationAgendaView: React.FC<ApplicationAgendaViewProps> = ({
  agenda,
  loading,
  error,
  days,
  includeOverdue,
  onChangeDays,
  onToggleOverdue,
  onReload,
  onOpenApplication,
}) => {
  const [desktopLayout, setDesktopLayout] = useState<"chronological" | "weekly">(
    "chronological"
  );

  const groupedByDay = useMemo(() => {
    const groups = new Map<string, AgendaEventItem[]>();
    for (const ev of agenda?.events ?? []) {
      const key = getLocalDayKey(ev.scheduled_at);
      const list = groups.get(key) ?? [];
      list.push(ev);
      groups.set(key, list);
    }
    return Array.from(groups.entries());
  }, [agenda]);

  const weeklyBuckets = useMemo(() => {
    const start = new Date();
    start.setHours(0, 0, 0, 0);
    const buckets: Array<{
      key: string;
      label: string;
      isToday: boolean;
      items: AgendaEventItem[];
    }> = [];
    const byKey = new Map(groupedByDay);
    for (let offset = 0; offset < 7; offset += 1) {
      const d = new Date(start);
      d.setDate(start.getDate() + offset);
      const key = getLocalDayKey(d.toISOString());
      const label = d.toLocaleDateString("pt-BR", {
        weekday: "short",
        day: "2-digit",
        month: "2-digit",
      });
      buckets.push({
        key,
        label,
        isToday: offset === 0,
        items: byKey.get(key) ?? [],
      });
    }
    return buckets;
  }, [groupedByDay]);

  const summary = agenda?.summary;

  return (
    <div className="space-y-4" data-testid="applications-agenda-view">
      {/* Resumo imediato da agenda */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Card>
          <CardContent className="flex flex-col gap-1 p-4">
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>Vencidos</span>
              <AlertTriangle className="h-4 w-4 text-destructive" />
            </div>
            <span className="text-2xl font-bold">{summary?.overdue_count ?? 0}</span>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="flex flex-col gap-1 p-4">
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>Próximas 24h</span>
              <Clock className="h-4 w-4 text-amber-500" />
            </div>
            <span className="text-2xl font-bold">
              {summary?.imminent_24h_count ?? 0}
            </span>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="flex flex-col gap-1 p-4">
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>Entrevistas agendadas</span>
              <CalendarClock className="h-4 w-4 text-primary" />
            </div>
            <span className="text-2xl font-bold">
              {summary?.interviews_count ?? 0}
            </span>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="flex flex-col gap-1 p-4">
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>Testes com prazo</span>
              <ClipboardCheck className="h-4 w-4 text-primary" />
            </div>
            <span className="text-2xl font-bold">
              {summary?.assessments_count ?? 0}
            </span>
          </CardContent>
        </Card>
      </div>

      {/* Controles da agenda */}
      <Card>
        <CardContent className="flex flex-wrap items-center justify-between gap-3 p-4">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs font-medium text-muted-foreground">
              Janela:
            </span>
            {[7, 15, 30, 90].map((win) => (
              <Button
                key={win}
                type="button"
                size="sm"
                variant={days === win ? "default" : "outline"}
                onClick={() => onChangeDays(win)}
              >
                {win} dias
              </Button>
            ))}

            <label className="ml-2 inline-flex cursor-pointer items-center gap-2 text-xs text-foreground">
              <input
                type="checkbox"
                checked={includeOverdue}
                onChange={(e) => onToggleOverdue(e.target.checked)}
                className="h-4 w-4 rounded border-input accent-primary"
              />
              Incluir prazos vencidos
            </label>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <div className="hidden items-center gap-1 rounded-lg border border-border p-0.5 md:inline-flex">
              <Button
                type="button"
                size="sm"
                variant={desktopLayout === "chronological" ? "default" : "ghost"}
                onClick={() => setDesktopLayout("chronological")}
              >
                <ListChecks className="mr-1.5 h-3.5 w-3.5" />
                Lista cronológica
              </Button>
              <Button
                type="button"
                size="sm"
                variant={desktopLayout === "weekly" ? "default" : "ghost"}
                onClick={() => setDesktopLayout("weekly")}
              >
                <CalendarDays className="mr-1.5 h-3.5 w-3.5" />
                Visão 7 dias
              </Button>
            </div>

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
        </CardContent>
      </Card>

      {error && (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          <span>{error}</span>
          <Button type="button" variant="outline" size="sm" onClick={onReload}>
            Tentar novamente
          </Button>
        </div>
      )}

      {loading ? (
        <Card>
          <CardContent className="flex items-center justify-center gap-2 py-12 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin text-primary" />
            Carregando agenda unificada no fuso horário local...
          </CardContent>
        </Card>
      ) : groupedByDay.length === 0 ? (
        <Card>
          <CardContent className="space-y-1.5 py-10 text-center">
            <p className="text-sm font-medium text-foreground">
              Nenhum compromisso ou prazo encontrado nesta janela.
            </p>
            <p className="text-xs text-muted-foreground">
              Agende entrevistas, cadastre testes técnicos com prazo ou defina
              próximas ações dentro de uma candidatura para vê-los aqui.
            </p>
          </CardContent>
        </Card>
      ) : (
        <>
          {/* Grade semanal no desktop quando selecionada */}
          {desktopLayout === "weekly" && (
            <div
              className="hidden gap-3 md:grid md:grid-cols-7"
              data-testid="agenda-weekly-grid"
            >
              {weeklyBuckets.map((bucket) => (
                <div
                  key={bucket.key}
                  className={`flex flex-col rounded-xl border p-2.5 ${
                    bucket.isToday
                      ? "border-primary/60 bg-primary/5"
                      : "border-border bg-card/70"
                  }`}
                >
                  <div className="mb-2 flex items-center justify-between border-b border-border pb-1.5 text-xs font-semibold">
                    <span className="capitalize">{bucket.label}</span>
                    {bucket.isToday && (
                      <Badge variant="default" className="text-[10px]">
                        Hoje
                      </Badge>
                    )}
                  </div>
                  <div className="space-y-2">
                    {bucket.items.length === 0 ? (
                      <p className="py-3 text-center text-[11px] text-muted-foreground">
                        Livre
                      </p>
                    ) : (
                      bucket.items.map((ev) => (
                        <button
                          key={ev.id}
                          type="button"
                          onClick={() =>
                            onOpenApplication(
                              ev.application_id,
                              defaultTabForEvent(ev)
                            )
                          }
                          className="w-full space-y-1 rounded-lg border border-border bg-background p-2 text-left text-[11px] transition-colors hover:border-primary/50"
                        >
                          <div className="flex items-center justify-between gap-1 font-semibold text-primary">
                            <span>{formatLocalTime(ev.scheduled_at)}</span>
                            <span>{EVENT_TYPE_LABEL[ev.event_type]}</span>
                          </div>
                          <p className="line-clamp-2 font-medium text-foreground">
                            {ev.title}
                          </p>
                          <p className="truncate text-muted-foreground">
                            {ev.company_name || ev.role_title}
                          </p>
                        </button>
                      ))
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Lista vertical cronológica agrupada por dia (sempre visível no mobile e opção padrão no desktop) */}
          <div
            className={`space-y-3 ${
              desktopLayout === "weekly" ? "md:hidden" : ""
            }`}
            data-testid="agenda-chronological-list"
          >
            {groupedByDay.map(([dayKey, items]) => (
              <Card key={dayKey}>
                <CardHeader className="pb-2.5">
                  <CardTitle className="flex flex-wrap items-center justify-between gap-2 text-sm capitalize">
                    <span>{formatLocalDayHeading(dayKey)}</span>
                    <Badge variant="outline">{items.length} evento(s)</Badge>
                  </CardTitle>
                  <CardDescription className="text-[11px]">
                    Horários convertidos para o fuso horário local do navegador
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-2.5">
                  {items.map((ev) => (
                    <div
                      key={ev.id}
                      className={`flex flex-col gap-2.5 rounded-xl border p-3 sm:flex-row sm:items-center sm:justify-between ${
                        ev.is_overdue
                          ? "border-destructive/40 bg-destructive/5"
                          : ev.is_imminent
                          ? "border-amber-500/40 bg-amber-500/5"
                          : "border-border bg-background"
                      }`}
                    >
                      <div className="min-w-0 space-y-1">
                        <div className="flex flex-wrap items-center gap-1.5">
                          <Badge variant="default">
                            {EVENT_TYPE_LABEL[ev.event_type]}
                          </Badge>
                          <span className="text-xs font-semibold text-foreground">
                            {formatLocalTime(ev.scheduled_at)}
                          </span>
                          {eventUrgencyBadge(ev)}
                          <Badge variant="outline">
                            {ev.application_status_label}
                          </Badge>
                        </div>

                        <p className="break-words text-sm font-semibold text-foreground">
                          {ev.title}
                        </p>
                        <p className="break-words text-xs text-muted-foreground">
                          {ev.role_title}
                          {ev.company_name ? ` • ${ev.company_name}` : ""}
                          {ev.subtitle ? ` • ${ev.subtitle}` : ""}
                        </p>
                      </div>

                      <div className="flex shrink-0 flex-wrap items-center gap-2">
                        {ev.action_url && (
                          <a
                            href={ev.action_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline"
                          >
                            Link
                            <ExternalLink className="h-3.5 w-3.5" />
                          </a>
                        )}
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          onClick={() =>
                            onOpenApplication(
                              ev.application_id,
                              defaultTabForEvent(ev)
                            )
                          }
                        >
                          Abrir candidatura
                        </Button>
                      </div>
                    </div>
                  ))}
                </CardContent>
              </Card>
            ))}
          </div>
        </>
      )}
    </div>
  );
};

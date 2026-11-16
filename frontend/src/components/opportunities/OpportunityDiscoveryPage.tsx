import React, { useEffect, useState } from "react";
import {
  AlertTriangle,
  Bookmark,
  BookmarkCheck,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  EyeOff,
  Filter,
  Loader2,
  MapPin,
  Plus,
  RefreshCw,
  RotateCcw,
  Search,
  ShieldAlert,
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
import { ApiError, api } from "@/lib/api";
import type {
  EmploymentType,
  ExternalSourceStatus,
  Opportunity,
  OpportunitySourcePublic,
  OpportunityType,
  OverallCompatibility,
  ProfessionalArea,
  SeniorityLevel,
  WorkMode,
} from "@/types/api";

interface OpportunityDiscoveryPageProps {
  category: "internship" | "junior" | "freelance";
  title: string;
  subtitle: string;
  refreshTrigger?: number;
  onOpenManualModal: (defaultCategory: OpportunityType) => void;
  preferencesSummary?: React.ReactNode;
}

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

const PROFESSIONAL_AREA_LABELS: Record<ProfessionalArea, string> = {
  software_development: "Desenvolvimento de Software",
  backend: "Backend",
  frontend: "Frontend",
  fullstack: "Full Stack",
  data: "Dados e Analytics",
  artificial_intelligence: "Inteligência Artificial e ML",
  devops_cloud: "DevOps, Cloud e SRE",
  api_integrations: "APIs, Integrações e Automação",
  infrastructure: "Infraestrutura de TI",
  technical_support: "Suporte Técnico e Help Desk",
  customer_support: "Atendimento e Suporte ao Cliente",
  marketing_sales: "Marketing e Vendas",
  healthcare: "Saúde",
  administration: "Administração e Operações",
  other: "Outras Áreas",
  unknown: "Área não identificada",
};

const NON_DEV_AREAS = new Set<string>([
  "technical_support",
  "customer_support",
  "marketing_sales",
  "healthcare",
  "administration",
  "other",
  "unknown",
]);

const SOURCE_STATUS_LABELS: Record<ExternalSourceStatus, string> = {
  active: "Aberta",
  expired: "Expirada",
  closed: "Encerrada",
  removed: "Publicação removida",
  source_unavailable: "Fonte temporariamente indisponível",
  unconfirmed: "Estado não confirmado",
  unknown: "Estado não confirmado",
};

const SENIORITY_LABELS: Record<SeniorityLevel, string> = {
  internship: "Estágio",
  entry_level: "Início de carreira / Entry-level",
  junior: "Júnior",
  mid_level: "Pleno",
  senior: "Sênior",
  staff_principal: "Staff / Principal",
  management: "Liderança / Gestão",
  unknown: "Senioridade não informada",
};

const OVERALL_COMPAT_LABELS: Record<OverallCompatibility, string> = {
  compatible: "Compatível",
  potential: "Potencialmente compatível",
  incompatible: "Incompatível",
};

function formatDatePtBr(iso: string | null): string {
  if (!iso) return "Data não informada";
  try {
    return new Date(iso).toLocaleDateString("pt-BR");
  } catch {
    return iso;
  }
}

function formatSalary(opp: Opportunity): string | null {
  if (opp.salary_min == null && opp.salary_max == null) return null;
  const currency = opp.salary_currency || "";
  const periodMap: Record<string, string> = {
    hour: "/hora",
    month: "/mês",
    year: "/ano",
  };
  const period = opp.salary_period ? periodMap[opp.salary_period] || "" : "";
  if (
    opp.salary_min != null &&
    opp.salary_max != null &&
    opp.salary_min !== opp.salary_max
  ) {
    return `${currency} ${opp.salary_min.toLocaleString("pt-BR")} – ${opp.salary_max.toLocaleString("pt-BR")} ${period}`.trim();
  }
  const value = opp.salary_min ?? opp.salary_max ?? 0;
  return `${currency} ${value.toLocaleString("pt-BR")} ${period}`.trim();
}

export const OpportunityDiscoveryPage: React.FC<OpportunityDiscoveryPageProps> = ({
  category,
  title,
  subtitle,
  refreshTrigger = 0,
  onOpenManualModal,
  preferencesSummary,
}) => {
  const [items, setItems] = useState<Opportunity[]>([]);
  const [sources, setSources] = useState<OpportunitySourcePublic[]>([]);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [page, setPage] = useState(1);

  const [queryText, setQueryText] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [workModeFilter, setWorkModeFilter] = useState<string>("");
  const [employmentFilter, setEmploymentFilter] = useState<string>("");
  const [areaFilter, setAreaFilter] = useState<string>("");
  const [seniorityFilter, setSeniorityFilter] = useState<string>("");
  const [compatibilityFilter, setCompatibilityFilter] = useState<string>("");
  const [countryFilter, setCountryFilter] = useState("");
  const [sourceFilter, setSourceFilter] = useState("");
  const [sortOrder, setSortOrder] = useState<"recent" | "oldest">("recent");
  const [savedOnly, setSavedOnly] = useState(false);
  const [includeDismissed, setIncludeDismissed] = useState(false);
  const [includeExcluded, setIncludeExcluded] = useState(false);

  const [loading, setLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [actionBusyId, setActionBusyId] = useState<string | null>(null);
  const [reloadNonce, setReloadNonce] = useState(0);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setDebouncedQuery(queryText);
      setPage(1);
    }, 250);
    return () => window.clearTimeout(timer);
  }, [queryText]);

  useEffect(() => {
    let active = true;
    api.opportunities
      .listSources()
      .then((res) => {
        if (active) setSources(res);
      })
      .catch(() => {
        /* Fonte é informacional; erro principal é exibido na listagem */
      });
    return () => {
      active = false;
    };
  }, [refreshTrigger]);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setErrorMessage(null);

    const effectiveIncludeExcluded =
      includeExcluded ||
      compatibilityFilter === "incompatible" ||
      (areaFilter !== "" && NON_DEV_AREAS.has(areaFilter));

    api.opportunities
      .list({
        q: debouncedQuery || undefined,
        type: category,
        seniority: (seniorityFilter as SeniorityLevel) || undefined,
        compatibility:
          (compatibilityFilter as OverallCompatibility) || undefined,
        work_mode: (workModeFilter as WorkMode) || undefined,
        employment_type: (employmentFilter as EmploymentType) || undefined,
        area: (areaFilter as ProfessionalArea) || undefined,
        country: countryFilter || undefined,
        source: sourceFilter || undefined,
        saved_only: savedOnly,
        include_dismissed: includeDismissed,
        include_excluded: effectiveIncludeExcluded,
        sort: sortOrder,
        page,
        page_size: 10,
      })
      .then((res) => {
        if (!active) return;
        setItems(res.items);
        setTotal(res.total);
        setTotalPages(Math.max(1, res.total_pages));
      })
      .catch((err) => {
        if (!active) return;
        const msg =
          err instanceof ApiError
            ? err.message
            : "Não foi possível carregar as oportunidades no momento.";
        setErrorMessage(msg);
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [
    category,
    debouncedQuery,
    seniorityFilter,
    compatibilityFilter,
    workModeFilter,
    employmentFilter,
    areaFilter,
    countryFilter,
    sourceFilter,
    savedOnly,
    includeDismissed,
    includeExcluded,
    sortOrder,
    page,
    refreshTrigger,
    reloadNonce,
  ]);

  async function handleToggleSave(opp: Opportunity) {
    setActionBusyId(opp.id);
    try {
      const nextState = await api.opportunities.updateState(opp.id, {
        is_saved: !opp.user_state.is_saved,
      });
      setItems((prev) =>
        prev.map((item) =>
          item.id === opp.id ? { ...item, user_state: nextState } : item
        )
      );
    } catch {
      setErrorMessage("Não foi possível atualizar o estado salvo da vaga.");
    } finally {
      setActionBusyId(null);
    }
  }

  async function handleToggleDismiss(opp: Opportunity) {
    setActionBusyId(opp.id);
    const nextDismissed = !opp.user_state.is_dismissed;
    try {
      const nextState = await api.opportunities.updateState(opp.id, {
        is_dismissed: nextDismissed,
      });
      if (nextDismissed && !includeDismissed) {
        setItems((prev) => prev.filter((item) => item.id !== opp.id));
        setTotal((t) => Math.max(0, t - 1));
      } else {
        setItems((prev) =>
          prev.map((item) =>
            item.id === opp.id ? { ...item, user_state: nextState } : item
          )
        );
      }
    } catch {
      setErrorMessage("Não foi possível atualizar o descarte da vaga.");
    } finally {
      setActionBusyId(null);
    }
  }

  const unsyncedSources = sources.filter(
    (s) => s.enabled && s.last_synced_at === null
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">{title}</h2>
          <p className="text-sm text-muted-foreground">{subtitle}</p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => setReloadNonce((n) => n + 1)}
            disabled={loading}
          >
            <RefreshCw className="mr-1.5 h-4 w-4" />
            Atualizar
          </Button>
          <Button
            type="button"
            size="sm"
            onClick={() => onOpenManualModal(category)}
          >
            <Plus className="mr-1.5 h-4 w-4" />
            Adicionar Oportunidade
          </Button>
        </div>
      </div>

      {preferencesSummary}

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <Filter className="h-4 w-4 text-primary" />
            Busca e Filtros Personalizados
          </CardTitle>
          <CardDescription>
            Filtragem determinística no servidor considerando elegibilidade geográfica,
            contrato e restrições configuradas no seu perfil.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-6">
            <div className="space-y-1 lg:col-span-2">
              <Label htmlFor={`search-${category}`}>Busca textual</Label>
              <div className="relative">
                <Search className="pointer-events-none absolute top-3 left-3 h-4 w-4 text-muted-foreground" />
                <Input
                  id={`search-${category}`}
                  className="pl-9"
                  value={queryText}
                  onChange={(e) => setQueryText(e.target.value)}
                  placeholder="Título, empresa, tecnologia (Python, React, SQL...)"
                />
              </div>
            </div>

            <div className="space-y-1">
              <Label htmlFor={`area-${category}`}>Área profissional</Label>
              <select
                id={`area-${category}`}
                value={areaFilter}
                onChange={(e) => {
                  setAreaFilter(e.target.value);
                  setPage(1);
                }}
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground"
              >
                <option value="">Todas as áreas</option>
                <optgroup label="Tecnologia e Desenvolvimento">
                  <option value="software_development">Desenvolvimento de Software</option>
                  <option value="backend">Backend</option>
                  <option value="frontend">Frontend</option>
                  <option value="fullstack">Full Stack</option>
                  <option value="api_integrations">APIs, Integrações e Automação</option>
                  <option value="artificial_intelligence">Inteligência Artificial e ML</option>
                  <option value="data">Dados e Analytics</option>
                  <option value="devops_cloud">DevOps, Cloud e SRE</option>
                  <option value="infrastructure">Infraestrutura de TI</option>
                </optgroup>
                <optgroup label="Outras Áreas (consultar separadamente)">
                  <option value="technical_support">Suporte Técnico e Help Desk</option>
                  <option value="customer_support">Atendimento ao Cliente</option>
                  <option value="marketing_sales">Marketing e Vendas</option>
                  <option value="healthcare">Saúde</option>
                  <option value="administration">Administração e Operações</option>
                  <option value="other">Outras Áreas</option>
                  <option value="unknown">Área não identificada</option>
                </optgroup>
              </select>
            </div>

            <div className="space-y-1">
              <Label htmlFor={`mode-${category}`}>Modalidade</Label>
              <select
                id={`mode-${category}`}
                value={workModeFilter}
                onChange={(e) => {
                  setWorkModeFilter(e.target.value);
                  setPage(1);
                }}
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground"
              >
                <option value="">Todas</option>
                <option value="remote">Remoto</option>
                <option value="hybrid">Híbrido</option>
                <option value="onsite">Presencial</option>
              </select>
            </div>

            <div className="space-y-1">
              <Label htmlFor={`contract-${category}`}>Contrato</Label>
              <select
                id={`contract-${category}`}
                value={employmentFilter}
                onChange={(e) => {
                  setEmploymentFilter(e.target.value);
                  setPage(1);
                }}
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground"
              >
                <option value="">Todos</option>
                <option value="internship">Estágio</option>
                <option value="pj">PJ</option>
                <option value="freelance">Freelance</option>
                <option value="temporary">Temporário</option>
                <option value="clt">CLT</option>
                <option value="unknown">Contrato não informado</option>
                <option value="other">Outro</option>
              </select>
            </div>

            <div className="space-y-1">
              <Label htmlFor={`source-${category}`}>Fonte</Label>
              <select
                id={`source-${category}`}
                value={sourceFilter}
                onChange={(e) => {
                  setSourceFilter(e.target.value);
                  setPage(1);
                }}
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground"
              >
                <option value="">Todas as fontes</option>
                <option value="manual">Somente Manuais / Privadas</option>
                {sources.map((src) => (
                  <option key={src.id} value={src.slug}>
                    {src.name}
                    {src.enabled ? "" : " (desabilitada)"}
                  </option>
                ))}
              </select>
            </div>

            <div className="space-y-1">
              <Label htmlFor={`seniority-${category}`}>Senioridade</Label>
              <select
                id={`seniority-${category}`}
                value={seniorityFilter}
                onChange={(e) => {
                  setSeniorityFilter(e.target.value);
                  setPage(1);
                }}
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground"
              >
                <option value="">Todas</option>
                <option value="internship">Estágio</option>
                <option value="entry_level">Início de carreira</option>
                <option value="junior">Júnior</option>
                <option value="mid_level">Pleno</option>
                <option value="senior">Sênior</option>
                <option value="staff_principal">Staff / Principal</option>
                <option value="management">Liderança / Gestão</option>
                <option value="unknown">Não informada</option>
              </select>
            </div>

            <div className="space-y-1">
              <Label htmlFor={`compatibility-${category}`}>Compatibilidade</Label>
              <select
                id={`compatibility-${category}`}
                value={compatibilityFilter}
                onChange={(e) => {
                  setCompatibilityFilter(e.target.value);
                  setPage(1);
                }}
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground"
              >
                <option value="">Elegíveis (Compatível / Potencial)</option>
                <option value="compatible">Somente Compatíveis</option>
                <option value="potential">Potencialmente Compatíveis</option>
                <option value="incompatible">Incompatíveis</option>
              </select>
            </div>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border pt-3">
            <div className="flex flex-wrap items-center gap-4 text-xs">
              <label className="inline-flex cursor-pointer items-center gap-2">
                <input
                  type="checkbox"
                  checked={savedOnly}
                  onChange={(e) => {
                    setSavedOnly(e.target.checked);
                    setPage(1);
                  }}
                />
                Somente salvas
              </label>

              <label className="inline-flex cursor-pointer items-center gap-2">
                <input
                  type="checkbox"
                  checked={includeDismissed}
                  onChange={(e) => {
                    setIncludeDismissed(e.target.checked);
                    setPage(1);
                  }}
                />
                Mostrar dispensadas
              </label>

              <label className="inline-flex cursor-pointer items-center gap-2">
                <input
                  type="checkbox"
                  checked={includeExcluded}
                  onChange={(e) => {
                    setIncludeExcluded(e.target.checked);
                    setPage(1);
                  }}
                />
                Incluir incompatíveis com perfil
              </label>
            </div>

            <div className="flex items-center gap-2">
              <Label htmlFor={`country-${category}`} className="text-xs">
                País/Região:
              </Label>
              <Input
                id={`country-${category}`}
                className="h-8 w-36 text-xs"
                value={countryFilter}
                onChange={(e) => {
                  setCountryFilter(e.target.value);
                  setPage(1);
                }}
                placeholder="Ex.: Brasil, Worldwide"
              />
              <select
                aria-label="Ordenação"
                value={sortOrder}
                onChange={(e) => {
                  setSortOrder(e.target.value as "recent" | "oldest");
                  setPage(1);
                }}
                className="h-8 rounded-md border border-input bg-background px-2 text-xs text-foreground"
              >
                <option value="recent">Mais recentes</option>
                <option value="oldest">Mais antigas</option>
              </select>
            </div>
          </div>
        </CardContent>
      </Card>

      {errorMessage && (
        <div className="flex items-center justify-between rounded-xl border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          <span>{errorMessage}</span>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => setReloadNonce((n) => n + 1)}
          >
            Tentar novamente
          </Button>
        </div>
      )}

      {loading ? (
        <Card>
          <CardContent className="flex items-center justify-center gap-2 py-12 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin text-primary" />
            Consultando oportunidades compatíveis...
          </CardContent>
        </Card>
      ) : items.length === 0 ? (
        <Card>
          <CardContent className="space-y-3 py-10 text-center">
            <p className="text-sm font-medium">
              Nenhuma oportunidade encontrada com os filtros atuais.
            </p>
            <p className="mx-auto max-w-xl text-xs text-muted-foreground">
              {unsyncedSources.length > 0
                ? "As fontes externas ainda não foram sincronizadas neste ambiente. Execute `python -m app.cli sync-opportunities` no backend ou cadastre uma vaga manualmente."
                : "Tente limpar a busca textual, ativar 'Incluir incompatíveis com perfil' ou adicionar uma vaga manualmente."}
            </p>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => onOpenManualModal(category)}
            >
              <Plus className="mr-1.5 h-4 w-4" />
              Cadastrar oportunidade manualmente
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {items.map((opp) => {
            const salaryLabel = formatSalary(opp);
            const busy = actionBusyId === opp.id;
            const outboundUrl = opp.application_url || opp.source_url;
            const overallCompat: OverallCompatibility =
              opp.match.overall_compatibility ||
              (opp.match.eligible ? "compatible" : "incompatible");

            return (
              <Card
                key={opp.id}
                className={
                  opp.user_state.is_dismissed
                    ? "border-dashed opacity-75"
                    : !opp.match.eligible
                      ? "border-destructive/40"
                      : ""
                }
              >
                <CardHeader className="pb-3">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="space-y-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <CardTitle className="text-lg">{opp.title}</CardTitle>
                        {opp.is_manual ? (
                          <Badge variant="outline">Manual / Privada</Badge>
                        ) : opp.source ? (
                          <Badge variant="secondary">{opp.source.name}</Badge>
                        ) : null}
                        <Badge variant="outline">
                          {WORK_MODE_LABELS[opp.work_mode] || opp.work_mode}
                        </Badge>
                        <Badge variant="outline">
                          {EMPLOYMENT_LABELS[opp.employment_type] ||
                            opp.employment_type}
                        </Badge>
                        {opp.seniority_level && (
                          <Badge
                            variant={
                              opp.seniority_level === "unknown"
                                ? "outline"
                                : "secondary"
                            }
                          >
                            Nível:{" "}
                            {SENIORITY_LABELS[opp.seniority_level] ||
                              opp.seniority_level}
                          </Badge>
                        )}
                        {opp.professional_area && (
                          <Badge
                            variant={
                              opp.professional_area === "unknown"
                                ? "outline"
                                : "secondary"
                            }
                          >
                            Área:{" "}
                            {PROFESSIONAL_AREA_LABELS[opp.professional_area] ||
                              "Outras Áreas"}
                          </Badge>
                        )}
                        <Badge
                          variant={
                            overallCompat === "compatible"
                              ? "success"
                              : "outline"
                          }
                          className={
                            overallCompat === "potential"
                              ? "border-amber-500/40 bg-amber-500/15 text-amber-700 dark:text-amber-300"
                              : overallCompat === "incompatible"
                                ? "border-destructive/40 bg-destructive/10 text-destructive"
                                : ""
                          }
                        >
                          {overallCompat === "compatible" && (
                            <CheckCircle2 className="mr-1 h-3 w-3" />
                          )}
                          {overallCompat === "potential" && (
                            <AlertTriangle className="mr-1 h-3 w-3" />
                          )}
                          {overallCompat === "incompatible" && (
                            <ShieldAlert className="mr-1 h-3 w-3" />
                          )}
                          {OVERALL_COMPAT_LABELS[overallCompat]}
                        </Badge>
                        {opp.experience_summary && (
                          <Badge variant="outline">
                            Experiência: {opp.experience_summary}
                          </Badge>
                        )}
                        {opp.professional_area === "unknown" && (
                          <Badge className="border-amber-500/40 bg-amber-500/15 text-amber-700 dark:text-amber-300">
                            <AlertTriangle className="mr-1 h-3 w-3" />
                            Classificação de área incerta
                          </Badge>
                        )}
                        {opp.match.geographic_eligibility === "unknown" && (
                          <Badge className="border-amber-500/40 bg-amber-500/15 text-amber-700 dark:text-amber-300">
                            <AlertTriangle className="mr-1 h-3 w-3" />
                            Elegibilidade geográfica não confirmada
                          </Badge>
                        )}
                      </div>
                      <CardDescription className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
                        <span>{opp.company_name || "Empresa não informada"}</span>
                        <span>•</span>
                        <span className="inline-flex items-center gap-1">
                          <MapPin className="h-3.5 w-3.5" />
                          {opp.location_text ||
                            (opp.eligible_countries.length > 0
                              ? opp.eligible_countries.join(", ")
                              : "Localidade não especificada")}
                        </span>
                        <span>•</span>
                        <span>Publicada: {formatDatePtBr(opp.published_at)}</span>
                        {salaryLabel && (
                          <>
                            <span>•</span>
                            <span className="font-medium text-foreground">
                              {salaryLabel}
                            </span>
                          </>
                        )}
                      </CardDescription>
                    </div>

                    <div className="flex flex-wrap items-center gap-2">
                      <Button
                        type="button"
                        size="sm"
                        variant={opp.user_state.is_saved ? "default" : "outline"}
                        disabled={busy}
                        onClick={() => handleToggleSave(opp)}
                      >
                        {opp.user_state.is_saved ? (
                          <>
                            <BookmarkCheck className="mr-1.5 h-4 w-4" />
                            Salva
                          </>
                        ) : (
                          <>
                            <Bookmark className="mr-1.5 h-4 w-4" />
                            Salvar
                          </>
                        )}
                      </Button>

                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        disabled={busy}
                        onClick={() => handleToggleDismiss(opp)}
                      >
                        {opp.user_state.is_dismissed ? (
                          <>
                            <RotateCcw className="mr-1.5 h-4 w-4" />
                            Restaurar
                          </>
                        ) : (
                          <>
                            <EyeOff className="mr-1.5 h-4 w-4" />
                            Dispensar
                          </>
                        )}
                      </Button>
                    </div>
                  </div>
                </CardHeader>

                <CardContent className="space-y-3 text-sm">
                  {opp.secondary_areas && opp.secondary_areas.length > 0 && (
                    <div className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                      <span className="font-medium text-foreground">
                        Especialidades secundárias:
                      </span>
                      {opp.secondary_areas.map((sec) => (
                        <Badge key={sec} variant="outline" className="text-xs">
                          {PROFESSIONAL_AREA_LABELS[sec] || "Outras Áreas"}
                        </Badge>
                      ))}
                    </div>
                  )}

                  {opp.description && (
                    <p className="line-clamp-3 whitespace-pre-line text-xs text-muted-foreground">
                      {opp.description}
                    </p>
                  )}

                  {opp.technologies.length > 0 && (
                    <div className="flex flex-wrap gap-1.5">
                      {opp.technologies.slice(0, 10).map((tech) => (
                        <Badge key={tech} variant="outline" className="text-xs">
                          {tech}
                        </Badge>
                      ))}
                    </div>
                  )}

                  {(opp.match.required_technologies?.length ||
                    opp.match.matched_skills?.length ||
                    opp.match.desirable_technologies?.length) ? (
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
                      {opp.match.required_technologies &&
                        opp.match.required_technologies.length > 0 && (
                          <span>
                            <strong className="text-foreground">
                              Requisitos técnicos:
                            </strong>{" "}
                            {opp.match.required_technologies.join(", ")}
                          </span>
                        )}
                      {opp.match.matched_skills &&
                        opp.match.matched_skills.length > 0 && (
                          <span className="text-emerald-700 dark:text-emerald-300">
                            <strong>No seu perfil:</strong>{" "}
                            {opp.match.matched_skills.slice(0, 6).join(", ")}
                          </span>
                        )}
                      {opp.match.desirable_technologies &&
                        opp.match.desirable_technologies.length > 0 && (
                          <span>
                            <strong className="text-foreground">
                              Diferenciais:
                            </strong>{" "}
                            {opp.match.desirable_technologies.slice(0, 4).join(", ")}
                          </span>
                        )}
                    </div>
                  ) : null}

                  {(opp.match.inclusion_reasons.length > 0 ||
                    opp.match.exclusion_reasons.length > 0 ||
                    (opp.match.uncertainty_notes &&
                      opp.match.uncertainty_notes.length > 0)) && (
                    <div className="grid gap-2 rounded-lg border border-border bg-muted/30 p-3 text-xs">
                      {opp.match.inclusion_reasons.map((reason) => (
                        <div
                          key={reason}
                          className="flex items-start gap-1.5 text-emerald-700 dark:text-emerald-300"
                        >
                          <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                          <span>{reason}</span>
                        </div>
                      ))}
                      {opp.match.uncertainty_notes?.map((note) => (
                        <div
                          key={note}
                          className="flex items-start gap-1.5 text-amber-700 dark:text-amber-300"
                        >
                          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                          <span>{note}</span>
                        </div>
                      ))}
                      {opp.match.exclusion_reasons.map((reason) => (
                        <div
                          key={reason}
                          className="flex items-start gap-1.5 text-destructive"
                        >
                          <ShieldAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                          <span>{reason}</span>
                        </div>
                      ))}
                    </div>
                  )}

                  {opp.status_uncertainty_note && (
                    <div className="flex items-start gap-1.5 rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-800 dark:text-amber-300">
                      <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                      <span>{opp.status_uncertainty_note}</span>
                    </div>
                  )}

                  <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border pt-3 text-xs">
                    <div className="space-y-1 text-muted-foreground">
                      {opp.source ? (
                        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                          <span>
                            Origem:{" "}
                            <a
                              href={opp.source_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="font-medium text-primary underline-offset-2 hover:underline"
                            >
                              {opp.source.name}
                            </a>
                          </span>
                          <span>•</span>
                          <span>
                            Status:{" "}
                            <strong className="font-medium text-foreground">
                              {SOURCE_STATUS_LABELS[opp.source_status] ||
                                opp.source_status}
                            </strong>
                          </span>
                          <span>•</span>
                          <span>
                            Verificada:{" "}
                            {formatDatePtBr(
                              opp.last_status_check_at || opp.last_seen_at
                            )}
                          </span>
                        </div>
                      ) : (
                        <span>Registro privado adicionado manualmente</span>
                      )}

                      {opp.source_links &&
                        opp.source_links.filter((l) => !l.is_primary).length >
                          0 && (
                          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px]">
                            <span className="font-medium text-foreground">
                              Também publicada em:
                            </span>
                            {opp.source_links
                              .filter((l) => !l.is_primary)
                              .map((link) => (
                                <a
                                  key={link.id}
                                  href={link.source_url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="text-primary underline-offset-2 hover:underline"
                                >
                                  {link.source_name}
                                  {link.location_text
                                    ? ` (${link.location_text})`
                                    : ""}
                                </a>
                              ))}
                          </div>
                        )}
                    </div>

                    <div className="flex flex-wrap items-center gap-3">
                      {opp.application_url &&
                        opp.application_url !== opp.source_url && (
                          <a
                            href={opp.source_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1 text-muted-foreground hover:text-foreground hover:underline"
                          >
                            Publicação na fonte
                            <ExternalLink className="h-3 w-3" />
                          </a>
                        )}
                      <a
                        href={outboundUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1.5 font-medium text-primary hover:underline"
                      >
                        Ver oportunidade original
                        <ExternalLink className="h-3.5 w-3.5" />
                      </a>
                    </div>
                  </div>
                </CardContent>
              </Card>
            );
          })}

          <div className="flex flex-wrap items-center justify-between gap-3 pt-2 text-xs text-muted-foreground">
            <span>
              Página {page} de {totalPages} • {total} oportunidade(s)
            </span>
            <div className="flex items-center gap-2">
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
              >
                <ChevronLeft className="mr-1 h-4 w-4" />
                Anterior
              </Button>
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={page >= totalPages}
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              >
                Próxima
                <ChevronRight className="ml-1 h-4 w-4" />
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

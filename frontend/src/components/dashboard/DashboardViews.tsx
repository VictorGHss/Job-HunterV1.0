import {
  AlertTriangle,
  ArrowRight,
  Ban,
  Briefcase,
  CheckCircle2,
  Clock,
  Code2,
  FileCheck2,
  FolderGit2,
  Globe2,
  GraduationCap,
  Languages,
  MapPin,
  ShieldAlert,
  Wrench,
} from "lucide-react";
import { Badge, VerificationBadge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { NavSection } from "@/components/layout/AppShell";
import type { FullProfileBundle } from "@/types/api";

interface DashboardProps {
  bundle: FullProfileBundle;
  onNavigate: (section: NavSection) => void;
}

export function HomeDashboardView({
  bundle,
  onNavigate,
}: DashboardProps) {
  const {
    profile,
    experiences,
    educations,
    skills,
    languages,
    projects,
    validation_summary,
  } = bundle;

  return (
    <div className="space-y-6">
      {/* Hero / Status Principal */}
      <Card className="border-primary/30 bg-gradient-to-br from-card via-card to-primary/5">
        <CardHeader className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div className="space-y-1.5">
            <div className="flex flex-wrap items-center gap-2">
              <VerificationBadge status={profile.verification_status} />
              {profile.city && (
                <Badge variant="outline">
                  <MapPin className="h-3 w-3" />
                  {profile.city}
                  {profile.state ? `, ${profile.state}` : ""} •{" "}
                  {profile.country || "Brasil"}
                </Badge>
              )}
            </div>
            <CardTitle className="text-xl sm:text-2xl">
              {profile.full_name || "Perfil Profissional Central"}
            </CardTitle>
            <CardDescription className="text-sm max-w-2xl">
              {profile.professional_title ||
                "Defina seu título e valide suas experiências para alimentar futuras análises e candidaturas."}
            </CardDescription>
          </div>

          <div className="flex flex-wrap items-center gap-2.5">
            <Button onClick={() => onNavigate("perfil")}>
              Gerenciar Perfil Completo
              <ArrowRight className="h-4 w-4" />
            </Button>
          </div>
        </CardHeader>

        <CardContent className="space-y-4">
          {profile.professional_summary && (
            <p className="text-sm text-muted-foreground leading-relaxed border-t border-border/60 pt-3">
              {profile.professional_summary}
            </p>
          )}

          {/* Barra de Governança de Fatos Confirmados */}
          <div className="rounded-lg border border-border bg-muted/40 p-3.5 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="flex items-start sm:items-center gap-2.5 text-xs sm:text-sm">
              {validation_summary.confirmed_count > 0 ? (
                <CheckCircle2 className="h-5 w-5 text-emerald-500 shrink-0" />
              ) : (
                <Clock className="h-5 w-5 text-amber-500 shrink-0" />
              )}
              <div>
                <span className="font-semibold text-foreground">
                  Validação de Fatos do Perfil:{" "}
                </span>
                <span className="text-muted-foreground">
                  <strong>{validation_summary.confirmed_count}</strong> de{" "}
                  <strong>{validation_summary.total_items}</strong> registros
                  confirmados pelo usuário (
                  {validation_summary.pending_or_draft_count} em rascunho ou
                  pendentes de revisão).
                </span>
              </div>
            </div>
            <Badge
              variant={
                validation_summary.ready_for_future_applications
                  ? "success"
                  : "warning"
              }
            >
              {validation_summary.ready_for_future_applications
                ? "Base Confirmada Ativa"
                : "Revisão Pendente"}
            </Badge>
          </div>
        </CardContent>
      </Card>

      {/* Contadores Reais do Perfil */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3.5">
        <Card
          className="cursor-pointer hover:border-primary/50 transition-colors"
          onClick={() => onNavigate("perfil")}
        >
          <CardContent className="p-4 flex flex-col gap-1">
            <div className="flex items-center justify-between text-muted-foreground">
              <span className="text-xs font-medium">Experiências</span>
              <Briefcase className="h-4 w-4 text-primary" />
            </div>
            <span className="text-2xl font-bold">{experiences.length}</span>
            <span className="text-[11px] text-muted-foreground">
              {
                experiences.filter((e) => e.verification_status === "confirmed")
                  .length
              }{" "}
              confirmada(s)
            </span>
          </CardContent>
        </Card>

        <Card
          className="cursor-pointer hover:border-primary/50 transition-colors"
          onClick={() => onNavigate("perfil")}
        >
          <CardContent className="p-4 flex flex-col gap-1">
            <div className="flex items-center justify-between text-muted-foreground">
              <span className="text-xs font-medium">Formação</span>
              <GraduationCap className="h-4 w-4 text-primary" />
            </div>
            <span className="text-2xl font-bold">{educations.length}</span>
            <span className="text-[11px] text-muted-foreground">
              {
                educations.filter((e) => e.verification_status === "confirmed")
                  .length
              }{" "}
              confirmada(s)
            </span>
          </CardContent>
        </Card>

        <Card
          className="cursor-pointer hover:border-primary/50 transition-colors"
          onClick={() => onNavigate("perfil")}
        >
          <CardContent className="p-4 flex flex-col gap-1">
            <div className="flex items-center justify-between text-muted-foreground">
              <span className="text-xs font-medium">Habilidades</span>
              <Wrench className="h-4 w-4 text-primary" />
            </div>
            <span className="text-2xl font-bold">{skills.length}</span>
            <span className="text-[11px] text-muted-foreground">
              {
                skills.filter((s) => s.verification_status === "confirmed")
                  .length
              }{" "}
              confirmada(s)
            </span>
          </CardContent>
        </Card>

        <Card
          className="cursor-pointer hover:border-primary/50 transition-colors"
          onClick={() => onNavigate("perfil")}
        >
          <CardContent className="p-4 flex flex-col gap-1">
            <div className="flex items-center justify-between text-muted-foreground">
              <span className="text-xs font-medium">Idiomas</span>
              <Languages className="h-4 w-4 text-primary" />
            </div>
            <span className="text-2xl font-bold">{languages.length}</span>
            <span className="text-[11px] text-muted-foreground">
              {
                languages.filter((l) => l.verification_status === "confirmed")
                  .length
              }{" "}
              confirmado(s)
            </span>
          </CardContent>
        </Card>

        <Card
          className="col-span-2 sm:col-span-1 cursor-pointer hover:border-primary/50 transition-colors"
          onClick={() => onNavigate("perfil")}
        >
          <CardContent className="p-4 flex flex-col gap-1">
            <div className="flex items-center justify-between text-muted-foreground">
              <span className="text-xs font-medium">Projetos</span>
              <FolderGit2 className="h-4 w-4 text-primary" />
            </div>
            <span className="text-2xl font-bold">{projects.length}</span>
            <span className="text-[11px] text-muted-foreground">
              {
                projects.filter((p) => p.verification_status === "confirmed")
                  .length
              }{" "}
              confirmado(s)
            </span>
          </CardContent>
        </Card>
      </div>

      {/* Visão das Três Frentes Configuradas */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card className="flex flex-col justify-between">
          <CardHeader>
            <div className="flex items-center justify-between">
              <Badge variant="default">Frente 01</Badge>
              <GraduationCap className="h-4 w-4 text-primary" />
            </div>
            <CardTitle className="text-base pt-1">
              Estágios em Tecnologia
            </CardTitle>
            <CardDescription>
              {profile.preferences.internships.priority_areas.length} áreas
              prioritárias configuradas
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex flex-wrap gap-1.5">
              {profile.preferences.internships.priority_areas
                .slice(0, 4)
                .map((area) => (
                  <Badge key={area} variant="secondary">
                    {area}
                  </Badge>
                ))}
            </div>
            <p className="text-xs text-muted-foreground">
              Excluídos:{" "}
              {profile.preferences.internships.excluded_areas.join(", ")}
            </p>
            <Button
              variant="outline"
              size="sm"
              className="w-full"
              onClick={() => onNavigate("estagios")}
            >
              Ver Diretrizes de Estágio
            </Button>
          </CardContent>
        </Card>

        <Card className="flex flex-col justify-between">
          <CardHeader>
            <div className="flex items-center justify-between">
              <Badge variant="default">Frente 02</Badge>
              <Code2 className="h-4 w-4 text-primary" />
            </div>
            <CardTitle className="text-base pt-1">
              Desenvolvedor Júnior
            </CardTitle>
            <CardDescription>
              Posições técnicas de entrada com filtro contratual
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex items-center gap-2">
              {profile.preferences.junior_developer.block_clt ? (
                <Badge variant="warning">
                  <Ban className="h-3 w-3" />
                  Vagas CLT Bloqueadas
                </Badge>
              ) : (
                <Badge variant="success">CLT Permitido</Badge>
              )}
            </div>
            <p className="text-xs text-muted-foreground">
              Modalidades aceitas:{" "}
              {profile.preferences.junior_developer.accepted_contract_types.join(
                ", "
              )}
            </p>
            <Button
              variant="outline"
              size="sm"
              className="w-full"
              onClick={() => onNavigate("junior")}
            >
              Ver Diretrizes Dev Júnior
            </Button>
          </CardContent>
        </Card>

        <Card className="flex flex-col justify-between">
          <CardHeader>
            <div className="flex items-center justify-between">
              <Badge variant="default">Frente 03</Badge>
              <Globe2 className="h-4 w-4 text-primary" />
            </div>
            <CardTitle className="text-base pt-1">
              Projetos Freelance
            </CardTitle>
            <CardDescription>
              Escopo: {profile.preferences.freelance.scopes.join(" & ")}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex flex-wrap gap-1.5">
              {profile.preferences.freelance.priority_categories
                .slice(0, 4)
                .map((cat) => (
                  <Badge key={cat} variant="secondary">
                    {cat}
                  </Badge>
                ))}
            </div>
            <p className="text-xs text-muted-foreground">
              Workana:{" "}
              {profile.preferences.source_restrictions.workana_enabled
                ? "Habilitada"
                : "Desabilitada (sem investimento inicial)"}
            </p>
            <Button
              variant="outline"
              size="sm"
              className="w-full"
              onClick={() => onNavigate("freelancers")}
            >
              Ver Diretrizes Freelance
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

export function InternshipsSectionView({
  bundle,
  onNavigate,
}: {
  bundle: FullProfileBundle;
  onNavigate: (section: NavSection) => void;
}) {
  const prefs = bundle.profile.preferences.internships;
  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2 text-primary text-xs font-semibold">
            <GraduationCap className="h-4 w-4" />
            Diretrizes Configuradas no Perfil
          </div>
          <CardTitle>Estágios na Área de Tecnologia</CardTitle>
          <CardDescription>
            Configuração ativa do seu perfil para filtragem e ranqueamento nas
            próximas fases de coleta. Nenhum dado fictício é exibido.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="space-y-2">
            <h4 className="text-sm font-semibold">Áreas Prioritárias</h4>
            <div className="flex flex-wrap gap-2">
              {prefs.priority_areas.map((area) => (
                <Badge key={area} variant="default">
                  {area}
                </Badge>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="rounded-lg border border-border p-4 space-y-2">
              <h4 className="text-sm font-semibold">Idiomas Preferenciais</h4>
              <div className="flex flex-wrap gap-1.5">
                {prefs.preferred_languages.map((lang) => (
                  <Badge key={lang} variant="secondary">
                    {lang}
                  </Badge>
                ))}
              </div>
            </div>

            <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 space-y-2">
              <h4 className="text-sm font-semibold flex items-center gap-1.5 text-destructive">
                <Ban className="h-4 w-4" />
                Áreas Explicitamente Excluídas
              </h4>
              <div className="flex flex-wrap gap-1.5">
                {prefs.excluded_areas.map((ex) => (
                  <Badge key={ex} variant="outline">
                    {ex}
                  </Badge>
                ))}
              </div>
              <p className="text-xs text-muted-foreground">
                Experiências mantidas apenas como histórico (não elegíveis como
                cargo-alvo) permanecem no currículo como base profissional, mas
                não tornam áreas excluídas elegíveis.
              </p>
            </div>
          </div>

          <div className="flex justify-end">
            <Button variant="outline" onClick={() => onNavigate("perfil")}>
              Editar Preferências no Perfil
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

export function JuniorDeveloperSectionView({
  bundle,
  onNavigate,
}: {
  bundle: FullProfileBundle;
  onNavigate: (section: NavSection) => void;
}) {
  const prefs = bundle.profile.preferences.junior_developer;
  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2 text-primary text-xs font-semibold">
            <Code2 className="h-4 w-4" />
            Diretrizes Configuradas no Perfil
          </div>
          <CardTitle>Desenvolvedor Júnior & Posições de Entrada</CardTitle>
          <CardDescription>
            Regras de elegibilidade técnica e modalidades de contratação aceitas
            pelo usuário.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-4 flex items-start gap-3">
            <AlertTriangle className="h-5 w-5 text-amber-500 shrink-0 mt-0.5" />
            <div className="space-y-1 text-sm">
              <p className="font-semibold">
                Status do Bloqueio CLT:{" "}
                {prefs.block_clt
                  ? "ATIVO (Oportunidades exclusivamente CLT serão bloqueadas)"
                  : "DESATIVADO (Oportunidades CLT permitidas)"}
              </p>
              <p className="text-xs text-muted-foreground">
                Esta preferência pode ser alterada a qualquer momento na aba
                Preferências do seu Perfil Profissional.
              </p>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="rounded-lg border border-border p-4 space-y-2">
              <h4 className="text-sm font-semibold">
                Modalidades de Contratação Compatíveis
              </h4>
              <div className="flex flex-wrap gap-1.5">
                {prefs.accepted_contract_types.map((c) => (
                  <Badge key={c} variant="success">
                    {c}
                  </Badge>
                ))}
              </div>
            </div>

            <div className="rounded-lg border border-border p-4 space-y-2">
              <h4 className="text-sm font-semibold">Áreas Técnicas Alvo</h4>
              <div className="flex flex-wrap gap-1.5">
                {prefs.priority_areas.map((area) => (
                  <Badge key={area} variant="secondary">
                    {area}
                  </Badge>
                ))}
              </div>
            </div>
          </div>

          <div className="flex justify-end">
            <Button variant="outline" onClick={() => onNavigate("perfil")}>
              Configurar Modalidades no Perfil
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

export function FreelancersSectionView({
  bundle,
  onNavigate,
}: {
  bundle: FullProfileBundle;
  onNavigate: (section: NavSection) => void;
}) {
  const freelance = bundle.profile.preferences.freelance;
  const restrictions = bundle.profile.preferences.source_restrictions;
  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2 text-primary text-xs font-semibold">
            <Globe2 className="h-4 w-4" />
            Diretrizes Configuradas no Perfil
          </div>
          <CardTitle>Projetos Freelance (Brasil & Exterior)</CardTitle>
          <CardDescription>
            Escopo de atuação sob demanda e políticas de fontes configuradas.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="space-y-2">
            <h4 className="text-sm font-semibold">Categorias Prioritárias</h4>
            <div className="flex flex-wrap gap-2">
              {freelance.priority_categories.map((cat) => (
                <Badge key={cat} variant="default">
                  {cat}
                </Badge>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="rounded-lg border border-border p-4 space-y-2">
              <h4 className="text-sm font-semibold">Escopo & Idiomas</h4>
              <p className="text-xs text-muted-foreground">
                Mercados: <strong>{freelance.scopes.join(", ")}</strong>
              </p>
              <p className="text-xs text-muted-foreground">
                Idiomas:{" "}
                <strong>{freelance.preferred_languages.join(", ")}</strong>
              </p>
            </div>

            <div className="rounded-lg border border-border p-4 space-y-2">
              <h4 className="text-sm font-semibold">Restrições de Fontes</h4>
              <ul className="text-xs text-muted-foreground space-y-1">
                <li>
                  • <strong>Workana:</strong>{" "}
                  {restrictions.workana_enabled
                    ? "Habilitada"
                    : `Desabilitada (${restrictions.workana_disabled_reason})`}
                </li>
                <li>
                  • <strong>Gupy:</strong> Modo seletivo (alta compatibilidade)
                </li>
                <li>
                  • <strong>Planos pagos / taxas:</strong> Bloqueados sem
                  autorização explícita
                </li>
              </ul>
            </div>
          </div>

          <div className="flex justify-end">
            <Button variant="outline" onClick={() => onNavigate("perfil")}>
              Ajustar Preferências Freelance
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

export function ApplicationsSectionView({
  bundle,
  onNavigate,
}: {
  bundle: FullProfileBundle;
  onNavigate: (section: NavSection) => void;
}) {
  const { validation_summary } = bundle;
  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2 text-primary text-xs font-semibold">
            <FileCheck2 className="h-4 w-4" />
            Governança & Preparação de Candidaturas
          </div>
          <CardTitle>Central de Candidaturas Supervisionadas</CardTitle>
          <CardDescription>
            Na Fase 01 estabelecemos a fonte única de verdade do seu perfil
            profissional. A geração de currículos e propostas será conectada nas
            próximas fases respeitando estritamente os fatos confirmados.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="rounded-lg border border-primary/30 bg-primary/5 p-4 space-y-2">
            <div className="flex items-center gap-2 font-semibold text-sm">
              <ShieldAlert className="h-4 w-4 text-primary" />
              Salvaguardas Invioláveis do Job Hunter
            </div>
            <ul className="text-xs text-muted-foreground space-y-1.5">
              <li>
                1. A IA <strong>nunca</strong> inventará experiências,
                tecnologias, resultados, competências, cursos ou qualificações.
              </li>
              <li>
                2. Somente registros com status{" "}
                <strong>Confirmado pelo usuário</strong> poderão ser utilizados
                como fatos em currículos e propostas.
              </li>
              <li>
                3. Nenhum teste seletivo será executado automaticamente e
                nenhuma candidatura será enviada sem aprovação humana explícita.
              </li>
            </ul>
          </div>

          <div className="rounded-lg border border-border p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div className="space-y-1">
              <p className="text-sm font-semibold">
                Status atual do seu dossiê profissional
              </p>
              <p className="text-xs text-muted-foreground">
                {validation_summary.confirmed_count} item(ns) confirmado(s) e{" "}
                {validation_summary.pending_or_draft_count} item(ns) aguardando
                revisão/confirmação.
              </p>
            </div>
            <Button onClick={() => onNavigate("perfil")}>
              Revisar e Confirmar Dados do Perfil
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

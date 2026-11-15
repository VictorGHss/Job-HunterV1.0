import React, { useEffect, useState } from "react";
import {
  Briefcase,
  CheckCircle2,
  Edit3,
  FolderGit2,
  GraduationCap,
  Languages,
  Plus,
  Save,
  Sliders,
  Trash2,
  UserCheck,
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
import { Input, Label, Textarea } from "@/components/ui/input";
import { api } from "@/lib/api";
import { cn, joinCommaSeparated, splitCommaSeparated } from "@/lib/utils";
import type {
  Education,
  EducationPayload,
  EducationStatus,
  ExperienceType,
  FullProfileBundle,
  Language,
  LanguagePayload,
  LanguageProficiency,
  ProfessionalProject,
  ProfessionalProjectPayload,
  Skill,
  SkillPayload,
  SkillProficiency,
  VerificationStatus,
  WorkExperience,
  WorkExperiencePayload,
} from "@/types/api";

type ProfileSubTab =
  | "dados"
  | "experiencias"
  | "formacao"
  | "habilidades"
  | "idiomas"
  | "projetos"
  | "preferencias";

const SUB_TABS: {
  id: ProfileSubTab;
  label: string;
  icon: typeof UserCheck;
}[] = [
  { id: "dados", label: "Dados & Resumo", icon: UserCheck },
  { id: "experiencias", label: "Experiências", icon: Briefcase },
  { id: "formacao", label: "Formação", icon: GraduationCap },
  { id: "habilidades", label: "Habilidades", icon: Wrench },
  { id: "idiomas", label: "Idiomas", icon: Languages },
  { id: "projetos", label: "Projetos", icon: FolderGit2 },
  { id: "preferencias", label: "Preferências", icon: Sliders },
];

const VERIFICATION_LABELS: Record<VerificationStatus, string> = {
  draft: "Rascunho (Não usar em candidaturas)",
  pending_validation: "Pendente de validação pelo usuário",
  confirmed: "Confirmado pelo usuário (Apto para uso)",
};

const EXPERIENCE_TYPE_LABELS: Record<ExperienceType, string> = {
  internship: "Estágio",
  junior: "Júnior",
  freelance: "Freelance",
  pj: "PJ / Prestação de Serviços",
  clt: "CLT",
  academic: "Acadêmica / Pesquisa",
  other: "Outro",
};

const EDUCATION_STATUS_LABELS: Record<EducationStatus, string> = {
  in_progress: "Em andamento",
  completed: "Concluído",
  paused: "Trancado / Pausado",
  planned: "Planejado",
};

const SKILL_LEVEL_LABELS: Record<SkillProficiency, string> = {
  beginner: "Iniciante",
  basic: "Básico",
  intermediate: "Intermediário",
  advanced: "Avançado",
  expert: "Especialista",
};

const LANGUAGE_LEVEL_LABELS: Record<LanguageProficiency, string> = {
  basic: "Básico",
  intermediate: "Intermediário",
  advanced: "Avançado",
  fluent: "Fluente",
  native: "Nativo",
};

interface ProfilePageProps {
  bundle: FullProfileBundle;
  onRefresh: () => Promise<void>;
}

export function ProfilePage({ bundle, onRefresh }: ProfilePageProps) {
  const [subTab, setSubTab] = useState<ProfileSubTab>("dados");
  const [feedback, setFeedback] = useState<{
    type: "success" | "error";
    text: string;
  } | null>(null);
  const [busy, setBusy] = useState(false);

  const showSuccess = (text: string) => {
    setFeedback({ type: "success", text });
  };

  const showError = (err: unknown) => {
    setFeedback({
      type: "error",
      text:
        err instanceof Error
          ? err.message
          : "Não foi possível salvar as alterações.",
    });
  };

  // --- Estado: Dados Gerais do Perfil ---
  const [profileForm, setProfileForm] = useState({
    full_name: bundle.profile.full_name || "",
    professional_email: bundle.profile.professional_email || "",
    phone: bundle.profile.phone || "",
    city: bundle.profile.city || "",
    state: bundle.profile.state || "",
    country: bundle.profile.country || "",
    professional_title: bundle.profile.professional_title || "",
    professional_summary: bundle.profile.professional_summary || "",
    linkedin_url: bundle.profile.linkedin_url || "",
    github_url: bundle.profile.github_url || "",
    portfolio_url: bundle.profile.portfolio_url || "",
    verification_status: bundle.profile.verification_status,
  });

  // --- Estado: Preferências ---
  const [prefsForm, setPrefsForm] = useState({
    internshipAreas: joinCommaSeparated(
      bundle.profile.preferences.internships.priority_areas
    ),
    internshipLangs: joinCommaSeparated(
      bundle.profile.preferences.internships.preferred_languages
    ),
    internshipExcluded: joinCommaSeparated(
      bundle.profile.preferences.internships.excluded_areas
    ),
    juniorBlockClt: bundle.profile.preferences.junior_developer.block_clt,
    juniorContracts: joinCommaSeparated(
      bundle.profile.preferences.junior_developer.accepted_contract_types
    ),
    juniorAreas: joinCommaSeparated(
      bundle.profile.preferences.junior_developer.priority_areas
    ),
    freelanceScopes: joinCommaSeparated(
      bundle.profile.preferences.freelance.scopes
    ),
    freelanceCategories: joinCommaSeparated(
      bundle.profile.preferences.freelance.priority_categories
    ),
    freelanceLangs: joinCommaSeparated(
      bundle.profile.preferences.freelance.preferred_languages
    ),
    workanaEnabled:
      bundle.profile.preferences.source_restrictions.workana_enabled,
    gupyMode: bundle.profile.preferences.source_restrictions.gupy_mode,
  });

  useEffect(() => {
    setProfileForm({
      full_name: bundle.profile.full_name || "",
      professional_email: bundle.profile.professional_email || "",
      phone: bundle.profile.phone || "",
      city: bundle.profile.city || "",
      state: bundle.profile.state || "",
      country: bundle.profile.country || "",
      professional_title: bundle.profile.professional_title || "",
      professional_summary: bundle.profile.professional_summary || "",
      linkedin_url: bundle.profile.linkedin_url || "",
      github_url: bundle.profile.github_url || "",
      portfolio_url: bundle.profile.portfolio_url || "",
      verification_status: bundle.profile.verification_status,
    });
    setPrefsForm({
      internshipAreas: joinCommaSeparated(
        bundle.profile.preferences.internships.priority_areas
      ),
      internshipLangs: joinCommaSeparated(
        bundle.profile.preferences.internships.preferred_languages
      ),
      internshipExcluded: joinCommaSeparated(
        bundle.profile.preferences.internships.excluded_areas
      ),
      juniorBlockClt: bundle.profile.preferences.junior_developer.block_clt,
      juniorContracts: joinCommaSeparated(
        bundle.profile.preferences.junior_developer.accepted_contract_types
      ),
      juniorAreas: joinCommaSeparated(
        bundle.profile.preferences.junior_developer.priority_areas
      ),
      freelanceScopes: joinCommaSeparated(
        bundle.profile.preferences.freelance.scopes
      ),
      freelanceCategories: joinCommaSeparated(
        bundle.profile.preferences.freelance.priority_categories
      ),
      freelanceLangs: joinCommaSeparated(
        bundle.profile.preferences.freelance.preferred_languages
      ),
      workanaEnabled:
        bundle.profile.preferences.source_restrictions.workana_enabled,
      gupyMode: bundle.profile.preferences.source_restrictions.gupy_mode,
    });
  }, [bundle]);

  const handleSaveGeneralProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setFeedback(null);
    try {
      await api.profile.updateProfile({
        full_name: profileForm.full_name || null,
        professional_email: profileForm.professional_email || null,
        phone: profileForm.phone || null,
        city: profileForm.city || null,
        state: profileForm.state || null,
        country: profileForm.country || null,
        professional_title: profileForm.professional_title || null,
        professional_summary: profileForm.professional_summary || null,
        linkedin_url: profileForm.linkedin_url || null,
        github_url: profileForm.github_url || null,
        portfolio_url: profileForm.portfolio_url || null,
        verification_status: profileForm.verification_status,
      });
      await onRefresh();
      showSuccess("Dados gerais do perfil atualizados com sucesso.");
    } catch (err) {
      showError(err);
    } finally {
      setBusy(false);
    }
  };

  const handleSavePreferences = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setFeedback(null);
    try {
      await api.profile.updateProfile({
        preferences: {
          internships: {
            enabled: true,
            priority_areas: splitCommaSeparated(prefsForm.internshipAreas),
            preferred_languages: splitCommaSeparated(prefsForm.internshipLangs),
            excluded_areas: splitCommaSeparated(prefsForm.internshipExcluded),
          },
          junior_developer: {
            enabled: true,
            priority_areas: splitCommaSeparated(prefsForm.juniorAreas),
            block_clt: prefsForm.juniorBlockClt,
            accepted_contract_types: splitCommaSeparated(
              prefsForm.juniorContracts
            ),
            excluded_areas: splitCommaSeparated(prefsForm.internshipExcluded),
          },
          freelance: {
            enabled: true,
            scopes: splitCommaSeparated(prefsForm.freelanceScopes),
            priority_categories: splitCommaSeparated(
              prefsForm.freelanceCategories
            ),
            preferred_languages: splitCommaSeparated(prefsForm.freelanceLangs),
          },
          source_restrictions: {
            workana_enabled: prefsForm.workanaEnabled,
            workana_disabled_reason:
              bundle.profile.preferences.source_restrictions
                .workana_disabled_reason,
            gupy_mode: prefsForm.gupyMode,
            auto_execute_tests: false,
            pay_premium_or_fees_without_approval: false,
            strict_platform_terms_compliance: true,
          },
        },
      });
      await onRefresh();
      showSuccess("Preferências de oportunidades e restrições salvas.");
    } catch (err) {
      showError(err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Cabeçalho do Perfil */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">
            Perfil Profissional Central
          </h1>
          <p className="text-sm text-muted-foreground">
            Fonte única de verdade do seu histórico. Marque como{" "}
            <strong className="text-foreground">Confirmado</strong> somente o
            que já foi revisado por você.
          </p>
        </div>
      </div>

      {/* Feedback Banner */}
      {feedback && (
        <div
          role="status"
          className={cn(
            "rounded-xl border px-4 py-3 text-sm flex items-center justify-between",
            feedback.type === "success"
              ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
              : "border-destructive/40 bg-destructive/10 text-destructive"
          )}
        >
          <span>{feedback.text}</span>
          <button
            type="button"
            onClick={() => setFeedback(null)}
            className="text-xs underline ml-4"
          >
            Fechar
          </button>
        </div>
      )}

      {/* Sub-navegação do Perfil */}
      <div
        role="tablist"
        aria-label="Seções do perfil profissional"
        className="flex items-center gap-1.5 overflow-x-auto pb-1 border-b border-border"
      >
        {SUB_TABS.map((tab) => {
          const Icon = tab.icon;
          const active = subTab === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              role="tab"
              aria-selected={active}
              onClick={() => {
                setFeedback(null);
                setSubTab(tab.id);
              }}
              className={cn(
                "inline-flex items-center gap-2 rounded-lg px-3.5 py-2 text-xs sm:text-sm font-medium whitespace-nowrap transition-colors",
                active
                  ? "bg-primary text-primary-foreground shadow-sm"
                  : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
              )}
            >
              <Icon className="h-4 w-4" />
              <span>{tab.label}</span>
            </button>
          );
        })}
      </div>

      {/* Aba 1: Dados Gerais & Resumo */}
      {subTab === "dados" && (
        <Card>
          <CardHeader className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
            <div>
              <CardTitle>Identificação, Contato & Resumo</CardTitle>
              <CardDescription>
                Campos pessoais são opcionais enquanto o perfil estiver em
                rascunho.
              </CardDescription>
            </div>
            <VerificationBadge status={bundle.profile.verification_status} />
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSaveGeneralProfile} className="space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <Label htmlFor="prof-fullname">Nome completo</Label>
                  <Input
                    id="prof-fullname"
                    value={profileForm.full_name}
                    onChange={(e) =>
                      setProfileForm({
                        ...profileForm,
                        full_name: e.target.value,
                      })
                    }
                    placeholder="Seu nome completo"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="prof-email">E-mail profissional</Label>
                  <Input
                    id="prof-email"
                    type="email"
                    value={profileForm.professional_email}
                    onChange={(e) =>
                      setProfileForm({
                        ...profileForm,
                        professional_email: e.target.value,
                      })
                    }
                    placeholder="contato@dominio.com"
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
                <div className="space-y-1.5">
                  <Label htmlFor="prof-phone">Telefone (opcional)</Label>
                  <Input
                    id="prof-phone"
                    value={profileForm.phone}
                    onChange={(e) =>
                      setProfileForm({ ...profileForm, phone: e.target.value })
                    }
                    placeholder="(42) 99999-9999"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="prof-city">Localidade / Cidade</Label>
                  <Input
                    id="prof-city"
                    value={profileForm.city}
                    onChange={(e) =>
                      setProfileForm({ ...profileForm, city: e.target.value })
                    }
                    placeholder="Sua cidade"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="prof-state">Estado</Label>
                  <Input
                    id="prof-state"
                    value={profileForm.state}
                    onChange={(e) =>
                      setProfileForm({ ...profileForm, state: e.target.value })
                    }
                    placeholder="Seu estado / UF"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="prof-country">País</Label>
                  <Input
                    id="prof-country"
                    value={profileForm.country}
                    onChange={(e) =>
                      setProfileForm({
                        ...profileForm,
                        country: e.target.value,
                      })
                    }
                    placeholder="Brasil"
                  />
                </div>
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="prof-title">Título profissional</Label>
                <Input
                  id="prof-title"
                  value={profileForm.professional_title}
                  onChange={(e) =>
                    setProfileForm({
                      ...profileForm,
                      professional_title: e.target.value,
                    })
                  }
                  placeholder="Ex: Desenvolvedor Backend Júnior | Python & Automações"
                />
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="prof-summary">Resumo profissional</Label>
                <Textarea
                  id="prof-summary"
                  rows={4}
                  value={profileForm.professional_summary}
                  onChange={(e) =>
                    setProfileForm({
                      ...profileForm,
                      professional_summary: e.target.value,
                    })
                  }
                  placeholder="Descreva sua trajetória e foco profissional..."
                />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div className="space-y-1.5">
                  <Label htmlFor="prof-linkedin">URL do LinkedIn</Label>
                  <Input
                    id="prof-linkedin"
                    value={profileForm.linkedin_url}
                    onChange={(e) =>
                      setProfileForm({
                        ...profileForm,
                        linkedin_url: e.target.value,
                      })
                    }
                    placeholder="https://www.linkedin.com/in/..."
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="prof-github">URL do GitHub</Label>
                  <Input
                    id="prof-github"
                    value={profileForm.github_url}
                    onChange={(e) =>
                      setProfileForm({
                        ...profileForm,
                        github_url: e.target.value,
                      })
                    }
                    placeholder="https://github.com/..."
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="prof-portfolio">URL do Portfólio</Label>
                  <Input
                    id="prof-portfolio"
                    value={profileForm.portfolio_url}
                    onChange={(e) =>
                      setProfileForm({
                        ...profileForm,
                        portfolio_url: e.target.value,
                      })
                    }
                    placeholder="https://..."
                  />
                </div>
              </div>

              <div className="rounded-lg border border-border bg-muted/40 p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div className="space-y-1">
                  <Label htmlFor="prof-verification">
                    Estado de validação destes dados gerais
                  </Label>
                  <p className="text-xs text-muted-foreground">
                    Somente dados marcados como Confirmados serão utilizados
                    como fatos em documentos finais.
                  </p>
                </div>
                <select
                  id="prof-verification"
                  value={profileForm.verification_status}
                  onChange={(e) =>
                    setProfileForm({
                      ...profileForm,
                      verification_status: e.target.value as VerificationStatus,
                    })
                  }
                  className="h-10 rounded-md border border-input bg-background px-3 text-sm"
                >
                  {Object.entries(VERIFICATION_LABELS).map(([val, label]) => (
                    <option key={val} value={val}>
                      {label}
                    </option>
                  ))}
                </select>
              </div>

              <div className="flex justify-end">
                <Button type="submit" disabled={busy}>
                  <Save className="h-4 w-4" />
                  {busy ? "Salvando..." : "Salvar Dados Gerais"}
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      {/* Aba 2: Experiências Profissionais */}
      {subTab === "experiencias" && (
        <ExperiencesSection
          items={bundle.experiences}
          onRefresh={onRefresh}
          onSuccess={showSuccess}
          onError={showError}
        />
      )}

      {/* Aba 3: Formação Acadêmica */}
      {subTab === "formacao" && (
        <EducationsSection
          items={bundle.educations}
          onRefresh={onRefresh}
          onSuccess={showSuccess}
          onError={showError}
        />
      )}

      {/* Aba 4: Habilidades */}
      {subTab === "habilidades" && (
        <SkillsSection
          items={bundle.skills}
          onRefresh={onRefresh}
          onSuccess={showSuccess}
          onError={showError}
        />
      )}

      {/* Aba 5: Idiomas */}
      {subTab === "idiomas" && (
        <LanguagesSection
          items={bundle.languages}
          onRefresh={onRefresh}
          onSuccess={showSuccess}
          onError={showError}
        />
      )}

      {/* Aba 6: Projetos Profissionais */}
      {subTab === "projetos" && (
        <ProjectsSection
          items={bundle.projects}
          onRefresh={onRefresh}
          onSuccess={showSuccess}
          onError={showError}
        />
      )}

      {/* Aba 7: Preferências & Restrições */}
      {subTab === "preferencias" && (
        <Card>
          <CardHeader>
            <CardTitle>Preferências de Oportunidades & Restrições</CardTitle>
            <CardDescription>
              Configure áreas prioritárias, idiomas, bloqueio de CLT e
              restrições de plataformas. Separe múltiplos itens por vírgula.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSavePreferences} className="space-y-6">
              {/* Estágios */}
              <div className="rounded-lg border border-border p-4 space-y-4">
                <h4 className="font-semibold text-sm text-primary">
                  1. Estágios em Tecnologia
                </h4>
                <div className="space-y-1.5">
                  <Label htmlFor="pref-intern-areas">Áreas prioritárias</Label>
                  <Input
                    id="pref-intern-areas"
                    value={prefsForm.internshipAreas}
                    onChange={(e) =>
                      setPrefsForm({
                        ...prefsForm,
                        internshipAreas: e.target.value,
                      })
                    }
                  />
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div className="space-y-1.5">
                    <Label htmlFor="pref-intern-langs">
                      Idiomas preferenciais
                    </Label>
                    <Input
                      id="pref-intern-langs"
                      value={prefsForm.internshipLangs}
                      onChange={(e) =>
                        setPrefsForm({
                          ...prefsForm,
                          internshipLangs: e.target.value,
                        })
                      }
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="pref-intern-excl">
                      Áreas excluídas (não elegíveis)
                    </Label>
                    <Input
                      id="pref-intern-excl"
                      value={prefsForm.internshipExcluded}
                      onChange={(e) =>
                        setPrefsForm({
                          ...prefsForm,
                          internshipExcluded: e.target.value,
                        })
                      }
                    />
                  </div>
                </div>
              </div>

              {/* Desenvolvedor Júnior */}
              <div className="rounded-lg border border-border p-4 space-y-4">
                <h4 className="font-semibold text-sm text-primary">
                  2. Desenvolvedor Júnior & Posições de Entrada
                </h4>
                <label className="flex items-center gap-3 text-sm font-medium cursor-pointer">
                  <input
                    type="checkbox"
                    checked={prefsForm.juniorBlockClt}
                    onChange={(e) =>
                      setPrefsForm({
                        ...prefsForm,
                        juniorBlockClt: e.target.checked,
                      })
                    }
                    className="h-4 w-4 accent-primary"
                  />
                  <span>
                    Bloquear oportunidades exclusivamente CLT até alteração
                    explícita
                  </span>
                </label>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div className="space-y-1.5">
                    <Label htmlFor="pref-jr-contracts">
                      Modalidades de contratação aceitas
                    </Label>
                    <Input
                      id="pref-jr-contracts"
                      value={prefsForm.juniorContracts}
                      onChange={(e) =>
                        setPrefsForm({
                          ...prefsForm,
                          juniorContracts: e.target.value,
                        })
                      }
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="pref-jr-areas">Áreas técnicas alvo</Label>
                    <Input
                      id="pref-jr-areas"
                      value={prefsForm.juniorAreas}
                      onChange={(e) =>
                        setPrefsForm({
                          ...prefsForm,
                          juniorAreas: e.target.value,
                        })
                      }
                    />
                  </div>
                </div>
              </div>

              {/* Freelancer */}
              <div className="rounded-lg border border-border p-4 space-y-4">
                <h4 className="font-semibold text-sm text-primary">
                  3. Projetos Freelance (Nacional & Internacional)
                </h4>
                <div className="space-y-1.5">
                  <Label htmlFor="pref-free-cats">
                    Categorias prioritárias de projetos
                  </Label>
                  <Input
                    id="pref-free-cats"
                    value={prefsForm.freelanceCategories}
                    onChange={(e) =>
                      setPrefsForm({
                        ...prefsForm,
                        freelanceCategories: e.target.value,
                      })
                    }
                  />
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div className="space-y-1.5">
                    <Label htmlFor="pref-free-scopes">Escopos de busca</Label>
                    <Input
                      id="pref-free-scopes"
                      value={prefsForm.freelanceScopes}
                      onChange={(e) =>
                        setPrefsForm({
                          ...prefsForm,
                          freelanceScopes: e.target.value,
                        })
                      }
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="pref-free-langs">Idiomas</Label>
                    <Input
                      id="pref-free-langs"
                      value={prefsForm.freelanceLangs}
                      onChange={(e) =>
                        setPrefsForm({
                          ...prefsForm,
                          freelanceLangs: e.target.value,
                        })
                      }
                    />
                  </div>
                </div>
              </div>

              {/* Restrições de fontes */}
              <div className="rounded-lg border border-border p-4 space-y-4">
                <h4 className="font-semibold text-sm text-primary">
                  4. Restrições de Fontes & Plataformas
                </h4>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 items-center">
                  <label className="flex items-center gap-3 text-sm cursor-pointer">
                    <input
                      type="checkbox"
                      checked={prefsForm.workanaEnabled}
                      onChange={(e) =>
                        setPrefsForm({
                          ...prefsForm,
                          workanaEnabled: e.target.checked,
                        })
                      }
                      className="h-4 w-4 accent-primary"
                    />
                    <span>
                      Habilitar Workana (controle opcional de plataforma)
                    </span>
                  </label>
                  <div className="space-y-1.5">
                    <Label htmlFor="pref-gupy">Política para Gupy</Label>
                    <select
                      id="pref-gupy"
                      value={prefsForm.gupyMode}
                      onChange={(e) =>
                        setPrefsForm({
                          ...prefsForm,
                          gupyMode: e.target.value as
                            | "disabled"
                            | "selective_high_compatibility"
                            | "enabled",
                        })
                      }
                      className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                    >
                      <option value="selective_high_compatibility">
                        Seletiva (Apenas alta compatibilidade)
                      </option>
                      <option value="enabled">Habilitada geral</option>
                      <option value="disabled">Desabilitada</option>
                    </select>
                  </div>
                </div>
              </div>

              <div className="flex justify-end">
                <Button type="submit" disabled={busy}>
                  <Save className="h-4 w-4" />
                  {busy ? "Salvando..." : "Salvar Preferências"}
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

/* ============================================================================
 * SUB-SEÇÃO: EXPERIÊNCIAS PROFISSIONAIS
 * ============================================================================ */
function ExperiencesSection({
  items,
  onRefresh,
  onSuccess,
  onError,
}: {
  items: WorkExperience[];
  onRefresh: () => Promise<void>;
  onSuccess: (msg: string) => void;
  onError: (err: unknown) => void;
}) {
  const emptyForm = {
    company: "",
    role: "",
    description: "",
    start_date: "",
    end_date: "",
    is_current: false,
    experience_type: "internship" as ExperienceType,
    technologiesText: "",
    relatedSkillsText: "",
    eligible_as_target_role: true,
    verification_status: "pending_validation" as VerificationStatus,
  };

  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState(emptyForm);
  const [saving, setSaving] = useState(false);

  const startEdit = (exp: WorkExperience) => {
    setEditingId(exp.id);
    setForm({
      company: exp.company,
      role: exp.role,
      description: exp.description || "",
      start_date: exp.start_date || "",
      end_date: exp.end_date || "",
      is_current: exp.is_current,
      experience_type: exp.experience_type,
      technologiesText: joinCommaSeparated(exp.technologies),
      relatedSkillsText: joinCommaSeparated(exp.related_skills),
      eligible_as_target_role: exp.eligible_as_target_role,
      verification_status: exp.verification_status,
    });
  };

  const resetForm = () => {
    setEditingId(null);
    setForm(emptyForm);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    const payload: WorkExperiencePayload = {
      company: form.company,
      role: form.role,
      description: form.description || null,
      start_date: form.start_date || null,
      end_date: form.is_current ? null : form.end_date || null,
      is_current: form.is_current,
      experience_type: form.experience_type,
      technologies: splitCommaSeparated(form.technologiesText),
      related_skills: splitCommaSeparated(form.relatedSkillsText),
      eligible_as_target_role: form.eligible_as_target_role,
      verification_status: form.verification_status,
    };

    try {
      if (editingId) {
        await api.profile.updateExperience(editingId, payload);
        onSuccess("Experiência profissional atualizada.");
      } else {
        await api.profile.createExperience(payload);
        onSuccess("Nova experiência profissional adicionada.");
      }
      resetForm();
      await onRefresh();
    } catch (err) {
      onError(err);
    } finally {
      setSaving(false);
    }
  };

  const handleQuickConfirm = async (exp: WorkExperience) => {
    const nextStatus: VerificationStatus =
      exp.verification_status === "confirmed"
        ? "pending_validation"
        : "confirmed";
    try {
      await api.profile.updateExperience(exp.id, {
        company: exp.company,
        role: exp.role,
        description: exp.description,
        start_date: exp.start_date,
        end_date: exp.end_date,
        is_current: exp.is_current,
        experience_type: exp.experience_type,
        technologies: exp.technologies,
        related_skills: exp.related_skills,
        eligible_as_target_role: exp.eligible_as_target_role,
        verification_status: nextStatus,
      });
      await onRefresh();
      onSuccess(
        nextStatus === "confirmed"
          ? `Experiência em "${exp.company}" marcada como Confirmada.`
          : `Experiência em "${exp.company}" movida para Pendente de Validação.`
      );
    } catch (err) {
      onError(err);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await api.profile.deleteExperience(id);
      if (editingId === id) resetForm();
      await onRefresh();
      onSuccess("Experiência removida.");
    } catch (err) {
      onError(err);
    }
  };

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>
            {editingId
              ? "Editar Experiência Profissional"
              : "Adicionar Experiência Profissional"}
          </CardTitle>
          <CardDescription>
            Registre apenas atividades e tecnologias reais.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div className="space-y-1.5">
                <Label htmlFor="exp-company">Empresa *</Label>
                <Input
                  id="exp-company"
                  required
                  value={form.company}
                  onChange={(e) =>
                    setForm({ ...form, company: e.target.value })
                  }
                  placeholder="Ex: Empresa Exemplo Ltda."
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="exp-role">Cargo *</Label>
                <Input
                  id="exp-role"
                  required
                  value={form.role}
                  onChange={(e) => setForm({ ...form, role: e.target.value })}
                  placeholder="Ex: Estagiário de TI"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="exp-type">Tipo de experiência</Label>
                <select
                  id="exp-type"
                  value={form.experience_type}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      experience_type: e.target.value as ExperienceType,
                    })
                  }
                  className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                >
                  {Object.entries(EXPERIENCE_TYPE_LABELS).map(([k, v]) => (
                    <option key={k} value={k}>
                      {v}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 items-end">
              <div className="space-y-1.5">
                <Label htmlFor="exp-start">Data de início</Label>
                <Input
                  id="exp-start"
                  type="date"
                  value={form.start_date}
                  onChange={(e) =>
                    setForm({ ...form, start_date: e.target.value })
                  }
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="exp-end">Data de término</Label>
                <Input
                  id="exp-end"
                  type="date"
                  disabled={form.is_current}
                  value={form.is_current ? "" : form.end_date}
                  onChange={(e) =>
                    setForm({ ...form, end_date: e.target.value })
                  }
                />
              </div>
              <label className="flex items-center gap-2.5 h-10 text-sm font-medium cursor-pointer">
                <input
                  type="checkbox"
                  checked={form.is_current}
                  onChange={(e) =>
                    setForm({ ...form, is_current: e.target.checked })
                  }
                  className="h-4 w-4 accent-primary"
                />
                <span>Emprego / Atuação atual</span>
              </label>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="exp-desc">Descrição das atividades</Label>
              <Textarea
                id="exp-desc"
                rows={3}
                value={form.description}
                onChange={(e) =>
                  setForm({ ...form, description: e.target.value })
                }
                placeholder="Descreva suas responsabilidades comprovadas..."
              />
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <Label htmlFor="exp-tech">
                  Tecnologias utilizadas (separadas por vírgula)
                </Label>
                <Input
                  id="exp-tech"
                  value={form.technologiesText}
                  onChange={(e) =>
                    setForm({ ...form, technologiesText: e.target.value })
                  }
                  placeholder="Python, TypeScript, Docker, SQL..."
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="exp-skills">
                  Competências relacionadas (separadas por vírgula)
                </Label>
                <Input
                  id="exp-skills"
                  value={form.relatedSkillsText}
                  onChange={(e) =>
                    setForm({ ...form, relatedSkillsText: e.target.value })
                  }
                  placeholder="APIs REST, Automação, Sistemas internos..."
                />
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 items-center pt-1">
              <label className="flex items-start gap-2.5 text-xs sm:text-sm cursor-pointer">
                <input
                  type="checkbox"
                  checked={form.eligible_as_target_role}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      eligible_as_target_role: e.target.checked,
                    })
                  }
                  className="h-4 w-4 mt-0.5 accent-primary"
                />
                <span>
                  Utilizar este cargo também como cargo-alvo na busca de vagas
                  (desmarque para experiências de suporte que não devem atrair
                  vagas de suporte)
                </span>
              </label>

              <div className="space-y-1.5">
                <Label htmlFor="exp-status">Status de validação</Label>
                <select
                  id="exp-status"
                  value={form.verification_status}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      verification_status: e.target.value as VerificationStatus,
                    })
                  }
                  className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                >
                  {Object.entries(VERIFICATION_LABELS).map(([k, v]) => (
                    <option key={k} value={k}>
                      {v}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="flex justify-end gap-2">
              {editingId && (
                <Button type="button" variant="outline" onClick={resetForm}>
                  Cancelar Edição
                </Button>
              )}
              <Button type="submit" disabled={saving}>
                <Plus className="h-4 w-4" />
                {saving
                  ? "Salvando..."
                  : editingId
                  ? "Salvar Alterações"
                  : "Adicionar Experiência"}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      <div className="space-y-3">
        {items.map((exp) => (
          <Card key={exp.id}>
            <CardContent className="p-5 flex flex-col gap-3">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <h4 className="font-semibold text-base">{exp.role}</h4>
                    <Badge variant="secondary">
                      {EXPERIENCE_TYPE_LABELS[exp.experience_type]}
                    </Badge>
                    <VerificationBadge status={exp.verification_status} />
                  </div>
                  <p className="text-sm text-muted-foreground">
                    {exp.company} •{" "}
                    {exp.start_date || "Início não informado"} até{" "}
                    {exp.is_current ? "Atual" : exp.end_date || "Não informado"}
                  </p>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleQuickConfirm(exp)}
                  >
                    <CheckCircle2 className="h-3.5 w-3.5" />
                    {exp.verification_status === "confirmed"
                      ? "Marcar Pendente"
                      : "Confirmar Fato"}
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => startEdit(exp)}
                  >
                    <Edit3 className="h-3.5 w-3.5" />
                    Editar
                  </Button>
                  <Button
                    variant="destructive"
                    size="sm"
                    onClick={() => handleDelete(exp.id)}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </div>

              {exp.description && (
                <p className="text-sm text-muted-foreground leading-relaxed">
                  {exp.description}
                </p>
              )}

              <div className="flex flex-wrap gap-1.5">
                {exp.technologies.map((t) => (
                  <Badge key={t} variant="default">
                    {t}
                  </Badge>
                ))}
                {!exp.eligible_as_target_role && (
                  <Badge variant="warning">
                    Experiência de base (Cargo não elegível como vaga-alvo)
                  </Badge>
                )}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

/* ============================================================================
 * SUB-SEÇÃO: FORMAÇÃO ACADÊMICA
 * ============================================================================ */
function EducationsSection({
  items,
  onRefresh,
  onSuccess,
  onError,
}: {
  items: Education[];
  onRefresh: () => Promise<void>;
  onSuccess: (msg: string) => void;
  onError: (err: unknown) => void;
}) {
  const emptyForm = {
    institution: "",
    course: "",
    field_of_study: "",
    current_semester: "",
    start_date: "",
    expected_graduation_date: "",
    education_status: "in_progress" as EducationStatus,
    verification_status: "pending_validation" as VerificationStatus,
  };

  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState(emptyForm);
  const [saving, setSaving] = useState(false);

  const startEdit = (edu: Education) => {
    setEditingId(edu.id);
    setForm({
      institution: edu.institution,
      course: edu.course,
      field_of_study: edu.field_of_study || "",
      current_semester: edu.current_semester || "",
      start_date: edu.start_date || "",
      expected_graduation_date: edu.expected_graduation_date || "",
      education_status: edu.education_status,
      verification_status: edu.verification_status,
    });
  };

  const resetForm = () => {
    setEditingId(null);
    setForm(emptyForm);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    const payload: EducationPayload = {
      institution: form.institution,
      course: form.course,
      field_of_study: form.field_of_study || null,
      current_semester: form.current_semester || null,
      start_date: form.start_date || null,
      expected_graduation_date: form.expected_graduation_date || null,
      education_status: form.education_status,
      verification_status: form.verification_status,
    };

    try {
      if (editingId) {
        await api.profile.updateEducation(editingId, payload);
        onSuccess("Formação acadêmica atualizada.");
      } else {
        await api.profile.createEducation(payload);
        onSuccess("Formação acadêmica adicionada.");
      }
      resetForm();
      await onRefresh();
    } catch (err) {
      onError(err);
    } finally {
      setSaving(false);
    }
  };

  const handleQuickConfirm = async (edu: Education) => {
    const nextStatus: VerificationStatus =
      edu.verification_status === "confirmed"
        ? "pending_validation"
        : "confirmed";
    try {
      await api.profile.updateEducation(edu.id, {
        institution: edu.institution,
        course: edu.course,
        field_of_study: edu.field_of_study,
        current_semester: edu.current_semester,
        start_date: edu.start_date,
        expected_graduation_date: edu.expected_graduation_date,
        education_status: edu.education_status,
        verification_status: nextStatus,
      });
      await onRefresh();
      onSuccess("Status de validação da formação atualizado.");
    } catch (err) {
      onError(err);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await api.profile.deleteEducation(id);
      if (editingId === id) resetForm();
      await onRefresh();
      onSuccess("Formação removida.");
    } catch (err) {
      onError(err);
    }
  };

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>
            {editingId
              ? "Editar Formação Acadêmica"
              : "Adicionar Formação Acadêmica"}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <Label htmlFor="edu-inst">Instituição *</Label>
                <Input
                  id="edu-inst"
                  required
                  value={form.institution}
                  onChange={(e) =>
                    setForm({ ...form, institution: e.target.value })
                  }
                  placeholder="Ex: Universidade / Instituto"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="edu-course">Curso *</Label>
                <Input
                  id="edu-course"
                  required
                  value={form.course}
                  onChange={(e) => setForm({ ...form, course: e.target.value })}
                  placeholder="Ex: Ciência da Computação"
                />
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div className="space-y-1.5">
                <Label htmlFor="edu-field">Área de formação</Label>
                <Input
                  id="edu-field"
                  value={form.field_of_study}
                  onChange={(e) =>
                    setForm({ ...form, field_of_study: e.target.value })
                  }
                  placeholder="Tecnologia da Informação"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="edu-sem">Semestre / Período atual</Label>
                <Input
                  id="edu-sem"
                  value={form.current_semester}
                  onChange={(e) =>
                    setForm({ ...form, current_semester: e.target.value })
                  }
                  placeholder="3º semestre"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="edu-status">Estado da formação</Label>
                <select
                  id="edu-status"
                  value={form.education_status}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      education_status: e.target.value as EducationStatus,
                    })
                  }
                  className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                >
                  {Object.entries(EDUCATION_STATUS_LABELS).map(([k, v]) => (
                    <option key={k} value={k}>
                      {v}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div className="space-y-1.5">
                <Label htmlFor="edu-start">Data de início</Label>
                <Input
                  id="edu-start"
                  type="date"
                  value={form.start_date}
                  onChange={(e) =>
                    setForm({ ...form, start_date: e.target.value })
                  }
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="edu-grad">Previsão de conclusão</Label>
                <Input
                  id="edu-grad"
                  type="date"
                  value={form.expected_graduation_date}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      expected_graduation_date: e.target.value,
                    })
                  }
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="edu-verif">Status de validação</Label>
                <select
                  id="edu-verif"
                  value={form.verification_status}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      verification_status: e.target.value as VerificationStatus,
                    })
                  }
                  className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                >
                  {Object.entries(VERIFICATION_LABELS).map(([k, v]) => (
                    <option key={k} value={k}>
                      {v}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="flex justify-end gap-2">
              {editingId && (
                <Button type="button" variant="outline" onClick={resetForm}>
                  Cancelar
                </Button>
              )}
              <Button type="submit" disabled={saving}>
                <Plus className="h-4 w-4" />
                {saving
                  ? "Salvando..."
                  : editingId
                  ? "Salvar Alterações"
                  : "Adicionar Formação"}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      <div className="space-y-3">
        {items.map((edu) => (
          <Card key={edu.id}>
            <CardContent className="p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div className="space-y-1">
                <div className="flex flex-wrap items-center gap-2">
                  <h4 className="font-semibold text-base">{edu.course}</h4>
                  <Badge variant="secondary">
                    {EDUCATION_STATUS_LABELS[edu.education_status]}
                  </Badge>
                  <VerificationBadge status={edu.verification_status} />
                </div>
                <p className="text-sm text-muted-foreground">
                  {edu.institution}
                  {edu.current_semester ? ` • ${edu.current_semester}` : ""}
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => handleQuickConfirm(edu)}
                >
                  <CheckCircle2 className="h-3.5 w-3.5" />
                  {edu.verification_status === "confirmed"
                    ? "Marcar Pendente"
                    : "Confirmar Fato"}
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => startEdit(edu)}
                >
                  <Edit3 className="h-3.5 w-3.5" />
                  Editar
                </Button>
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={() => handleDelete(edu.id)}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

/* ============================================================================
 * SUB-SEÇÃO: HABILIDADES TÉCNICAS (SKILLS)
 * ============================================================================ */
function SkillsSection({
  items,
  onRefresh,
  onSuccess,
  onError,
}: {
  items: Skill[];
  onRefresh: () => Promise<void>;
  onSuccess: (msg: string) => void;
  onError: (err: unknown) => void;
}) {
  const emptyForm = {
    name: "",
    category: "Backend",
    proficiency_level: "intermediate" as SkillProficiency,
    notes: "",
    verification_status: "pending_validation" as VerificationStatus,
  };

  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState(emptyForm);
  const [saving, setSaving] = useState(false);

  const startEdit = (sk: Skill) => {
    setEditingId(sk.id);
    setForm({
      name: sk.name,
      category: sk.category,
      proficiency_level: sk.proficiency_level,
      notes: sk.notes || "",
      verification_status: sk.verification_status,
    });
  };

  const resetForm = () => {
    setEditingId(null);
    setForm(emptyForm);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    const payload: SkillPayload = {
      name: form.name,
      category: form.category,
      proficiency_level: form.proficiency_level,
      notes: form.notes || null,
      verification_status: form.verification_status,
    };

    try {
      if (editingId) {
        await api.profile.updateSkill(editingId, payload);
        onSuccess("Habilidade atualizada.");
      } else {
        await api.profile.createSkill(payload);
        onSuccess("Habilidade adicionada.");
      }
      resetForm();
      await onRefresh();
    } catch (err) {
      onError(err);
    } finally {
      setSaving(false);
    }
  };

  const handleQuickConfirm = async (sk: Skill) => {
    const nextStatus: VerificationStatus =
      sk.verification_status === "confirmed"
        ? "pending_validation"
        : "confirmed";
    try {
      await api.profile.updateSkill(sk.id, {
        name: sk.name,
        category: sk.category,
        proficiency_level: sk.proficiency_level,
        notes: sk.notes,
        verification_status: nextStatus,
      });
      await onRefresh();
      onSuccess(`Habilidade "${sk.name}" atualizada.`);
    } catch (err) {
      onError(err);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await api.profile.deleteSkill(id);
      if (editingId === id) resetForm();
      await onRefresh();
      onSuccess("Habilidade removida.");
    } catch (err) {
      onError(err);
    }
  };

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>
            {editingId ? "Editar Habilidade" : "Adicionar Habilidade"}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
              <div className="space-y-1.5">
                <Label htmlFor="sk-name">Nome da habilidade *</Label>
                <Input
                  id="sk-name"
                  required
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  placeholder="Ex: Python, FastAPI, React..."
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="sk-cat">Categoria *</Label>
                <Input
                  id="sk-cat"
                  required
                  value={form.category}
                  onChange={(e) =>
                    setForm({ ...form, category: e.target.value })
                  }
                  placeholder="Backend, Automação & Bots..."
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="sk-level">Nível autodeclarado</Label>
                <select
                  id="sk-level"
                  value={form.proficiency_level}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      proficiency_level: e.target.value as SkillProficiency,
                    })
                  }
                  className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                >
                  {Object.entries(SKILL_LEVEL_LABELS).map(([k, v]) => (
                    <option key={k} value={k}>
                      {v}
                    </option>
                  ))}
                </select>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="sk-verif">Status de validação</Label>
                <select
                  id="sk-verif"
                  value={form.verification_status}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      verification_status: e.target.value as VerificationStatus,
                    })
                  }
                  className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                >
                  {Object.entries(VERIFICATION_LABELS).map(([k, v]) => (
                    <option key={k} value={k}>
                      {v}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="sk-notes">Observações / Contexto de uso</Label>
              <Input
                id="sk-notes"
                value={form.notes}
                onChange={(e) => setForm({ ...form, notes: e.target.value })}
                placeholder="Onde e como utilizou esta competência..."
              />
            </div>

            <div className="flex justify-end gap-2">
              {editingId && (
                <Button type="button" variant="outline" onClick={resetForm}>
                  Cancelar
                </Button>
              )}
              <Button type="submit" disabled={saving}>
                <Plus className="h-4 w-4" />
                {saving
                  ? "Salvando..."
                  : editingId
                  ? "Salvar Alterações"
                  : "Adicionar Habilidade"}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {items.map((sk) => (
          <Card key={sk.id}>
            <CardContent className="p-4 flex flex-col justify-between gap-3 h-full">
              <div className="space-y-1.5">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-sm">{sk.name}</span>
                    <Badge variant="outline">{sk.category}</Badge>
                  </div>
                  <VerificationBadge status={sk.verification_status} />
                </div>
                <p className="text-xs text-muted-foreground">
                  Nível: <strong>{SKILL_LEVEL_LABELS[sk.proficiency_level]}</strong>
                </p>
                {sk.notes && (
                  <p className="text-xs text-muted-foreground">{sk.notes}</p>
                )}
              </div>

              <div className="flex items-center justify-end gap-1.5 pt-1">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => handleQuickConfirm(sk)}
                >
                  <CheckCircle2 className="h-3.5 w-3.5" />
                  {sk.verification_status === "confirmed"
                    ? "Pendente"
                    : "Confirmar"}
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => startEdit(sk)}
                >
                  <Edit3 className="h-3.5 w-3.5" />
                </Button>
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={() => handleDelete(sk.id)}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

/* ============================================================================
 * SUB-SEÇÃO: IDIOMAS
 * ============================================================================ */
function LanguagesSection({
  items,
  onRefresh,
  onSuccess,
  onError,
}: {
  items: Language[];
  onRefresh: () => Promise<void>;
  onSuccess: (msg: string) => void;
  onError: (err: unknown) => void;
}) {
  const emptyForm = {
    language_name: "",
    proficiency_level: "intermediate" as LanguageProficiency,
    cefr_level: "",
    verification_status: "pending_validation" as VerificationStatus,
  };

  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState(emptyForm);
  const [saving, setSaving] = useState(false);

  const startEdit = (lang: Language) => {
    setEditingId(lang.id);
    setForm({
      language_name: lang.language_name,
      proficiency_level: lang.proficiency_level,
      cefr_level: lang.cefr_level || "",
      verification_status: lang.verification_status,
    });
  };

  const resetForm = () => {
    setEditingId(null);
    setForm(emptyForm);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    const payload: LanguagePayload = {
      language_name: form.language_name,
      proficiency_level: form.proficiency_level,
      cefr_level: form.cefr_level || null,
      verification_status: form.verification_status,
    };

    try {
      if (editingId) {
        await api.profile.updateLanguage(editingId, payload);
        onSuccess("Idioma atualizado.");
      } else {
        await api.profile.createLanguage(payload);
        onSuccess("Idioma adicionado.");
      }
      resetForm();
      await onRefresh();
    } catch (err) {
      onError(err);
    } finally {
      setSaving(false);
    }
  };

  const handleQuickConfirm = async (lang: Language) => {
    const nextStatus: VerificationStatus =
      lang.verification_status === "confirmed"
        ? "pending_validation"
        : "confirmed";
    try {
      await api.profile.updateLanguage(lang.id, {
        language_name: lang.language_name,
        proficiency_level: lang.proficiency_level,
        cefr_level: lang.cefr_level,
        verification_status: nextStatus,
      });
      await onRefresh();
      onSuccess(`Idioma "${lang.language_name}" atualizado.`);
    } catch (err) {
      onError(err);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await api.profile.deleteLanguage(id);
      if (editingId === id) resetForm();
      await onRefresh();
      onSuccess("Idioma removido.");
    } catch (err) {
      onError(err);
    }
  };

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>
            {editingId ? "Editar Idioma" : "Adicionar Idioma"}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
              <div className="space-y-1.5">
                <Label htmlFor="lang-name">Idioma *</Label>
                <Input
                  id="lang-name"
                  required
                  value={form.language_name}
                  onChange={(e) =>
                    setForm({ ...form, language_name: e.target.value })
                  }
                  placeholder="Ex: Inglês, Português..."
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="lang-prof">Nível informado</Label>
                <select
                  id="lang-prof"
                  value={form.proficiency_level}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      proficiency_level: e.target.value as LanguageProficiency,
                    })
                  }
                  className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                >
                  {Object.entries(LANGUAGE_LEVEL_LABELS).map(([k, v]) => (
                    <option key={k} value={k}>
                      {v}
                    </option>
                  ))}
                </select>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="lang-cefr">Referência CEFR (opcional)</Label>
                <select
                  id="lang-cefr"
                  value={form.cefr_level}
                  onChange={(e) =>
                    setForm({ ...form, cefr_level: e.target.value })
                  }
                  className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                >
                  <option value="">Não aplicável / Não informado</option>
                  {["A1", "A2", "B1", "B2", "C1", "C2"].map((lvl) => (
                    <option key={lvl} value={lvl}>
                      {lvl}
                    </option>
                  ))}
                </select>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="lang-verif">Status de validação</Label>
                <select
                  id="lang-verif"
                  value={form.verification_status}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      verification_status: e.target.value as VerificationStatus,
                    })
                  }
                  className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                >
                  {Object.entries(VERIFICATION_LABELS).map(([k, v]) => (
                    <option key={k} value={k}>
                      {v}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="flex justify-end gap-2">
              {editingId && (
                <Button type="button" variant="outline" onClick={resetForm}>
                  Cancelar
                </Button>
              )}
              <Button type="submit" disabled={saving}>
                <Plus className="h-4 w-4" />
                {saving
                  ? "Salvando..."
                  : editingId
                  ? "Salvar Alterações"
                  : "Adicionar Idioma"}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {items.map((lang) => (
          <Card key={lang.id}>
            <CardContent className="p-4 flex items-center justify-between gap-3">
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-sm">
                    {lang.language_name}
                  </span>
                  {lang.cefr_level && (
                    <Badge variant="default">CEFR {lang.cefr_level}</Badge>
                  )}
                  <VerificationBadge status={lang.verification_status} />
                </div>
                <p className="text-xs text-muted-foreground">
                  Nível:{" "}
                  <strong>
                    {LANGUAGE_LEVEL_LABELS[lang.proficiency_level]}
                  </strong>
                </p>
              </div>

              <div className="flex items-center gap-1.5">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => handleQuickConfirm(lang)}
                >
                  <CheckCircle2 className="h-3.5 w-3.5" />
                  {lang.verification_status === "confirmed"
                    ? "Pendente"
                    : "Confirmar"}
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => startEdit(lang)}
                >
                  <Edit3 className="h-3.5 w-3.5" />
                </Button>
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={() => handleDelete(lang.id)}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

/* ============================================================================
 * SUB-SEÇÃO: PROJETOS PROFISSIONAIS
 * ============================================================================ */
function ProjectsSection({
  items,
  onRefresh,
  onSuccess,
  onError,
}: {
  items: ProfessionalProject[];
  onRefresh: () => Promise<void>;
  onSuccess: (msg: string) => void;
  onError: (err: unknown) => void;
}) {
  const emptyForm = {
    name: "",
    role: "",
    description: "",
    technologiesText: "",
    repoUrl: "",
    liveUrl: "",
    verified_results: "",
    verification_status: "draft" as VerificationStatus,
  };

  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState(emptyForm);
  const [saving, setSaving] = useState(false);

  const startEdit = (proj: ProfessionalProject) => {
    setEditingId(proj.id);
    setForm({
      name: proj.name,
      role: proj.role || "",
      description: proj.description || "",
      technologiesText: joinCommaSeparated(proj.technologies),
      repoUrl: proj.links["Repositório"] || proj.links["GitHub"] || "",
      liveUrl: proj.links["Demo"] || proj.links["Website"] || "",
      verified_results: proj.verified_results || "",
      verification_status: proj.verification_status,
    });
  };

  const resetForm = () => {
    setEditingId(null);
    setForm(emptyForm);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    const links: Record<string, string> = {};
    if (form.repoUrl.trim()) links["Repositório"] = form.repoUrl.trim();
    if (form.liveUrl.trim()) links["Website"] = form.liveUrl.trim();

    const payload: ProfessionalProjectPayload = {
      name: form.name,
      role: form.role || null,
      description: form.description || null,
      technologies: splitCommaSeparated(form.technologiesText),
      links,
      verified_results: form.verified_results || null,
      verification_status: form.verification_status,
    };

    try {
      if (editingId) {
        await api.profile.updateProject(editingId, payload);
        onSuccess("Projeto profissional atualizado.");
      } else {
        await api.profile.createProject(payload);
        onSuccess("Projeto profissional adicionado.");
      }
      resetForm();
      await onRefresh();
    } catch (err) {
      onError(err);
    } finally {
      setSaving(false);
    }
  };

  const handleQuickConfirm = async (proj: ProfessionalProject) => {
    const nextStatus: VerificationStatus =
      proj.verification_status === "confirmed" ? "draft" : "confirmed";
    try {
      await api.profile.updateProject(proj.id, {
        name: proj.name,
        role: proj.role,
        description: proj.description,
        technologies: proj.technologies,
        links: proj.links,
        verified_results: proj.verified_results,
        verification_status: nextStatus,
      });
      await onRefresh();
      onSuccess(`Projeto "${proj.name}" atualizado.`);
    } catch (err) {
      onError(err);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await api.profile.deleteProject(id);
      if (editingId === id) resetForm();
      await onRefresh();
      onSuccess("Projeto removido.");
    } catch (err) {
      onError(err);
    }
  };

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>
            {editingId
              ? "Editar Projeto Profissional"
              : "Adicionar Projeto Profissional"}
          </CardTitle>
          <CardDescription>
            Documente seus projetos relevantes com tecnologias e resultados
            comprovados.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div className="space-y-1.5">
                <Label htmlFor="proj-name">Nome do projeto *</Label>
                <Input
                  id="proj-name"
                  required
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  placeholder="Ex: Sistema de Gestão / API"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="proj-role">Papel desempenhado</Label>
                <Input
                  id="proj-role"
                  value={form.role}
                  onChange={(e) => setForm({ ...form, role: e.target.value })}
                  placeholder="Ex: Criador & Desenvolvedor Full Stack"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="proj-verif">Status de validação</Label>
                <select
                  id="proj-verif"
                  value={form.verification_status}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      verification_status: e.target.value as VerificationStatus,
                    })
                  }
                  className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                >
                  {Object.entries(VERIFICATION_LABELS).map(([k, v]) => (
                    <option key={k} value={k}>
                      {v}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="proj-desc">Descrição do projeto</Label>
              <Textarea
                id="proj-desc"
                rows={3}
                value={form.description}
                onChange={(e) =>
                  setForm({ ...form, description: e.target.value })
                }
                placeholder="Objetivo, arquitetura e funcionalidades reais do projeto..."
              />
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div className="space-y-1.5">
                <Label htmlFor="proj-tech">
                  Tecnologias (separadas por vírgula)
                </Label>
                <Input
                  id="proj-tech"
                  value={form.technologiesText}
                  onChange={(e) =>
                    setForm({ ...form, technologiesText: e.target.value })
                  }
                  placeholder="Python, PostgreSQL, Redis, Docker..."
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="proj-repo">URL do Repositório (opcional)</Label>
                <Input
                  id="proj-repo"
                  value={form.repoUrl}
                  onChange={(e) =>
                    setForm({ ...form, repoUrl: e.target.value })
                  }
                  placeholder="https://github.com/..."
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="proj-live">URL do Projeto / Demo (opcional)</Label>
                <Input
                  id="proj-live"
                  value={form.liveUrl}
                  onChange={(e) =>
                    setForm({ ...form, liveUrl: e.target.value })
                  }
                  placeholder="https://..."
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="proj-results">
                Resultados comprovados (Nunca inventados pela IA)
              </Label>
              <Textarea
                id="proj-results"
                rows={2}
                value={form.verified_results}
                onChange={(e) =>
                  setForm({ ...form, verified_results: e.target.value })
                }
                placeholder="Informe apenas entregas ou resultados reais verificáveis..."
              />
            </div>

            <div className="flex justify-end gap-2">
              {editingId && (
                <Button type="button" variant="outline" onClick={resetForm}>
                  Cancelar
                </Button>
              )}
              <Button type="submit" disabled={saving}>
                <Plus className="h-4 w-4" />
                {saving
                  ? "Salvando..."
                  : editingId
                  ? "Salvar Alterações"
                  : "Adicionar Projeto"}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      <div className="space-y-3">
        {items.map((proj) => (
          <Card key={proj.id}>
            <CardContent className="p-5 flex flex-col gap-3">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <h4 className="font-semibold text-base">{proj.name}</h4>
                    {proj.role && (
                      <Badge variant="secondary">{proj.role}</Badge>
                    )}
                    <VerificationBadge status={proj.verification_status} />
                  </div>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleQuickConfirm(proj)}
                  >
                    <CheckCircle2 className="h-3.5 w-3.5" />
                    {proj.verification_status === "confirmed"
                      ? "Voltar p/ Rascunho"
                      : "Confirmar Projeto"}
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => startEdit(proj)}
                  >
                    <Edit3 className="h-3.5 w-3.5" />
                    Editar
                  </Button>
                  <Button
                    variant="destructive"
                    size="sm"
                    onClick={() => handleDelete(proj.id)}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </div>

              {proj.description && (
                <p className="text-sm text-muted-foreground">
                  {proj.description}
                </p>
              )}

              {proj.verified_results && (
                <p className="text-xs text-emerald-600 dark:text-emerald-400">
                  <strong>Resultados comprovados:</strong>{" "}
                  {proj.verified_results}
                </p>
              )}

              {proj.technologies.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {proj.technologies.map((tech) => (
                    <Badge key={tech} variant="default">
                      {tech}
                    </Badge>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

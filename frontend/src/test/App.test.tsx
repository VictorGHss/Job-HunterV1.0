import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "@/App";
import { api } from "@/lib/api";
import type { FullProfileBundle, User } from "@/types/api";

const mockUser: User = {
  id: "11111111-1111-1111-1111-111111111111",
  email: "usuario@example.com",
  display_name: "Usuário Teste",
  account_status: "active",
  is_admin: true,
  created_at: "2026-11-15T19:00:00Z",
  updated_at: "2026-11-15T19:00:00Z",
};

const mockBundle: FullProfileBundle = {
  profile: {
    id: "22222222-2222-2222-2222-222222222222",
    user_id: mockUser.id,
    full_name: "Usuário Teste",
    professional_email: "usuario@example.com",
    phone: null,
    city: "Cidade Exemplo",
    state: "Estado Exemplo",
    country: "Brasil",
    professional_title: "Desenvolvedor Backend | Python & APIs",
    professional_summary: "Perfil de exemplo para testes unitários.",
    linkedin_url: null,
    github_url: null,
    portfolio_url: null,
    preferences: {
      internships: {
        enabled: true,
        priority_areas: ["Desenvolvimento Backend", "Automação"],
        preferred_languages: ["Português Brasileiro", "Inglês"],
        excluded_areas: ["Suporte técnico"],
      },
      junior_developer: {
        enabled: true,
        priority_areas: ["Desenvolvimento Backend"],
        block_clt: true,
        accepted_contract_types: ["Estágio", "PJ", "Contrato Freelance"],
        excluded_areas: ["Suporte técnico"],
      },
      freelance: {
        enabled: true,
        scopes: ["Brasil", "Exterior (Internacional)"],
        priority_categories: ["Python", "Automação", "APIs"],
        preferred_languages: ["Português", "Inglês"],
      },
      source_restrictions: {
        workana_enabled: false,
        workana_disabled_reason: "Configuração opcional de exemplo.",
        gupy_mode: "selective_high_compatibility",
        auto_execute_tests: false,
        pay_premium_or_fees_without_approval: false,
        strict_platform_terms_compliance: true,
      },
    },
    verification_status: "pending_validation",
    confirmed_at: null,
    created_at: "2026-11-15T19:00:00Z",
    updated_at: "2026-11-15T19:00:00Z",
  },
  experiences: [
    {
      id: "33333333-3333-3333-3333-333333333333",
      user_id: mockUser.id,
      company: "Empresa Exemplo LTDA",
      role: "Desenvolvedor Estagiário",
      description: "Desenvolvimento e manutenção de APIs REST.",
      start_date: "2025-01-01",
      end_date: null,
      is_current: true,
      experience_type: "internship",
      technologies: ["Python", "PostgreSQL"],
      related_skills: ["APIs"],
      eligible_as_target_role: true,
      verification_status: "pending_validation",
      confirmed_at: null,
      created_at: "2026-11-15T19:00:00Z",
      updated_at: "2026-11-15T19:00:00Z",
    },
  ],
  educations: [
    {
      id: "44444444-4444-4444-4444-444444444444",
      user_id: mockUser.id,
      institution: "Instituição Exemplo",
      course: "Análise e Desenvolvimento de Sistemas",
      field_of_study: "Tecnologia",
      current_semester: "2º semestre",
      start_date: null,
      expected_graduation_date: null,
      education_status: "in_progress",
      verification_status: "pending_validation",
      confirmed_at: null,
      created_at: "2026-11-15T19:00:00Z",
      updated_at: "2026-11-15T19:00:00Z",
    },
  ],
  skills: [
    {
      id: "55555555-5555-5555-5555-555555555555",
      user_id: mockUser.id,
      name: "Python",
      category: "Backend",
      proficiency_level: "intermediate",
      notes: "APIs FastAPI",
      verification_status: "pending_validation",
      confirmed_at: null,
      created_at: "2026-11-15T19:00:00Z",
      updated_at: "2026-11-15T19:00:00Z",
    },
  ],
  languages: [
    {
      id: "66666666-6666-6666-6666-666666666666",
      user_id: mockUser.id,
      language_name: "Inglês",
      proficiency_level: "intermediate",
      cefr_level: "B1",
      verification_status: "pending_validation",
      confirmed_at: null,
      created_at: "2026-11-15T19:00:00Z",
      updated_at: "2026-11-15T19:00:00Z",
    },
  ],
  projects: [
    {
      id: "77777777-7777-7777-7777-777777777777",
      user_id: mockUser.id,
      name: "Projeto Exemplo",
      description: "Projeto em rascunho para testes.",
      role: "Desenvolvedor",
      technologies: ["Python"],
      links: {},
      verified_results: null,
      verification_status: "draft",
      confirmed_at: null,
      created_at: "2026-11-15T19:00:00Z",
      updated_at: "2026-11-15T19:00:00Z",
    },
  ],
  validation_summary: {
    profile_confirmed: false,
    confirmed_count: 0,
    pending_or_draft_count: 6,
    total_items: 6,
    ready_for_future_applications: false,
  },
};

describe("Job Hunter Frontend - Fase 01.1", () => {
  beforeEach(() => {
    window.localStorage.clear();
    vi.restoreAllMocks();
  });

  it("exibe tela de login quando não autenticado e permite alternar e persistir o tema", async () => {
    vi.spyOn(api.auth, "me").mockRejectedValue(new Error("Não autenticado"));

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText("Entrar no Job Hunter")).toBeInTheDocument();
    });

    expect(
      screen.getByText(/Cadastro público desabilitado nesta versão/i)
    ).toBeInTheDocument();
    expect(screen.queryByText(/--seed-initial-profile/i)).not.toBeInTheDocument();

    // Testa alternância para o modo Claro e persistência no localStorage
    const lightBtn = screen.getByTitle("Modo Claro");
    fireEvent.click(lightBtn);
    expect(window.localStorage.getItem("jh_theme_mode")).toBe("light");
    expect(document.documentElement.classList.contains("light")).toBe(true);

    // Testa alternância para o modo Escuro
    const darkBtn = screen.getByTitle("Modo Escuro");
    fireEvent.click(darkBtn);
    expect(window.localStorage.getItem("jh_theme_mode")).toBe("dark");
    expect(document.documentElement.classList.contains("dark")).toBe(true);
  });

  it("autentica o usuário, renderiza o dashboard sem botão de seed público e edita o Perfil", async () => {
    vi.spyOn(api.auth, "me").mockRejectedValueOnce(new Error("Não autenticado"));
    vi.spyOn(api.auth, "login").mockResolvedValue({
      authenticated: true,
      user: mockUser,
      csrf_token: "test-csrf",
    });
    vi.spyOn(api.profile, "getBundle").mockResolvedValue(mockBundle);
    const updateProfileSpy = vi
      .spyOn(api.profile, "updateProfile")
      .mockResolvedValue({
        ...mockBundle.profile,
        verification_status: "confirmed",
      });

    render(<App />);

    await waitFor(() => {
      expect(screen.getByLabelText("E-mail")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText("E-mail"), {
      target: { value: "usuario@example.com" },
    });
    fireEvent.change(screen.getByLabelText("Senha"), {
      target: { value: "StrongPassword!2026" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Acessar Plataforma/i }));

    await waitFor(() => {
      expect(
        screen.getByText(/Cidade Exemplo, Estado Exemplo • Brasil/i)
      ).toBeInTheDocument();
    });

    expect(screen.getByText(/Vagas CLT Bloqueadas/i)).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Carregar Rascunho Inicial/i })
    ).not.toBeInTheDocument();

    // Navega para a tela de Perfil Profissional
    fireEvent.click(
      screen.getByRole("button", { name: /Gerenciar Perfil Completo/i })
    );

    await waitFor(() => {
      expect(
        screen.getByText("Identificação, Contato & Resumo")
      ).toBeInTheDocument();
    });

    expect(
      screen.queryByRole("button", { name: /Preencher Rascunho Base/i })
    ).not.toBeInTheDocument();

    // Salva os dados gerais do perfil
    fireEvent.click(
      screen.getByRole("button", { name: /Salvar Dados Gerais/i })
    );

    await waitFor(() => {
      expect(updateProfileSpy).toHaveBeenCalledTimes(1);
    });

    // Navega para a sub-aba de Experiências
    fireEvent.click(screen.getByRole("tab", { name: /Experiências/i }));

    await waitFor(() => {
      expect(screen.getByText(/Empresa Exemplo LTDA/i)).toBeInTheDocument();
    });
  });
});

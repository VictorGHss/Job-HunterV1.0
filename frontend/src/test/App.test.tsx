import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "@/App";
import { ApiError, api } from "@/lib/api";
import type {
  ApplicationAnswersStructuredContent,
  ApplicationItem,
  CoverLetterStructuredContent,
  FreelanceProposalStructuredContent,
  FullProfileBundle,
  MaterialDetailResponse,
  MaterialPreAnalysisResponse,
  Opportunity,
  OpportunityListResponse,
  OpportunitySourcePublic,
  RecruiterMessageStructuredContent,
  ResumeStructuredContent,
  User,
} from "@/types/api";

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

const mockSources: OpportunitySourcePublic[] = [
  {
    id: "src-remoteok",
    slug: "remote_ok",
    name: "Remote OK",
    source_type: "json_api",
    base_url: "https://remoteok.com/api",
    terms_url: "https://remoteok.com/terms",
    attribution_text: "Fonte: Remote OK — atribuição obrigatória.",
    enabled: true,
    refresh_interval_seconds: 3600,
    last_synced_at: "2026-11-15T20:00:00Z",
    last_success_at: "2026-11-15T20:00:00Z",
    last_error_summary: null,
  },
];

function buildMockOpportunity(overrides: Partial<Opportunity> = {}): Opportunity {
  return {
    id: "opp-1",
    is_manual: false,
    external_id: "109001",
    title: "Junior Python Backend Developer",
    company_name: "Acme Cloud",
    description: "Build FastAPI services and PostgreSQL databases.",
    opportunity_type: "junior",
    seniority_level: "junior",
    experience_requirement_mode: "none_required",
    experience_min_years: 0,
    experience_preferred_years: null,
    experience_summary: "Sem exigência de experiência prévia",
    employment_type: "pj",
    work_mode: "remote",
    professional_area: "backend",
    secondary_areas: ["software_development", "api_integrations"],
    location_text: "Worldwide",
    city: null,
    state: null,
    country: "Worldwide",
    eligible_countries: ["Worldwide"],
    eligibility_unknown: false,
    language: "English",
    salary_min: 4000,
    salary_max: 6000,
    salary_currency: "USD",
    salary_period: "month",
    requirements: ["Python", "FastAPI"],
    technologies: ["Python", "FastAPI", "PostgreSQL"],
    source_url: "https://remoteok.com/remote-jobs/junior-python-109001",
    application_url: "https://remoteok.com/remote-jobs/junior-python-109001",
    published_at: "2026-11-12T10:00:00Z",
    deadline_at: null,
    source_status: "active",
    first_seen_at: "2026-11-15T20:00:00Z",
    last_seen_at: "2026-11-15T20:00:00Z",
    source: mockSources[0],
    user_state: {
      is_saved: false,
      is_dismissed: false,
      last_viewed_at: null,
    },
    match: {
      eligible: true,
      overall_compatibility: "compatible",
      geographic_eligibility: "eligible",
      seniority_compatibility: "compatible",
      experience_compatibility: "compatible",
      technical_compatibility: "compatible",
      matched_skills: ["Python", "PostgreSQL"],
      required_technologies: ["Python"],
      desirable_technologies: ["Docker"],
      inclusion_reasons: [
        "Categoria compatível com a frente de Desenvolvedor Júnior ativa.",
        "Elegibilidade remota compatível com o perfil (Worldwide).",
      ],
      exclusion_reasons: [],
    },
    ...overrides,
  };
}

describe("Job Hunter Frontend - Fase 02 Descoberta de Oportunidades", () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.history.replaceState({}, "", "/");
    vi.restoreAllMocks();
  });

  it("renderiza listagem por frente, busca, paginação, salvar/dispensar e links com atribuição sem nofollow", async () => {
    vi.spyOn(api.auth, "me").mockResolvedValue({
      authenticated: true,
      user: mockUser,
      csrf_token: "test-csrf",
    });
    vi.spyOn(api.profile, "getBundle").mockResolvedValue(mockBundle);
    vi.spyOn(api.opportunities, "listSources").mockResolvedValue(mockSources);

    const oppJr = buildMockOpportunity();
    const oppJrFreela = buildMockOpportunity({
      id: "opp-jr-freela",
      external_id: "109002",
      title: "Freelance Junior Python API Developer",
      opportunity_type: "freelance",
      seniority_level: "junior",
      employment_type: "freelance",
    });
    const listSpy = vi
      .spyOn(api.opportunities, "list")
      .mockImplementation(async (params = {}) => {
        if (params.seniority === "internship") {
          return {
            items: [
              buildMockOpportunity({
                id: "opp-intern",
                title: "Estágio Engenharia de Dados",
                opportunity_type: "internship",
                seniority_level: "internship",
                employment_type: "internship",
                eligibility_unknown: true,
                match: {
                  eligible: true,
                  geographic_eligibility: "unknown",
                  inclusion_reasons: [
                    "Trabalho remoto com elegibilidade geográfica não especificada.",
                  ],
                  exclusion_reasons: [],
                },
              }),
            ],
            total: 1,
            page: 1,
            page_size: 10,
            total_pages: 1,
          };
        }
        if (params.employment_type === "freelance") {
          return {
            items: [oppJrFreela],
            total: 1,
            page: 1,
            page_size: 10,
            total_pages: 1,
          };
        }
        return {
          items: [oppJr, oppJrFreela],
          total: 20,
          page: params.page || 1,
          page_size: 10,
          total_pages: 2,
        } satisfies OpportunityListResponse;
      });

    const updateStateSpy = vi
      .spyOn(api.opportunities, "updateState")
      .mockResolvedValue({
        is_saved: true,
        is_dismissed: false,
        last_viewed_at: null,
      });

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText(/Cidade Exemplo/i)).toBeInTheDocument();
    });

    // Navega para Desenvolvedor Júnior (filtra por seniority="junior", sem depender de type legado)
    fireEvent.click(screen.getAllByRole("button", { name: /^Desenvolvedor Júnior$/i })[0]);

    await waitFor(() => {
      expect(screen.getByText("Junior Python Backend Developer")).toBeInTheDocument();
      expect(screen.getByText("Freelance Junior Python API Developer")).toBeInTheDocument();
    });
    expect(listSpy).toHaveBeenCalledWith(
      expect.objectContaining({ seniority: "junior" })
    );
    expect(listSpy.mock.calls.some((call) => call[0]?.type !== undefined)).toBe(false);
    expect(screen.getAllByText(/Área: Backend/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/Nível: Júnior/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/^Compatível$/i).length).toBeGreaterThanOrEqual(1);
    expect(
      screen.getAllByText(/Experiência: Sem exigência de experiência prévia/i).length
    ).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/Especialidades secundárias:/i).length).toBeGreaterThanOrEqual(1);
    expect(
      screen.getAllByText(/APIs, Integrações e Automação/i).length
    ).toBeGreaterThanOrEqual(2);

    const senioritySelect = screen.getByLabelText(/Senioridade/i);
    fireEvent.change(senioritySelect, { target: { value: "entry_level" } });
    await waitFor(() => {
      expect(listSpy).toHaveBeenCalledWith(
        expect.objectContaining({ seniority: "entry_level" })
      );
    });
    fireEvent.change(senioritySelect, { target: { value: "junior" } });

    const areaSelect = screen.getByLabelText(/Área profissional/i);
    fireEvent.change(areaSelect, { target: { value: "backend" } });
    await waitFor(() => {
      expect(listSpy).toHaveBeenCalledWith(
        expect.objectContaining({ seniority: "junior", area: "backend" })
      );
    });

    // Verifica atribuição visível e ausência de nofollow nos links de saída
    const outboundLink = screen.getAllByRole("link", {
      name: /Ver oportunidade original/i,
    })[0];
    expect(outboundLink).toHaveAttribute(
      "href",
      "https://remoteok.com/remote-jobs/junior-python-109001"
    );
    expect(outboundLink.getAttribute("rel") || "").not.toContain("nofollow");

    // Salva oportunidade
    fireEvent.click(screen.getAllByRole("button", { name: /^Salvar$/i })[0]);
    await waitFor(() => {
      expect(updateStateSpy).toHaveBeenCalledWith("opp-1", { is_saved: true });
    });

    // Paginação Próxima página
    fireEvent.click(screen.getByRole("button", { name: /Próxima/i }));
    await waitFor(() => {
      expect(listSpy).toHaveBeenCalledWith(
        expect.objectContaining({ seniority: "junior", page: 2 })
      );
    });

    // Navega para Freelancers e confirma mesma vaga Júnior Freelance via employment_type="freelance"
    fireEvent.click(screen.getAllByRole("button", { name: /^Freelancers$/i })[0]);
    await waitFor(() => {
      expect(listSpy).toHaveBeenCalledWith(
        expect.objectContaining({ employment_type: "freelance" })
      );
    });
    expect(screen.getByText("Freelance Junior Python API Developer")).toBeInTheDocument();

    // Navega para Estágios (filtra por seniority="internship") e verifica elegibilidade geográfica desconhecida
    fireEvent.click(screen.getAllByRole("button", { name: /^Estágios$/i })[0]);
    await waitFor(() => {
      expect(listSpy).toHaveBeenCalledWith(
        expect.objectContaining({ seniority: "internship" })
      );
    });
    await waitFor(() => {
      expect(screen.getByText("Estágio Engenharia de Dados")).toBeInTheDocument();
    });
    expect(
      screen.getByText(/Elegibilidade geográfica não confirmada/i)
    ).toBeInTheDocument();

    // Dispensa estágio
    fireEvent.click(screen.getByRole("button", { name: /^Dispensar$/i }));
    await waitFor(() => {
      expect(updateStateSpy).toHaveBeenCalledWith("opp-intern", {
        is_dismissed: true,
      });
    });
  });

  it("exibe estados vazio e de erro e captura links do PWA Web Share Target para cadastro manual", async () => {
    window.history.replaceState(
      {},
      "",
      "/?share_title=Freela%20API%20FastAPI&share_url=https%3A%2F%2Fexample.org%2Ffreela&share_text=Projeto%20Python"
    );

    vi.spyOn(api.auth, "me").mockResolvedValue({
      authenticated: true,
      user: mockUser,
      csrf_token: "test-csrf",
    });
    vi.spyOn(api.profile, "getBundle").mockResolvedValue(mockBundle);
    vi.spyOn(api.opportunities, "listSources").mockResolvedValue([]);

    let callCount = 0;
    vi.spyOn(api.opportunities, "list").mockImplementation(async () => {
      callCount += 1;
      if (callCount === 1) {
        throw new Error("Falha temporária de rede");
      }
      return {
        items: [],
        total: 0,
        page: 1,
        page_size: 10,
        total_pages: 1,
      };
    });

    const createManualSpy = vi
      .spyOn(api.opportunities, "createManual")
      .mockResolvedValue(
        buildMockOpportunity({
          id: "manual-1",
          is_manual: true,
          source: null,
          title: "Freela API FastAPI",
          opportunity_type: "freelance",
          source_url: "https://example.org/freela",
        })
      );

    render(<App />);

    await waitFor(() => {
      expect(
        screen.getByText(/Link recebido via Web Share Target \(PWA\)/i)
      ).toBeInTheDocument();
    });

    // Converte link compartilhado via PWA no modal de cadastro manual
    fireEvent.click(
      screen.getByRole("button", {
        name: /Cadastrar como Oportunidade Privada/i,
      })
    );

    await waitFor(() => {
      expect(
        screen.getByLabelText(/Título da oportunidade/i)
      ).toHaveValue("Freela API FastAPI");
    });
    expect(screen.getByLabelText(/URL oficial da oportunidade/i)).toHaveValue(
      "https://example.org/freela"
    );

    fireEvent.change(screen.getByLabelText(/Categoria alvo/i), {
      target: { value: "freelance" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: /Salvar Oportunidade Privada/i })
    );

    await waitFor(() => {
      expect(createManualSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          title: "Freela API FastAPI",
          opportunity_type: "freelance",
          source_url: "https://example.org/freela",
        })
      );
    });

    // Na aba Freelancers: 1a tentativa falha (estado de erro) e Retry cai no estado vazio
    await waitFor(() => {
      expect(
        screen.getByText(/Não foi possível carregar as oportunidades/i)
      ).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /Tentar novamente/i }));

    await waitFor(() => {
      expect(
        screen.getByText(/Nenhuma oportunidade encontrada com os filtros atuais/i)
      ).toBeInTheDocument();
    });
  });
});

describe("Job Hunter Frontend - Fase 03.1 Pipeline de Candidaturas", () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.history.replaceState({}, "", "/");
    vi.restoreAllMocks();
  });

  it("acompanha vaga do catálogo, renderiza Kanban/indicadores, sinaliza prazo vencido e faz reversão em falha de movimentação", async () => {
    vi.spyOn(api.auth, "me").mockResolvedValue({
      authenticated: true,
      user: mockUser,
      csrf_token: "test-csrf",
    });
    vi.spyOn(api.profile, "getBundle").mockResolvedValue(mockBundle);
    vi.spyOn(api.opportunities, "listSources").mockResolvedValue(mockSources);

    const oppJr = buildMockOpportunity();
    vi.spyOn(api.opportunities, "list").mockResolvedValue({
      items: [oppJr],
      total: 1,
      page: 1,
      page_size: 10,
      total_pages: 1,
    });

    const createdFromOpp = {
      id: "app-opp-1",
      opportunity_id: "opp-1",
      opportunity_source_status: "active",
      company_name: "Acme Cloud",
      role_title: "Junior Python Backend Developer",
      personal_summary: "Build FastAPI services.",
      source_name: "Remote OK",
      source_url: "https://remoteok.com/remote-jobs/junior-python-109001",
      application_url: "https://remoteok.com/remote-jobs/junior-python-109001",
      location_text: "Worldwide",
      employment_type: "pj" as const,
      work_mode: "remote" as const,
      seniority_level: "junior" as const,
      status: "interested" as const,
      status_label: "Interesse",
      is_closed: false,
      applied_at: null,
      interview_at: null,
      assessment_deadline_at: null,
      expected_response_at: null,
      next_action: "Preparar portfólio",
      next_action_due_at: "2020-01-01T12:00:00Z",
      next_deadline_at: "2020-01-01T12:00:00Z",
      next_deadline_label: "Próxima ação",
      notes: "Vaga aderente.",
      closed_at: null,
      created_at: "2026-11-16T00:00:00Z",
      updated_at: "2026-11-16T00:10:00Z",
      status_history: [
        {
          id: "h-1",
          from_status: null,
          from_status_label: null,
          to_status: "interested",
          to_status_label: "Interesse",
          note: "Candidatura criada a partir de oportunidade do catálogo.",
          changed_at: "2026-11-16T00:00:00Z",
        },
      ],
    };

    const closedItem = {
      ...createdFromOpp,
      id: "app-closed-1",
      opportunity_id: null,
      role_title: "Estágio Backend Encerrado",
      company_name: "Beta Co",
      status: "rejected" as const,
      status_label: "Rejeitado",
      is_closed: true,
      next_deadline_at: null,
      next_deadline_label: null,
      closed_at: "2026-11-10T12:00:00Z",
    };

    const createAppSpy = vi
      .spyOn(api.applications, "create")
      .mockResolvedValue(createdFromOpp);

    vi.spyOn(api.applications, "kanban").mockResolvedValue({
      columns: [
        {
          status: "interested",
          label: "Interesse",
          is_closed: false,
          count: 1,
          items: [createdFromOpp],
        },
        {
          status: "preparing",
          label: "Preparação",
          is_closed: false,
          count: 0,
          items: [],
        },
        {
          status: "applied",
          label: "Candidatura enviada",
          is_closed: false,
          count: 0,
          items: [],
        },
        {
          status: "assessment",
          label: "Teste técnico",
          is_closed: false,
          count: 0,
          items: [],
        },
        {
          status: "interview",
          label: "Entrevista",
          is_closed: false,
          count: 0,
          items: [],
        },
        {
          status: "offer",
          label: "Proposta",
          is_closed: false,
          count: 0,
          items: [],
        },
      ],
      closed_columns: [
        {
          status: "accepted",
          label: "Aprovado",
          is_closed: true,
          count: 0,
          items: [],
        },
        {
          status: "rejected",
          label: "Rejeitado",
          is_closed: true,
          count: 1,
          items: [closedItem],
        },
        {
          status: "withdrawn",
          label: "Desistência",
          is_closed: true,
          count: 0,
          items: [],
        },
      ],
      closed_items: [closedItem],
      indicators: {
        total_count: 2,
        active_count: 1,
        applied_count: 0,
        assessment_count: 0,
        interview_count: 0,
        offer_count: 0,
        accepted_count: 0,
        rejected_count: 1,
        withdrawn_count: 0,
        closed_count: 1,
        status_counts: {
          interested: 1,
          preparing: 0,
          applied: 0,
          assessment: 0,
          interview: 0,
          offer: 0,
          accepted: 0,
          rejected: 1,
          withdrawn: 0,
        },
      },
      labels: {
        interested: "Interesse",
        preparing: "Preparação",
        applied: "Candidatura enviada",
        assessment: "Teste técnico",
        interview: "Entrevista",
        offer: "Proposta",
        accepted: "Aprovado",
        rejected: "Rejeitado",
        withdrawn: "Desistência",
      },
    });

    vi.spyOn(api.applications, "changeStatus").mockRejectedValueOnce(
      new ApiError("Falha simulada de servidor", 500)
    );

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText(/Cidade Exemplo/i)).toBeInTheDocument();
    });

    // 1. Navega para Desenvolvedor Júnior e acompanha vaga do catálogo
    fireEvent.click(
      screen.getAllByRole("button", { name: /^Desenvolvedor Júnior$/i })[0]
    );
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /Acompanhar candidatura/i })
      ).toBeInTheDocument();
    });

    fireEvent.click(
      screen.getByRole("button", { name: /Acompanhar candidatura/i })
    );
    await waitFor(() => {
      expect(createAppSpy).toHaveBeenCalledWith({ opportunity_id: "opp-1" });
      expect(
        screen.getByRole("button", { name: /No pipeline: Interesse/i })
      ).toBeInTheDocument();
    });

    // 2. Navega para Candidaturas e valida Kanban, prazo vencido, encerradas separadas e reversão em erro 500
    fireEvent.click(
      screen.getAllByRole("button", { name: /^Candidaturas$/i })[0]
    );

    await waitFor(() => {
      expect(
        screen.getAllByText("Junior Python Backend Developer").length
      ).toBeGreaterThanOrEqual(1);
    });
    expect(screen.getByText(/Candidaturas ativas/i)).toBeInTheDocument();
    expect(
      screen.getByTestId("closed-applications-section")
    ).toHaveTextContent("Estágio Backend Encerrado");
    expect(screen.getAllByText(/Prazo vencido/i).length).toBeGreaterThanOrEqual(
      1
    );

    // Simula falha de movimentação e valida reversão otimista + exibição de erro
    const desktopColSelect = screen.getByLabelText(
      /Mover etapa de Junior Python Backend Developer/i
    );
    fireEvent.change(desktopColSelect, { target: { value: "applied" } });
    await waitFor(() => {
      expect(
        screen.getByText(/Falha simulada de servidor/i)
      ).toBeInTheDocument();
      expect(
        screen.getByLabelText(/Mover etapa de Junior Python Backend Developer/i)
      ).toHaveValue("interested");
    });

    // Abre detalhes e verifica histórico de movimentações
    fireEvent.click(screen.getAllByRole("button", { name: /Abrir detalhes/i })[0]);
    await waitFor(() => {
      expect(
        screen.getByText(/Histórico de Movimentações \(1\)/i)
      ).toBeInTheDocument();
    });
  });
});

describe("Job Hunter Frontend - Fase 03.2 Gestão Avançada de Processos Seletivos", () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.history.replaceState({}, "", "/");
    vi.restoreAllMocks();
  });

  function buildBaseKanbanItem(): ApplicationItem {
    return {
      id: "app-32-1",
      opportunity_id: "opp-1",
      opportunity_source_status: "active",
      company_name: "Orbit Cloud",
      role_title: "Backend Python Engineer Junior",
      personal_summary: "Atuação com FastAPI e PostgreSQL.",
      source_name: "Remote OK",
      source_url: "https://remoteok.com/remote-jobs/orbit-32",
      application_url: "https://apply.example.org/orbit-32",
      location_text: "Remoto - Brasil",
      employment_type: "pj" as const,
      work_mode: "remote" as const,
      seniority_level: "junior" as const,
      status: "interview" as const,
      status_label: "Entrevista",
      is_closed: false,
      applied_at: "2026-11-01T12:00:00Z",
      interview_at: "2026-11-20T18:00:00Z",
      assessment_deadline_at: null,
      expected_response_at: null,
      next_action: "Revisar arquitetura REST",
      next_action_due_at: null,
      next_deadline_at: "2026-11-20T18:00:00Z",
      next_deadline_label: "Entrevista (Entrevista Técnica)",
      notes: "Processo estratégico.",
      closed_at: null,
      last_external_interaction_at: null,
      last_external_interaction_type: null,
      last_external_interaction_type_label: null,
      last_external_interaction_note: null,
      created_at: "2026-11-01T10:00:00Z",
      updated_at: "2026-11-10T10:00:00Z",
      status_history: [
        {
          id: "hist-32-1",
          from_status: null,
          from_status_label: null,
          to_status: "interview",
          to_status_label: "Entrevista",
          note: "Avançou para entrevista.",
          changed_at: "2026-11-10T10:00:00Z",
        },
      ],
      interviews: [
        {
          id: "iv-32-1",
          application_id: "app-32-1",
          round_name: "Triagem RH",
          interview_format: "online",
          interview_format_label: "Online / Vídeo",
          scheduled_at: "2026-11-20T18:00:00Z",
          previous_scheduled_at: null,
          duration_minutes: 45,
          meeting_url: "https://meet.google.com/aaa-bbbb-ccc",
          interviewers: "Mariana",
          notes: "Conversa sobre trajetória.",
          feedback_received: null,
          status: "scheduled",
          status_label: "Agendada",
          completed_at: null,
          created_at: "2026-11-10T10:00:00Z",
          updated_at: "2026-11-10T10:00:00Z",
        },
      ],
      assessments: [],
      contacts: [],
    };
  }

  function mockKanbanResponse(item: ReturnType<typeof buildBaseKanbanItem>) {
    return {
      columns: [
        { status: "interested" as const, label: "Interesse", is_closed: false, count: 0, items: [] },
        { status: "preparing" as const, label: "Preparação", is_closed: false, count: 0, items: [] },
        { status: "applied" as const, label: "Candidatura enviada", is_closed: false, count: 0, items: [] },
        { status: "assessment" as const, label: "Teste técnico", is_closed: false, count: 0, items: [] },
        { status: "interview" as const, label: "Entrevista", is_closed: false, count: 1, items: [item] },
        { status: "offer" as const, label: "Proposta", is_closed: false, count: 0, items: [] },
      ],
      closed_columns: [],
      closed_items: [],
      indicators: {
        total_count: 1,
        active_count: 1,
        applied_count: 1,
        assessment_count: 0,
        interview_count: 1,
        offer_count: 0,
        accepted_count: 0,
        rejected_count: 0,
        withdrawn_count: 0,
        closed_count: 0,
        status_counts: { interview: 1 },
      },
      labels: { interview: "Entrevista" },
    };
  }

  it("exibe Agenda responsiva em 390x844 com retry de erro, estado vazio e Acompanhamento com cópia de follow-up", async () => {
    window.innerWidth = 390;
    window.innerHeight = 844;
    window.dispatchEvent(new Event("resize"));

    const writeTextMock = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText: writeTextMock },
      configurable: true,
    });

    const baseItem = buildBaseKanbanItem();
    vi.spyOn(api.auth, "me").mockResolvedValue({
      authenticated: true,
      user: mockUser,
      csrf_token: "test-csrf",
    });
    vi.spyOn(api.profile, "getBundle").mockResolvedValue(mockBundle);
    vi.spyOn(api.opportunities, "listSources").mockResolvedValue(mockSources);
    vi.spyOn(api.opportunities, "list").mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 10,
      total_pages: 1,
    });
    vi.spyOn(api.applications, "kanban").mockResolvedValue(
      mockKanbanResponse(baseItem)
    );

    const imminentIso = new Date(Date.now() + 2 * 3600 * 1000).toISOString();
    const expectedLocalTime = new Date(imminentIso).toLocaleTimeString("pt-BR", {
      hour: "2-digit",
      minute: "2-digit",
    });

    let agendaCall = 0;
    vi.spyOn(api.applications, "agenda").mockImplementation(async () => {
      agendaCall += 1;
      if (agendaCall === 1) {
        throw new ApiError("Erro temporário na agenda", 500);
      }
      if (agendaCall === 2) {
        return {
          days: 30,
          summary: {
            total_count: 2,
            overdue_count: 1,
            imminent_24h_count: 1,
            today_count: 1,
            interviews_count: 1,
            assessments_count: 1,
            actions_count: 0,
            reference_now_utc: new Date().toISOString(),
          },
          events: [
            {
              id: "assessment:a-overdue",
              event_type: "assessment",
              source_kind: "structured",
              entity_id: "a-overdue",
              application_id: "app-32-1",
              company_name: "Orbit Cloud",
              role_title: "Backend Python Engineer Junior",
              application_status: "interview",
              application_status_label: "Entrevista",
              title: "Teste técnico: API Python",
              subtitle: "Plataforma: GitHub",
              scheduled_at: new Date(Date.now() - 24 * 3600 * 1000).toISOString(),
              status: "pending",
              status_label: "Pendente",
              is_overdue: true,
              is_today: false,
              is_imminent: false,
              urgency: "overdue",
              action_url: "https://github.com/orbit/challenge",
            },
            {
              id: "interview:iv-32-1",
              event_type: "interview",
              source_kind: "structured",
              entity_id: "iv-32-1",
              application_id: "app-32-1",
              company_name: "Orbit Cloud",
              role_title: "Backend Python Engineer Junior",
              application_status: "interview",
              application_status_label: "Entrevista",
              title: "Entrevista: Triagem RH",
              subtitle: "Online / Vídeo • Mariana",
              scheduled_at: imminentIso,
              status: "scheduled",
              status_label: "Agendada",
              is_overdue: false,
              is_today: true,
              is_imminent: true,
              urgency: "imminent",
              action_url: "https://meet.google.com/aaa-bbbb-ccc",
            },
          ],
        };
      }
      return {
        days: 7,
        summary: {
          total_count: 0,
          overdue_count: 0,
          imminent_24h_count: 0,
          today_count: 0,
          interviews_count: 0,
          assessments_count: 0,
          actions_count: 0,
          reference_now_utc: new Date().toISOString(),
        },
        events: [],
      };
    });

    vi.spyOn(api.applications, "stale").mockResolvedValue({
      stale_days_param: 7,
      total_count: 1,
      items: [
        {
          application_id: "app-32-1",
          company_name: "Orbit Cloud",
          role_title: "Backend Python Engineer Junior",
          status: "applied",
          status_label: "Candidatura enviada",
          last_external_interaction_at: null,
          reference_timestamp_at: "2026-11-01T12:00:00Z",
          reference_kind: "applied_at",
          reference_description: "Data de envio da candidatura",
          days_without_external_interaction: 15,
          threshold_days: 10,
          notice: "Sem interação externa registrada há 15 dia(s).",
          recommended_follow_up:
            "Enviar mensagem cordial de acompanhamento da candidatura.",
        },
      ],
    });

    vi.spyOn(api.applications, "followUpTemplate").mockResolvedValue({
      application_id: "app-32-1",
      subject: "Acompanhamento — Processo seletivo Backend Python Engineer Junior",
      message:
        "Olá, Mariana,\n\nGostaria de acompanhar minha candidatura na Orbit Cloud.",
      recipient_name: "Mariana",
      recipient_email: "mariana@orbit.example.com",
      context_summary: "Baseado no envio da candidatura.",
      used_facts: ["Cargo: Backend Python Engineer Junior"],
      disclaimer: "Mensagem determinística gerada com base nos registros salvos.",
    });

    render(<App />);
    await waitFor(() => {
      expect(
        screen.getAllByRole("button", { name: /^Candidaturas$/i }).length
      ).toBeGreaterThanOrEqual(1);
    });

    fireEvent.click(
      screen.getAllByRole("button", { name: /^Candidaturas$/i })[0]
    );

    // Muda para aba Agenda: 1a chamada falha -> Retry carrega compromissos com hora local
    fireEvent.click(screen.getByRole("tab", { name: /^Agenda$/i }));
    await waitFor(() => {
      expect(screen.getByText(/Erro temporário na agenda/i)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /Tentar novamente/i }));
    await waitFor(() => {
      expect(screen.getByText(/Entrevista: Triagem RH/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/Teste técnico: API Python/i)).toBeInTheDocument();
    expect(screen.getByText(expectedLocalTime)).toBeInTheDocument();
    expect(screen.getByTestId("agenda-chronological-list")).toBeInTheDocument();

    // Testa estado vazio ao filtrar para 7 dias (3a chamada mockada vazia)
    fireEvent.click(screen.getByRole("button", { name: /^7 dias$/i }));
    await waitFor(() => {
      expect(
        screen.getByText(/Nenhum compromisso ou prazo encontrado nesta janela/i)
      ).toBeInTheDocument();
    });

    // Muda para Acompanhamento e copia follow-up determinístico
    fireEvent.click(screen.getByRole("tab", { name: /^Acompanhamento$/i }));
    await waitFor(() => {
      expect(
        screen.getByText(/15 dia\(s\) sem interação registrada/i)
      ).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /Copiar follow-up/i }));
    await waitFor(() => {
      expect(writeTextMock).toHaveBeenCalledWith(
        expect.stringContaining("Olá, Mariana")
      );
      expect(screen.getByText(/Mensagem copiada!/i)).toBeInTheDocument();
    });
  });

  it("gerencia Entrevistas (com reagendamento), Testes Técnicos, Contatos e Interação Externa no modal de detalhes", async () => {
    const initialItem = buildBaseKanbanItem();
    let currentItem = { ...initialItem };

    vi.spyOn(api.auth, "me").mockResolvedValue({
      authenticated: true,
      user: mockUser,
      csrf_token: "test-csrf",
    });
    vi.spyOn(api.profile, "getBundle").mockResolvedValue(mockBundle);
    vi.spyOn(api.opportunities, "listSources").mockResolvedValue(mockSources);
    vi.spyOn(api.opportunities, "list").mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 10,
      total_pages: 1,
    });
    vi.spyOn(api.applications, "kanban").mockImplementation(async () =>
      mockKanbanResponse(currentItem)
    );
    vi.spyOn(api.applications, "get").mockImplementation(async () => currentItem);

    const updateIvSpy = vi
      .spyOn(api.applications, "updateInterview")
      .mockImplementation(async (_appId, ivId, payload) => {
        const baseIv = (currentItem.interviews ?? [])[0];
        const updatedIv = {
          ...baseIv,
          id: ivId,
          previous_scheduled_at: baseIv.scheduled_at,
          scheduled_at: payload.scheduled_at || baseIv.scheduled_at,
        };
        currentItem = {
          ...currentItem,
          interviews: [updatedIv],
        };
        return updatedIv;
      });

    const createAsmtSpy = vi
      .spyOn(api.applications, "createAssessment")
      .mockImplementation(async (_appId, payload) => {
        const createdAsmt = {
          id: "asmt-new-1",
          application_id: "app-32-1",
          title: payload.title || "Desafio Novo",
          description: payload.description || null,
          platform: payload.platform || null,
          instructions_url: payload.instructions_url || null,
          submission_url: payload.submission_url || null,
          deadline_at: payload.deadline_at || null,
          submitted_at: null,
          status: payload.status || "pending",
          status_label: "Pendente",
          is_overdue: false,
          is_due_soon_24h: false,
          feedback: null,
          notes: null,
          created_at: "2026-11-16T12:00:00Z",
          updated_at: "2026-11-16T12:00:00Z",
        };
        currentItem = {
          ...currentItem,
          assessments: [createdAsmt],
        };
        return createdAsmt;
      });

    const createContactSpy = vi
      .spyOn(api.applications, "createContact")
      .mockImplementation(async (_appId, payload) => {
        const createdCt = {
          id: "ct-new-1",
          application_id: "app-32-1",
          name: payload.name || "Recrutador",
          role_title: payload.role_title || null,
          email: payload.email || null,
          linkedin_url: payload.linkedin_url || null,
          notes: payload.notes || null,
          created_at: "2026-11-16T12:00:00Z",
          updated_at: "2026-11-16T12:00:00Z",
        };
        currentItem = {
          ...currentItem,
          contacts: [createdCt],
        };
        return createdCt;
      });

    const extSpy = vi
      .spyOn(api.applications, "recordExternalInteraction")
      .mockImplementation(async (_appId, payload) => {
        currentItem = {
          ...currentItem,
          last_external_interaction_at:
            payload.interaction_at || "2026-11-16T15:00:00Z",
          last_external_interaction_type: payload.interaction_type,
          last_external_interaction_type_label: "E-mail",
          last_external_interaction_note: payload.note || null,
        };
        return currentItem;
      });

    render(<App />);
    await waitFor(() => {
      expect(
        screen.getAllByRole("button", { name: /^Candidaturas$/i }).length
      ).toBeGreaterThanOrEqual(1);
    });
    fireEvent.click(
      screen.getAllByRole("button", { name: /^Candidaturas$/i })[0]
    );
    await waitFor(() => {
      expect(
        screen.getAllByRole("button", { name: /Abrir detalhes/i }).length
      ).toBeGreaterThanOrEqual(1);
    });

    fireEvent.click(
      screen.getAllByRole("button", { name: /Abrir detalhes/i })[0]
    );
    await waitFor(() => {
      expect(screen.getByRole("tab", { name: /^Geral$/i })).toBeInTheDocument();
    });

    // 1. Aba Entrevistas -> reagendar rodada existente
    fireEvent.click(screen.getByRole("tab", { name: /^Entrevistas/i }));
    await waitFor(() => {
      expect(screen.getByText("Triagem RH")).toBeInTheDocument();
    });
    fireEvent.click(
      screen.getByRole("button", { name: /Editar \/ Reagendar/i })
    );
    fireEvent.change(screen.getByLabelText(/Data e hora \(local\)/i), {
      target: { value: "2026-11-25T14:30" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: /Salvar reagendamento/i })
    );
    await waitFor(() => {
      expect(updateIvSpy).toHaveBeenCalledWith(
        "app-32-1",
        "iv-32-1",
        expect.objectContaining({
          scheduled_at: new Date("2026-11-25T14:30").toISOString(),
        })
      );
      expect(screen.getByText(/Reagendada \(horário anterior:/i)).toBeInTheDocument();
    });

    // 2. Aba Testes técnicos -> cadastrar desafio
    fireEvent.click(screen.getByRole("tab", { name: /^Testes técnicos/i }));
    fireEvent.change(screen.getByLabelText(/Título do desafio/i), {
      target: { value: "API REST FastAPI + Testes" },
    });
    fireEvent.change(screen.getByLabelText(/Plataforma/i), {
      target: { value: "GitHub" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: /Salvar desafio técnico/i })
    );
    await waitFor(() => {
      expect(createAsmtSpy).toHaveBeenCalledWith(
        "app-32-1",
        expect.objectContaining({
          title: "API REST FastAPI + Testes",
          platform: "GitHub",
        })
      );
      expect(screen.getByText("API REST FastAPI + Testes")).toBeInTheDocument();
    });

    // 3. Aba Contatos -> adicionar recrutador
    fireEvent.click(screen.getByRole("tab", { name: /^Contatos/i }));
    fireEvent.change(screen.getByLabelText(/^Nome \*/i), {
      target: { value: "Lucas Recruiter" },
    });
    fireEvent.change(screen.getByLabelText(/E-mail/i), {
      target: { value: "lucas@orbit.example.com" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Salvar contato/i }));
    await waitFor(() => {
      expect(createContactSpy).toHaveBeenCalledWith(
        "app-32-1",
        expect.objectContaining({
          name: "Lucas Recruiter",
          email: "lucas@orbit.example.com",
        })
      );
      expect(screen.getByText("Lucas Recruiter")).toBeInTheDocument();
    });

    // 4. Aba Acompanhamento -> registrar interação externa explícita dentro do modal
    const modalDialog = screen.getByRole("dialog");
    fireEvent.click(
      within(modalDialog).getByRole("tab", { name: /^Acompanhamento$/i })
    );
    fireEvent.change(screen.getByLabelText(/Resumo da conversa/i), {
      target: { value: "Retorno por e-mail confirmando próxima etapa." },
    });
    fireEvent.click(
      screen.getByRole("button", { name: /Registrar interação externa/i })
    );
    await waitFor(() => {
      expect(extSpy).toHaveBeenCalledWith(
        "app-32-1",
        expect.objectContaining({
          interaction_type: "email",
          note: "Retorno por e-mail confirmando próxima etapa.",
        })
      );
      expect(
        screen.getByText(/Retorno por e-mail confirmando próxima etapa\./i)
      ).toBeInTheDocument();
    });
  });
});

describe("Job Hunter Frontend - Fase 04.1 Materiais & Currículo Direcionado Determinístico", () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.history.replaceState({}, "", "/");
    vi.restoreAllMocks();
  });

  function buildSampleMaterial(overrides?: Partial<MaterialDetailResponse>): MaterialDetailResponse {
    return {
      id: "mat-41-1",
      opportunity_id: "opp-1",
      opportunity_title: "Junior Python Backend Developer",
      opportunity_company_name: "Orbit Cloud",
      material_type: "resume",
      title: "Currículo — Junior Python Backend Developer (Orbit Cloud)",
      target_language: "pt-BR",
      latest_version_number: 1,
      has_approved_version: false,
      versions: [
        {
          id: "ver-41-1",
          material_id: "mat-41-1",
          version_number: 1,
          origin: "generated",
          parent_version_id: null,
          user_instructions: null,
          structured_content: {
            schema_version: 1,
            language: "pt-BR",
            header: {
              full_name: "Usuário Teste",
              professional_title: "Desenvolvedor Backend Python",
              location_text: "Cidade Exemplo, Estado Exemplo, Brasil",
              email: "usuario@example.com",
              phone: null,
              links: [],
              source_fact_keys: ["profile:22222222-2222-2222-2222-222222222222"],
              provenance: "confirmed_fact",
            },
            summary: {
              text: "Desenvolvedor focado em Python e FastAPI.",
              source_fact_keys: ["profile:22222222-2222-2222-2222-222222222222"],
              provenance: "confirmed_fact",
            },
            target_alignment: {
              target_role: "Junior Python Backend Developer",
              company_name: "Orbit Cloud",
              highlighted_requirements: ["Python", "FastAPI"],
              alignment_note: "Evidências confirmadas aderentes aos requisitos: Python, FastAPI.",
              source_fact_keys: [],
              provenance: "confirmed_fact",
            },
            experiences: [
              {
                entity_id: "exp-1",
                company: "Suporte Central",
                role: "Suporte Técnico",
                period_label: "01/2023 – 06/2024",
                description: "Automação de rotinas em Python.",
                technologies: ["Python"],
                experience_type: "other",
                eligible_as_target_role: false,
                source_fact_keys: ["experience:exp-1"],
                provenance: "confirmed_fact",
              },
            ],
            projects: [
              {
                entity_id: "proj-1",
                name: "Job Hunter",
                role: "Desenvolvedor",
                description: "Sistema determinístico em FastAPI e PostgreSQL.",
                technologies: ["Python", "FastAPI"],
                links: [],
                verified_results: "Cobertura de testes determinísticos.",
                source_fact_keys: ["project:proj-1"],
                provenance: "confirmed_fact",
              },
            ],
            education: [
              {
                entity_id: "edu-1",
                institution: "UF Teste",
                course: "Ciência da Computação",
                field_of_study: "Computação",
                education_status: "in_progress",
                status_label: "Em andamento",
                current_semester: "5º semestre",
                period_label: null,
                source_fact_keys: ["education:edu-1"],
                provenance: "confirmed_fact",
              },
            ],
            skills: [
              {
                entity_id: "sk-1",
                name: "FastAPI",
                category: "Backend",
                proficiency_level: "intermediate",
                proficiency_label: "Intermediário",
                notes: null,
                source_fact_keys: ["skill:sk-1"],
                provenance: "confirmed_fact",
              },
            ],
            languages: [
              {
                entity_id: "lg-1",
                language_name: "Português",
                proficiency_level: "native",
                proficiency_label: "Nativo",
                cefr_level: null,
                source_fact_keys: ["language:lg-1"],
                provenance: "confirmed_fact",
              },
            ],
            manual_notes: [],
            has_unverified_manual_edits: false,
          },
          source_facts_snapshot: { schema_version: 1, facts: {} },
          unconfirmed_warnings: [],
          missing_requirements: [],
          rendered_markdown: "# Usuário Teste\n\n## Resumo Profissional\nDesenvolvedor focado em Python e FastAPI.\n",
          is_approved: false,
          approved_at: null,
          is_linked_to_any_application: false,
          is_mutable: true,
          created_at: "2026-11-17T18:00:00Z",
          updated_at: "2026-11-17T18:00:00Z",
        },
      ],
      links: [],
      created_at: "2026-11-17T18:00:00Z",
      updated_at: "2026-11-17T18:00:00Z",
      ...overrides,
    };
  }

  it("permite pré-análise com bloqueio, confirmação em lote seletiva sem pré-seleção, geração, edição, aprovação, exportação e vínculo em 390x844 e 768x1024", async () => {
    window.innerWidth = 390;
    window.innerHeight = 844;

    vi.spyOn(api.auth, "me").mockResolvedValue({
      authenticated: true,
      user: mockUser,
      csrf_token: "csrf-41",
    });
    vi.spyOn(api.profile, "getBundle").mockResolvedValue(mockBundle);
    vi.spyOn(api.opportunities, "listSources").mockResolvedValue([]);
    vi.spyOn(api.opportunities, "list").mockResolvedValue({
      items: [
        buildMockOpportunity({
          tracked_application_id: "app-41-1",
          tracked_application_status: "interested",
        }),
      ],
      total: 1,
      page: 1,
      page_size: 12,
      total_pages: 1,
    });

    const blockedPreAnalysis: MaterialPreAnalysisResponse = {
      can_generate: false,
      blocking_reasons: [
        "Nenhum bloco substantivo confirmado foi encontrado no seu perfil.",
      ],
      target_language: "pt-BR",
      opportunity_context: {
        opportunity_id: "opp-1",
        application_id: "app-41-1",
        title: "Junior Python Backend Developer",
        company_name: "Orbit Cloud",
        professional_area: "backend",
        seniority_level: "junior",
        experience_summary: null,
        required_technologies: ["Python"],
        desirable_technologies: ["FastAPI"],
        all_technologies: ["Python", "FastAPI"],
        language: "pt-BR",
      },
      contact_preview: {
        profile_confirmed: true,
        has_full_name: true,
        has_email: true,
        has_phone: false,
        has_location: true,
        links_count: 1,
        location_label: "Cidade Exemplo, Estado Exemplo, Brasil",
      },
      used_facts: [],
      unconfirmed_warnings: [
        {
          entity_type: "skill",
          entity_id: "sk-pending-1",
          verification_status: "pending_validation",
          label: "FastAPI",
          summary: "Backend · intermediate",
          details: {},
          reason: "Habilidade técnica aguardando confirmação.",
          matched_requirements: ["FastAPI"],
          can_batch_confirm: true,
        },
        {
          entity_type: "project",
          entity_id: "proj-draft-1",
          verification_status: "draft",
          label: "Projeto Rascunho",
          summary: "Projeto profissional",
          details: {},
          reason: "Projeto em rascunho.",
          matched_requirements: [],
          can_batch_confirm: false,
        },
      ],
      missing_requirements: [
        {
          requirement: "FastAPI",
          requirement_kind: "desirable_technology",
          note: "Existe item não confirmado relacionado.",
          covered_by_unconfirmed: true,
        },
      ],
      confirmed_counts: {
        profile: 1,
        experiences: 0,
        projects: 0,
        educations: 0,
        skills: 0,
        languages: 1,
      },
    };

    const unblockedPreAnalysis: MaterialPreAnalysisResponse = {
      ...blockedPreAnalysis,
      can_generate: true,
      blocking_reasons: [],
      unconfirmed_warnings: [blockedPreAnalysis.unconfirmed_warnings[1]],
      missing_requirements: [],
      confirmed_counts: {
        ...blockedPreAnalysis.confirmed_counts,
        skills: 1,
      },
    };

    const preSpy = vi
      .spyOn(api.materials, "preAnalyze")
      .mockResolvedValueOnce(blockedPreAnalysis)
      .mockResolvedValue(unblockedPreAnalysis);

    const confirmBatchSpy = vi
      .spyOn(api, "profileConfirmBatch")
      .mockResolvedValue({
        confirmed_profile: false,
        confirmed_experiences: 0,
        confirmed_educations: 0,
        confirmed_skills: 1,
        confirmed_languages: 0,
        confirmed_projects: 0,
        total_confirmed: 1,
      });

    const initialMat = buildSampleMaterial();
    const initialResumeContent = initialMat.versions[0]
      .structured_content as ResumeStructuredContent;
    const editedMat = buildSampleMaterial({
      versions: [
        {
          ...initialMat.versions[0],
          origin: "manual_edit",
          structured_content: {
            ...initialResumeContent,
            summary: {
              text: "Resumo revisado para Orbit Cloud.",
              source_fact_keys: ["profile:22222222-2222-2222-2222-222222222222"],
              provenance: "manual_edit",
            },
            has_unverified_manual_edits: true,
          },
          rendered_markdown: "# Usuário Teste\n\n## Resumo Profissional\nResumo revisado para Orbit Cloud.\n",
        },
      ],
    });
    const approvedMat = buildSampleMaterial({
      has_approved_version: true,
      versions: [
        {
          ...editedMat.versions[0],
          is_approved: true,
          approved_at: "2026-11-17T18:10:00Z",
          is_mutable: false,
        },
      ],
    });
    const linkedMat = buildSampleMaterial({
      has_approved_version: true,
      versions: approvedMat.versions,
      links: [
        {
          id: "lnk-1",
          application_id: "app-41-1",
          application_role_title: "Junior Python Backend Developer",
          application_company_name: "Orbit Cloud",
          material_id: "mat-41-1",
          version_id: "ver-41-1",
          version_number: 1,
          linked_at: "2026-11-17T18:15:00Z",
          unlinked_at: null,
          is_active: true,
        },
      ],
    });

    vi.spyOn(api.materials, "create").mockResolvedValue(initialMat);
    const updateVerSpy = vi
      .spyOn(api.materials, "updateVersion")
      .mockResolvedValue(editedMat);
    const approveSpy = vi
      .spyOn(api.materials, "approveVersion")
      .mockResolvedValue(approvedMat);
    const exportSpy = vi
      .spyOn(api.materials, "exportVersion")
      .mockResolvedValue({
        material_id: "mat-41-1",
        version_id: "ver-41-1",
        version_number: 1,
        format: "markdown",
        filename_suggestion: "curriculo-v1.md",
        content: editedMat.versions[0].rendered_markdown,
        is_approved: true,
      });
    const linkSpy = vi
      .spyOn(api.materials, "link")
      .mockResolvedValue(linkedMat);

    render(<App />);
    await waitFor(() => {
      expect(screen.getByText(/Cidade Exemplo/i)).toBeInTheDocument();
    });

    fireEvent.click(
      screen.getAllByRole("button", { name: /^Desenvolvedor Júnior$/i })[0]
    );
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /Gerar currículo/i })
      ).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /Gerar currículo/i }));

    // 1. Verifica bloqueio inicial e checkbox SEM pré-seleção
    await waitFor(() => {
      expect(
        screen.getByText(/Geração bloqueada por integridade factual/i)
      ).toBeInTheDocument();
    });
    expect(
      screen.getByRole("button", { name: /Gerar Currículo Direcionado/i })
    ).toBeDisabled();
    const fastApiCheckbox = screen.getByRole("checkbox", { name: /FastAPI/i });
    expect(fastApiCheckbox).not.toBeChecked();
    expect(
      screen.getByRole("button", { name: /Confirmar selecionados \(0\)/i })
    ).toBeDisabled();

    // 2. Seleciona explicitamente FastAPI pendente e confirma em lote
    fireEvent.click(fastApiCheckbox);
    fireEvent.click(
      screen.getByRole("button", { name: /Confirmar selecionados \(1\)/i })
    );
    await waitFor(() => {
      expect(confirmBatchSpy).toHaveBeenCalledWith(
        expect.objectContaining({ skill_ids: ["sk-pending-1"] })
      );
      expect(preSpy).toHaveBeenCalledTimes(2);
      expect(
        screen.getByRole("button", { name: /Gerar Currículo Direcionado/i })
      ).not.toBeDisabled();
    });

    // 3. Muda viewport para tablet 768x1024, gera currículo e verifica separação Experiência vs Projeto + Educação Em andamento
    window.innerWidth = 768;
    window.innerHeight = 1024;
    fireEvent.click(
      screen.getByRole("button", { name: /Gerar Currículo Direcionado/i })
    );
    await waitFor(() => {
      expect(screen.getByText(/Experiência Profissional \(1\)/i)).toBeInTheDocument();
      expect(screen.getByText(/Projetos \(1\)/i)).toBeInTheDocument();
      expect(screen.getByText(/UF Teste · Em andamento/i)).toBeInTheDocument();
    });

    // 4. Edita resumo e salva rascunho -> exibe aviso de alteração manual antes de aprovar
    const summaryTextarea = screen.getByDisplayValue(
      "Desenvolvedor focado em Python e FastAPI."
    );
    fireEvent.change(summaryTextarea, {
      target: { value: "Resumo revisado para Orbit Cloud." },
    });
    fireEvent.click(screen.getByRole("button", { name: /Salvar rascunho/i }));
    await waitFor(() => {
      expect(updateVerSpy).toHaveBeenCalled();
      expect(
        screen.getByText(/Este rascunho contém alterações manuais/i)
      ).toBeInTheDocument();
    });

    // 5. Aprova versão e vincula à candidatura; valida exportação em Markdown
    fireEvent.click(screen.getByRole("button", { name: /Aprovar versão/i }));
    await waitFor(() => {
      expect(approveSpy).toHaveBeenCalledWith("mat-41-1", "ver-41-1");
      expect(
        screen.getByRole("button", { name: /Vincular à candidatura/i })
      ).toBeInTheDocument();
    });

    fireEvent.click(
      screen.getByRole("button", { name: /Vincular à candidatura/i })
    );
    await waitFor(() => {
      expect(linkSpy).toHaveBeenCalledWith("mat-41-1", {
        application_id: "app-41-1",
        version_id: "ver-41-1",
      });
    });

    fireEvent.click(
      screen.getByRole("button", { name: /Pré-visualização & Exportação/i })
    );
    fireEvent.click(screen.getByRole("button", { name: /Copiar Markdown/i }));
    await waitFor(() => {
      expect(exportSpy).toHaveBeenCalledWith("mat-41-1", "ver-41-1", "markdown");
    });
  });
});

describe("Job Hunter Frontend - Fase 04.1.2 Transições de Confirmação no Perfil", () => {
  beforeEach(() => {
    window.localStorage.clear();
    vi.restoreAllMocks();
  });

  it("permite confirmar projeto inicialmente em draft via Confirmar Projeto e confirma perfil em draft", async () => {
    const draftBundle: FullProfileBundle = {
      ...mockBundle,
      profile: {
        ...mockBundle.profile,
        verification_status: "draft",
        confirmed_at: null,
      },
      projects: [
        {
          ...mockBundle.projects[0],
          verification_status: "draft",
          confirmed_at: null,
        },
      ],
    };

    vi.spyOn(api.auth, "me").mockResolvedValue({
      authenticated: true,
      user: mockUser,
      csrf_token: "csrf-0412",
    });
    vi.spyOn(api.profile, "getBundle").mockResolvedValue(draftBundle);

    const updateProfileSpy = vi
      .spyOn(api.profile, "updateProfile")
      .mockResolvedValue({
        ...draftBundle.profile,
        verification_status: "confirmed",
        confirmed_at: "2026-11-17T22:00:00Z",
      });

    const updateProjectSpy = vi
      .spyOn(api.profile, "updateProject")
      .mockResolvedValue({
        ...draftBundle.projects[0],
        verification_status: "confirmed",
        confirmed_at: "2026-11-17T22:01:00Z",
      });

    render(<App />);

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /Gerenciar Perfil Completo/i })
      ).toBeInTheDocument();
    });

    fireEvent.click(
      screen.getByRole("button", { name: /Gerenciar Perfil Completo/i })
    );

    await waitFor(() => {
      expect(
        screen.getByLabelText(/Estado de validação destes dados gerais/i)
      ).toBeInTheDocument();
    });

    // Perfil inicialmente em draft seleciona confirmed e salva
    const profStatusSelect = screen.getByLabelText(
      /Estado de validação destes dados gerais/i
    ) as HTMLSelectElement;
    expect(profStatusSelect.value).toBe("draft");
    fireEvent.change(profStatusSelect, { target: { value: "confirmed" } });
    fireEvent.click(
      screen.getByRole("button", { name: /Salvar Dados Gerais/i })
    );

    await waitFor(() => {
      expect(updateProfileSpy).toHaveBeenCalledWith(
        expect.objectContaining({ verification_status: "confirmed" })
      );
      expect(
        screen.getByText(/Dados gerais do perfil salvo\(a\) com status Confirmado\./i)
      ).toBeInTheDocument();
    });

    // Navega para aba Projetos e clica Confirmar Projeto no item em draft
    fireEvent.click(screen.getByRole("tab", { name: /Projetos/i }));
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /Confirmar Projeto/i })
      ).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /Confirmar Projeto/i }));

    await waitFor(() => {
      expect(updateProjectSpy).toHaveBeenCalledWith(
        draftBundle.projects[0].id,
        expect.objectContaining({ verification_status: "confirmed" })
      );
      expect(
        screen.getByText(/Projeto "Projeto Exemplo" salvo\(a\) com status Confirmado\./i)
      ).toBeInTheDocument();
    });
  });

  it("reflete exatamente o status retornado pelo backend quando permanece draft ou reabre para pending_validation", async () => {
    const confirmedProfileBundle: FullProfileBundle = {
      ...mockBundle,
      profile: {
        ...mockBundle.profile,
        verification_status: "confirmed",
        confirmed_at: "2026-11-17T21:00:00Z",
      },
      projects: [
        {
          ...mockBundle.projects[0],
          verification_status: "draft",
          confirmed_at: null,
        },
      ],
    };

    vi.spyOn(api.auth, "me").mockResolvedValue({
      authenticated: true,
      user: mockUser,
      csrf_token: "csrf-0412-b",
    });
    vi.spyOn(api.profile, "getBundle").mockResolvedValue(confirmedProfileBundle);

    // Simula backend reabrindo perfil confirmado para pending_validation apos edicao factual
    vi.spyOn(api.profile, "updateProfile").mockResolvedValue({
      ...confirmedProfileBundle.profile,
      professional_title: "Engenheiro Backend Senior",
      verification_status: "pending_validation",
      confirmed_at: null,
    });

    // Simula backend mantendo projeto em draft apesar da solicitacao de confirmacao
    vi.spyOn(api.profile, "updateProject").mockResolvedValue({
      ...confirmedProfileBundle.projects[0],
      verification_status: "draft",
      confirmed_at: null,
    });

    render(<App />);

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /Gerenciar Perfil Completo/i })
      ).toBeInTheDocument();
    });
    fireEvent.click(
      screen.getByRole("button", { name: /Gerenciar Perfil Completo/i })
    );

    await waitFor(() => {
      expect(
        screen.getByLabelText(/Estado de validação destes dados gerais/i)
      ).toBeInTheDocument();
    });

    fireEvent.click(
      screen.getByRole("button", { name: /Salvar Dados Gerais/i })
    );

    await waitFor(() => {
      expect(
        screen.getByText(
          /Como houve alteração factual, a validação foi reaberta para Pendente de Validação\./i
        )
      ).toBeInTheDocument();
      const profStatusSelect = screen.getByLabelText(
        /Estado de validação destes dados gerais/i
      ) as HTMLSelectElement;
      expect(profStatusSelect.value).toBe("pending_validation");
    });

    expect(
      screen.queryByText(/salvo\(a\) com status Confirmado/i)
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: /Projetos/i }));
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /Confirmar Projeto/i })
      ).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /Confirmar Projeto/i }));

    await waitFor(() => {
      expect(
        screen.getByText(
          /Projeto "Projeto Exemplo" permaneceu em Rascunho e não pôde ser confirmado automaticamente\./i
        )
      ).toBeInTheDocument();
    });
  });
});

describe("Job Hunter Frontend - Fase 04.2 Propostas, Cartas e Mensagens Direcionadas", () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.history.replaceState({}, "", "/");
    vi.restoreAllMocks();
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
      configurable: true,
    });
  });

  function buildPhase042PreAnalysis(
    materialType: "resume" | "cover_letter" | "recruiter_message" | "freelance_proposal" | "application_answers"
  ): MaterialPreAnalysisResponse {
    return {
      can_generate: true,
      blocking_reasons: [],
      material_type: materialType,
      compatible_material_types: [
        "resume",
        "cover_letter",
        "recruiter_message",
        "application_answers",
      ],
      target_language: "pt-BR",
      opportunity_context: {
        opportunity_id: "opp-1",
        application_id: "app-42-1",
        title: "Desenvolvedor Python Júnior",
        company_name: "Orbit Cloud",
        professional_area: "backend",
        seniority_level: "junior",
        employment_type: "clt",
        opportunity_type: "job",
        experience_summary: null,
        required_technologies: ["Python"],
        desirable_technologies: ["FastAPI"],
        all_technologies: ["Python", "FastAPI"],
        language: "pt-BR",
      },
      contact_preview: {
        profile_confirmed: true,
        has_full_name: true,
        has_email: true,
        has_phone: false,
        has_location: true,
        links_count: 1,
        location_label: "Cidade Exemplo, Estado Exemplo, Brasil",
      },
      used_facts: [
        {
          fact_key: "project:proj-1",
          entity_type: "project",
          entity_id: "proj-1",
          confirmed_at: "2026-11-17T10:00:00Z",
          label: "Job Hunter",
          summary: "Sistema determinístico em Python e FastAPI.",
          relevance_score: 0.92,
          matched_requirements: ["Python", "FastAPI"],
          eligible_as_target_role: null,
        },
      ],
      unconfirmed_warnings: [],
      missing_requirements: [],
      additional_info_needed:
        materialType === "freelance_proposal"
          ? [
              {
                field_id: "availability",
                label: "Disponibilidade",
                question: "Informe sua disponibilidade semanal.",
                required: true,
                status: "pending",
                user_value: null,
              },
            ]
          : [],
      confirmed_counts: {
        profile: 1,
        experiences: 1,
        projects: 1,
        educations: 1,
        skills: 1,
        languages: 1,
      },
    };
  }

  it("permite escolher entre os 5 tipos, bloqueia aprovação de proposta freelance com campos pendentes até preencher em 390x844 e 768x1024 e trata erro de API", async () => {
    window.innerWidth = 390;
    window.innerHeight = 844;

    vi.spyOn(api.auth, "me").mockResolvedValue({
      authenticated: true,
      user: mockUser,
      csrf_token: "csrf-42",
    });
    vi.spyOn(api.profile, "getBundle").mockResolvedValue(mockBundle);
    vi.spyOn(api.opportunities, "listSources").mockResolvedValue([]);
    vi.spyOn(api.opportunities, "list").mockResolvedValue({
      items: [
        buildMockOpportunity({
          tracked_application_id: "app-42-1",
          tracked_application_status: "preparing",
        }),
      ],
      total: 1,
      page: 1,
      page_size: 12,
      total_pages: 1,
    });
    vi.spyOn(api.materials, "preAnalyze").mockImplementation(async (payload) =>
      buildPhase042PreAnalysis(payload.material_type || "resume")
    );

    const fpBlockedContent: FreelanceProposalStructuredContent = {
      schema_version: 1,
      material_type: "freelance_proposal",
      language: "pt-BR",
      header: {
        full_name: "Usuário Teste",
        professional_title: "Desenvolvedor Backend | Python & APIs",
        email: "usuario@example.com",
        phone: null,
        location_text: "Cidade Exemplo, Estado Exemplo, Brasil",
        links: [],
        source_fact_keys: ["profile:22222222-2222-2222-2222-222222222222"],
        provenance: "confirmed_fact",
      },
      introduction: {
        text: "Olá! Tenho interesse em colaborar com a entrega técnica de Desenvolvedor Júnior.",
        source_fact_keys: ["profile:22222222-2222-2222-2222-222222222222"],
        provenance: "confirmed_fact",
      },
      project_understanding: {
        text: "O escopo envolve desenvolvimento backend em Python com APIs REST.",
        source_fact_keys: [],
        provenance: "confirmed_fact",
      },
      relevant_evidence: [
        {
          entity_id: "proj-1",
          entity_type: "project",
          title: "Job Hunter",
          summary_text: "Sistema determinístico em Python e FastAPI.",
          matched_requirements: ["Python", "FastAPI"],
          source_fact_keys: ["project:proj-1"],
          provenance: "confirmed_fact",
        },
      ],
      suggested_approach: {
        text: "Estrutura modular com testes automatizados em Pytest.",
        source_fact_keys: ["project:proj-1"],
        provenance: "confirmed_fact",
      },
      alignment_points: {
        text: "Condições comerciais serão confirmadas antes do envio final.",
        source_fact_keys: ["profile:22222222-2222-2222-2222-222222222222"],
        provenance: "confirmed_fact",
      },
      pending_fields: [
        {
          field_id: "availability",
          label: "Disponibilidade",
          question: "Informe sua disponibilidade semanal ou data de início.",
          required: true,
          status: "pending",
          user_value: null,
        },
        {
          field_id: "estimated_delivery",
          label: "Prazo estimado",
          question: "Informe o prazo estimado real de entrega.",
          required: true,
          status: "pending",
          user_value: null,
        },
        {
          field_id: "budget_or_price",
          label: "Valor / Orçamento",
          question: "Informe o valor fechado ou por hora.",
          required: true,
          status: "pending",
          user_value: null,
        },
      ],
      closing: {
        text: "À disposição para alinhar detalhes de escopo.",
        source_fact_keys: ["profile:22222222-2222-2222-2222-222222222222"],
        provenance: "confirmed_fact",
      },
      manual_notes: [],
      has_unverified_manual_edits: false,
    };

    const fpResolvedContent: FreelanceProposalStructuredContent = {
      ...fpBlockedContent,
      pending_fields: [
        {
          ...fpBlockedContent.pending_fields[0],
          status: "provided",
          user_value: "20h semanais",
        },
        {
          ...fpBlockedContent.pending_fields[1],
          status: "provided",
          user_value: "15 dias corridos",
        },
        {
          ...fpBlockedContent.pending_fields[2],
          status: "provided",
          user_value: "R$ 3.000",
        },
      ],
      has_unverified_manual_edits: true,
    };

    const blockedMaterial: MaterialDetailResponse = {
      id: "mat-42-fp",
      material_type: "freelance_proposal",
      title: "Proposta Freelance — Desenvolvedor Júnior",
      target_language: "pt-BR",
      opportunity_id: "opp-1",
      opportunity_title: "Desenvolvedor Júnior",
      opportunity_company_name: "Orbit Cloud",
      latest_version_number: 1,
      has_approved_version: false,
      versions: [
        {
          id: "ver-42-fp-1",
          material_id: "mat-42-fp",
          material_type: "freelance_proposal",
          version_number: 1,
          parent_version_id: null,
          origin: "generated",
          user_instructions: null,
          structured_content: fpBlockedContent,
          source_facts_snapshot: { schema_version: 1, facts: {} },
          unconfirmed_warnings: [],
          missing_requirements: [],
          rendered_markdown: "# Proposta Freelance\n",
          rendered_plain_text: "Proposta Freelance\n",
          has_blocking_pending_fields: true,
          pending_requirements_count: 3,
          is_approved: false,
          approved_at: null,
          is_linked_to_any_application: false,
          is_mutable: true,
          created_at: "2026-11-17T22:10:00Z",
          updated_at: "2026-11-17T22:10:00Z",
        },
      ],
      links: [],
      created_at: "2026-11-17T22:10:00Z",
      updated_at: "2026-11-17T22:10:00Z",
    };

    const resolvedMaterial: MaterialDetailResponse = {
      ...blockedMaterial,
      versions: [
        {
          ...blockedMaterial.versions[0],
          origin: "manual_edit",
          structured_content: fpResolvedContent,
          has_blocking_pending_fields: false,
          pending_requirements_count: 0,
        },
      ],
    };

    const approvedMaterial: MaterialDetailResponse = {
      ...resolvedMaterial,
      has_approved_version: true,
      versions: [
        {
          ...resolvedMaterial.versions[0],
          is_approved: true,
          approved_at: "2026-11-17T22:15:00Z",
          is_mutable: false,
        },
      ],
    };

    const createSpy = vi
      .spyOn(api.materials, "create")
      .mockRejectedValueOnce(new ApiError("Falha simulada ao gerar proposta.", 422))
      .mockResolvedValueOnce(blockedMaterial);
    const updateSpy = vi
      .spyOn(api.materials, "updateVersion")
      .mockResolvedValue(resolvedMaterial);
    const approveSpy = vi
      .spyOn(api.materials, "approveVersion")
      .mockResolvedValue(approvedMaterial);

    render(<App />);
    await waitFor(() => {
      expect(screen.getByText(/Cidade Exemplo/i)).toBeInTheDocument();
    });

    fireEvent.click(
      screen.getAllByRole("button", { name: /^Desenvolvedor Júnior$/i })[0]
    );
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /Gerar currículo/i })
      ).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /Gerar currículo/i }));

    await waitFor(() => {
      expect(
        screen.getByRole("radio", { name: /Proposta Freelance/i })
      ).toBeInTheDocument();
    });

    const fpRadio = screen.getByRole("radio", { name: /Proposta Freelance/i });
    const coverRadio = screen.getByRole("radio", {
      name: /Carta de Apresentação/i,
    });
    expect(within(fpRadio).getByText(/Sob solicitação/i)).toBeInTheDocument();
    expect(within(coverRadio).getByText(/Recomendado/i)).toBeInTheDocument();
    expect(
      screen.getByRole("radio", { name: /Currículo Direcionado/i })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("radio", { name: /Mensagem para Recrutador/i })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("radio", { name: /Respostas de Candidatura/i })
    ).toBeInTheDocument();

    fireEvent.click(fpRadio);
    await waitFor(() => {
      expect(screen.getByLabelText(/Disponibilidade/i)).toBeInTheDocument();
    });

    // Erro de API deve exibir alerta claro sem quebrar modal
    fireEvent.click(
      screen.getByRole("button", { name: /Gerar Proposta Freelance/i })
    );
    await waitFor(() => {
      expect(
        screen.getByText(/Falha simulada ao gerar proposta\./i)
      ).toBeInTheDocument();
    });

    // Segunda tentativa gera proposta com 3 pendencias obrigatorias bloqueando aprovacao
    fireEvent.click(
      screen.getByRole("button", { name: /Gerar Proposta Freelance/i })
    );
    await waitFor(() => {
      expect(createSpy).toHaveBeenCalledTimes(2);
      expect(
        screen.getByText(/informação\(ões\) obrigatória\(s\) pendente\(s\)/i)
      ).toBeInTheDocument();
    });

    window.innerWidth = 768;
    window.innerHeight = 1024;
    expect(
      screen.getByRole("button", { name: /Aprovar versão/i })
    ).toBeDisabled();

    fireEvent.change(screen.getByLabelText(/^Disponibilidade$/i), {
      target: { value: "20h semanais" },
    });
    fireEvent.change(screen.getByLabelText(/^Prazo estimado$/i), {
      target: { value: "15 dias corridos" },
    });
    fireEvent.change(screen.getByLabelText(/^Valor \/ Orçamento$/i), {
      target: { value: "R$ 3.000" },
    });

    fireEvent.click(screen.getByRole("button", { name: /Salvar rascunho/i }));
    await waitFor(() => {
      expect(updateSpy).toHaveBeenCalled();
      expect(
        screen.getByRole("button", { name: /Aprovar versão/i })
      ).not.toBeDisabled();
    });

    fireEvent.click(screen.getByRole("button", { name: /Aprovar versão/i }));
    await waitFor(() => {
      expect(approveSpy).toHaveBeenCalledWith("mat-42-fp", "ver-42-fp-1");
      expect(screen.getByText(/Versão v1 está aprovada/i)).toBeInTheDocument();
    });
  });

  it("gera respostas para perguntas de candidatura exigindo perguntas válidas, sinalizando gaps e desbloqueando após resposta manual em desktop", async () => {
    window.innerWidth = 1280;
    window.innerHeight = 800;

    vi.spyOn(api.auth, "me").mockResolvedValue({
      authenticated: true,
      user: mockUser,
      csrf_token: "csrf-42-ans",
    });
    vi.spyOn(api.profile, "getBundle").mockResolvedValue(mockBundle);
    vi.spyOn(api.opportunities, "listSources").mockResolvedValue([]);
    vi.spyOn(api.opportunities, "list").mockResolvedValue({
      items: [
        buildMockOpportunity({
          tracked_application_id: "app-42-2",
          tracked_application_status: "preparing",
        }),
      ],
      total: 1,
      page: 1,
      page_size: 12,
      total_pages: 1,
    });
    vi.spyOn(api.materials, "preAnalyze").mockResolvedValue(
      buildPhase042PreAnalysis("application_answers")
    );

    const ansBlocked: ApplicationAnswersStructuredContent = {
      schema_version: 1,
      material_type: "application_answers",
      language: "pt-BR",
      items: [
        {
          question_id: "q-1",
          question: "Você já trabalhou com Python?",
          question_kind: "technical_experience",
          answer_text:
            "Sim. Tenho evidência confirmada em Job Hunter com uso de Python e FastAPI.",
          requires_user_input: false,
          status: "answered_from_facts",
          follow_up_prompt: null,
          source_fact_keys: ["project:proj-1"],
          evidence_notes: ["Projeto: Job Hunter"],
          provenance: "confirmed_fact",
        },
        {
          question_id: "q-2",
          question: "Qual sua pretensão salarial?",
          question_kind: "compensation",
          answer_text: null,
          requires_user_input: true,
          status: "needs_user_input",
          follow_up_prompt: "Informe sua pretensão salarial.",
          source_fact_keys: [],
          evidence_notes: [],
          provenance: "user_authored",
        },
      ],
      manual_notes: [],
      has_unverified_manual_edits: false,
    };

    const ansResolved: ApplicationAnswersStructuredContent = {
      ...ansBlocked,
      items: [
        ansBlocked.items[0],
        {
          ...ansBlocked.items[1],
          answer_text: "A combinar conforme pacote CLT.",
          requires_user_input: false,
          status: "user_answered",
          follow_up_prompt: null,
          provenance: "user_authored",
        },
      ],
      has_unverified_manual_edits: true,
    };

    const initialAnsMat: MaterialDetailResponse = {
      id: "mat-42-ans",
      material_type: "application_answers",
      title: "Respostas — Desenvolvedor Júnior",
      target_language: "pt-BR",
      opportunity_id: "opp-1",
      opportunity_title: "Desenvolvedor Júnior",
      opportunity_company_name: "Orbit Cloud",
      latest_version_number: 1,
      has_approved_version: false,
      versions: [
        {
          id: "ver-42-ans-1",
          material_id: "mat-42-ans",
          material_type: "application_answers",
          version_number: 1,
          parent_version_id: null,
          origin: "generated",
          user_instructions: null,
          structured_content: ansBlocked,
          source_facts_snapshot: { schema_version: 1, facts: {} },
          unconfirmed_warnings: [],
          missing_requirements: [],
          rendered_markdown: "## 1. Você já trabalhou com Python?\n",
          rendered_plain_text: "1. Você já trabalhou com Python?\n",
          has_blocking_pending_fields: true,
          pending_requirements_count: 1,
          is_approved: false,
          approved_at: null,
          is_linked_to_any_application: false,
          is_mutable: true,
          created_at: "2026-11-17T22:20:00Z",
          updated_at: "2026-11-17T22:20:00Z",
        },
      ],
      links: [],
      created_at: "2026-11-17T22:20:00Z",
      updated_at: "2026-11-17T22:20:00Z",
    };

    const resolvedAnsMat: MaterialDetailResponse = {
      ...initialAnsMat,
      versions: [
        {
          ...initialAnsMat.versions[0],
          origin: "manual_edit",
          structured_content: ansResolved,
          has_blocking_pending_fields: false,
          pending_requirements_count: 0,
        },
      ],
    };

    const approvedAnsMat: MaterialDetailResponse = {
      ...resolvedAnsMat,
      has_approved_version: true,
      versions: [
        {
          ...resolvedAnsMat.versions[0],
          is_approved: true,
          approved_at: "2026-11-17T22:25:00Z",
          is_mutable: false,
        },
      ],
    };

    const createSpy = vi
      .spyOn(api.materials, "create")
      .mockResolvedValue(initialAnsMat);
    vi.spyOn(api.materials, "updateVersion").mockResolvedValue(resolvedAnsMat);
    const approveSpy = vi
      .spyOn(api.materials, "approveVersion")
      .mockResolvedValue(approvedAnsMat);

    render(<App />);
    await waitFor(() => {
      expect(screen.getByText(/Cidade Exemplo/i)).toBeInTheDocument();
    });

    fireEvent.click(
      screen.getAllByRole("button", { name: /^Desenvolvedor Júnior$/i })[0]
    );
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /Gerar currículo/i })
      ).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /Gerar currículo/i }));
    await waitFor(() => {
      expect(
        screen.getByRole("radio", { name: /Respostas de Candidatura/i })
      ).toBeInTheDocument();
    });

    fireEvent.click(
      screen.getByRole("radio", { name: /Respostas de Candidatura/i })
    );

    const generateBtn = await screen.findByRole("button", {
      name: /Gerar Respostas de Candidatura/i,
    });
    expect(generateBtn).toBeDisabled();

    fireEvent.change(screen.getByLabelText("Pergunta 1"), {
      target: { value: "Você já trabalhou com Python?" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: /Adicionar pergunta/i })
    );
    fireEvent.change(screen.getByLabelText("Pergunta 2"), {
      target: { value: "Qual sua pretensão salarial?" },
    });
    expect(generateBtn).not.toBeDisabled();

    fireEvent.click(generateBtn);
    await waitFor(() => {
      expect(createSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          material_type: "application_answers",
          writing_options: expect.objectContaining({
            questions: [
              "Você já trabalhou com Python?",
              "Qual sua pretensão salarial?",
            ],
          }),
        })
      );
      expect(screen.getByText(/Baseada em fatos/i)).toBeInTheDocument();
      expect(screen.getByText(/Exige resposta sua/i)).toBeInTheDocument();
      expect(
        screen.getByText(/Informe sua pretensão salarial\./i)
      ).toBeInTheDocument();
    });

    expect(
      screen.getByRole("button", { name: /Aprovar versão/i })
    ).toBeDisabled();

    fireEvent.change(screen.getByLabelText("Resposta para pergunta 2"), {
      target: { value: "A combinar conforme pacote CLT." },
    });
    fireEvent.click(screen.getByRole("button", { name: /Salvar rascunho/i }));

    await waitFor(() => {
      expect(screen.getByText(/Respondida manualmente/i)).toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: /Aprovar versão/i })
      ).not.toBeDisabled();
    });

    fireEvent.click(screen.getByRole("button", { name: /Aprovar versão/i }));
    await waitFor(() => {
      expect(approveSpy).toHaveBeenCalledWith("mat-42-ans", "ver-42-ans-1");
    });
  });

  it("abre estúdio via Aplicação -> Materiais -> Novo material direcionado, gera mensagem para recrutador com contagem de caracteres e exporta texto simples", async () => {
    window.innerWidth = 390;
    window.innerHeight = 844;

    const appItem: ApplicationItem = {
      id: "app-42-rm",
      opportunity_id: "opp-1",
      opportunity_source_status: "active",
      company_name: "Orbit Cloud",
      role_title: "Backend Python Developer",
      personal_summary: "Atuação com Python e FastAPI.",
      source_name: "Remote OK",
      source_url: "https://remoteok.com/jobs/1",
      application_url: "https://orbit.example.com/jobs/1",
      location_text: "Remoto",
      work_mode: "remote",
      employment_type: "clt",
      seniority_level: "junior",
      status: "preparing",
      status_label: "Preparação",
      is_closed: false,
      applied_at: null,
      assessment_deadline_at: null,
      interview_at: null,
      expected_response_at: null,
      last_external_interaction_at: null,
      last_external_interaction_type: null,
      last_external_interaction_type_label: null,
      last_external_interaction_note: null,
      notes: null,
      next_action: null,
      next_action_due_at: null,
      next_deadline_at: null,
      next_deadline_label: null,
      closed_at: null,
      status_history: [],
      interviews: [],
      assessments: [],
      contacts: [],
      created_at: "2026-11-17T20:00:00Z",
      updated_at: "2026-11-17T20:00:00Z",
    };

    vi.spyOn(api.auth, "me").mockResolvedValue({
      authenticated: true,
      user: mockUser,
      csrf_token: "csrf-42-rm",
    });
    vi.spyOn(api.profile, "getBundle").mockResolvedValue(mockBundle);
    vi.spyOn(api.opportunities, "listSources").mockResolvedValue([]);
    vi.spyOn(api.opportunities, "list").mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 12,
      total_pages: 1,
    });
    vi.spyOn(api.applications, "kanban").mockResolvedValue({
      columns: [
        { status: "interested", label: "Interesse", is_closed: false, count: 0, items: [] },
        { status: "preparing", label: "Preparação", is_closed: false, count: 1, items: [appItem] },
        { status: "applied", label: "Candidatura enviada", is_closed: false, count: 0, items: [] },
        { status: "assessment", label: "Teste técnico", is_closed: false, count: 0, items: [] },
        { status: "interview", label: "Entrevista", is_closed: false, count: 0, items: [] },
        { status: "offer", label: "Proposta", is_closed: false, count: 0, items: [] },
      ],
      closed_columns: [],
      closed_items: [],
      indicators: {
        total_count: 1,
        active_count: 1,
        applied_count: 0,
        assessment_count: 0,
        interview_count: 0,
        offer_count: 0,
        accepted_count: 0,
        rejected_count: 0,
        withdrawn_count: 0,
        closed_count: 0,
        status_counts: { preparing: 1 },
      },
      labels: { preparing: "Preparação" },
    });
    vi.spyOn(api.applications, "agenda").mockResolvedValue({
      days: 30,
      summary: {
        total_count: 0,
        overdue_count: 0,
        imminent_24h_count: 0,
        today_count: 0,
        interviews_count: 0,
        assessments_count: 0,
        actions_count: 0,
        reference_now_utc: new Date().toISOString(),
      },
      events: [],
    });
    vi.spyOn(api.applications, "stale").mockResolvedValue({
      stale_days_param: 7,
      total_count: 0,
      items: [],
    });
    vi.spyOn(api.applications, "get").mockResolvedValue(appItem);
    vi.spyOn(api.materials, "list").mockResolvedValue([]);
    vi.spyOn(api.materials, "preAnalyze").mockResolvedValue(
      buildPhase042PreAnalysis("recruiter_message")
    );

    const rmContent: RecruiterMessageStructuredContent = {
      schema_version: 1,
      material_type: "recruiter_message",
      language: "pt-BR",
      channel: "linkedin",
      subject: null,
      greeting: {
        text: "Olá, Ana Paula!",
        source_fact_keys: [],
        provenance: "confirmed_fact",
      },
      body: {
        text: "Notei a oportunidade de Backend Python Developer na Orbit Cloud e compartilho minha experiência confirmada no projeto Job Hunter com Python e FastAPI.",
        source_fact_keys: ["project:proj-1"],
        provenance: "confirmed_fact",
      },
      sign_off: {
        text: "Obrigado pela atenção.\nUsuário Teste — usuario@example.com",
        source_fact_keys: ["profile:22222222-2222-2222-2222-222222222222"],
        provenance: "confirmed_fact",
      },
      character_count: 235,
      manual_notes: [],
      has_unverified_manual_edits: false,
    };

    const rmMaterial: MaterialDetailResponse = {
      id: "mat-42-rm",
      material_type: "recruiter_message",
      title: "Mensagem — Backend Python Developer",
      target_language: "pt-BR",
      opportunity_id: "opp-1",
      opportunity_title: "Backend Python Developer",
      opportunity_company_name: "Orbit Cloud",
      latest_version_number: 1,
      has_approved_version: false,
      versions: [
        {
          id: "ver-42-rm-1",
          material_id: "mat-42-rm",
          material_type: "recruiter_message",
          version_number: 1,
          parent_version_id: null,
          origin: "generated",
          user_instructions: null,
          structured_content: rmContent,
          source_facts_snapshot: { schema_version: 1, facts: {} },
          unconfirmed_warnings: [],
          missing_requirements: [],
          rendered_markdown:
            "Olá, Ana Paula!\n\nNotei a oportunidade de Backend Python Developer.\n",
          rendered_plain_text:
            "Olá, Ana Paula!\n\nNotei a oportunidade de Backend Python Developer.\n",
          has_blocking_pending_fields: false,
          pending_requirements_count: 0,
          is_approved: false,
          approved_at: null,
          is_linked_to_any_application: false,
          is_mutable: true,
          created_at: "2026-11-17T22:30:00Z",
          updated_at: "2026-11-17T22:30:00Z",
        },
      ],
      links: [],
      created_at: "2026-11-17T22:30:00Z",
      updated_at: "2026-11-17T22:30:00Z",
    };

    const coverContent: CoverLetterStructuredContent = {
      schema_version: 1,
      material_type: "cover_letter",
      language: "pt-BR",
      header: {
        full_name: "Usuário Teste",
        professional_title: "Desenvolvedor Backend | Python & APIs",
        email: "usuario@example.com",
        phone: null,
        location_text: "Cidade Exemplo, Estado Exemplo, Brasil",
        links: [],
        source_fact_keys: ["profile:22222222-2222-2222-2222-222222222222"],
        provenance: "confirmed_fact",
      },
      recipient_line: {
        text: "Equipe de Seleção — Orbit Cloud",
        source_fact_keys: [],
        provenance: "confirmed_fact",
      },
      greeting: {
        text: "Olá,",
        source_fact_keys: [],
        provenance: "confirmed_fact",
      },
      opening: {
        text: "Apresento minha candidatura à vaga de Backend Python Developer na Orbit Cloud.",
        source_fact_keys: ["profile:22222222-2222-2222-2222-222222222222"],
        provenance: "confirmed_fact",
      },
      relevance_highlights: [],
      opportunity_alignment: null,
      closing: {
        text: "Atenciosamente, Usuário Teste.",
        source_fact_keys: ["profile:22222222-2222-2222-2222-222222222222"],
        provenance: "confirmed_fact",
      },
      manual_notes: [],
      has_unverified_manual_edits: false,
    };
    expect(coverContent.material_type).toBe("cover_letter");

    const createSpy = vi
      .spyOn(api.materials, "create")
      .mockResolvedValue(rmMaterial);
    const exportSpy = vi.spyOn(api.materials, "exportVersion").mockResolvedValue({
      material_id: "mat-42-rm",
      version_id: "ver-42-rm-1",
      version_number: 1,
      format: "text",
      filename_suggestion: "mensagem-recrutador-v1.txt",
      content: rmMaterial.versions[0].rendered_plain_text || "",
      is_approved: false,
    });

    render(<App />);
    await waitFor(() => {
      expect(
        screen.getAllByRole("button", { name: /^Candidaturas$/i }).length
      ).toBeGreaterThanOrEqual(1);
    });

    fireEvent.click(
      screen.getAllByRole("button", { name: /^Candidaturas$/i })[0]
    );
    await waitFor(() => {
      expect(
        screen.getAllByRole("button", { name: /Abrir detalhes/i }).length
      ).toBeGreaterThanOrEqual(1);
    });

    fireEvent.click(
      screen.getAllByRole("button", { name: /Abrir detalhes/i })[0]
    );
    await waitFor(() => {
      expect(screen.getByRole("tab", { name: /^Materiais/i })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("tab", { name: /^Materiais/i }));
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /Novo material direcionado/i })
      ).toBeInTheDocument();
    });

    fireEvent.click(
      screen.getByRole("button", { name: /Novo material direcionado/i })
    );
    await waitFor(() => {
      expect(
        screen.getByRole("radio", { name: /Mensagem para Recrutador/i })
      ).toBeInTheDocument();
    });

    fireEvent.click(
      screen.getByRole("radio", { name: /Mensagem para Recrutador/i })
    );
    fireEvent.click(screen.getByRole("button", { name: /^LinkedIn$/i }));
    fireEvent.change(
      screen.getByLabelText(/Nome do contato \/ recrutador/i),
      { target: { value: "Ana Paula" } }
    );

    const rmGenerateBtn = await screen.findByRole("button", {
      name: /Gerar Mensagem/i,
    });
    fireEvent.click(rmGenerateBtn);
    await waitFor(() => {
      expect(createSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          material_type: "recruiter_message",
          application_id: "app-42-rm",
          writing_options: expect.objectContaining({
            channel: "linkedin",
            contact_name: "Ana Paula",
          }),
        })
      );
      expect(screen.getByText(/Contagem aproximada:/i)).toBeInTheDocument();
      expect(screen.getByText(/linkedin/i)).toBeInTheDocument();
    });

    fireEvent.click(
      screen.getByRole("button", { name: /Pré-visualização & Exportação/i })
    );
    fireEvent.click(
      screen.getByRole("button", { name: /Copiar Texto Simples/i })
    );
    await waitFor(() => {
      expect(exportSpy).toHaveBeenCalledWith(
        "mat-42-rm",
        "ver-42-rm-1",
        "text"
      );
    });
  });
});

describe("Job Hunter Frontend - Fase 04.3 Exportação Profissional em PDF e DOCX", () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.history.replaceState({}, "", "/");
    vi.restoreAllMocks();
  });

  it("exibe preview documental com templates, download final/rascunho, bloqueio por pendências e tratamento de erro", async () => {
    window.innerWidth = 390;
    window.innerHeight = 844;

    vi.spyOn(api.auth, "me").mockResolvedValue({
      authenticated: true,
      user: mockUser,
      csrf_token: "csrf-43",
    });
    vi.spyOn(api.profile, "getBundle").mockResolvedValue(mockBundle);
    vi.spyOn(api.opportunities, "listSources").mockResolvedValue([]);
    vi.spyOn(api.opportunities, "list").mockResolvedValue({
      items: [
        buildMockOpportunity({
          tracked_application_id: "app-43-1",
          tracked_application_status: "preparing",
        }),
      ],
      total: 1,
      page: 1,
      page_size: 12,
      total_pages: 1,
    });
    vi.spyOn(api.materials, "preAnalyze").mockResolvedValue({
      can_generate: true,
      blocking_reasons: [],
      material_type: "resume",
      compatible_material_types: [
        "resume",
        "cover_letter",
        "recruiter_message",
        "application_answers",
      ],
      target_language: "pt-BR",
      opportunity_context: {
        opportunity_id: "opp-1",
        application_id: "app-43-1",
        title: "Desenvolvedor Python Júnior",
        company_name: "Orbit Cloud",
        professional_area: "backend",
        seniority_level: "junior",
        employment_type: "clt",
        opportunity_type: "job",
        experience_summary: null,
        required_technologies: ["Python"],
        desirable_technologies: ["FastAPI"],
        all_technologies: ["Python", "FastAPI"],
        language: "pt-BR",
      },
      contact_preview: {
        profile_confirmed: true,
        has_full_name: true,
        has_email: true,
        has_phone: false,
        has_location: true,
        links_count: 1,
        location_label: "Cidade Exemplo, Estado Exemplo, Brasil",
      },
      used_facts: [],
      unconfirmed_warnings: [],
      missing_requirements: [],
      additional_info_needed: [],
      confirmed_counts: {
        profile: 1,
        experiences: 1,
        projects: 1,
        educations: 1,
        skills: 1,
        languages: 1,
      },
    });

    const approvedResumeMat: MaterialDetailResponse = {
      id: "mat-43-res",
      material_type: "resume",
      title: "Currículo — Orbit Cloud",
      target_language: "pt-BR",
      opportunity_id: "opp-1",
      opportunity_title: "Desenvolvedor Python Júnior",
      opportunity_company_name: "Orbit Cloud",
      latest_version_number: 1,
      has_approved_version: true,
      versions: [
        {
          id: "ver-43-res-1",
          material_id: "mat-43-res",
          material_type: "resume",
          version_number: 1,
          origin: "generated",
          parent_version_id: null,
          user_instructions: null,
          structured_content: {
            schema_version: 1,
            language: "pt-BR",
            header: {
              full_name: "Usuário Teste",
              professional_title: "Desenvolvedor Backend Python",
              location_text: "Cidade Exemplo, Estado Exemplo, Brasil",
              email: "usuario@example.com",
              phone: null,
              links: [{ label: "GitHub", url: "https://github.com/usuario" }],
              source_fact_keys: ["profile:22222222-2222-2222-2222-222222222222"],
              provenance: "confirmed_fact",
            },
            summary: {
              text: "Experiência em Python e FastAPI.",
              source_fact_keys: ["profile:22222222-2222-2222-2222-222222222222"],
              provenance: "confirmed_fact",
            },
            target_alignment: null,
            experiences: [],
            projects: [],
            education: [],
            skills: [],
            languages: [],
            manual_notes: [],
            has_unverified_manual_edits: false,
          } satisfies ResumeStructuredContent,
          source_facts_snapshot: { schema_version: 1, facts: {} },
          unconfirmed_warnings: [],
          missing_requirements: [],
          rendered_markdown: "# Usuário Teste\n\nExperiência em Python e FastAPI.\n",
          rendered_plain_text: "Usuário Teste\n",
          has_blocking_pending_fields: false,
          pending_requirements_count: 0,
          is_approved: true,
          approved_at: "2026-11-17T23:00:00Z",
          is_linked_to_any_application: false,
          is_mutable: false,
          created_at: "2026-11-17T23:00:00Z",
          updated_at: "2026-11-17T23:00:00Z",
        },
      ],
      links: [],
      created_at: "2026-11-17T23:00:00Z",
      updated_at: "2026-11-17T23:00:00Z",
    };

    const draftCoverMat: MaterialDetailResponse = {
      ...approvedResumeMat,
      id: "mat-43-cov",
      material_type: "cover_letter",
      title: "Carta — Orbit Cloud",
      has_approved_version: false,
      versions: [
        {
          ...approvedResumeMat.versions[0],
          id: "ver-43-cov-1",
          material_id: "mat-43-cov",
          material_type: "cover_letter",
          is_approved: false,
          approved_at: null,
          is_mutable: true,
          structured_content: {
            schema_version: 1,
            material_type: "cover_letter",
            language: "pt-BR",
            header: {
              full_name: "Usuário Teste",
              professional_title: "Desenvolvedor Backend Python",
              email: "usuario@example.com",
              phone: null,
              location_text: "Cidade Exemplo",
              links: [],
              source_fact_keys: ["profile:22222222-2222-2222-2222-222222222222"],
              provenance: "confirmed_fact",
            },
            recipient_line: {
              text: "À equipe de seleção de Orbit Cloud",
              source_fact_keys: [],
              provenance: "confirmed_fact",
            },
            greeting: {
              text: "Prezados(as),",
              source_fact_keys: [],
              provenance: "confirmed_fact",
            },
            opening: {
              text: "Apresento minha candidatura.",
              source_fact_keys: ["profile:22222222-2222-2222-2222-222222222222"],
              provenance: "confirmed_fact",
            },
            relevance_highlights: [],
            opportunity_alignment: null,
            closing: {
              text: "Atenciosamente, Usuário Teste.",
              source_fact_keys: ["profile:22222222-2222-2222-2222-222222222222"],
              provenance: "confirmed_fact",
            },
            manual_notes: [],
            has_unverified_manual_edits: false,
          } satisfies CoverLetterStructuredContent,
        },
      ],
    };

    vi.spyOn(api.materials, "create")
      .mockResolvedValueOnce(approvedResumeMat)
      .mockResolvedValueOnce(draftCoverMat);
    const downloadSpy = vi
      .spyOn(api.materials, "downloadVersion")
      .mockResolvedValueOnce({
        filename: "curriculo-orbit-cloud-v1.pdf",
        contentType: "application/pdf",
        sizeBytes: 2048,
      })
      .mockRejectedValueOnce(new ApiError("Falha simulada ao baixar DOCX.", 422))
      .mockResolvedValueOnce({
        filename: "carta-apresentacao-orbit-cloud-v1-rascunho.docx",
        contentType:
          "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        sizeBytes: 4096,
      });

    render(<App />);
    await waitFor(() => {
      expect(screen.getByText(/Cidade Exemplo/i)).toBeInTheDocument();
    });
    fireEvent.click(
      screen.getAllByRole("button", { name: /^Desenvolvedor Júnior$/i })[0]
    );
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /Gerar currículo/i })
      ).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /Gerar currículo/i }));

    const genBtn = await screen.findByRole("button", {
      name: /Gerar Currículo Direcionado/i,
    });
    fireEvent.click(genBtn);
    const previewTabBtn = await screen.findByRole("button", {
      name: /Pré-visualização & Exportação/i,
    });
    fireEvent.click(previewTabBtn);

    // Muda para tablet 768x1024 e altera template para Modern Minimalist
    window.innerWidth = 768;
    window.innerHeight = 1024;
    const modernBtn = await screen.findByRole("button", {
      name: /^Modern Minimalist$/i,
    });
    fireEvent.click(modernBtn);
    expect(modernBtn).toHaveAttribute("aria-pressed", "true");
    expect(
      screen.getByLabelText(/Pré-visualização documental \(modern_minimal\)/i)
    ).toBeInTheDocument();

    // Download PDF aprovado -> allow_draft: false
    fireEvent.click(screen.getByRole("button", { name: /^Baixar PDF$/i }));
    await waitFor(() => {
      expect(downloadSpy).toHaveBeenCalledWith("mat-43-res", "ver-43-res-1", {
        format: "pdf",
        template: "modern_minimal",
        allow_draft: false,
      });
      expect(
        screen.getByText(/Download concluído: curriculo-orbit-cloud-v1\.pdf/i)
      ).toBeInTheDocument();
    });

    // Erro de download DOCX exibido sem quebrar UI
    fireEvent.click(screen.getByRole("button", { name: /^Baixar DOCX$/i }));
    await waitFor(() => {
      expect(
        screen.getByText(/Falha simulada ao baixar DOCX\./i)
      ).toBeInTheDocument();
    });

    // Alterna visualização para Markdown
    fireEvent.click(screen.getByRole("button", { name: /^Markdown$/i }));
    expect(screen.getByText(/# Usuário Teste/i)).toBeInTheDocument();

    // Fecha e testa modo Rascunho com Carta não aprovada + versão com pendências bloqueadas
    fireEvent.click(
      screen.getByRole("button", { name: /Fechar janela de material/i })
    );
    fireEvent.click(screen.getByRole("button", { name: /Gerar currículo/i }));
    const coverRadio = await screen.findByRole("radio", {
      name: /Carta de Apresentação/i,
    });
    fireEvent.click(coverRadio);
    const genCoverBtn = await screen.findByRole("button", {
      name: /Gerar Carta/i,
    });
    fireEvent.click(genCoverBtn);

    const coverPreviewTab = await screen.findByRole("button", {
      name: /Pré-visualização & Exportação/i,
    });
    fireEvent.click(coverPreviewTab);

    await waitFor(() => {
      expect(
        screen.getByLabelText(/Pré-visualização documental \(classic_ats\)/i)
      ).toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: /Baixar DOCX \(Rascunho\)/i })
      ).toBeInTheDocument();
    });
    fireEvent.click(
      screen.getByRole("button", { name: /Baixar DOCX \(Rascunho\)/i })
    );
    await waitFor(() => {
      expect(downloadSpy).toHaveBeenLastCalledWith("mat-43-cov", "ver-43-cov-1", {
        format: "docx",
        template: "classic_ats",
        allow_draft: true,
      });
    });

    // Também valida bloqueio de downloads quando há pendências obrigatórias na versão
    const blockedPreviewMat: MaterialDetailResponse = {
      ...draftCoverMat,
      id: "mat-43-blocked",
      material_type: "application_answers",
      versions: [
        {
          ...draftCoverMat.versions[0],
          id: "ver-43-blocked-1",
          material_id: "mat-43-blocked",
          material_type: "application_answers",
          has_blocking_pending_fields: true,
          pending_requirements_count: 2,
        },
      ],
    };
    vi.spyOn(api.materials, "create").mockResolvedValueOnce(blockedPreviewMat);
    fireEvent.click(
      screen.getByRole("button", { name: /Fechar janela de material/i })
    );
    fireEvent.click(screen.getByRole("button", { name: /Gerar currículo/i }));
    const genBlockedBtn = await screen.findByRole("button", {
      name: /Gerar Currículo Direcionado/i,
    });
    fireEvent.click(genBlockedBtn);
    const blockedPreviewTab = await screen.findByRole("button", {
      name: /Pré-visualização & Exportação/i,
    });
    fireEvent.click(blockedPreviewTab);
    await waitFor(() => {
      expect(
        screen.getByText(/Downloads PDF\/DOCX bloqueados/i)
      ).toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: /Baixar PDF \(Rascunho\)/i })
      ).toBeDisabled();
      expect(
        screen.getByRole("button", { name: /Baixar DOCX \(Rascunho\)/i })
      ).toBeDisabled();
    });
  });

  it("baixa exatamente a versão histórica vinculada na aba Materiais da candidatura e valida requestBlob", async () => {
    window.innerWidth = 1280;
    window.innerHeight = 800;

    // 1. Valida requestBlob real extraindo filename e revogando ObjectURL
    const createUrlSpy = vi.fn().mockReturnValue("blob:mock-url-43");
    const revokeUrlSpy = vi.fn();
    Object.defineProperty(URL, "createObjectURL", {
      value: createUrlSpy,
      configurable: true,
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      value: revokeUrlSpy,
      configurable: true,
    });
    const fakeBlob = new Blob(["%PDF-1.4\n%%EOF"], { type: "application/pdf" });
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({
        "content-type": "application/pdf",
        "content-disposition":
          'attachment; filename="curriculo-orbit-v1.pdf"; filename*=UTF-8\'\'curriculo-orbit-v1.pdf',
      }),
      blob: async () => fakeBlob,
    } as unknown as Response);

    const blobRes = await api.materials.downloadVersion("mat-x", "ver-x1", {
      format: "pdf",
      template: "classic_ats",
      allow_draft: false,
    });
    expect(blobRes.filename).toBe("curriculo-orbit-v1.pdf");
    expect(blobRes.contentType).toBe("application/pdf");
    expect(createUrlSpy).toHaveBeenCalledTimes(1);
    fetchMock.mockRestore();

    // 2. Na aba Materiais de ApplicationDetailModal, material vinculado usa linked_version_id (v1), mesmo com v2 rascunho mais recente
    const appItem: ApplicationItem = {
      id: "app-43-hist",
      opportunity_id: "opp-1",
      opportunity_source_status: "active",
      company_name: "Orbit Cloud",
      role_title: "Backend Python Engineer",
      personal_summary: null,
      source_name: "Remote OK",
      source_url: "https://remoteok.com/jobs/43",
      application_url: "https://orbit.example.com/jobs/43",
      location_text: "Remoto",
      work_mode: "remote",
      employment_type: "clt",
      seniority_level: "junior",
      status: "applied",
      status_label: "Candidatura enviada",
      is_closed: false,
      applied_at: "2026-11-17T10:00:00Z",
      assessment_deadline_at: null,
      interview_at: null,
      expected_response_at: null,
      last_external_interaction_at: null,
      last_external_interaction_type: null,
      last_external_interaction_type_label: null,
      last_external_interaction_note: null,
      notes: null,
      next_action: null,
      next_action_due_at: null,
      next_deadline_at: null,
      next_deadline_label: null,
      closed_at: null,
      status_history: [],
      interviews: [],
      assessments: [],
      contacts: [],
      created_at: "2026-11-17T10:00:00Z",
      updated_at: "2026-11-17T10:00:00Z",
    };

    vi.spyOn(api.auth, "me").mockResolvedValue({
      authenticated: true,
      user: mockUser,
      csrf_token: "csrf-43-hist",
    });
    vi.spyOn(api.profile, "getBundle").mockResolvedValue(mockBundle);
    vi.spyOn(api.opportunities, "listSources").mockResolvedValue([]);
    vi.spyOn(api.opportunities, "list").mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 12,
      total_pages: 1,
    });
    vi.spyOn(api.applications, "kanban").mockResolvedValue({
      columns: [
        { status: "interested", label: "Interesse", is_closed: false, count: 0, items: [] },
        { status: "preparing", label: "Preparação", is_closed: false, count: 0, items: [] },
        { status: "applied", label: "Candidatura enviada", is_closed: false, count: 1, items: [appItem] },
        { status: "assessment", label: "Teste técnico", is_closed: false, count: 0, items: [] },
        { status: "interview", label: "Entrevista", is_closed: false, count: 0, items: [] },
        { status: "offer", label: "Proposta", is_closed: false, count: 0, items: [] },
      ],
      closed_columns: [],
      closed_items: [],
      indicators: {
        total_count: 1,
        active_count: 1,
        applied_count: 1,
        assessment_count: 0,
        interview_count: 0,
        offer_count: 0,
        accepted_count: 0,
        rejected_count: 0,
        withdrawn_count: 0,
        closed_count: 0,
        status_counts: { applied: 1 },
      },
      labels: { applied: "Candidatura enviada" },
    });
    vi.spyOn(api.applications, "agenda").mockResolvedValue({
      days: 30,
      summary: {
        total_count: 0,
        overdue_count: 0,
        imminent_24h_count: 0,
        today_count: 0,
        interviews_count: 0,
        assessments_count: 0,
        actions_count: 0,
        reference_now_utc: new Date().toISOString(),
      },
      events: [],
    });
    vi.spyOn(api.applications, "stale").mockResolvedValue({
      stale_days_param: 7,
      total_count: 0,
      items: [],
    });
    vi.spyOn(api.applications, "get").mockResolvedValue(appItem);
    vi.spyOn(api.materials, "list").mockImplementation(async (params) => {
      if (params?.application_id === "app-43-hist") {
        return [
          {
            id: "mat-linked-43",
            opportunity_id: "opp-1",
            opportunity_title: "Backend Python Engineer",
            opportunity_company_name: "Orbit Cloud",
            material_type: "resume",
            title: "Currículo Orbit Cloud",
            target_language: "pt-BR",
            latest_version_number: 2,
            latest_version_id: "ver-latest-v2-unapproved",
            latest_is_approved: false,
            linked_version_id: "ver-linked-v1-approved",
            linked_version_number: 1,
            linked_version_is_approved: true,
            has_approved_version: true,
            active_links_count: 1,
            created_at: "2026-11-17T10:00:00Z",
            updated_at: "2026-11-17T11:00:00Z",
          },
        ];
      }
      return [];
    });

    const downloadVerSpy = vi
      .spyOn(api.materials, "downloadVersion")
      .mockResolvedValue({
        filename: "curriculo-orbit-cloud-v1.pdf",
        contentType: "application/pdf",
        sizeBytes: 1500,
      });

    render(<App />);
    await waitFor(() => {
      expect(
        screen.getAllByRole("button", { name: /^Candidaturas$/i }).length
      ).toBeGreaterThanOrEqual(1);
    });
    fireEvent.click(
      screen.getAllByRole("button", { name: /^Candidaturas$/i })[0]
    );
    await waitFor(() => {
      expect(
        screen.getAllByRole("button", { name: /Abrir detalhes/i }).length
      ).toBeGreaterThanOrEqual(1);
    });
    fireEvent.click(
      screen.getAllByRole("button", { name: /Abrir detalhes/i })[0]
    );
    await waitFor(() => {
      expect(screen.getByRole("tab", { name: /^Materiais/i })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("tab", { name: /^Materiais/i }));

    const pdfLinkedBtn = await screen.findByRole("button", {
      name: /Baixar PDF de Currículo Orbit Cloud v1/i,
    });
    fireEvent.click(pdfLinkedBtn);
    await waitFor(() => {
      expect(downloadVerSpy).toHaveBeenCalledWith(
        "mat-linked-43",
        "ver-linked-v1-approved",
        {
          format: "pdf",
          template: "classic_ats",
          allow_draft: false,
        }
      );
    });

    const docxLinkedBtn = screen.getByRole("button", {
      name: /Baixar DOCX de Currículo Orbit Cloud v1/i,
    });
    fireEvent.click(docxLinkedBtn);
    await waitFor(() => {
      expect(downloadVerSpy).toHaveBeenCalledWith(
        "mat-linked-43",
        "ver-linked-v1-approved",
        {
          format: "docx",
          template: "classic_ats",
          allow_draft: false,
        }
      );
    });
  });
});

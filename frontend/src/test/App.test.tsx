import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "@/App";
import { ApiError, api } from "@/lib/api";
import type {
  FullProfileBundle,
  Opportunity,
  OpportunityListResponse,
  OpportunitySourcePublic,
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

import type {
  AuthSessionResponse,
  Education,
  EducationPayload,
  FullProfileBundle,
  Language,
  LanguagePayload,
  ManualOpportunityCreatePayload,
  Opportunity,
  OpportunityListParams,
  OpportunityListResponse,
  OpportunitySourcePublic,
  OpportunityUserState,
  OpportunityUserStateUpdatePayload,
  ProfessionalProfile,
  ProfessionalProfileUpdatePayload,
  ProfessionalProject,
  ProfessionalProjectPayload,
  Skill,
  SkillPayload,
  WorkExperience,
  WorkExperiencePayload,
} from "@/types/api";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "/api/v1";

let csrfTokenMemory: string | null = null;

export function setCsrfToken(token: string | null) {
  csrfTokenMemory = token;
}

function getCookieValue(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(new RegExp(`(^| )${name}=([^;]+)`));
  return match ? decodeURIComponent(match[2]) : null;
}

export function getActiveCsrfToken(): string | null {
  return csrfTokenMemory || getCookieValue("jh_csrf");
}

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const method = (options.method || "GET").toUpperCase();
  const headers = new Headers(options.headers || {});

  if (!headers.has("Accept")) {
    headers.set("Accept", "application/json");
  }
  if (options.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
    const csrf = getActiveCsrfToken();
    if (csrf) {
      headers.set("X-CSRF-Token", csrf);
    }
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    method,
    headers,
    credentials: "include",
  });

  if (response.status === 204) {
    return undefined as T;
  }

  let data: unknown = null;
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    data = await response.json();
  }

  if (!response.ok) {
    let message = "Não foi possível concluir a operação.";
    if (data && typeof data === "object" && "detail" in data) {
      const detail = (data as { detail: unknown }).detail;
      if (typeof detail === "string") {
        message = detail;
      } else if (Array.isArray(detail) && detail.length > 0) {
        const first = detail[0] as { msg?: string; loc?: (string | number)[] };
        const field = first.loc ? first.loc[first.loc.length - 1] : "";
        message = field
          ? `Campo '${field}': ${first.msg || "valor inválido"}`
          : first.msg || "Dados inválidos.";
      }
    }
    throw new ApiError(message, response.status);
  }

  return data as T;
}

export const api = {
  auth: {
    async login(email: string, password: string): Promise<AuthSessionResponse> {
      const res = await request<AuthSessionResponse>("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      setCsrfToken(res.csrf_token);
      return res;
    },
    async me(): Promise<AuthSessionResponse> {
      const res = await request<AuthSessionResponse>("/auth/me");
      setCsrfToken(res.csrf_token);
      return res;
    },
    async logout(): Promise<void> {
      await request<{ message: string }>("/auth/logout", { method: "POST" });
      setCsrfToken(null);
    },
  },
  profile: {
    getBundle(): Promise<FullProfileBundle> {
      return request<FullProfileBundle>("/profile/bundle");
    },
    getProfile(): Promise<ProfessionalProfile> {
      return request<ProfessionalProfile>("/profile");
    },
    updateProfile(
      payload: ProfessionalProfileUpdatePayload
    ): Promise<ProfessionalProfile> {
      return request<ProfessionalProfile>("/profile", {
        method: "PUT",
        body: JSON.stringify(payload),
      });
    },
    // Experiences
    createExperience(payload: WorkExperiencePayload): Promise<WorkExperience> {
      return request<WorkExperience>("/profile/experiences", {
        method: "POST",
        body: JSON.stringify(payload),
      });
    },
    updateExperience(
      id: string,
      payload: WorkExperiencePayload
    ): Promise<WorkExperience> {
      return request<WorkExperience>(`/profile/experiences/${id}`, {
        method: "PUT",
        body: JSON.stringify(payload),
      });
    },
    deleteExperience(id: string): Promise<void> {
      return request<void>(`/profile/experiences/${id}`, {
        method: "DELETE",
      });
    },
    // Educations
    createEducation(payload: EducationPayload): Promise<Education> {
      return request<Education>("/profile/educations", {
        method: "POST",
        body: JSON.stringify(payload),
      });
    },
    updateEducation(id: string, payload: EducationPayload): Promise<Education> {
      return request<Education>(`/profile/educations/${id}`, {
        method: "PUT",
        body: JSON.stringify(payload),
      });
    },
    deleteEducation(id: string): Promise<void> {
      return request<void>(`/profile/educations/${id}`, {
        method: "DELETE",
      });
    },
    // Skills
    createSkill(payload: SkillPayload): Promise<Skill> {
      return request<Skill>("/profile/skills", {
        method: "POST",
        body: JSON.stringify(payload),
      });
    },
    updateSkill(id: string, payload: SkillPayload): Promise<Skill> {
      return request<Skill>(`/profile/skills/${id}`, {
        method: "PUT",
        body: JSON.stringify(payload),
      });
    },
    deleteSkill(id: string): Promise<void> {
      return request<void>(`/profile/skills/${id}`, {
        method: "DELETE",
      });
    },
    // Languages
    createLanguage(payload: LanguagePayload): Promise<Language> {
      return request<Language>("/profile/languages", {
        method: "POST",
        body: JSON.stringify(payload),
      });
    },
    updateLanguage(id: string, payload: LanguagePayload): Promise<Language> {
      return request<Language>(`/profile/languages/${id}`, {
        method: "PUT",
        body: JSON.stringify(payload),
      });
    },
    deleteLanguage(id: string): Promise<void> {
      return request<void>(`/profile/languages/${id}`, {
        method: "DELETE",
      });
    },
    // Projects
    createProject(
      payload: ProfessionalProjectPayload
    ): Promise<ProfessionalProject> {
      return request<ProfessionalProject>("/profile/projects", {
        method: "POST",
        body: JSON.stringify(payload),
      });
    },
    updateProject(
      id: string,
      payload: ProfessionalProjectPayload
    ): Promise<ProfessionalProject> {
      return request<ProfessionalProject>(`/profile/projects/${id}`, {
        method: "PUT",
        body: JSON.stringify(payload),
      });
    },
    deleteProject(id: string): Promise<void> {
      return request<void>(`/profile/projects/${id}`, {
        method: "DELETE",
      });
    },
  },
  opportunities: {
    listSources(): Promise<OpportunitySourcePublic[]> {
      return request<OpportunitySourcePublic[]>("/opportunities/sources");
    },
    list(params: OpportunityListParams = {}): Promise<OpportunityListResponse> {
      const search = new URLSearchParams();
      if (params.q && params.q.trim()) search.set("q", params.q.trim());
      if (params.type) search.set("type", params.type);
      if (params.seniority) search.set("seniority", params.seniority);
      if (params.compatibility)
        search.set("compatibility", params.compatibility);
      if (params.work_mode) search.set("work_mode", params.work_mode);
      if (params.employment_type)
        search.set("employment_type", params.employment_type);
      if (params.area) search.set("area", params.area);
      if (params.location && params.location.trim())
        search.set("location", params.location.trim());
      if (params.country && params.country.trim())
        search.set("country", params.country.trim());
      if (params.source && params.source.trim())
        search.set("source", params.source.trim());
      if (params.published_after)
        search.set("published_after", params.published_after);
      if (params.saved_only) search.set("saved_only", "true");
      if (params.include_dismissed) search.set("include_dismissed", "true");
      if (params.include_excluded) search.set("include_excluded", "true");
      if (params.sort) search.set("sort", params.sort);
      if (params.page) search.set("page", String(params.page));
      if (params.page_size) search.set("page_size", String(params.page_size));

      const query = search.toString();
      return request<OpportunityListResponse>(
        query ? `/opportunities?${query}` : "/opportunities"
      );
    },
    get(id: string): Promise<Opportunity> {
      return request<Opportunity>(`/opportunities/${id}`);
    },
    createManual(payload: ManualOpportunityCreatePayload): Promise<Opportunity> {
      return request<Opportunity>("/opportunities/manual", {
        method: "POST",
        body: JSON.stringify(payload),
      });
    },
    updateState(
      id: string,
      payload: OpportunityUserStateUpdatePayload
    ): Promise<OpportunityUserState> {
      return request<OpportunityUserState>(`/opportunities/${id}/state`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      });
    },
  },
};

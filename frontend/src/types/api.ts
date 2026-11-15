export type VerificationStatus = "draft" | "pending_validation" | "confirmed";

export type ExperienceType =
  | "internship"
  | "junior"
  | "freelance"
  | "pj"
  | "clt"
  | "academic"
  | "other";

export type EducationStatus = "in_progress" | "completed" | "paused" | "planned";

export type SkillProficiency =
  | "beginner"
  | "basic"
  | "intermediate"
  | "advanced"
  | "expert";

export type LanguageProficiency =
  | "basic"
  | "intermediate"
  | "advanced"
  | "fluent"
  | "native";

export interface User {
  id: string;
  email: string;
  display_name: string;
  account_status: string;
  is_admin: boolean;
  created_at: string;
  updated_at: string;
}

export interface AuthSessionResponse {
  authenticated: boolean;
  user: User;
  csrf_token: string;
}

export interface InternshipPreferences {
  enabled: boolean;
  priority_areas: string[];
  preferred_languages: string[];
  excluded_areas: string[];
}

export interface JuniorDeveloperPreferences {
  enabled: boolean;
  priority_areas: string[];
  block_clt: boolean;
  accepted_contract_types: string[];
  excluded_areas: string[];
}

export interface FreelancePreferences {
  enabled: boolean;
  scopes: string[];
  priority_categories: string[];
  preferred_languages: string[];
}

export interface SourceRestrictions {
  workana_enabled: boolean;
  workana_disabled_reason: string;
  gupy_mode: "disabled" | "selective_high_compatibility" | "enabled";
  auto_execute_tests: boolean;
  pay_premium_or_fees_without_approval: boolean;
  strict_platform_terms_compliance: boolean;
}

export interface CareerPreferences {
  internships: InternshipPreferences;
  junior_developer: JuniorDeveloperPreferences;
  freelance: FreelancePreferences;
  source_restrictions: SourceRestrictions;
}

export interface ProfessionalProfile {
  id: string;
  user_id: string;
  full_name: string | null;
  professional_email: string | null;
  phone: string | null;
  city: string | null;
  state: string | null;
  country: string | null;
  professional_title: string | null;
  professional_summary: string | null;
  linkedin_url: string | null;
  github_url: string | null;
  portfolio_url: string | null;
  preferences: CareerPreferences;
  verification_status: VerificationStatus;
  confirmed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProfessionalProfileUpdatePayload {
  full_name?: string | null;
  professional_email?: string | null;
  phone?: string | null;
  city?: string | null;
  state?: string | null;
  country?: string | null;
  professional_title?: string | null;
  professional_summary?: string | null;
  linkedin_url?: string | null;
  github_url?: string | null;
  portfolio_url?: string | null;
  preferences?: CareerPreferences;
  verification_status?: VerificationStatus;
}

export interface WorkExperience {
  id: string;
  user_id: string;
  company: string;
  role: string;
  description: string | null;
  start_date: string | null;
  end_date: string | null;
  is_current: boolean;
  experience_type: ExperienceType;
  technologies: string[];
  related_skills: string[];
  eligible_as_target_role: boolean;
  verification_status: VerificationStatus;
  confirmed_at: string | null;
  created_at: string;
  updated_at: string;
}

export type WorkExperiencePayload = Omit<
  WorkExperience,
  "id" | "user_id" | "confirmed_at" | "created_at" | "updated_at"
>;

export interface Education {
  id: string;
  user_id: string;
  institution: string;
  course: string;
  field_of_study: string | null;
  current_semester: string | null;
  start_date: string | null;
  expected_graduation_date: string | null;
  education_status: EducationStatus;
  verification_status: VerificationStatus;
  confirmed_at: string | null;
  created_at: string;
  updated_at: string;
}

export type EducationPayload = Omit<
  Education,
  "id" | "user_id" | "confirmed_at" | "created_at" | "updated_at"
>;

export interface Skill {
  id: string;
  user_id: string;
  name: string;
  category: string;
  proficiency_level: SkillProficiency;
  notes: string | null;
  verification_status: VerificationStatus;
  confirmed_at: string | null;
  created_at: string;
  updated_at: string;
}

export type SkillPayload = Omit<
  Skill,
  "id" | "user_id" | "confirmed_at" | "created_at" | "updated_at"
>;

export interface Language {
  id: string;
  user_id: string;
  language_name: string;
  proficiency_level: LanguageProficiency;
  cefr_level: string | null;
  verification_status: VerificationStatus;
  confirmed_at: string | null;
  created_at: string;
  updated_at: string;
}

export type LanguagePayload = Omit<
  Language,
  "id" | "user_id" | "confirmed_at" | "created_at" | "updated_at"
>;

export interface ProfessionalProject {
  id: string;
  user_id: string;
  name: string;
  description: string | null;
  role: string | null;
  technologies: string[];
  links: Record<string, string>;
  verified_results: string | null;
  verification_status: VerificationStatus;
  confirmed_at: string | null;
  created_at: string;
  updated_at: string;
}

export type ProfessionalProjectPayload = Omit<
  ProfessionalProject,
  "id" | "user_id" | "confirmed_at" | "created_at" | "updated_at"
>;

export interface ProfileValidationSummary {
  profile_confirmed: boolean;
  confirmed_count: number;
  pending_or_draft_count: number;
  total_items: number;
  ready_for_future_applications: boolean;
}

export interface FullProfileBundle {
  profile: ProfessionalProfile;
  experiences: WorkExperience[];
  educations: Education[];
  skills: Skill[];
  languages: Language[];
  projects: ProfessionalProject[];
  validation_summary: ProfileValidationSummary;
}

export type OpportunityType =
  | "internship"
  | "junior"
  | "freelance"
  | "other"
  | "unknown";

export type WorkMode = "remote" | "hybrid" | "onsite" | "unknown";

export type EmploymentType =
  | "internship"
  | "clt"
  | "pj"
  | "freelance"
  | "temporary"
  | "other"
  | "unknown";

export type ExternalSourceStatus = "active" | "closed" | "unknown";

export interface OpportunitySourcePublic {
  id: string;
  slug: string;
  name: string;
  source_type: string;
  base_url: string;
  terms_url: string | null;
  attribution_text: string | null;
  enabled: boolean;
  refresh_interval_seconds: number;
  last_synced_at: string | null;
  last_success_at: string | null;
  last_error_summary: string | null;
}

export interface OpportunityMatchEvaluation {
  eligible: boolean;
  geographic_eligibility: "eligible" | "excluded" | "unknown";
  inclusion_reasons: string[];
  exclusion_reasons: string[];
}

export interface OpportunityUserState {
  is_saved: boolean;
  is_dismissed: boolean;
  last_viewed_at: string | null;
}

export interface Opportunity {
  id: string;
  is_manual: boolean;
  external_id: string | null;
  title: string;
  company_name: string | null;
  description: string | null;
  opportunity_type: OpportunityType;
  employment_type: EmploymentType;
  work_mode: WorkMode;
  location_text: string | null;
  city: string | null;
  state: string | null;
  country: string | null;
  eligible_countries: string[];
  eligibility_unknown: boolean;
  language: string | null;
  salary_min: number | null;
  salary_max: number | null;
  salary_currency: string | null;
  salary_period: string | null;
  requirements: string[];
  technologies: string[];
  source_url: string;
  application_url: string | null;
  published_at: string | null;
  deadline_at: string | null;
  source_status: ExternalSourceStatus;
  first_seen_at: string;
  last_seen_at: string;
  source: OpportunitySourcePublic | null;
  user_state: OpportunityUserState;
  match: OpportunityMatchEvaluation;
}

export interface OpportunityListResponse {
  items: Opportunity[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface OpportunityListParams {
  q?: string;
  type?: OpportunityType;
  work_mode?: WorkMode;
  employment_type?: EmploymentType;
  location?: string;
  country?: string;
  source?: string;
  published_after?: string;
  saved_only?: boolean;
  include_dismissed?: boolean;
  include_excluded?: boolean;
  sort?: "recent" | "oldest";
  page?: number;
  page_size?: number;
}

export interface ManualOpportunityCreatePayload {
  title: string;
  company_name?: string | null;
  description?: string | null;
  opportunity_type: OpportunityType;
  employment_type: EmploymentType;
  work_mode: WorkMode;
  location_text?: string | null;
  country?: string | null;
  eligible_countries?: string[];
  technologies?: string[];
  source_url: string;
  application_url?: string | null;
}

export interface OpportunityUserStateUpdatePayload {
  is_saved?: boolean;
  is_dismissed?: boolean;
  mark_viewed?: boolean;
}

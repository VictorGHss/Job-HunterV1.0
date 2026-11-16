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

export type SeniorityLevel =
  | "internship"
  | "entry_level"
  | "junior"
  | "mid_level"
  | "senior"
  | "staff_principal"
  | "management"
  | "unknown";

export type ExperienceRequirementMode =
  | "not_specified"
  | "none_required"
  | "preferred"
  | "required";

export type OverallCompatibility = "compatible" | "potential" | "incompatible";

export type DimensionCompatibility =
  | "compatible"
  | "potential"
  | "incompatible"
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

export type ProfessionalArea =
  | "software_development"
  | "backend"
  | "frontend"
  | "fullstack"
  | "data"
  | "artificial_intelligence"
  | "devops_cloud"
  | "api_integrations"
  | "infrastructure"
  | "technical_support"
  | "customer_support"
  | "marketing_sales"
  | "healthcare"
  | "administration"
  | "other"
  | "unknown";

export type ExternalSourceStatus =
  | "active"
  | "expired"
  | "closed"
  | "removed"
  | "source_unavailable"
  | "unconfirmed"
  | "unknown";

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
  last_error_at?: string | null;
  last_error_summary: string | null;
  unique_opportunities_count?: number;
  open_opportunities_count?: number;
  closed_or_expired_count?: number;
  unconfirmed_count?: number;
}

export interface OpportunitySourceLink {
  id: string;
  source_id: string;
  source_slug: string;
  source_name: string;
  external_id: string;
  source_url: string;
  application_url: string | null;
  is_primary: boolean;
  source_status: ExternalSourceStatus;
  published_at: string | null;
  deadline_at: string | null;
  location_text: string | null;
  eligible_countries: string[];
  salary_min: number | null;
  salary_max: number | null;
  salary_currency: string | null;
  salary_period: string | null;
  first_seen_at: string;
  last_seen_at: string;
  last_checked_at: string | null;
  missing_sync_count: number;
}

export interface OpportunityMatchEvaluation {
  eligible: boolean;
  overall_compatibility?: OverallCompatibility;
  geographic_eligibility: "eligible" | "excluded" | "unknown";
  area_compatibility?: "compatible" | "incompatible" | "unknown";
  contract_compatibility?: "compatible" | "incompatible" | "unknown";
  seniority_compatibility?: DimensionCompatibility;
  experience_compatibility?: DimensionCompatibility;
  technical_compatibility?: DimensionCompatibility;
  matched_areas?: ProfessionalArea[];
  matched_technologies?: string[];
  matched_skills?: string[];
  required_technologies?: string[];
  missing_required_technologies?: string[];
  desirable_technologies?: string[];
  missing_priority_technologies?: string[];
  uncertainty_notes?: string[];
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
  seniority_level?: SeniorityLevel;
  experience_requirement_mode?: ExperienceRequirementMode;
  experience_min_years?: number | null;
  experience_preferred_years?: number | null;
  experience_summary?: string | null;
  employment_type: EmploymentType;
  work_mode: WorkMode;
  professional_area?: ProfessionalArea;
  secondary_areas?: ProfessionalArea[];
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
  last_status_check_at?: string | null;
  status_uncertainty_note?: string | null;
  source: OpportunitySourcePublic | null;
  source_links?: OpportunitySourceLink[];
  user_state: OpportunityUserState;
  match: OpportunityMatchEvaluation;
  tracked_application_id?: string | null;
  tracked_application_status?: string | null;
  closed_applications_count?: number;
  last_closed_application_status?: string | null;
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
  seniority?: SeniorityLevel;
  compatibility?: OverallCompatibility;
  work_mode?: WorkMode;
  employment_type?: EmploymentType;
  area?: ProfessionalArea;
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
  seniority_level?: SeniorityLevel;
  experience_requirement_mode?: ExperienceRequirementMode;
  experience_min_years?: number | null;
  experience_preferred_years?: number | null;
  experience_summary?: string | null;
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

export type ApplicationStatus =
  | "interested"
  | "preparing"
  | "applied"
  | "assessment"
  | "interview"
  | "offer"
  | "accepted"
  | "rejected"
  | "withdrawn";

export interface ApplicationStatusHistoryItem {
  id: string;
  from_status: ApplicationStatus | string | null;
  from_status_label: string | null;
  to_status: ApplicationStatus | string;
  to_status_label: string;
  note: string | null;
  changed_at: string;
}

export interface ApplicationItem {
  id: string;
  opportunity_id: string | null;
  opportunity_source_status: string | null;
  company_name: string | null;
  role_title: string;
  personal_summary: string | null;
  source_name: string | null;
  source_url: string | null;
  application_url: string | null;
  location_text: string | null;
  employment_type: EmploymentType;
  work_mode: WorkMode;
  seniority_level: SeniorityLevel;
  status: ApplicationStatus;
  status_label: string;
  is_closed: boolean;
  applied_at: string | null;
  interview_at: string | null;
  assessment_deadline_at: string | null;
  expected_response_at: string | null;
  next_action: string | null;
  next_action_due_at: string | null;
  next_deadline_at: string | null;
  next_deadline_label: string | null;
  notes: string | null;
  closed_at: string | null;
  created_at: string;
  updated_at: string;
  status_history: ApplicationStatusHistoryItem[];
}

export interface ApplicationListResponse {
  items: ApplicationItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface ApplicationIndicators {
  total_count: number;
  active_count: number;
  applied_count: number;
  assessment_count: number;
  interview_count: number;
  offer_count: number;
  accepted_count: number;
  rejected_count: number;
  withdrawn_count: number;
  closed_count: number;
  status_counts: Record<string, number>;
}

export interface ApplicationKanbanColumn {
  status: ApplicationStatus;
  label: string;
  is_closed: boolean;
  count: number;
  items: ApplicationItem[];
}

export interface ApplicationKanbanResponse {
  columns: ApplicationKanbanColumn[];
  closed_columns: ApplicationKanbanColumn[];
  closed_items: ApplicationItem[];
  indicators: ApplicationIndicators;
  labels: Record<string, string>;
}

export interface ApplicationCreatePayload {
  opportunity_id?: string | null;
  role_title?: string | null;
  company_name?: string | null;
  personal_summary?: string | null;
  source_name?: string | null;
  source_url?: string | null;
  application_url?: string | null;
  location_text?: string | null;
  employment_type?: EmploymentType;
  work_mode?: WorkMode;
  seniority_level?: SeniorityLevel;
  status?: ApplicationStatus;
  applied_at?: string | null;
  interview_at?: string | null;
  assessment_deadline_at?: string | null;
  expected_response_at?: string | null;
  next_action?: string | null;
  next_action_due_at?: string | null;
  notes?: string | null;
  status_note?: string | null;
}

export interface ApplicationUpdatePayload {
  role_title?: string;
  company_name?: string | null;
  personal_summary?: string | null;
  source_name?: string | null;
  source_url?: string | null;
  application_url?: string | null;
  location_text?: string | null;
  employment_type?: EmploymentType;
  work_mode?: WorkMode;
  seniority_level?: SeniorityLevel;
  applied_at?: string | null;
  interview_at?: string | null;
  assessment_deadline_at?: string | null;
  expected_response_at?: string | null;
  next_action?: string | null;
  next_action_due_at?: string | null;
  notes?: string | null;
}

export interface ApplicationStatusChangePayload {
  status: ApplicationStatus;
  note?: string | null;
  applied_at?: string | null;
  interview_at?: string | null;
  assessment_deadline_at?: string | null;
  expected_response_at?: string | null;
  next_action?: string | null;
  next_action_due_at?: string | null;
}

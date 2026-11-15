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

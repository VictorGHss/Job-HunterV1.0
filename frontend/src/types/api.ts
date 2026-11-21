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

export type InterviewFormat = "online" | "in_person" | "phone";
export type InterviewStatus = "scheduled" | "completed" | "cancelled";
export type AssessmentStatus =
  | "pending"
  | "in_progress"
  | "submitted"
  | "feedback_received"
  | "cancelled";
export type ExternalInteractionType =
  | "email"
  | "phone"
  | "linkedin"
  | "interview"
  | "other";

export interface ApplicationInterviewItem {
  id: string;
  application_id: string;
  round_name: string;
  interview_format: InterviewFormat | string;
  interview_format_label: string;
  scheduled_at: string;
  previous_scheduled_at: string | null;
  duration_minutes: number | null;
  meeting_url: string | null;
  interviewers: string | null;
  notes: string | null;
  feedback_received: string | null;
  status: InterviewStatus | string;
  status_label: string;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ApplicationInterviewPayload {
  round_name?: string;
  interview_format?: InterviewFormat;
  scheduled_at?: string;
  duration_minutes?: number | null;
  meeting_url?: string | null;
  interviewers?: string | null;
  notes?: string | null;
  feedback_received?: string | null;
  status?: InterviewStatus;
  completed_at?: string | null;
}

export interface ApplicationAssessmentItem {
  id: string;
  application_id: string;
  title: string;
  description: string | null;
  platform: string | null;
  instructions_url: string | null;
  submission_url: string | null;
  deadline_at: string | null;
  submitted_at: string | null;
  status: AssessmentStatus | string;
  status_label: string;
  is_overdue: boolean;
  is_due_soon_24h: boolean;
  feedback: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface ApplicationAssessmentPayload {
  title?: string;
  description?: string | null;
  platform?: string | null;
  instructions_url?: string | null;
  submission_url?: string | null;
  deadline_at?: string | null;
  submitted_at?: string | null;
  status?: AssessmentStatus;
  feedback?: string | null;
  notes?: string | null;
}

export interface ApplicationContactItem {
  id: string;
  application_id: string;
  name: string;
  role_title: string | null;
  email: string | null;
  linkedin_url: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface ApplicationContactPayload {
  name?: string;
  role_title?: string | null;
  email?: string | null;
  linkedin_url?: string | null;
  notes?: string | null;
}

export interface ExternalInteractionRecordPayload {
  interaction_type: ExternalInteractionType;
  interaction_at?: string | null;
  note?: string | null;
}

export interface AgendaEventItem {
  id: string;
  event_type: "interview" | "assessment" | "next_action" | "expected_response";
  source_kind: "structured" | "legacy";
  entity_id: string;
  application_id: string;
  company_name: string | null;
  role_title: string;
  application_status: ApplicationStatus | string;
  application_status_label: string;
  title: string;
  subtitle: string | null;
  scheduled_at: string;
  status: string;
  status_label: string;
  is_overdue: boolean;
  is_today: boolean;
  is_imminent: boolean;
  urgency: "overdue" | "imminent" | "upcoming";
  action_url: string | null;
}

export interface AgendaSummary {
  total_count: number;
  overdue_count: number;
  imminent_24h_count: number;
  today_count: number;
  interviews_count: number;
  assessments_count: number;
  actions_count: number;
  reference_now_utc: string;
}

export interface ApplicationAgendaResponse {
  days: number;
  summary: AgendaSummary;
  events: AgendaEventItem[];
}

export interface StaleApplicationItem {
  application_id: string;
  company_name: string | null;
  role_title: string;
  status: ApplicationStatus | string;
  status_label: string;
  last_external_interaction_at: string | null;
  reference_timestamp_at: string;
  reference_kind: "external_interaction" | "completed_interview" | "applied_at";
  reference_description: string;
  days_without_external_interaction: number;
  threshold_days: number;
  notice: string;
  recommended_follow_up: string;
}

export interface StaleApplicationsResponse {
  stale_days_param: number;
  total_count: number;
  items: StaleApplicationItem[];
}

export interface FollowUpTemplateResponse {
  application_id: string;
  subject: string;
  message: string;
  recipient_name: string | null;
  recipient_email: string | null;
  context_summary: string;
  used_facts: string[];
  disclaimer: string;
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
  last_external_interaction_at?: string | null;
  last_external_interaction_type?: ExternalInteractionType | string | null;
  last_external_interaction_type_label?: string | null;
  last_external_interaction_note?: string | null;
  created_at: string;
  updated_at: string;
  status_history: ApplicationStatusHistoryItem[];
  interviews?: ApplicationInterviewItem[];
  assessments?: ApplicationAssessmentItem[];
  contacts?: ApplicationContactItem[];
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

// ---------- Fase 04.1: Confirmação em lote & Materiais de Candidatura ----------

export interface ProfileConfirmBatchPayload {
  profile_confirmed?: boolean;
  experience_ids?: string[];
  education_ids?: string[];
  skill_ids?: string[];
  language_ids?: string[];
  project_ids?: string[];
}

export interface ProfileConfirmBatchResponse {
  confirmed_profile: boolean;
  confirmed_experiences: number;
  confirmed_educations: number;
  confirmed_skills: number;
  confirmed_languages: number;
  confirmed_projects: number;
  total_confirmed: number;
}

export type MaterialTargetLanguage = "pt-BR" | "en";
export type MaterialBlockProvenance = "confirmed_fact" | "manual_edit" | "user_authored";
export type MaterialExportFormat = "markdown" | "text";
export type DocumentDownloadFormat = "pdf" | "docx";
export type DocumentTemplateId = "classic_ats" | "modern_minimal";

export interface MaterialDownloadResult {
  filename: string;
  contentType: string;
  sizeBytes: number;
}
export type MaterialVersionOrigin =
  | "generated"
  | "manual_edit"
  | "regenerated"
  | "derived"
  | "ai_assisted";
export type MaterialTypeValue =
  | "resume"
  | "cover_letter"
  | "recruiter_message"
  | "freelance_proposal"
  | "application_answers";
export type RecruiterChannel = "linkedin" | "email" | "contact_form";
export type MaterialFactEntityType =
  | "profile"
  | "experience"
  | "project"
  | "education"
  | "skill"
  | "language";

export interface ContactInclusionOptions {
  include_email: boolean;
  include_phone: boolean;
  include_location: boolean;
  include_links: boolean;
}

export interface ResumeLinkItem {
  label: string;
  url: string;
}

export interface ResumeHeaderSection {
  full_name: string | null;
  professional_title: string | null;
  location_text: string | null;
  email: string | null;
  phone: string | null;
  links: ResumeLinkItem[];
  source_fact_keys: string[];
  provenance: MaterialBlockProvenance;
}

export interface ResumeSummarySection {
  text: string;
  source_fact_keys: string[];
  provenance: MaterialBlockProvenance;
}

export interface ResumeTargetAlignmentSection {
  target_role: string;
  company_name: string | null;
  highlighted_requirements: string[];
  alignment_note: string | null;
  source_fact_keys: string[];
  provenance: MaterialBlockProvenance;
}

export interface ResumeExperienceItem {
  entity_id: string | null;
  company: string;
  role: string;
  period_label: string | null;
  description: string | null;
  technologies: string[];
  experience_type: string;
  eligible_as_target_role: boolean;
  source_fact_keys: string[];
  provenance: MaterialBlockProvenance;
}

export interface ResumeProjectItem {
  entity_id: string | null;
  name: string;
  role: string | null;
  description: string | null;
  technologies: string[];
  links: ResumeLinkItem[];
  verified_results: string | null;
  source_fact_keys: string[];
  provenance: MaterialBlockProvenance;
}

export interface ResumeEducationItem {
  entity_id: string | null;
  institution: string;
  course: string;
  field_of_study: string | null;
  education_status: string;
  status_label: string;
  current_semester: string | null;
  period_label: string | null;
  source_fact_keys: string[];
  provenance: MaterialBlockProvenance;
}

export interface ResumeSkillItem {
  entity_id: string | null;
  name: string;
  category: string;
  proficiency_level: string;
  proficiency_label: string;
  notes: string | null;
  source_fact_keys: string[];
  provenance: MaterialBlockProvenance;
}

export interface ResumeLanguageItem {
  entity_id: string | null;
  language_name: string;
  proficiency_level: string;
  proficiency_label: string;
  cefr_level: string | null;
  source_fact_keys: string[];
  provenance: MaterialBlockProvenance;
}

export interface ResumeManualNoteItem {
  id: string;
  title: string;
  content: string;
  source_fact_keys: string[];
  provenance: MaterialBlockProvenance;
}

export interface ResumeStructuredContent {
  schema_version: 1;
  language: MaterialTargetLanguage;
  header: ResumeHeaderSection;
  summary: ResumeSummarySection | null;
  target_alignment: ResumeTargetAlignmentSection | null;
  experiences: ResumeExperienceItem[];
  projects: ResumeProjectItem[];
  education: ResumeEducationItem[];
  skills: ResumeSkillItem[];
  languages: ResumeLanguageItem[];
  manual_notes: ResumeManualNoteItem[];
  has_unverified_manual_edits: boolean;
}

export interface WritingTextBlock {
  text: string;
  source_fact_keys: string[];
  provenance: MaterialBlockProvenance;
}

export interface WritingEvidenceBlock {
  entity_id: string | null;
  entity_type: MaterialFactEntityType | null;
  title: string;
  summary_text: string;
  matched_requirements: string[];
  source_fact_keys: string[];
  provenance: MaterialBlockProvenance;
}

export interface PendingUserInputField {
  field_id: string;
  label: string;
  question: string;
  required: boolean;
  status: "pending" | "provided";
  user_value: string | null;
}

export interface CoverLetterStructuredContent {
  schema_version: 1;
  material_type: "cover_letter";
  language: MaterialTargetLanguage;
  header: ResumeHeaderSection;
  recipient_line: WritingTextBlock;
  greeting: WritingTextBlock;
  opening: WritingTextBlock;
  relevance_highlights: WritingEvidenceBlock[];
  opportunity_alignment: WritingTextBlock | null;
  closing: WritingTextBlock;
  manual_notes: ResumeManualNoteItem[];
  has_unverified_manual_edits: boolean;
}

export interface RecruiterMessageStructuredContent {
  schema_version: 1;
  material_type: "recruiter_message";
  language: MaterialTargetLanguage;
  channel: RecruiterChannel;
  subject: WritingTextBlock | null;
  greeting: WritingTextBlock;
  body: WritingTextBlock;
  sign_off: WritingTextBlock;
  character_count: number;
  manual_notes: ResumeManualNoteItem[];
  has_unverified_manual_edits: boolean;
}

export interface FreelanceProposalStructuredContent {
  schema_version: 1;
  material_type: "freelance_proposal";
  language: MaterialTargetLanguage;
  header: ResumeHeaderSection;
  introduction: WritingTextBlock;
  project_understanding: WritingTextBlock;
  relevant_evidence: WritingEvidenceBlock[];
  suggested_approach: WritingTextBlock;
  alignment_points: WritingTextBlock;
  pending_fields: PendingUserInputField[];
  closing: WritingTextBlock;
  manual_notes: ResumeManualNoteItem[];
  has_unverified_manual_edits: boolean;
}

export type ApplicationQuestionKind =
  | "technical_experience"
  | "project_example"
  | "education"
  | "language"
  | "motivation"
  | "compensation"
  | "availability"
  | "general_personal";

export interface ApplicationAnswerItem {
  question_id: string;
  question: string;
  question_kind: ApplicationQuestionKind;
  answer_text: string | null;
  requires_user_input: boolean;
  status: "answered_from_facts" | "needs_user_input" | "user_answered";
  follow_up_prompt: string | null;
  source_fact_keys: string[];
  evidence_notes: string[];
  provenance: MaterialBlockProvenance;
}

export interface ApplicationAnswersStructuredContent {
  schema_version: 1;
  material_type: "application_answers";
  language: MaterialTargetLanguage;
  items: ApplicationAnswerItem[];
  manual_notes: ResumeManualNoteItem[];
  has_unverified_manual_edits: boolean;
}

export type AnyMaterialStructuredContent =
  | ResumeStructuredContent
  | CoverLetterStructuredContent
  | RecruiterMessageStructuredContent
  | FreelanceProposalStructuredContent
  | ApplicationAnswersStructuredContent;

export interface FreelanceInputsPayload {
  availability?: string | null;
  estimated_delivery?: string | null;
  budget_or_price?: string | null;
  scope_clarifications?: string | null;
  additional_requirements?: string | null;
}

export interface ApplicationAnswerUserInput {
  question: string;
  user_answer?: string | null;
}

export interface WritingGenerationOptionsPayload {
  channel?: RecruiterChannel;
  contact_name?: string | null;
  contact_context?: string | null;
  freelance_inputs?: FreelanceInputsPayload;
  questions?: string[];
  initial_answers?: ApplicationAnswerUserInput[];
}

export interface OpportunityContextInfo {
  opportunity_id: string | null;
  application_id: string | null;
  title: string | null;
  company_name: string | null;
  professional_area: string | null;
  seniority_level: string | null;
  employment_type?: string | null;
  opportunity_type?: string | null;
  experience_summary: string | null;
  required_technologies: string[];
  desirable_technologies: string[];
  all_technologies: string[];
  language: string | null;
}

export interface SelectedFactReference {
  fact_key: string;
  entity_type: MaterialFactEntityType;
  entity_id: string;
  confirmed_at: string | null;
  label: string;
  summary: string;
  relevance_score: number;
  matched_requirements: string[];
  eligible_as_target_role: boolean | null;
}

export interface UnconfirmedWarningItem {
  entity_type: MaterialFactEntityType;
  entity_id: string;
  verification_status: "pending_validation" | "draft";
  label: string;
  summary: string;
  details: Record<string, unknown>;
  reason: string;
  matched_requirements: string[];
  can_batch_confirm: boolean;
}

export interface MissingRequirementItem {
  requirement: string;
  requirement_kind:
    | "required_technology"
    | "desirable_technology"
    | "general_technology"
    | "seniority_or_area";
  note: string;
  covered_by_unconfirmed: boolean;
}

export interface ContactPreviewInfo {
  profile_confirmed: boolean;
  has_full_name: boolean;
  has_email: boolean;
  has_phone: boolean;
  has_location: boolean;
  links_count: number;
  location_label: string | null;
}

export interface MaterialPreAnalysisResponse {
  can_generate: boolean;
  blocking_reasons: string[];
  material_type?: MaterialTypeValue;
  compatible_material_types?: MaterialTypeValue[];
  target_language: MaterialTargetLanguage;
  opportunity_context: OpportunityContextInfo;
  contact_preview: ContactPreviewInfo;
  used_facts: SelectedFactReference[];
  unconfirmed_warnings: UnconfirmedWarningItem[];
  missing_requirements: MissingRequirementItem[];
  additional_info_needed?: PendingUserInputField[];
  confirmed_counts: Record<string, number>;
}

export interface MaterialLinkItem {
  id: string;
  application_id: string;
  application_role_title: string | null;
  application_company_name: string | null;
  material_id: string;
  version_id: string;
  version_number: number;
  linked_at: string;
  unlinked_at: string | null;
  is_active: boolean;
}

export interface MaterialAIOverlayMetadata {
  ledger_entry_id?: string | null;
  source_version_id?: string;
  source_version_number?: number;
  provider_name?: string;
  model_name?: string;
  eligible_slot_ids?: string[];
  applied_slot_ids?: string[];
  preserved_user_authored_slot_ids?: string[];
  preserved_manual_edit_slot_ids?: string[];
}

export interface MaterialSnapshotFactItem {
  fact_key?: string;
  entity_type?: MaterialFactEntityType | string;
  entity_id?: string;
  confirmed_at?: string | null;
  label?: string;
  summary?: string;
  relevance_score?: number;
  matched_requirements?: string[];
  eligible_as_target_role?: boolean | null;
}

export interface MaterialAIEnhancePayload {
  target_slot_ids?: string[] | null;
  user_instructions?: string | null;
}

export interface MaterialVersionItem {
  id: string;
  material_id: string;
  material_type?: MaterialTypeValue | string;
  version_number: number;
  origin: MaterialVersionOrigin | string;
  parent_version_id: string | null;
  user_instructions: string | null;
  structured_content: AnyMaterialStructuredContent;
  source_facts_snapshot: Record<string, unknown>;
  unconfirmed_warnings: UnconfirmedWarningItem[];
  missing_requirements: MissingRequirementItem[];
  rendered_markdown: string;
  rendered_plain_text?: string;
  has_blocking_pending_fields?: boolean;
  pending_requirements_count?: number;
  is_approved: boolean;
  approved_at: string | null;
  is_rejected?: boolean;
  rejected_at?: string | null;
  is_linked_to_any_application: boolean;
  is_mutable: boolean;
  created_at: string;
  updated_at: string;
}

export interface MaterialDetailResponse {
  id: string;
  opportunity_id: string | null;
  opportunity_title: string | null;
  opportunity_company_name: string | null;
  material_type: string;
  title: string;
  target_language: MaterialTargetLanguage | string;
  latest_version_number: number;
  latest_active_version_number?: number;
  latest_active_version_id?: string | null;
  has_approved_version: boolean;
  versions: MaterialVersionItem[];
  links: MaterialLinkItem[];
  created_at: string;
  updated_at: string;
}

export interface MaterialSummaryItem {
  id: string;
  opportunity_id: string | null;
  opportunity_title: string | null;
  opportunity_company_name: string | null;
  material_type: string;
  title: string;
  target_language: string;
  latest_version_number: number;
  latest_version_id: string | null;
  latest_is_approved: boolean;
  latest_active_version_number?: number;
  latest_active_version_id?: string | null;
  latest_active_is_approved?: boolean;
  linked_version_id?: string | null;
  linked_version_number?: number | null;
  linked_version_is_approved?: boolean;
  has_approved_version: boolean;
  active_links_count: number;
  created_at: string;
  updated_at: string;
}

export interface MaterialExportResponse {
  material_id: string;
  version_id: string;
  version_number: number;
  format: MaterialExportFormat;
  filename_suggestion: string;
  content: string;
  is_approved: boolean;
}

export interface MaterialCreatePayload {
  opportunity_id?: string | null;
  application_id?: string | null;
  material_type?: MaterialTypeValue;
  title?: string | null;
  target_language?: MaterialTargetLanguage;
  contact_options?: ContactInclusionOptions;
  writing_options?: WritingGenerationOptionsPayload;
  user_instructions?: string | null;
}

export interface MaterialPreAnalyzePayload {
  opportunity_id?: string | null;
  application_id?: string | null;
  material_type?: MaterialTypeValue;
  target_language?: MaterialTargetLanguage;
  contact_options?: ContactInclusionOptions;
  writing_options?: WritingGenerationOptionsPayload;
}

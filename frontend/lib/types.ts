import type { UserRole, UserStatus } from "./constants";

export interface AuthUser {
  id: string;
  email: string;
  full_name: string;
  age: number | null;
  designation: string | null;
  hospital_name: string | null;
  avatar_data_url: string | null;
  role: UserRole;
  status: UserStatus;
  restricted_reason: string | null;
  has_password: boolean;
  has_google: boolean;
  created_at: string;
  last_login_at: string | null;
}

export interface AuthSessionResponse {
  user: AuthUser;
}

export interface SessionInfo {
  id: string;
  family_id: string;
  user_agent: string | null;
  ip: string | null;
  created_at: string;
  last_used_at: string | null;
  expires_at: string;
  is_current: boolean;
}

export type TaskType = "discharge_summary" | "case_summary" | "treatment_plan";

export type DocumentStatus =
  | "UPLOADED"
  | "PROCESSING"
  | "BLOCKED"
  | "REVIEW_REQUIRED"
  | "APPROVED"
  | "SENDING"
  | "COMPLETED"
  | "LLM_FAILED"
  | "FAILED";

export interface PipelineStepItem {
  step: string;
  status: "pending" | "running" | "succeeded" | "failed" | "skipped";
  attempts: number;
  error_code: string | null;
  error_message: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface DocumentEntityItem {
  id: string;
  token: string;
  entity_type: string;
  source: string;
  detector: string;
  rule_id: string;
  reason: string;
  score: number;
  occurrences: number;
}

export interface DocumentListItem {
  id: string;
  original_filename: string;
  size_bytes: number;
  page_count: number;
  task_type: TaskType;
  status: DocumentStatus;
  entity_count: number;
  vault_expired: boolean;
  created_at: string;
  updated_at: string;
}

export interface DocumentListResponse {
  items: DocumentListItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface DocumentDetail {
  id: string;
  original_filename: string;
  size_bytes: number;
  page_count: number;
  task_type: TaskType;
  status: DocumentStatus;
  failure_code: string | null;
  entity_summary: Record<string, number>;
  safety_report: {
    status: "PASS" | "BLOCK";
    findings: Array<{ type: string; reason: string; start: number; end: number }>;
    warnings?: string[];
    checked_at: string;
  } | null;
  llm_provider_used: string | null;
  approved_at: string | null;
  vault_expired: boolean;
  version: number;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
  sanitized_sha256: string | null;
  steps: PipelineStepItem[];
  entities: DocumentEntityItem[];
}

export interface OriginalTextResponse {
  document_id: string;
  original_text: string;
  highlights: Array<{
    start: number;
    end: number;
    type: string;
    token: string;
    source: string;
    rule: string;
  }>;
}

export interface SafetyFindingView {
  type: string;
  reason: string;
  start: number;
  end: number;
  snippet: string | null;
}

export interface SanitizedTextResponse {
  document_id: string;
  status: DocumentStatus;
  sanitized_text: string;
  sanitized_sha256: string;
  vault_expired: boolean;
  version: number;
  safety_status: "PASS" | "BLOCK" | null;
  findings: SafetyFindingView[];
  warnings: string[];
}

export interface DocumentResultResponse {
  document_id: string;
  text: string;
  rehydrated: boolean;
  vault_expired: boolean;
  llm_provider_used: string | null;
  fallback_used: boolean;
  warnings: Array<{ code: string; token: string }>;
}

export interface ActivityDayItem {
  date: string;
  total: number;
  documents_uploaded: number;
  reviews_and_marks: number;
  generations_completed: number;
  comments_and_help: number;
}

export interface DashboardResponse {
  counts_by_status: Record<string, number>;
  processed_last_7_days: number;
  waiting_for_review: number;
  blocked_count: number;
  recent_documents: DocumentListItem[];
  top_entity_types: Array<{ entity_type: string; count: number }>;
  avg_pipeline_seconds: number | null;
  activity_heatmap: ActivityDayItem[];
}

export type ComplaintCategory = "bug" | "account" | "privacy" | "other";
export type ComplaintStatus = "open" | "in_progress" | "resolved";

export interface ComplaintMessageItem {
  id: string;
  author_id: string;
  author_name: string;
  author_role: string;
  body: string;
  created_at: string;
}

export interface ComplaintSummaryItem {
  id: string;
  user_id: string;
  user_name: string;
  user_email: string;
  subject: string;
  category: ComplaintCategory;
  status: ComplaintStatus;
  document_id: string | null;
  created_at: string;
  updated_at: string;
  resolved_at: string | null;
}

export interface ComplaintDetail extends ComplaintSummaryItem {
  message: string;
  messages: ComplaintMessageItem[];
}

export interface ComplaintListResponse {
  items: ComplaintSummaryItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface AdminOverviewResponse {
  open_complaints: number;
  in_progress_complaints: number;
  restricted_users: number;
  documents_processed_today: number;
}

export interface AdminUserItem {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  status: UserStatus;
  restricted_reason: string | null;
  restricted_at: string | null;
  created_at: string;
  last_login_at: string | null;
  documents_count: number;
}

export interface AdminUserListResponse {
  items: AdminUserItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface AuditLogItem {
  id: number;
  ts: string;
  actor_id: string | null;
  actor_role: string | null;
  action: string;
  resource_type: string | null;
  resource_id: string | null;
  outcome: "allowed" | "denied" | "error";
  ip: string | null;
  metadata: Record<string, unknown>;
}

export interface AuditLogListResponse {
  items: AuditLogItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface AuditVerifyResponse {
  ok: boolean;
  checked: number;
  first_broken_id: number | null;
}

export interface AdminAnalyticsResponse {
  users_by_role: Record<string, number>;
  users_by_status: Record<string, number>;
  documents_per_day: Array<{
    date: string;
    total: number;
    by_status: Record<string, number>;
  }>;
  llm_provider_usage: Record<string, number>;
  llm_fallback_count: number;
  avg_llm_latency_ms: number | null;
  complaints_by_status: Record<string, number>;
  safety_block_rate: number;
  entity_type_totals: Array<{ entity_type: string; count: number }>;
  activity_heatmap: ActivityDayItem[];
}

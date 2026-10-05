/**
 * IPC 계약 타입 — 단일 진실 공급원: sidecar/README.md (42 commands).
 * Rust 코어는 제네릭 패스스루이므로 이 파일이 프런트엔드 쪽 타입 계약서다.
 */

export interface SidecarErrorInfo {
  code: string;
  message: string;
  retryable?: boolean;
  details?: unknown;
}

export interface Envelope<T = unknown> {
  id: number | null;
  ok: boolean;
  result?: T;
  error?: SidecarErrorInfo;
}

// ── 메일 ──

export interface MailRecord {
  id: number;
  entry_id: string;
  subject: string;
  sender_name: string;
  sender_email: string;
  recipients: string;
  cc: string;
  folder_name: string;
  received_at: string | null;
  sent_at: string | null;
  has_attachments: number;
  attachment_count: number;
  attachment_names: string;
  attachment_types: string;
  importance: number;
  is_read: number;
  categories: string;
  conversation_id: string;
  indexed_at: string;
  body_text?: string;
}

export interface SearchItem {
  email: MailRecord;
  rank_score: number;
  title_snippet: string;
  body_snippet: string;
}

export type SortKey =
  | "rank"
  | "received_at_desc"
  | "received_at_asc"
  | "newest"
  | "oldest";

export interface SearchParams {
  query: string;
  page?: number;
  per_page?: number;
  sort_by?: SortKey;
  folders?: string[];
  has_attachment?: boolean;
  date_from?: string;
  date_to?: string;
  range_months?: number;
  contains_search?: boolean;
  record_history?: boolean;
}

export interface SearchResponse {
  items: SearchItem[];
  total_count: number;
  total_db_count: number;
  page: number;
  per_page: number;
  total_pages: number;
  has_next: boolean;
  has_prev: boolean;
  elapsed_ms: number;
  query: string;
  sort_by: string;
}

export interface FolderCounts {
  counts: Record<string, number>;
  total: number;
}

// ── DB / 설정 ──

export interface DbStats {
  email_count: number;
  mock_count: number;
  bookmark_count: number;
  history_count: number;
  db_size_mb: number;
  db_path: string;
  last_sync_time: string | null;
  indexed_range_months: string | null;
  total_indexed: string | null;
  indexing_state: string | null;
  schema_version: string | null;
}

export type ThemeId = "dark" | "light" | "warm-dark";

export interface AppSettings {
  ui?: {
    theme?: ThemeId;
    font_scale?: number;
    preview_font_size?: number;
    [key: string]: unknown;
  };
  sync?: {
    auto_sync?: boolean;
    auto_sync_interval_minutes?: number;
    range_months?: number;
    include_subfolders?: boolean;
    folder_ids?: number[];
    [key: string]: unknown;
  };
  search?: {
    per_page?: number;
    contains_search?: boolean;
    [key: string]: unknown;
  };
  first_run_completed?: boolean;
  [key: string]: unknown;
}

// ── 동기화 / 인덱싱 ──

export interface SyncPlanView {
  plan_id: string;
  total_outlook: number;
  total_db: number;
  new_count: number;
  updated_count: number;
  deleted_count: number;
  new_ids_preview: string[];
  updated_ids_preview: string[];
  deleted_ids_preview: string[];
  skipped_count: number;
  has_changes: boolean;
  changes_summary: string;
  sync_started_at: string;
  scan_after_date: string | null;
  stopped: boolean;
}

export interface SyncStats {
  added: number;
  updated: number;
  deleted: number;
  skipped: number;
  errors: number;
  elapsed_sec: number;
  message: string;
}

export interface ProgressData {
  phase?: string;
  current?: number;
  total?: number;
  percent?: number;
  message?: string;
  folder?: string;
  [key: string]: unknown;
}

export interface JobView {
  kind?: string;
  phase?: string;
  current?: number;
  total?: number;
  message?: string;
  started_at?: string;
  [key: string]: unknown;
}

export interface JobStatus {
  running: boolean;
  job: JobView | null;
}

// ── 북마크 / 기타 ──

export interface Bookmark {
  id: number;
  keyword: string;
  [key: string]: unknown;
}

export interface SidecarStatus {
  ready: boolean;
  running: boolean;
  restarts: number;
  state?: string;
  detail?: string;
}

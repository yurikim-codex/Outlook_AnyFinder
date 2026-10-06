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

/**
 * config.json 스키마 — **legacy(utils/config.py)와 단일 스키마 유지** (Phase 4-3).
 * 롤백 시 PyQt6 판이 그대로 읽을 수 있어야 하므로 키 이름/구조를 바꾸지 않는다.
 * 새 UI 전용 키는 기본값과 함께 추가만 한다 (search.contains_search 등).
 */
export interface AppSettings {
  indexing?: {
    folders?: string[];
    folder_ids?: number[];
    include_subfolders?: boolean;
    range_months?: number;
    [key: string]: unknown;
  };
  sync?: {
    auto_sync?: boolean;
    interval_minutes?: number;
    [key: string]: unknown;
  };
  search?: {
    results_per_page?: number;
    default_sort?: "relevance" | "newest" | "oldest";
    autocomplete_delay_ms?: number;
    max_autocomplete_items?: number;
    max_related_keywords?: number;
    /** 새 UI 전용 추가 키 — 기본 true ("정확한 단어만" 미체크) */
    contains_search?: boolean;
    [key: string]: unknown;
  };
  ui?: {
    theme?: ThemeId;
    sidebar_width?: number;
    preview_ratio?: number;
    [key: string]: unknown;
  };
  first_run_completed?: boolean;
  [key: string]: unknown;
}

/** system.info 응답 (Phase 4-4 버전 불일치 감지용) */
export interface SystemInfo {
  sidecar_version: string;
  protocol_version: string;
  schema_version: number | string | null;
  commands_count: number;
  python: string;
  platform: string;
  mock: boolean;
  data_dir: string;
  db_path: string;
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
  name: string;
  query: string;
  filters?: Record<string, unknown> | null;
  position?: number;
  created_at?: string;
  [key: string]: unknown;
}

export interface SidecarStatus {
  ready: boolean;
  running: boolean;
  restarts: number;
  state?: string;
  detail?: string;
}

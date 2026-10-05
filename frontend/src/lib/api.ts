/**
 * 사이드카 명령 타입 래퍼 — Rust 대신 TypeScript 쪽 타입 안정성 계층.
 * 함수 하나가 사이드카 명령 하나에 대응한다 (계약: sidecar/README.md).
 */
import type { Transport } from "./transport";
import type {
  AppSettings,
  Bookmark,
  DbStats,
  FolderCounts,
  JobStatus,
  MailRecord,
  SearchParams,
  SearchResponse,
  SyncPlanView,
  SyncStats,
  SystemInfo,
} from "./types";

// ── system ──
export const systemPing = (t: Transport) => t.request<{ pong: boolean }>("system.ping");
export const systemCommands = (t: Transport) =>
  t.request<{ commands: string[] }>("system.commands");
export const systemInfo = (t: Transport) => t.request<SystemInfo>("system.info");

// ── search ──
export const searchQuery = (t: Transport, params: SearchParams) =>
  t.request<SearchResponse>("search.query", { ...params });
export const searchFolders = (t: Transport) => t.request<FolderCounts>("search.folders");
export const searchHistory = (t: Transport, limit = 20) =>
  t.request<{ items: { id: number; keyword: string; searched_at: string }[] }>(
    "search.history",
    { limit },
  );
export const searchRelated = (t: Transport, keyword: string, limit = 8) =>
  t.request<{ keywords: string[] }>("search.related", { keyword, limit });

// ── autocomplete ──
export const autocompleteEmails = (t: Transport, prefix: string, limit = 8) =>
  t.request<{ emails: string[] }>("autocomplete.emails", { prefix, limit });
export const autocompleteSuggest = (t: Transport, prefix: string, limit = 8) =>
  t.request<{ suggestions: string[] }>("autocomplete.suggest", { prefix, limit });

// ── db ──
export const dbStats = (t: Transport) => t.request<DbStats>("db.stats");
export const dbBackup = (t: Transport, targetPath?: string) =>
  t.request<{ backup_path: string }>("db.backup", targetPath ? { path: targetPath } : {});
export const dbIntegrity = (t: Transport) => t.request<{ ok: boolean; message?: string }>("db.integrity");
export const dbClearHistory = (t: Transport) => t.request<{ deleted: number }>("db.clear_history");
export const dbResetAll = (t: Transport) => t.request<{ ok: boolean }>("db.reset_all", { confirm: true });

// ── sync ──
export const syncMeta = (t: Transport) =>
  t.request<{
    last_sync_time: string | null;
    indexed_range_months: number;
    total_indexed: string | null;
    indexing_state: string | null;
  }>("sync.meta");
export const syncPlan = (t: Transport, params: Record<string, unknown> = {}) =>
  t.request<SyncPlanView>("sync.plan", params);
export const syncExecute = (t: Transport, params: Record<string, unknown>) =>
  t.request<SyncStats>("sync.execute", params);
export const syncRun = (t: Transport, params: Record<string, unknown> = {}) =>
  t.request<SyncStats>("sync.run", params);
export const syncCancel = (t: Transport) => t.request<{ ok: boolean }>("sync.cancel");
export const syncStatus = (t: Transport) => t.request<JobStatus>("sync.status");

// ── index ──
export const indexBuild = (t: Transport, params: Record<string, unknown> = {}) =>
  t.request<{ ok: boolean; message?: string }>("index.build", params);
export const indexRebuildFts = (t: Transport) => t.request<{ ok: boolean }>("index.rebuild_fts");

// ── bookmark ──
export const bookmarkList = (t: Transport) => t.request<{ items: Bookmark[] }>("bookmark.list");
export const bookmarkAdd = (t: Transport, keyword: string) =>
  t.request<{ id: number }>("bookmark.add", { keyword });
export const bookmarkRemove = (t: Transport, id: number) =>
  t.request<{ ok: boolean }>("bookmark.remove", { id });
export const bookmarkToggle = (t: Transport, keyword: string) =>
  t.request<{ added: boolean; id?: number }>("bookmark.toggle", { keyword });
export const bookmarkRename = (t: Transport, id: number, keyword: string) =>
  t.request<{ ok: boolean }>("bookmark.rename", { id, keyword });

// ── settings ──
export const settingsGet = (t: Transport) =>
  t.request<{ settings: AppSettings; path: string }>("settings.get");
export const settingsSet = (t: Transport, patch: Record<string, unknown>) =>
  t.request<{ settings: AppSettings }>("settings.set", { patch });

// ── preview / mail ──
/** HTML → 평문 변환 (sanitize는 사이드카 utils/html_cleaner 담당) */
export const previewHtmlToText = (t: Transport, html: string) =>
  t.request<{ text: string; char_count: number }>("preview.html", { html });
/** entry_id → 메일 상세(본문 포함) — 미리보기 패널용 */
export const previewMail = (t: Transport, entryId: string) =>
  t.request<{ email: MailRecord & { attachments: string[]; attachment_type_list: string[] } }>(
    "preview.mail",
    { entry_id: entryId },
  );
export const mailOpen = (t: Transport, entryId: string) =>
  t.request<{ ok: boolean; message?: string }>("mail.open", { entry_id: entryId });
export const mailExport = (t: Transport, entryId: string, targetPath?: string) =>
  t.request<{ path?: string; ok: boolean }>("mail.export", {
    entry_id: entryId,
    ...(targetPath ? { path: targetPath } : {}),
  });

// ── outlook ──
export const outlookCheck = (t: Transport) =>
  t.request<{ available: boolean; mock: boolean; message?: string }>("outlook.check");
export const outlookFolders = (t: Transport) =>
  t.request<{ folders: { id: number; name: string; path?: string }[] }>("outlook.folders");
export const outlookDefaultFolders = (t: Transport) =>
  t.request<{ folder_ids: number[]; names?: string[] }>("outlook.default_folders");

// ── font ─
export const fontList = (t: Transport) => t.request<{ fonts: string[] }>("font.list");

import { BookmarkX, Folder, Inbox, Send, Star, Trash2, FileText, Archive } from "lucide-react";
import clsx from "clsx";

import { formatCount, formatMb } from "../lib/format";
import { useApp } from "../lib/store";

const FOLDER_ICONS: Record<string, typeof Inbox> = {
  받은편지함: Inbox,
  "받은 편지함": Inbox,
  Inbox: Inbox,
  보낸편지함: Send,
  "보낸 편지함": Send,
  "Sent Items": Send,
  Sent: Send,
  임시보관함: FileText,
  "임시 보관함": FileText,
  Drafts: FileText,
  지운편지함: Trash2,
  "지운 편지함": Trash2,
  "Deleted Items": Trash2,
  Trash: Trash2,
  Archive: Archive,
};

export function Sidebar() {
  const { folders, bookmarks, stats, search, doSearch, toggleBookmark, status } = useApp();
  const activeFolders = search.params.folders ?? [];
  const entries = Object.entries(folders?.counts ?? {}).sort((a, b) => b[1] - a[1]);

  return (
    <aside className="panel flex w-60 shrink-0 flex-col border-r border-[var(--border)]">
      <div className="min-h-0 flex-1 overflow-y-auto px-2 py-3">
        <div className="px-2 pb-1.5 text-[11px] font-semibold uppercase tracking-wider text-faint">폴더</div>
        <ul className="space-y-0.5">
          {entries.length === 0 && (
            <li className="px-2 py-1 text-[12px] text-faint">{status.ready ? "폴더 정보 없음" : "기동 중…"}</li>
          )}
          {entries.map(([name, count]) => {
            const Icon = FOLDER_ICONS[name] ?? Folder;
            const active = activeFolders.includes(name);
            return (
              <li key={name}>
                <button
                  className={clsx(
                    "flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-[13px] hover:bg-[var(--bg-hover)]",
                    active && "bg-[var(--accent-soft)] text-[var(--accent)] font-semibold",
                  )}
                  onClick={() => {
                    const next = active ? activeFolders.filter((f) => f !== name) : [...activeFolders, name];
                    void doSearch({ folders: next });
                  }}
                  title="클릭: 폴더 필터 토글 (다중 선택 가능)"
                >
                  <Icon size={14} className="shrink-0 opacity-80" />
                  <span className="min-w-0 flex-1 truncate">{name}</span>
                  <span className="text-[11px] text-faint">{formatCount(count)}</span>
                </button>
              </li>
            );
          })}
        </ul>

        <div className="mt-4 px-2 pb-1.5 text-[11px] font-semibold uppercase tracking-wider text-faint">
          북마크
        </div>
        <ul className="space-y-0.5">
          {bookmarks.length === 0 && (
            <li className="flex items-center gap-1.5 px-2 py-1 text-[12px] text-faint">
              <BookmarkX size={12} /> 검색어 별표로 추가
            </li>
          )}
          {bookmarks.map((b) => (
            <li key={b.id} className="group flex items-center">
              <button
                className="flex min-w-0 flex-1 items-center gap-2 rounded-md px-2 py-1.5 text-left text-[13px] hover:bg-[var(--bg-hover)]"
                onClick={() => void doSearch({ query: String(b.query) })}
                title="북마크 검색 실행"
              >
                <Star size={13} className="shrink-0 fill-[var(--warn)] text-[var(--warn)]" />
                <span className="truncate">{String(b.name || b.query)}</span>
              </button>
              <button
                className="btn btn-ghost invisible p-1 group-hover:visible"
                onClick={() => void toggleBookmark(String(b.query))}
                title="북마크 제거"
              >
                <BookmarkX size={12} />
              </button>
            </li>
          ))}
        </ul>
      </div>

      <div className="border-t border-[var(--border)] px-3 py-2 text-[11px] leading-relaxed text-faint">
        <div>
          인덱스 <span className="text-dim">{formatCount(stats?.email_count ?? 0)}</span>통
          {stats && stats.mock_count > 0 && <span title="Mock 데이터 포함"> (mock {formatCount(stats.mock_count)})</span>}
        </div>
        <div>
          DB {formatMb(stats?.db_size_mb ?? 0)} · 북마크 {stats?.bookmark_count ?? 0}
        </div>
      </div>
    </aside>
  );
}

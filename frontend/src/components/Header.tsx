import { useEffect, useRef, useState } from "react";
import {
  ArrowUpDown,
  CalendarRange,
  FolderInput,
  Paperclip,
  RefreshCw,
  Search,
  Settings,
  Star,
} from "lucide-react";
import clsx from "clsx";

import * as api from "../lib/api";
import { getTransport } from "../lib/transport";
import { useApp } from "../lib/store";
import type { SortKey } from "../lib/types";

const SORT_LABELS: Record<SortKey, string> = {
  rank: "관련도순",
  newest: "최신순",
  oldest: "오래된순",
  received_at_desc: "수신시각↓",
  received_at_asc: "수신시각↑",
};

const RANGE_OPTIONS: { value: number; label: string }[] = [
  { value: 0, label: "전체 기간" },
  { value: 1, label: "최근 1개월" },
  { value: 3, label: "최근 3개월" },
  { value: 6, label: "최근 6개월" },
  { value: 12, label: "최근 1년" },
];

export function Header() {
  const { search, doSearch, folders, status, job, runSync, openDialog, bookmarks, toggleBookmark, toast } =
    useApp();

  const [query, setQuery] = useState(search.params.query);
  // 설정(search.contains_search)과 양방향 동기 — bootstrap이 config 기본값을 주입한다
  const exactOnly = search.params.contains_search === false;
  const setExactOnly = (v: boolean) => void doSearch({ contains_search: !v });
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [showSuggest, setShowSuggest] = useState(false);
  const boxRef = useRef<HTMLDivElement>(null);

  // 자동완성 (디바운스 200ms)
  useEffect(() => {
    if (!showSuggest || query.trim().length < 1) {
      setSuggestions([]);
      return;
    }
    const t = window.setTimeout(() => {
      api
        .autocompleteSuggest(getTransport(), query.trim(), 8)
        .then((r) => setSuggestions(r.suggestions ?? []))
        .catch(() => setSuggestions([]));
    }, 200);
    return () => window.clearTimeout(t);
  }, [query, showSuggest]);

  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setShowSuggest(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, []);

  const submit = () => {
    setShowSuggest(false);
    void doSearch({ query, contains_search: !exactOnly });
  };

  const folderNames = Object.keys(folders?.counts ?? {});
  const activeFolders = search.params.folders ?? [];
  const busy = job.running;

  return (
    <header className="panel border-b border-[var(--border)] px-4 pb-2.5 pt-3">
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2 select-none">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-[var(--accent)] text-white">
            <Search size={16} />
          </div>
          <div className="leading-tight">
            <div className="text-[14px] font-bold">OutLook AnyFinder</div>
            <div className="text-[10px] text-faint">SESUNG Team · Ver 1.0 (React)</div>
          </div>
        </div>

        {/* 검색 바 */}
        <div ref={boxRef} className="relative min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <div className="relative min-w-0 flex-1">
              <Search size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-faint" />
              <input
                className="input w-full pl-8 pr-3"
                placeholder="메일 검색 — 제목/본문/보낸사람 (예: 계약서 검토)"
                value={query}
                disabled={!status.ready}
                onChange={(e) => {
                  setQuery(e.target.value);
                  setShowSuggest(true);
                }}
                onFocus={() => setShowSuggest(true)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") submit();
                  if (e.key === "Escape") setShowSuggest(false);
                }}
              />
              {suggestions.length > 0 && showSuggest && (
                <ul className="absolute z-30 mt-1 w-full overflow-hidden rounded-lg border border-[var(--border)] bg-[var(--bg-elev)] py-1 shadow-[var(--shadow)]">
                  {suggestions.map((s) => (
                    <li key={s}>
                      <button
                        className="block w-full px-3 py-1.5 text-left text-[13px] hover:bg-[var(--bg-hover)]"
                        onMouseDown={(e) => {
                          e.preventDefault();
                          setQuery(s);
                          setShowSuggest(false);
                          void doSearch({ query: s, contains_search: !exactOnly });
                        }}
                      >
                        {s}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <label className="flex shrink-0 cursor-pointer items-center gap-1.5 text-[12px] text-dim select-none">
              <input
                type="checkbox"
                checked={exactOnly}
                onChange={(e) => setExactOnly(e.target.checked)}
              />
              정확한 단어만
            </label>
            <button className="btn btn-primary" onClick={submit} disabled={!status.ready || search.loading}>
              <Search size={14} /> 검색
            </button>
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-1.5">
          {search.params.query.trim() && (
            <button
              className="btn btn-ghost"
              title="현재 검색어 북마크"
              onClick={() => void toggleBookmark(search.params.query.trim())}
            >
              <Star size={14} className={clsx(bookmarks.some((b) => b.keyword === search.params.query.trim()) && "fill-[var(--warn)] text-[var(--warn)]")} />
            </button>
          )}
          <button
            className="btn"
            onClick={() => (busy ? void toast("동기화 진행 중입니다", "warn") : void runSync({}))}
            disabled={!status.ready}
            title="기본 설정으로 즉시 동기화"
          >
            <RefreshCw size={14} className={clsx(busy && "animate-spin")} /> 동기화
          </button>
          <button className="btn" onClick={() => openDialog("sync")} disabled={!status.ready} title="폴더 선택 동기화">
            <FolderInput size={14} />
          </button>
          <button className="btn" onClick={() => openDialog("settings")} title="설정">
            <Settings size={14} />
          </button>
        </div>
      </div>

      {/* 필터 칩 row */}
      <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
        {folderNames.map((name) => (
          <button
            key={name}
            className={clsx("chip", activeFolders.includes(name) && "chip-active")}
            onClick={() => {
              const next = activeFolders.includes(name)
                ? activeFolders.filter((f) => f !== name)
                : [...activeFolders, name];
              void doSearch({ folders: next });
            }}
            title="폴더 필터 (다중 선택 = OR 결합)"
          >
            {name}
            <span className="text-faint">{folders?.counts[name] ?? 0}</span>
          </button>
        ))}
        <button
          className={clsx("chip", search.params.has_attachment && "chip-active")}
          onClick={() => void doSearch({ has_attachment: !search.params.has_attachment })}
          title="첨부파일 있는 메일만"
        >
          <Paperclip size={12} /> 첨부
        </button>
        <label className="ml-1 flex items-center gap-1 text-[12px] text-dim">
          <CalendarRange size={13} />
          <select
            className="input px-2 py-1 text-[12px]"
            value={search.params.range_months ?? 0}
            onChange={(e) => void doSearch({ range_months: Number(e.target.value) })}
          >
            {RANGE_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-1 text-[12px] text-dim">
          <ArrowUpDown size={13} />
          <select
            className="input px-2 py-1 text-[12px]"
            value={search.params.sort_by ?? "rank"}
            onChange={(e) => void doSearch({ sort_by: e.target.value as SortKey })}
          >
            {Object.entries(SORT_LABELS).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        </label>
      </div>
    </header>
  );
}



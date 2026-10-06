/**
 * 전역 앱 상태 — 사이드카 이벤트/상태와 UI 상태를 한 곳에서 묶는다.
 * 컴포넌트는 useApp() 하나로 모든 액션에 접근한다.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import * as api from "./api";
import { getTransport, isTauri, SidecarError } from "./transport";
import { compareSemver, PROTOCOL_VERSION, SIDECAR_VERSION_MIN } from "./version";
import type {
  AppSettings,
  Bookmark,
  DbStats,
  FolderCounts,
  JobStatus,
  MailRecord,
  ProgressData,
  SearchItem,
  SearchParams,
  SearchResponse,
  SidecarStatus,
  SystemInfo,
  ThemeId,
} from "./types";

export interface Toast {
  id: number;
  kind: "info" | "success" | "warn" | "error";
  message: string;
}

export interface SearchState {
  params: SearchParams;
  response: SearchResponse | null;
  loading: boolean;
  error: string | null;
}

const DEFAULT_PARAMS: SearchParams = {
  query: "",
  page: 1,
  per_page: 50,
  sort_by: "rank",
  folders: [],
  contains_search: true, // "정확한 단어만" 체크 시 false로 전환
};

interface AppContextValue {
  transportKind: "tauri" | "http";
  status: SidecarStatus;
  settings: AppSettings | null;
  stats: DbStats | null;
  folders: FolderCounts | null;
  bookmarks: Bookmark[];
  search: SearchState;
  selected: SearchItem | null;
  previewEmail: MailRecord | null;
  previewLoading: boolean;
  job: JobStatus;
  progress: ProgressData | null;
  toasts: Toast[];
  dialog: null | "settings" | "sync";
  firstRun: boolean;
  systemInfo: SystemInfo | null;
  versionWarning: string | null;
  relatedKeywords: string[];
  // actions
  doSearch: (patch: Partial<SearchParams>, opts?: { resetPage?: boolean }) => Promise<void>;
  selectItem: (item: SearchItem | null) => void;
  openDialog: (d: null | "settings" | "sync") => void;
  dismissFirstRun: () => void;
  runIndexBuild: () => Promise<void>;
  runSync: (params?: Record<string, unknown>) => Promise<void>;
  cancelSync: () => Promise<void>;
  refreshMeta: () => Promise<void>;
  refreshBookmarks: () => Promise<void>;
  toggleBookmark: (query: string) => Promise<void>;
  setTheme: (theme: ThemeId) => Promise<void>;
  updateSettings: (patch: Record<string, unknown>) => Promise<void>;
  restartSidecar: () => Promise<void>;
  toast: (message: string, kind?: Toast["kind"]) => void;
  dismissToast: (id: number) => void;
}

const AppContext = createContext<AppContextValue | null>(null);

export function useApp(): AppContextValue {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp은 AppProvider 내부에서만 사용 가능");
  return ctx;
}

let toastSeq = 1;

export function AppProvider({ children }: { children: ReactNode }) {
  const transport = useMemo(() => getTransport(), []);

  const [status, setStatus] = useState<SidecarStatus>({ ready: false, running: false, restarts: 0 });
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [stats, setStats] = useState<DbStats | null>(null);
  const [folders, setFolders] = useState<FolderCounts | null>(null);
  const [bookmarks, setBookmarks] = useState<Bookmark[]>([]);
  const [search, setSearch] = useState<SearchState>({
    params: DEFAULT_PARAMS,
    response: null,
    loading: false,
    error: null,
  });
  const [selected, setSelected] = useState<SearchItem | null>(null);
  const [previewEmail, setPreviewEmail] = useState<MailRecord | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [job, setJob] = useState<JobStatus>({ running: false, job: null });
  const [progress, setProgress] = useState<ProgressData | null>(null);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [dialog, setDialog] = useState<null | "settings" | "sync">(null);
  const [firstRun, setFirstRun] = useState(false);
  const [systemInfo, setSystemInfo] = useState<SystemInfo | null>(null);
  const [versionWarning, setVersionWarning] = useState<string | null>(null);
  const [relatedKeywords, setRelatedKeywords] = useState<string[]>([]);

  const bootstrapped = useRef(false);
  const searchSeq = useRef(0);
  const paramsRef = useRef<SearchParams>(DEFAULT_PARAMS);
  const readyRef = useRef(false);
  const settingsRef = useRef<AppSettings | null>(null);
  const statsRef = useRef<DbStats | null>(null);
  const jobRunningRef = useRef(false);

  const toast = useCallback((message: string, kind: Toast["kind"] = "info") => {
    const id = toastSeq++;
    setToasts((prev) => [...prev.slice(-4), { id, kind, message }]);
    window.setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, kind === "error" ? 8000 : 4000);
  }, []);

  const dismissToast = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const errText = (e: unknown) =>
    e instanceof SidecarError ? `[${e.code}] ${e.message}` : e instanceof Error ? e.message : String(e);

  // ── 메타 갱신 ──

  const refreshMeta = useCallback(async () => {
    try {
      const [s, f] = await Promise.all([api.dbStats(transport), api.searchFolders(transport)]);
      setStats(s);
      setFolders(f);
    } catch (e) {
      transport.frontendLog(`refreshMeta 실패: ${errText(e)}`);
    }
  }, [transport]);

  const refreshBookmarks = useCallback(async () => {
    try {
      const r = await api.bookmarkList(transport);
      setBookmarks(r.items);
    } catch (e) {
      transport.frontendLog(`bookmark.list 실패: ${errText(e)}`);
    }
  }, [transport]);

  const bootstrap = useCallback(async () => {
    try {
      const { settings: loaded } = await api.settingsGet(transport);
      setSettings(loaded);

      // Phase 4-3: 레거시 config.json 기본값을 초기 검색 파라미터에 반영
      const sortMap: Record<string, SearchParams["sort_by"]> = {
        relevance: "rank",
        newest: "newest",
        oldest: "oldest",
      };
      paramsRef.current = {
        ...paramsRef.current,
        per_page: Number(loaded.search?.results_per_page ?? 20),
        contains_search: loaded.search?.contains_search !== false,
        sort_by: sortMap[String(loaded.search?.default_sort ?? "relevance")] ?? "rank",
      };
      setSearch((prev) => ({ ...prev, params: { ...prev.params, ...paramsRef.current } }));

      // Phase 4-4: 사이드카/프런트 버전 불일치 감지
      try {
        const info = await api.systemInfo(transport);
        setSystemInfo(info);
        if (info.protocol_version !== PROTOCOL_VERSION) {
          setVersionWarning(
            `사이드카 프로토콜 v${info.protocol_version} ≠ 프런트엔드 v${PROTOCOL_VERSION} — 앱 업데이트가 필요합니다`,
          );
        } else if (compareSemver(info.sidecar_version, SIDECAR_VERSION_MIN) < 0) {
          setVersionWarning(
            `사이드카 ${info.sidecar_version}이 최소 지원 버전(${SIDECAR_VERSION_MIN})보다 오래되었습니다`,
          );
        }
      } catch {
        /* system.info 미지원 구버전 사이드카 — 무시 */
      }

      await refreshMeta();
      await refreshBookmarks();
      if (loaded.first_run_completed === false || !loaded.first_run_completed) {
        const s = await api.dbStats(transport);
        if (s.email_count === 0) setFirstRun(true);
      }
    } catch (e) {
      toast(`설정 로드 실패: ${errText(e)}`, "error");
    }
  }, [transport, refreshMeta, refreshBookmarks, toast]);

  // ── 검색 ──

  const doSearch = useCallback(
    async (patch: Partial<SearchParams>, opts?: { resetPage?: boolean }) => {
      const seq = ++searchSeq.current;
      const next: SearchParams = {
        ...paramsRef.current,
        ...patch,
        page: opts?.resetPage === false ? (patch.page ?? paramsRef.current.page) : 1,
      };
      // Parity: legacy는 검색 시 기록을 적립했다 — 자동완성/연관검색어의 원료
      next.record_history = Boolean(next.query?.trim());
      paramsRef.current = next;
      setSearch((prev) => ({ params: next, response: prev.response, loading: true, error: null }));
      try {
        const response = await api.searchQuery(transport, next);
        if (seq !== searchSeq.current) return; // 이전 요청의 늦은 응답 폐기
        setSearch({ params: next, response, loading: false, error: null });
      } catch (e) {
        if (seq !== searchSeq.current) return;
        setSearch((prev) => ({ ...prev, loading: false, error: errText(e) }));
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [transport],
  );

  const selectItem = useCallback(
    (item: SearchItem | null) => {
      setSelected(item);
      setPreviewEmail(null);
      if (!item) return;
      setPreviewLoading(true);
      api
        .previewMail(transport, item.email.entry_id)
        .then((r) => setPreviewEmail(r.email))
        .catch((e) => {
          setPreviewEmail(null);
          toast(`미리보기 실패: ${errText(e)}`, "warn");
        })
        .finally(() => setPreviewLoading(false));
    },
    [transport, toast],
  );

  // ── 동기화 / 인덱싱 ──

  const runSync = useCallback(
    async (params: Record<string, unknown> = {}) => {
      setJob({ running: true, job: { kind: "sync" } });
      setProgress(null);
      try {
        const result = await api.syncRun(transport, params);
        toast(
          `동기화 완료 — 신규 ${result.added}, 갱신 ${result.updated}, 삭제 ${result.deleted} (${result.elapsed_sec.toFixed(1)}초)`,
          "success",
        );
        await refreshMeta();
      } catch (e) {
        toast(`동기화 실패: ${errText(e)}`, "error");
      } finally {
        setJob({ running: false, job: null });
        setProgress(null);
      }
    },
    [transport, toast, refreshMeta],
  );

  const cancelSync = useCallback(async () => {
    try {
      await api.syncCancel(transport);
      toast("동기화 취소 요청됨", "warn");
    } catch (e) {
      toast(`취소 실패: ${errText(e)}`, "error");
    }
  }, [transport, toast]);

  const runIndexBuild = useCallback(async () => {
    setFirstRun(false);
    setJob({ running: true, job: { kind: "index" } });
    setProgress(null);
    try {
      await api.indexBuild(transport);
      toast("인덱싱 완료", "success");
      await refreshMeta();
    } catch (e) {
      toast(`인덱싱 실패: ${errText(e)}`, "error");
    } finally {
      setJob({ running: false, job: null });
      setProgress(null);
    }
  }, [transport, toast, refreshMeta]);

  // ── 설정 ─

  const updateSettings = useCallback(
    async (patch: Record<string, unknown>) => {
      try {
        const r = await api.settingsSet(transport, patch);
        setSettings(r.settings);
      } catch (e) {
        toast(`설정 저장 실패: ${errText(e)}`, "error");
      }
    },
    [transport, toast],
  );

  const setTheme = useCallback(
    async (theme: ThemeId) => {
      document.documentElement.dataset.theme = theme;
      await updateSettings({ ui: { theme } });
    },
    [updateSettings],
  );

  const restartSidecar = useCallback(async () => {
    try {
      await transport.restart();
      toast("사이드카 재시작 중…", "info");
    } catch (e) {
      toast(`재시작 실패: ${errText(e)}`, "error");
    }
  }, [transport, toast]);

  const toggleBookmark = useCallback(
    async (query: string) => {
      try {
        const r = await api.bookmarkToggle(transport, query);
        await refreshBookmarks();
        toast(r.bookmarked ? `"${query}" 북마크 추가` : `"${query}" 북마크 제거`, "info");
      } catch (e) {
        toast(`북마크 실패: ${errText(e)}`, "error");
      }
    },
    [transport, refreshBookmarks, toast],
  );

  // ── 테마 적용 + 스케줄러용 ref 미러링 ──

  useEffect(() => {
    const theme = settings?.ui?.theme;
    if (theme) document.documentElement.dataset.theme = theme;
  }, [settings]);

  useEffect(() => {
    settingsRef.current = settings;
  }, [settings]);
  useEffect(() => {
    statsRef.current = stats;
  }, [stats]);
  useEffect(() => {
    jobRunningRef.current = job.running;
  }, [job.running]);

  // ── 사이드카 이벤트 구독 ──

  useEffect(() => {
    let cancelled = false;
    const unsubs: (() => void)[] = [];

    transport.onStatus((s) => {
      if (cancelled) return;
      if (!readyRef.current && s.ready && !bootstrapped.current) {
        bootstrapped.current = true;
        void bootstrap();
      }
      readyRef.current = s.ready;
      if (s.state === "fatal" && s.detail) toast(s.detail, "error");
      setStatus(s);
    }).then((u) => unsubs.push(u));

    transport.onEvent((event, data) => {
      if (cancelled) return;
      const payload = (data ?? {}) as ProgressData;
      switch (event) {
        case "ready":
          if (!bootstrapped.current) {
            bootstrapped.current = true;
            void bootstrap();
          }
          break;
        case "sync.progress":
        case "sync.plan.progress":
        case "index.progress":
          setProgress(payload);
          setJob({ running: true, job: { kind: event.startsWith("index") ? "index" : "sync", ...payload } });
          break;
        case "error":
          toast(`사이드카 오류: ${String(payload.message ?? "알 수 없음")}`, "error");
          break;
        case "bridge.sidecar_exited":
          setStatus((prev) => ({ ...prev, ready: false, running: false }));
          toast("사이드카 프로세스가 종료되었습니다", "error");
          break;
        default:
          break;
      }
    }).then((u) => unsubs.push(u));

    // 트레이 "지금 동기화"
    if (isTauri) {
      import("@tauri-apps/api/event")
        .then(({ listen }) => listen("tray://sync", () => void runSync({})))
        .then((u) => unsubs.push(u))
        .catch(() => undefined);
    }

    return () => {
      cancelled = true;
      for (const u of unsubs) u();
    };
  }, [transport, bootstrap, runSync, toast]);

  // ── 연관 검색어 (Parity #7): 검색 완료 시 자동 조회 ──

  useEffect(() => {
    const q = search.response?.query?.trim();
    if (!q) {
      setRelatedKeywords([]);
      return;
    }
    let cancelled = false;
    api
      .searchRelated(transport, q, 8)
      .then((r) => {
        if (!cancelled) setRelatedKeywords(r.keywords ?? []);
      })
      .catch(() => {
        if (!cancelled) setRelatedKeywords([]);
      });
    return () => {
      cancelled = true;
    };
  }, [transport, search.response]);

  // ── 자동 동기화 스케줄러 (Phase 3-9): 만료 시점에 busy면 다음 틱으로 지연 ──

  useEffect(() => {
    const timer = window.setInterval(() => {
      if (!readyRef.current || !settingsRef.current) return;
      const sync = settingsRef.current.sync;
      if (sync?.auto_sync !== true) return;
      const intervalMin = Number(sync.interval_minutes ?? 10);
      const last = statsRef.current?.last_sync_time;
      if (!last) return; // 동기화 이력 없으면 자동 시작하지 않음 (첫 sync는 사용자 동작)
      const dueAt = new Date(last.replace(" ", "T")).getTime() + intervalMin * 60_000;
      if (Date.now() < dueAt) return;
      if (jobRunningRef.current) return; // busy → 다음 틱으로 지연
      void runSync({});
    }, 30_000);
    return () => window.clearInterval(timer);
  }, [runSync]);

  // ── 잡 상태 폴백 폴링 (이벤트 유실 대비) ──

  useEffect(() => {
    const timer = window.setInterval(() => {
      if (!status.ready) return;
      api
        .syncStatus(transport)
        .then((s) => setJob((prev) => (prev.running === s.running && prev.job?.phase === s.job?.phase ? prev : s)))
        .catch(() => undefined);
    }, 4000);
    return () => window.clearInterval(timer);
  }, [transport, status.ready]);

  const value: AppContextValue = {
    transportKind: transport.kind,
    status,
    settings,
    stats,
    folders,
    bookmarks,
    search,
    selected,
    previewEmail,
    previewLoading,
    job,
    progress,
    toasts,
    dialog,
    firstRun,
    systemInfo,
    versionWarning,
    relatedKeywords,
    doSearch,
    selectItem,
    openDialog: setDialog,
    dismissFirstRun: () => setFirstRun(false),
    runIndexBuild,
    runSync,
    cancelSync,
    refreshMeta,
    refreshBookmarks,
    toggleBookmark,
    setTheme,
    updateSettings,
    restartSidecar,
    toast,
    dismissToast,
  };

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

import { useEffect, useState } from "react";
import { Circle, CircleDot, Loader2, X } from "lucide-react";

import { formatCount, timeAgo } from "../lib/format";
import { useApp } from "../lib/store";
import { APP_VERSION } from "../lib/version";

export function StatusBar() {
  const { status, search, stats, job, progress, cancelSync, transportKind, settings, systemInfo } = useApp();
  const [now, setNow] = useState(Date.now());

  // 자동 동기화 카운트다운 표시용 1초 틱
  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(t);
  }, []);

  const auto = settings?.sync?.auto_sync === true;
  const intervalMin = Number(settings?.sync?.interval_minutes ?? 10);
  let countdown = "";
  if (auto && stats?.last_sync_time) {
    const last = new Date(stats.last_sync_time.replace(" ", "T")).getTime();
    if (!Number.isNaN(last)) {
      const due = last + intervalMin * 60_000;
      const remain = Math.max(0, due - now);
      const mm = Math.floor(remain / 60_000);
      const ss = Math.floor((remain % 60_000) / 1000);
      countdown = remain === 0 ? "자동 동기화 대기 중(busy이면 지연)" : `자동 동기화 ${mm}:${String(ss).padStart(2, "0")}`;
    }
  }

  const percent =
    progress?.percent ??
    (progress && progress.total ? Math.round(((progress.current ?? 0) / progress.total) * 100) : null);

  return (
    <footer className="panel flex items-center gap-3 border-t border-[var(--border)] px-3 py-1 text-[11px] text-dim">
      <span className="flex items-center gap-1.5" title={`사이드카 상태: ${status.running ? "running" : "stopped"} / 재시작 ${status.restarts}회`}>
        {status.ready ? (
          <CircleDot size={11} className="text-[var(--ok)]" />
        ) : (
          <Circle size={11} className="text-[var(--warn)]" />
        )}
        {status.ready ? "사이드카 준비됨" : "사이드카 대기"}
        <span className="text-faint">({transportKind === "tauri" ? "Tauri" : "브라우저 dev"})</span>
      </span>

      <span className="text-faint">|</span>
      <span>
        {search.loading
          ? "검색 중…"
          : search.response
            ? `결과 ${formatCount(search.response.total_count)}건 / 전체 ${formatCount(search.response.total_db_count)}통 · ${search.response.elapsed_ms.toFixed(0)}ms · ${search.response.page}/${search.response.total_pages}쪽`
            : "검색어를 입력하세요"}
      </span>
      {search.error && <span className="text-[var(--danger)]">{search.error}</span>}

      {job.running && (
        <span className="flex min-w-0 items-center gap-2 text-[var(--accent)]">
          <Loader2 size={11} className="animate-spin" />
          <span className="truncate">
            {job.job?.kind === "index" ? "인덱싱" : "동기화"}
            {progress?.message ? ` — ${progress.message}` : progress?.phase ? ` — ${progress.phase}` : ""}
            {percent !== null ? ` ${percent}%` : progress?.total ? ` (${progress.current}/${progress.total})` : ""}
          </span>
          <button className="btn btn-ghost p-0.5" onClick={() => void cancelSync()} title="취소">
            <X size={11} />
          </button>
        </span>
      )}

      <span className="ml-auto flex items-center gap-3">
        {countdown && <span className="text-faint">{countdown}</span>}
        <span>마지막 동기화 {timeAgo(stats?.last_sync_time) || "—"}</span>
        <span className="text-faint" title={`사이드카 ${systemInfo?.sidecar_version ?? "?"} / 프로토콜 v${systemInfo?.protocol_version ?? "?"}`}>
          v{APP_VERSION}
          {systemInfo ? ` / sidecar ${systemInfo.sidecar_version}` : ""}
        </span>
      </span>
    </footer>
  );
}

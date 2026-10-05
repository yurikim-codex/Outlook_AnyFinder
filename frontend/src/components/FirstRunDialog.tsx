import { Loader2, Sparkles } from "lucide-react";

import { useApp } from "../lib/store";
import { Dialog } from "./Dialog";

/** 첫 실행(인덱스 0건) 안내 — index.build 진입점 (Phase 3-8 온보딩). */
export function FirstRunDialog() {
  const { runIndexBuild, dismissFirstRun, job, progress, transportKind } = useApp();
  const building = job.running && job.job?.kind === "index";
  const percent =
    progress?.percent ?? (progress?.total ? Math.round(((progress.current ?? 0) / progress.total) * 100) : null);

  return (
    <Dialog title="OutLook AnyFinder에 오신 것을 환영합니다" width={520}>
      <div className="space-y-3 text-[13px] leading-relaxed">
        <div className="flex items-center gap-2 text-[var(--accent)]">
          <Sparkles size={16} />
          아직 인덱스가 비어 있습니다.
        </div>
        <p className="text-dim">
          Outlook에 연결된 메일을 읽어 검색 인덱스를 만들어야 검색이 가능합니다. 첫 인덱싱은 메일 양에 따라
          수 분 걸릴 수 있으며, 진행 중에도 이 창을 닫고 설정을 둘러볼 수 있습니다.
        </p>
        {transportKind === "http" && (
          <p className="rounded-lg border border-[var(--warn)] px-3 py-2 text-[12px] text-[var(--warn)]">
            브라우저 개발 모드에서는 Mock 데이터(15통)로 인덱싱됩니다. 실제 Outlook 연동은 Windows의
            Tauri 빌드에서만 동작합니다.
          </p>
        )}
        {building && (
          <div className="space-y-1.5">
            <div className="h-2 overflow-hidden rounded-full bg-[var(--bg-elev)]">
              <div className="h-full bg-[var(--accent)] transition-all" style={{ width: `${percent ?? 8}%` }} />
            </div>
            <div className="text-[12px] text-dim">
              {progress?.message ?? "인덱싱 진행 중…"}
              {progress?.total ? ` (${progress.current}/${progress.total})` : ""}
            </div>
          </div>
        )}
        <div className="flex justify-end gap-2 pt-1">
          <button className="btn" onClick={dismissFirstRun} disabled={building}>
            나중에 하기
          </button>
          <button className="btn btn-primary" onClick={() => void runIndexBuild()} disabled={building}>
            {building ? <Loader2 size={13} className="animate-spin" /> : null}
            인덱스 만들기 시작
          </button>
        </div>
      </div>
    </Dialog>
  );
}

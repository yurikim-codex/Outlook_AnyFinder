import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";

import * as api from "../lib/api";
import { formatCount } from "../lib/format";
import { getTransport } from "../lib/transport";
import { useApp } from "../lib/store";
import type { SyncPlanView, SyncStats } from "../lib/types";
import { Dialog } from "./Dialog";

interface FolderOpt {
  id: number;
  name: string;
  path?: string;
}

type Step = "options" | "plan" | "running" | "done";

export function SyncFolderDialog() {
  const { openDialog, job, progress, cancelSync, refreshMeta, toast, settings } = useApp();
  const transport = getTransport();

  const [folders, setFolders] = useState<FolderOpt[]>([]);
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [includeSub, setIncludeSub] = useState(settings?.sync?.include_subfolders !== false);
  const [rangeMonths, setRangeMonths] = useState(Number(settings?.sync?.range_months ?? 0));
  const [incremental, setIncremental] = useState(false);
  const [step, setStep] = useState<Step>("options");
  const [plan, setPlan] = useState<SyncPlanView | null>(null);
  const [result, setResult] = useState<SyncStats | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .outlookFolders(transport)
      .then(async (r) => {
        setFolders(r.folders ?? []);
        try {
          const d = await api.outlookDefaultFolders(transport);
          setSelectedIds(d.folder_ids ?? []);
        } catch {
          setSelectedIds((r.folders ?? []).slice(0, 2).map((f) => f.id));
        }
      })
      .catch((e) => toast(`폴더 목록 실패: ${String(e)}`, "error"));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const makePlan = async () => {
    setBusy(true);
    try {
      const p = await api.syncPlan(transport, {
        folder_ids: selectedIds,
        include_subfolders: includeSub,
        range_months: rangeMonths,
        incremental,
      });
      setPlan(p);
      setStep("plan");
    } catch (e) {
      toast(`계획 생성 실패: ${String(e)}`, "error");
    } finally {
      setBusy(false);
    }
  };

  const execute = async () => {
    if (!plan) return;
    setStep("running");
    try {
      const r = await api.syncExecute(transport, {
        plan_id: plan.plan_id,
        folder_ids: selectedIds,
        include_subfolders: includeSub,
        range_months: rangeMonths,
        incremental,
      });
      setResult(r);
      setStep("done");
      await refreshMeta();
    } catch (e) {
      toast(`동기화 실패: ${String(e)}`, "error");
      setStep("plan");
    }
  };

  const percent =
    progress?.percent ?? (progress?.total ? Math.round(((progress.current ?? 0) / progress.total) * 100) : null);

  return (
    <Dialog
      title="폴더 선택 동기화"
      width={600}
      onClose={step === "running" ? undefined : () => openDialog(null)}
      footer={
        step === "options" ? (
          <>
            <button className="btn" onClick={() => openDialog(null)}>
              취소
            </button>
            <button className="btn btn-primary" onClick={() => void makePlan()} disabled={busy || selectedIds.length === 0}>
              {busy ? <Loader2 size={13} className="animate-spin" /> : null} 변경 계획 미리보기
            </button>
          </>
        ) : step === "plan" ? (
          <>
            <button className="btn" onClick={() => setStep("options")}>
              뒤로
            </button>
            <button className="btn btn-primary" onClick={() => void execute()} disabled={!plan?.has_changes}>
              동기화 실행
            </button>
          </>
        ) : step === "running" ? (
          <button className="btn btn-danger" onClick={() => void cancelSync()}>
            취소 요청
          </button>
        ) : (
          <button className="btn btn-primary" onClick={() => openDialog(null)}>
            닫기
          </button>
        )
      }
    >
      {step === "options" && (
        <div className="space-y-3 text-[13px]">
          <div className="max-h-56 space-y-1 overflow-y-auto rounded-lg border border-[var(--border)] p-2">
            {folders.length === 0 && <div className="p-2 text-[12px] text-faint">폴더 목록을 불러오는 중…</div>}
            {folders.map((f) => (
              <label key={f.id} className="flex cursor-pointer items-center gap-2 rounded px-2 py-1 hover:bg-[var(--bg-hover)]">
                <input
                  type="checkbox"
                  checked={selectedIds.includes(f.id)}
                  onChange={(e) =>
                    setSelectedIds((prev) => (e.target.checked ? [...prev, f.id] : prev.filter((x) => x !== f.id)))
                  }
                />
                <span className="min-w-0 flex-1 truncate">{f.name}</span>
                {f.path && <span className="truncate text-[11px] text-faint">{f.path}</span>}
              </label>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <label className="flex items-center gap-1.5">
              <input type="checkbox" checked={includeSub} onChange={(e) => setIncludeSub(e.target.checked)} />
              하위 폴더 포함
            </label>
            <label className="flex items-center gap-1.5">
              <input type="checkbox" checked={incremental} onChange={(e) => setIncremental(e.target.checked)} />
              증분 동기화 (빠름)
            </label>
            <label className="flex items-center gap-1.5">
              기간
              <select className="input px-2 py-1" value={rangeMonths} onChange={(e) => setRangeMonths(Number(e.target.value))}>
                <option value={0}>전체</option>
                <option value={1}>1개월</option>
                <option value={3}>3개월</option>
                <option value={6}>6개월</option>
                <option value={12}>1년</option>
              </select>
            </label>
          </div>
        </div>
      )}

      {step === "plan" && plan && (
        <div className="space-y-3 text-[13px]">
          <div className="rounded-lg border border-[var(--border)] p-3">
            <div className="font-semibold">변경 계획 미리보기</div>
            <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-[12.5px]">
              <div>Outlook 전체: <b>{formatCount(plan.total_outlook)}</b>통</div>
              <div>현재 인덱스: <b>{formatCount(plan.total_db)}</b>통</div>
              <div className="text-[var(--ok)]">신규: +{formatCount(plan.new_count)}</div>
              <div className="text-[var(--accent)]">갱신: {formatCount(plan.updated_count)}</div>
              <div className="text-[var(--danger)]">삭제: {formatCount(plan.deleted_count)}</div>
              <div className="text-dim">건너뜀: {formatCount(plan.skipped_count)}</div>
            </div>
            {plan.changes_summary && <p className="mt-2 text-[12px] text-dim">{plan.changes_summary}</p>}
            {!plan.has_changes && <p className="mt-2 text-[12px] text-[var(--ok)]">변경 사항이 없습니다 — 동기화가 필요 없어요.</p>}
          </div>
        </div>
      )}

      {step === "running" && (
        <div className="space-y-2 text-[13px]">
          <div className="flex items-center gap-2">
            <Loader2 size={15} className="animate-spin text-[var(--accent)]" />
            {job.running ? "동기화 진행 중…" : "동기화 처리 중…"}
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-[var(--bg-elev)]">
            <div
              className="h-full bg-[var(--accent)] transition-all"
              style={{ width: `${percent ?? (job.running ? 30 : 5)}%` }}
            />
          </div>
          <div className="text-[12px] text-dim">
            {progress?.message ?? progress?.phase ?? "Outlook 메일 읽는 중… (검색은 계속 사용할 수 있습니다)"}
            {progress?.total ? ` (${progress.current}/${progress.total})` : ""}
          </div>
        </div>
      )}

      {step === "done" && result && (
        <div className="space-y-2 text-[13px]">
          <div className="rounded-lg border border-[var(--ok)] p-3">
            <div className="font-semibold text-[var(--ok)]">동기화 완료</div>
            <div className="mt-1 grid grid-cols-2 gap-x-4 gap-y-1 text-[12.5px]">
              <div>추가: {formatCount(result.added)}</div>
              <div>갱신: {formatCount(result.updated)}</div>
              <div>삭제: {formatCount(result.deleted)}</div>
              <div>오류: {formatCount(result.errors)}</div>
            </div>
            <p className="mt-2 text-[12px] text-dim">{result.message} ({result.elapsed_sec.toFixed(1)}초)</p>
          </div>
        </div>
      )}
    </Dialog>
  );
}

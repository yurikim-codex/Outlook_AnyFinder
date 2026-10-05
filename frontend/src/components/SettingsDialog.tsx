import { useState } from "react";
import clsx from "clsx";

import * as api from "../lib/api";
import { formatCount, formatMb } from "../lib/format";
import { getTransport } from "../lib/transport";
import { useApp } from "../lib/store";
import type { ThemeId } from "../lib/types";
import { Dialog } from "./Dialog";

const TABS = ["인덱싱", "동기화", "검색", "화면", "데이터"] as const;
type Tab = (typeof TABS)[number];

const THEMES: { id: ThemeId; label: string; desc: string }[] = [
  { id: "dark", label: "다크", desc: "기본 — 눈이 편안한 어두운 톤" },
  { id: "light", label: "라이트", desc: "밝은 사무 환경용" },
  { id: "warm-dark", label: "웜 크", desc: "밤늦은 근무용 따뜻한 톤" },
];

export function SettingsDialog() {
  const { openDialog, settings, stats, updateSettings, setTheme, refreshMeta, restartSidecar, toast, transportKind } =
    useApp();
  const [tab, setTab] = useState<Tab>("인덱싱");
  const [confirmReset, setConfirmReset] = useState(false);
  const transport = getTransport();

  const sync = settings?.sync ?? {};
  const search = settings?.search ?? {};
  const ui = settings?.ui ?? {};

  return (
    <Dialog title="설정" width={640} onClose={() => openDialog(null)}>
      <div className="mb-4 flex gap-1 border-b border-[var(--border)]">
        {TABS.map((t) => (
          <button
            key={t}
            className={clsx(
              "px-3 py-1.5 text-[13px] font-medium text-dim",
              tab === t && "border-b-2 border-[var(--accent)] text-[var(--accent)]",
            )}
            onClick={() => setTab(t)}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === "인덱싱" && (
        <div className="space-y-3 text-[13px]">
          <div className="grid grid-cols-2 gap-2 rounded-lg border border-[var(--border)] p-3 text-[12px]">
            <div>인덱스된 메일: <b>{formatCount(stats?.email_count ?? 0)}</b>통</div>
            <div>DB 크기: <b>{formatMb(stats?.db_size_mb ?? 0)}</b></div>
            <div>스키마 버전: {stats?.schema_version ?? "-"}</div>
            <div>인덱싱 상태: {stats?.indexing_state ?? "-"}</div>
            <div className="col-span-2 truncate text-faint" title={stats?.db_path}>DB 경로: {stats?.db_path}</div>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              className="btn"
              onClick={() =>
                api
                  .indexRebuildFts(transport)
                  .then(() => toast("FTS 인덱스 재구축 완료", "success"))
                  .catch((e) => toast(`재구축 실패: ${String(e)}`, "error"))
              }
            >
              FTS 인덱스 재구축
            </button>
            <button
              className="btn"
              onClick={() =>
                api
                  .dbIntegrity(transport)
                  .then((r) => toast(r.message ?? (r.ok ? "DB 무결성 정상" : "DB 무결성 문제"), r.ok ? "success" : "error"))
                  .catch((e) => toast(`검사 실패: ${String(e)}`, "error"))
              }
            >
              DB 무결성 검사
            </button>
            <button
              className="btn"
              onClick={() =>
                api
                  .dbBackup(transport)
                  .then((r) => toast(`백업 완료: ${r.backup_path}`, "success"))
                  .catch((e) => toast(`백업 실패: ${String(e)}`, "error"))
              }
            >
              DB 백업
            </button>
            <button className="btn" onClick={() => void refreshMeta()}>
              상태 새로고침
            </button>
          </div>
          <p className="text-[12px] text-faint">
            인덱스 전체 재구축은 메인 화면 첫 실행 안내 또는 동기화 다이얼로그에서 수행합니다.
          </p>
        </div>
      )}

      {tab === "동기화" && (
        <div className="space-y-3 text-[13px]">
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={sync.auto_sync === true}
              onChange={(e) => void updateSettings({ sync: { auto_sync: e.target.checked } })}
            />
            자동 동기화 사용
          </label>
          <label className="flex items-center gap-2">
            자동 동기화 간격
            <select
              className="input px-2 py-1"
              value={Number(sync.auto_sync_interval_minutes ?? 30)}
              onChange={(e) => void updateSettings({ sync: { auto_sync_interval_minutes: Number(e.target.value) } })}
            >
              {[10, 15, 30, 60, 120].map((m) => (
                <option key={m} value={m}>
                  {m}분
                </option>
              ))}
            </select>
          </label>
          <label className="flex items-center gap-2">
            기본 동기화 기간
            <select
              className="input px-2 py-1"
              value={Number(sync.range_months ?? 0)}
              onChange={(e) => void updateSettings({ sync: { range_months: Number(e.target.value) } })}
            >
              <option value={0}>전체</option>
              <option value={1}>1개월</option>
              <option value={3}>3개월</option>
              <option value={6}>6개월</option>
              <option value={12}>1년</option>
            </select>
          </label>
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={sync.include_subfolders !== false}
              onChange={(e) => void updateSettings({ sync: { include_subfolders: e.target.checked } })}
            />
            하위 폴더 포함
          </label>
          <div className="border-t border-[var(--border)] pt-3">
            <button className="btn" onClick={() => void restartSidecar()}>
              사이드카 재시작
            </button>
            <p className="mt-1 text-[12px] text-faint">
              사이드카(Python 코어)가 응답하지 않을 때 사용합니다. 현재 모드: {transportKind}
            </p>
          </div>
        </div>
      )}

      {tab === "검색" && (
        <div className="space-y-3 text-[13px]">
          <label className="flex items-center gap-2">
            페이지당 결과 수
            <select
              className="input px-2 py-1"
              value={Number(search.per_page ?? 50)}
              onChange={(e) => void updateSettings({ search: { per_page: Number(e.target.value) } })}
            >
              {[20, 50, 100, 200, 500].map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </label>
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={search.contains_search !== false}
              onChange={(e) => void updateSettings({ search: { contains_search: e.target.checked } })}
            />
            부분 단어 포함 검색을 기본으로 사용 ("정확한 단어만" 체크박스와 연동)
          </label>
        </div>
      )}

      {tab === "화면" && (
        <div className="space-y-2">
          {THEMES.map((t) => (
            <label
              key={t.id}
              className={clsx(
                "flex cursor-pointer items-center gap-3 rounded-lg border px-3 py-2",
                (ui.theme ?? "dark") === t.id ? "border-[var(--accent)] bg-[var(--accent-soft)]" : "border-[var(--border)]",
              )}
            >
              <input type="radio" name="theme" checked={(ui.theme ?? "dark") === t.id} onChange={() => void setTheme(t.id)} />
              <span className="text-[13px] font-semibold">{t.label}</span>
              <span className="text-[12px] text-dim">{t.desc}</span>
            </label>
          ))}
        </div>
      )}

      {tab === "데이터" && (
        <div className="space-y-3 text-[13px]">
          <div className="rounded-lg border border-[var(--border)] p-3">
            <div className="font-semibold">검색 기록 지우기</div>
            <p className="mt-1 text-[12px] text-dim">
              자동완성·연관 검색에 사용되는 검색어 기록 {formatCount(stats?.history_count ?? 0)}건을 삭제합니다. 메일 인덱스와 북마크는 유지됩니다.
            </p>
            <button
              className="btn btn-danger mt-2"
              onClick={() =>
                api
                  .dbClearHistory(transport)
                  .then((r) => toast(`검색 기록 ${formatCount(r.deleted)}건 삭제`, "success"))
                  .catch((e) => toast(`실패: ${String(e)}`, "error"))
              }
            >
              기록 지우기
            </button>
          </div>
          <div className="rounded-lg border border-[var(--danger)] p-3">
            <div className="font-semibold text-[var(--danger)]">전체 초기화</div>
            <p className="mt-1 text-[12px] text-dim">
              메일 인덱스·검색 기록·설정 메타를 모두 삭제하고 첫 실행 상태로 되돌립니다. 북마크는 유지됩니다. 되돌릴 수 없습니다.
            </p>
            {!confirmReset ? (
              <button className="btn btn-danger mt-2" onClick={() => setConfirmReset(true)}>
                초기화 시작…
              </button>
            ) : (
              <div className="mt-2 flex items-center gap-2">
                <span className="text-[12px] text-[var(--danger)]">정말 삭제하시겠습니까?</span>
                <button
                  className="btn btn-danger"
                  onClick={() => {
                    api
                      .dbResetAll(transport)
                      .then(() => {
                        toast("전체 초기화 완료 — 인덱스를 다시 구축하세요", "warn");
                        setConfirmReset(false);
                        void refreshMeta();
                      })
                      .catch((e) => toast(`실패: ${String(e)}`, "error"));
                  }}
                >
                  네, 모두 삭제
                </button>
                <button className="btn" onClick={() => setConfirmReset(false)}>
                  취소
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </Dialog>
  );
}

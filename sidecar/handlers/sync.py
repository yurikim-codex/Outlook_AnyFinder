"""sync.* — 동기화 계획/실행/취소/상태.

흐름 (legacy PyQt AppController.do_smart_sync_with_approval 이식):
    sync.plan   → Outlook 스캔 + DB 비교 → plan_id 반환 (+ sync.plan.progress 이벤트)
    (사용자 승인 — React 승인 다이얼로그)
    sync.execute → 승인된 plan_id 실행 (+ sync.progress 이벤트)

자동 동기화는 sync.run 1회 호출로 plan+execute를 승인 없이 수행한다
(legacy SyncWorker 대체). 모든 Outlook 접근은 COM 스레드에서 직렬화된다.
"""

import logging
import uuid
from datetime import datetime, timedelta

from sidecar.async_runner import require_int, run_job
from sidecar.protocol import ErrorCode, SidecarError
from sidecar.serialize import to_jsonable

logger = logging.getLogger("sidecar.handlers.sync")

_PLAN_ID_PREVIEW_LIMIT = 100


def register(dispatcher):
    dispatcher.register("sync.meta", meta)
    dispatcher.register("sync.plan", plan)
    dispatcher.register("sync.execute", execute)
    dispatcher.register("sync.run", run)
    dispatcher.register("sync.cancel", cancel)
    dispatcher.register("sync.status", status)


# ── 헬퍼 ──

def _range_months_to_after_date(months):
    """3/6/12개월 → 기준일 (0/None = 전체). legacy main.py와 동일한 30일 근사."""
    try:
        months = int(months)
    except (TypeError, ValueError):
        return None
    if months <= 0:
        return None
    return (datetime.now() - timedelta(days=months * 30)).strftime("%Y-%m-%d %H:%M:%S")


def _default_folders(state):
    settings = state.load_settings()
    folder_ids = settings.get("indexing", {}).get("folder_ids") or [6, 5]
    include_sub = settings.get("indexing", {}).get("include_subfolders", True)
    return [int(f) for f in folder_ids], bool(include_sub)


def _sync_manager(conn, connector):
    from core.outlook_connector import MockOutlookConnector
    from core.sync_manager import MockSyncManager, SyncManager
    if isinstance(connector, MockOutlookConnector):
        return MockSyncManager(conn, connector)
    return SyncManager(conn, connector)


def _resolve_sync_params(state, params):
    default_folders, default_include = _default_folders(state)
    folder_ids = params.get("folder_ids") or default_folders
    folder_ids = [int(f) for f in folder_ids]
    include_sub = bool(params.get("include_subfolders", default_include))
    incremental = bool(params.get("incremental", False))
    range_months = params.get("range_months")
    after_date = params.get("after_date")
    if after_date in ("", None) and range_months is not None and not incremental:
        after_date = _range_months_to_after_date(range_months)
    mail_after_date = params.get("mail_after_date")
    if mail_after_date in ("", None) and range_months is not None and incremental:
        mail_after_date = _range_months_to_after_date(range_months)
    return {
        "folder_ids": folder_ids,
        "include_subfolders": include_sub,
        "incremental": incremental,
        "after_date": after_date or None,
        "mail_after_date": mail_after_date or None,
        "range_months": int(range_months) if range_months is not None else None,
    }


def _serialize_plan(plan_id, plan, stopped=False):
    """SyncPlan → JSON. outlook_hashes는 내부용이라 제외, id 목록은 미리보기만."""
    return {
        "plan_id": plan_id,
        "total_outlook": plan.total_outlook,
        "total_db": plan.total_db,
        "new_count": len(plan.new_ids),
        "updated_count": len(plan.updated_ids),
        "deleted_count": len(plan.deleted_ids),
        "new_ids_preview": plan.new_ids[:_PLAN_ID_PREVIEW_LIMIT],
        "updated_ids_preview": plan.updated_ids[:_PLAN_ID_PREVIEW_LIMIT],
        "deleted_ids_preview": plan.deleted_ids[:_PLAN_ID_PREVIEW_LIMIT],
        "skipped_count": plan.skipped_count,
        "has_changes": plan.has_changes,
        "changes_summary": plan.changes_summary,
        "sync_started_at": plan.sync_started_at,
        "scan_after_date": plan.scan_after_date,
        "stopped": stopped,
    }


def _stats_dict(result):
    return {
        "added": result.added,
        "updated": result.updated,
        "deleted": result.deleted,
        "skipped": result.skipped,
        "errors": result.errors,
        "elapsed_sec": result.elapsed_sec,
        "message": result.summary,
    }


def _merge_range_months(stored, requested):
    """DB 커버리지 메타 병합 (legacy main.py _merged_range_months 이식)."""
    if stored == 0 or requested == 0:
        return 0
    if stored is None or stored < 0:
        return requested
    return max(stored, requested)


def _remember_range_months(conn, range_months):
    if range_months is None:
        return
    from data.database import get_meta, set_meta
    try:
        raw = get_meta(conn, "indexed_range_months", None)
        stored = int(raw) if raw is not None and str(raw).strip() != "" else -1
    except Exception:
        stored = -1
    merged = _merge_range_months(stored, int(range_months))
    set_meta(conn, "indexed_range_months", str(merged))


# ── 명령 ──

def meta(state, params, ctx):
    from data.database import get_meta

    def work(conn):
        raw_range = get_meta(conn, "indexed_range_months", None)
        try:
            range_months = int(raw_range) if raw_range is not None else -1
        except (TypeError, ValueError):
            range_months = -1
        return {
            "last_sync_time": get_meta(conn, "last_sync_time", None),
            "indexed_range_months": range_months,
            "total_indexed": get_meta(conn, "total_indexed", None),
            "indexing_state": get_meta(conn, "indexing_state", None),
        }

    return state.in_db(work)


def plan(state, params, ctx):
    opts = _resolve_sync_params(state, params)
    channel = ctx["channel"]

    def job_fn(job):
        conn = state.job_conn()
        try:
            connector = state.com.get_connector()
            sm = _sync_manager(conn, connector)
            sync_plan = sm.create_plan(
                folder_ids=opts["folder_ids"],
                include_subfolders=opts["include_subfolders"],
                on_status=lambda msg: channel.send_event("sync.plan.progress", {"stage": "status", "message": msg}),
                should_stop=job.should_stop,
                after_date=opts["after_date"],
                incremental=opts["incremental"],
                mail_after_date=opts["mail_after_date"],
                on_scan_progress=lambda d, t, m, f: channel.send_event(
                    "sync.plan.progress",
                    {"stage": "scan", "done": d, "total": t, "message": m, "folder": f},
                ),
            )
            plan_id = uuid.uuid4().hex[:12]
            state.put_plan(plan_id, sync_plan)
            return _serialize_plan(plan_id, sync_plan, stopped=job.should_stop())
        finally:
            try:
                conn.close()
            except Exception:
                pass

    return run_job(ctx, "sync.plan", job_fn)


def execute(state, params, ctx):
    plan_id = params.get("plan_id")
    if not isinstance(plan_id, str) or not plan_id.strip():
        raise SidecarError(ErrorCode.INVALID_PARAMS, "plan_id가 필요합니다 — sync.plan을 먼저 실행하세요")
    sync_plan = state.get_plan(plan_id)  # PLAN_NOT_FOUND는 여기서 조기 반환

    opts = _resolve_sync_params(state, params)
    range_months = opts["range_months"]
    channel = ctx["channel"]

    def job_fn(job):
        conn = state.job_conn()
        try:
            connector = state.com.get_connector()
            sm = _sync_manager(conn, connector)
            result = sm.execute_plan(
                sync_plan,
                folder_ids=opts["folder_ids"],
                include_subfolders=opts["include_subfolders"],
                on_progress=lambda d, t, m: channel.send_event(
                    "sync.progress", {"done": d, "total": t, "message": m}),
                should_stop=job.should_stop,
                after_date=opts["after_date"],
                incremental=opts["incremental"],
            )
            _remember_range_months(conn, range_months)
            stats = _stats_dict(result)
            stats["stopped"] = job.should_stop()
            return stats
        finally:
            try:
                conn.close()
            except Exception:
                pass

    return run_job(ctx, "sync.execute", job_fn)


def run(state, params, ctx):
    """승인 없는 1회성 plan+execute — 자동 동기화용 (legacy SyncWorker 대체)."""
    opts = _resolve_sync_params(state, params)
    if params.get("incremental") is None:
        opts["incremental"] = True
    if opts["incremental"] and not opts["after_date"]:
        from data.database import get_meta
        try:
            opts["after_date"] = get_meta(state.require_db(), "last_sync_time", None)
        except Exception:
            opts["after_date"] = None
    channel = ctx["channel"]

    def job_fn(job):
        conn = state.job_conn()
        try:
            connector = state.com.get_connector()
            sm = _sync_manager(conn, connector)
            sync_plan = sm.create_plan(
                folder_ids=opts["folder_ids"],
                include_subfolders=opts["include_subfolders"],
                on_status=lambda msg: channel.send_event("sync.plan.progress", {"stage": "status", "message": msg}),
                should_stop=job.should_stop,
                after_date=opts["after_date"],
                incremental=opts["incremental"],
                mail_after_date=opts["mail_after_date"],
                on_scan_progress=lambda d, t, m, f: channel.send_event(
                    "sync.plan.progress",
                    {"stage": "scan", "done": d, "total": t, "message": m, "folder": f}),
            )
            if not sync_plan.has_changes:
                return {
                    "added": 0, "updated": 0, "deleted": 0,
                    "skipped": sync_plan.skipped_count, "errors": 0,
                    "elapsed_sec": 0.0,
                    "message": f"✅ 변경 없음 — {sync_plan.skipped_count:,}건 최신 상태",
                    "stopped": job.should_stop(),
                }
            result = sm.execute_plan(
                sync_plan,
                folder_ids=opts["folder_ids"],
                include_subfolders=opts["include_subfolders"],
                on_progress=lambda d, t, m: channel.send_event(
                    "sync.progress", {"done": d, "total": t, "message": m}),
                should_stop=job.should_stop,
                after_date=opts["after_date"],
                incremental=opts["incremental"],
            )
            _remember_range_months(conn, opts["range_months"])
            stats = _stats_dict(result)
            stats["stopped"] = job.should_stop()
            return stats
        finally:
            try:
                conn.close()
            except Exception:
                pass

    return run_job(ctx, "sync.run", job_fn)


def cancel(state, params, ctx):
    job = state.jobs.cancel()  # 실행 중 작업 없으면 JOB_NOT_RUNNING
    return {"ok": True, "cancelled": job.to_dict()}


def status(state, params, ctx):
    job = state.jobs.current()
    return {"running": job is not None, "job": job.to_dict() if job else None}

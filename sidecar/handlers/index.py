"""index.* — 최초/전체 인덱싱, FTS 재구축.

legacy workers/indexing_worker.IndexingWorker._do_full_indexing 의 사이드카 이식.
QThread → COM 워커 스레드 작업으로만 바뀌고 인덱싱 로직(IndexBuilder)은 무수정 재사용.
"""

import logging
import time

from sidecar.async_runner import run_job
from sidecar.handlers.sync import _range_months_to_after_date, _sync_manager  # noqa: F401 (재사용)

logger = logging.getLogger("sidecar.handlers.index")


def register(dispatcher):
    dispatcher.register("index.build", build)
    dispatcher.register("index.rebuild_fts", rebuild_fts)


def build(state, params, ctx):
    """최초/전체 인덱싱. folder_ids, include_subfolders, range_months(또는 after_date)."""
    folder_ids = [int(f) for f in (params.get("folder_ids") or [6, 5])]
    include_sub = bool(params.get("include_subfolders", True))
    range_months = params.get("range_months")
    after_date = params.get("after_date") or _range_months_to_after_date(range_months)
    channel = ctx["channel"]

    def job_fn(job):
        from core.index_builder import IndexBuilder
        from core.outlook_connector import OlDefaultFolders
        from data.database import set_meta

        conn = state.job_conn()
        try:
            connector = state.com.get_connector()
            builder = IndexBuilder(conn)

            total_count = 0
            try:
                total_count = connector.get_total_mail_count(
                    folder_ids=folder_ids,
                    include_subfolders=include_sub,
                    after_date=after_date,
                    incremental=False,
                )
            except Exception:
                total_count = 0

            channel.send_event("index.progress", {"done": 0, "total": total_count, "message": "시작 중...", "folder": ""})

            overall = {"added": 0, "skipped": 0, "errors": 0}
            start = time.time()

            for fid in folder_ids:
                if job.should_stop():
                    break
                fname = OlDefaultFolders.NAMES.get(fid, f"폴더{fid}")
                try:
                    mail_iter = connector.iter_mails(
                        fid, include_subfolders=include_sub,
                        after_date=after_date, incremental=False,
                    )

                    def on_progress(done, total, subject, _fname=fname):
                        channel.send_event("index.progress", {
                            "done": overall["added"] + overall["skipped"] + overall["errors"] + done,
                            "total": total_count,
                            "message": subject or "",
                            "folder": _fname,
                        })

                    stats = builder.build_from_iterator(
                        mail_iterator=mail_iter,
                        total_count=total_count,
                        on_progress=on_progress,
                        should_stop=job.should_stop,
                    )
                    overall["added"] += stats["indexed"]
                    overall["skipped"] += stats["skipped"]
                    overall["errors"] += stats["errors"]
                except Exception as e:
                    logger.error(f"폴더 '{fname}' 인덱싱 오류: {e}")
                    overall["errors"] += 1

            elapsed = round(time.time() - start, 2)
            if not job.should_stop():
                try:
                    builder.optimize_fts_index()
                except Exception:
                    pass
                if range_months is not None:
                    try:
                        set_meta(conn, "indexed_range_months", str(int(range_months)))
                    except Exception:
                        pass

            return {
                "added": overall["added"],
                "skipped": overall["skipped"],
                "errors": overall["errors"],
                "elapsed_sec": elapsed,
                "stopped": job.should_stop(),
                "message": f"{overall['added']}건 추가, {overall['skipped']}건 스킵, {elapsed}초",
            }
        finally:
            try:
                conn.close()
            except Exception:
                pass

    return run_job(ctx, "index.build", job_fn)


def rebuild_fts(state, params, ctx):
    """FTS5 검색 인덱스 재구축 (설정 → 데이터 탭 기능 이식)."""

    def job_fn(job):
        conn = state.job_conn()
        try:
            start = time.time()
            conn.execute("INSERT INTO emails_fts(emails_fts) VALUES('rebuild')")
            conn.commit()
            return {"ok": True, "elapsed_sec": round(time.time() - start, 2)}
        finally:
            try:
                conn.close()
            except Exception:
                pass

    return run_job(ctx, "index.rebuild_fts", job_fn)

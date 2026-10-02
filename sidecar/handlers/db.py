"""db.* — 통계 / 초기화 / 백업 / 무결성 / 스키마 버전."""

import logging
import os

logger = logging.getLogger("sidecar.handlers.db")


def register(dispatcher):
    dispatcher.register("db.stats", stats)
    dispatcher.register("db.reset", reset)
    dispatcher.register("db.backup", backup)
    dispatcher.register("db.integrity", integrity)
    dispatcher.register("db.schema_version", schema_version)


def _meta(conn, key, default=None):
    from data.database import get_meta
    return get_meta(conn, key, default)


def stats(state, params, ctx):
    from data.database import get_email_count, get_mock_email_count

    def work(conn):
        size_mb = 0.0
        try:
            size_mb = round(os.path.getsize(state.db_path) / 1024 / 1024, 2)
        except Exception:
            pass
        return {
            "email_count": get_email_count(conn),
            "mock_count": get_mock_email_count(conn),
            "bookmark_count": conn.execute("SELECT COUNT(*) as n FROM bookmarks").fetchone()["n"],
            "history_count": conn.execute("SELECT COUNT(*) as n FROM search_history").fetchone()["n"],
            "db_size_mb": size_mb,
            "db_path": str(state.db_path),
            "last_sync_time": _meta(conn, "last_sync_time"),
            "indexed_range_months": _meta(conn, "indexed_range_months"),
            "total_indexed": _meta(conn, "total_indexed"),
            "indexing_state": _meta(conn, "indexing_state"),
            "schema_version": _meta(conn, "schema_version"),
        }

    return state.in_db(work)


def reset(state, params, ctx):
    """Mock/데모 데이터 제거 (실 Outlook 동기화 준비)."""
    from data.database import purge_mock_data
    removed = state.in_db(purge_mock_data)
    return {"removed": removed}


def backup(state, params, ctx):
    """DB 백업 생성 (계획 §5 리스크 4 — 마이그레이션 전 백업).

    WAL 모드라 파일 복사보다 sqlite3 backup API가 안전하다.
    """
    import sqlite3

    suffix = str(params.get("suffix") or "bak-v0.9.1")
    suffix = "".join(c for c in suffix if c.isalnum() or c in "-_.")[:64] or "backup"
    dest = state.db_path.with_name(f"{state.db_path.name}.{suffix}")

    def work(conn):
        dest_conn = sqlite3.connect(str(dest))
        try:
            conn.backup(dest_conn)
        finally:
            dest_conn.close()
        return {"path": str(dest), "size_mb": round(os.path.getsize(dest) / 1024 / 1024, 2)}

    return state.in_db(work)


def integrity(state, params, ctx):
    from core.error_handler import check_db_integrity
    ok, message = state.in_db(check_db_integrity)
    return {"ok": bool(ok), "message": message}


def schema_version(state, params, ctx):
    """스키마 버전 조회/기록 — 사이드카·프론트 버전 불일치 감지용 (계획 리스크 4)."""
    from data.database import set_meta
    from sidecar.state import SCHEMA_VERSION

    requested = params.get("version")
    if requested is not None:
        try:
            requested = int(requested)
        except (TypeError, ValueError):
            from sidecar.protocol import ErrorCode, SidecarError
            raise SidecarError(ErrorCode.INVALID_PARAMS, "version은 정수여야 합니다")

        def write(conn):
            set_meta(conn, "schema_version", str(requested))
            return requested

        current = state.in_db(write)
    else:
        current = int(_meta(state.require_db(), "schema_version") or SCHEMA_VERSION)
    return {"schema_version": current, "sidecar_schema_version": SCHEMA_VERSION}

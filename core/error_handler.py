"""
OutLook AnyFinder Ver0.9.1.1 for SESUNG Team
에러 핸들링 통합 모듈

5가지 핵심 에러 시나리오:
  1. Outlook 미실행 / 연결 실패
  2. 인덱싱 중 Outlook 종료 / COM 연결 끊김
  3. DB 손상 / 무결성 오류
  4. 디스크 공간 부족
  5. 예상치 못한 일반 에러
"""

import os
import sqlite3
import logging
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class AppError(Exception):
    """앱 내부 에러 기본 클래스"""
    def __init__(self, title: str, message: str, suggestion: str = ""):
        self.title = title
        self.message = message
        self.suggestion = suggestion
        super().__init__(message)


class OutlookNotRunningError(AppError):
    def __init__(self):
        super().__init__(
            title="Outlook 연결 실패",
            message="Microsoft Outlook이 실행되고 있지 않거나 연결할 수 없습니다.",
            suggestion="Outlook을 실행한 후 다시 시도해 주세요.\n"
                       "Outlook이 설치되어 있지 않다면 데모 모드로 실행됩니다."
        )


class OutlookDisconnectedError(AppError):
    def __init__(self):
        super().__init__(
            title="Outlook 연결 끊김",
            message="인덱싱 중 Outlook과의 연결이 끊어졌습니다.",
            suggestion="이미 인덱싱된 메일은 검색 가능합니다.\n"
                       "Outlook을 확인한 후 '지금 동기화'를 클릭하세요."
        )


class DatabaseCorruptedError(AppError):
    def __init__(self, detail: str = ""):
        super().__init__(
            title="데이터베이스 오류",
            message=f"검색 데이터베이스에 문제가 발생했습니다.\n{detail}",
            suggestion="설정 → 데이터 → '전체 데이터 삭제 및 초기화'를 실행하거나\n"
                       "앱을 재시작하면 자동 복구를 시도합니다."
        )


class DiskSpaceError(AppError):
    def __init__(self, available_mb: float):
        super().__init__(
            title="디스크 공간 부족",
            message=f"디스크 여유 공간이 부족합니다. (현재: {available_mb:.0f}MB)",
            suggestion="불필요한 파일을 삭제하여 최소 200MB 이상 확보해 주세요."
        )


# ═══════════════════════════════════════
#  검증 함수들
# ═══════════════════════════════════════

def check_disk_space(path: Path = None, min_mb: float = 100) -> Tuple[bool, float]:
    """
    디스크 여유 공간 확인.

    Returns:
        (충분여부, 여유MB)
    """
    if path is None:
        path = Path.home()

    try:
        stat = os.statvfs(str(path)) if hasattr(os, 'statvfs') else None
        if stat:
            available_mb = (stat.f_bavail * stat.f_frsize) / (1024 * 1024)
        else:
            # Windows
            import shutil
            total, used, free = shutil.disk_usage(str(path))
            available_mb = free / (1024 * 1024)

        return available_mb >= min_mb, available_mb
    except Exception:
        return True, 999  # 확인 불가 시 통과 처리


def check_db_integrity(conn: sqlite3.Connection) -> Tuple[bool, str]:
    """
    DB 무결성 검사 (PRAGMA quick_check).

    Returns:
        (정상여부, 상세메시지)
    """
    try:
        result = conn.execute("PRAGMA quick_check").fetchone()
        if result and result[0] == "ok":
            return True, "ok"
        return False, str(result[0]) if result else "unknown error"
    except Exception as e:
        return False, str(e)


def try_recover_db(conn: sqlite3.Connection) -> bool:
    """
    DB 복구 시도 — FTS5 인덱스 재구축.

    Returns:
        복구 성공 여부
    """
    try:
        conn.execute("INSERT INTO emails_fts(emails_fts) VALUES('rebuild')")
        conn.commit()
        logger.info("FTS5 인덱스 재구축 성공")
        return True
    except Exception as e:
        logger.error(f"FTS5 재구축 실패: {e}")
        return False


def check_outlook_available() -> Tuple[bool, str]:
    """
    Outlook 연결 가능 여부 확인 (빠른 체크).

    Returns:
        (가능여부, 에러메시지)
    """
    try:
        import win32com.client
        outlook = win32com.client.Dispatch("Outlook.Application")
        mapi = outlook.GetNamespace("MAPI")
        # 간단한 접근 테스트
        _ = mapi.GetDefaultFolder(6).Name
        return True, ""
    except ImportError:
        return False, "win32com 미설치 (Windows 전용)"
    except Exception as e:
        return False, str(e)


def safe_search(conn: sqlite3.Connection, search_fn, *args, **kwargs):
    """
    검색 실행을 안전하게 래핑.
    DB 오류 시 자동 복구 시도 후 재실행.

    Args:
        conn: DB 연결
        search_fn: 실제 검색 함수
        *args, **kwargs: 검색 함수 인자

    Returns:
        검색 결과 또는 None
    """
    try:
        return search_fn(*args, **kwargs)
    except sqlite3.DatabaseError as e:
        logger.warning(f"검색 중 DB 오류: {e}, 복구 시도...")
        if try_recover_db(conn):
            try:
                return search_fn(*args, **kwargs)
            except Exception as e2:
                logger.error(f"복구 후 재검색 실패: {e2}")
                raise DatabaseCorruptedError(str(e2))
        raise DatabaseCorruptedError(str(e))
    except Exception as e:
        logger.error(f"검색 오류: {e}")
        raise


def safe_db_operation(conn: sqlite3.Connection, operation_fn, *args, **kwargs):
    """
    DB 쓰기 작업을 안전하게 래핑.
    디스크 공간 체크 + 에러 핸들링.
    """
    # 디스크 공간 체크
    ok, avail = check_disk_space()
    if not ok:
        raise DiskSpaceError(avail)

    try:
        return operation_fn(*args, **kwargs)
    except sqlite3.OperationalError as e:
        if "disk" in str(e).lower() or "full" in str(e).lower():
            raise DiskSpaceError(0)
        raise
    except sqlite3.DatabaseError as e:
        raise DatabaseCorruptedError(str(e))

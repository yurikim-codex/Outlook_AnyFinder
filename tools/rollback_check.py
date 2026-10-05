"""롤백 전/후 데이터 무결성 검사 (Phase 4-6).

신구 버전이 **같은 데이터 디렉터리·같은 스키마·같은 config 스키마**를 쓰므로
롤백은 설치물 교체만 필요하다. 이 스크립트는 그 전제(데이터 무사)를 기계적으로 확인한다.

사용:
  python tools/rollback_check.py            # 기본 검사
  python tools/rollback_check.py --full     # PRAGMA integrity_check 포함(대용량 시 느림)
  ANYFINDER_DATA_DIR=D:\\data python ...     # 데이터 디렉터리 지정

종료코드: 0 = 정상, 1 = 문제 있음 (롤백 스크립트는 1이면 중단)
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path

REQUIRED_TABLES = ["emails", "emails_fts", "bookmarks", "search_history", "sync_meta"]
LEGACY_CONFIG_KEYS = ["indexing", "sync", "search", "ui", "first_run_completed"]


def main() -> int:
    full = "--full" in sys.argv[1:]
    data_dir = Path(os.environ.get("ANYFINDER_DATA_DIR") or (Path.home() / ".outlook_anyfinder"))
    db_path = data_dir / "anyfinder.db"
    cfg_path = data_dir / "config.json"

    problems: list[str] = []
    print(f"[rollback-check] data_dir = {data_dir}")

    # 1) config.json — 레거시 스키마 키 보존 여부
    if cfg_path.exists():
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            missing = [k for k in LEGACY_CONFIG_KEYS if k not in cfg]
            if missing:
                problems.append(f"config.json 레거시 키 누락: {missing} (구버전 실행 시 기본값으로 대체됨)")
            else:
                print(f"  ✔ config.json 레거시 스키마 유지 (테마={cfg.get('ui', {}).get('theme')})")
        except Exception as e:
            problems.append(f"config.json 파싱 실패: {e}")
    else:
        print("  · config.json 없음 (첫 실행 전 — 정상)")

    # 2) DB — 열림/테이블/건수
    if not db_path.exists():
        print("  · anyfinder.db 없음 (첫 실행 전 — 정상)")
    else:
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            missing_tables = [t for t in REQUIRED_TABLES if t not in tables]
            if missing_tables:
                problems.append(f"DB 테이블 누락: {missing_tables}")
            emails = conn.execute("SELECT COUNT(*) FROM emails").fetchone()[0]
            bookmarks = conn.execute("SELECT COUNT(*) FROM bookmarks").fetchone()[0]
            meta = dict(
                (r[0], r[1])
                for r in conn.execute("SELECT key, value FROM sync_meta")
                if r[0] in ("schema_version", "last_sync_time", "indexed_range_months")
            )
            print(f"  ✔ DB 열림 — emails={emails}, bookmarks={bookmarks}, meta={meta}")
            if full:
                ok = conn.execute("PRAGMA integrity_check").fetchone()[0]
                if ok != "ok":
                    problems.append(f"integrity_check: {ok}")
                else:
                    print("  ✔ PRAGMA integrity_check = ok")
            conn.close()
        except Exception as e:
            problems.append(f"DB 열기 실패: {e}")

    # 3) 결론
    if problems:
        print("\n[rollback-check] 문제 발견:")
        for p in problems:
            print("  ✗", p)
        return 1
    print("\n[rollback-check] 데이터 무결 — 롤백/복귀 모두 안전합니다 ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())

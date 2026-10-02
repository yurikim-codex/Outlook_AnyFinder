"""
serialize — dataclass/sqlite3.Row/datetime → JSON 안전 변환.

원칙: 이 모듈은 어떤 입력에도 예외를 발생시키지 않는다 ("예외 불가침").
직렬화 실패는 프로토콜 장애(앱 전체 마비)로 이어지므로 항상 폴백(str)을 갖는다.
"""

import dataclasses
import datetime
import sqlite3
from pathlib import Path

_MAX_DEPTH = 8


def to_jsonable(obj, _depth: int = 0):
    if _depth > _MAX_DEPTH:
        return str(obj)
    if obj is None or isinstance(obj, (bool, int, str)):
        return obj
    if isinstance(obj, float):
        # NaN/Inf는 JSON 표준이 아니다 → None
        if obj != obj or obj in (float("inf"), float("-inf")):
            return None
        return obj
    if isinstance(obj, (datetime.datetime, datetime.date, datetime.time)):
        return obj.isoformat()
    if isinstance(obj, datetime.timedelta):
        return obj.total_seconds()
    if isinstance(obj, (bytes, bytearray)):
        return bytes(obj).decode("utf-8", errors="replace")
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, sqlite3.Row):
        try:
            return {k: to_jsonable(obj[k], _depth + 1) for k in obj.keys()}
        except Exception:
            return str(obj)
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        out = {}
        for f in dataclasses.fields(obj):
            try:
                out[f.name] = to_jsonable(getattr(obj, f.name, None), _depth + 1)
            except Exception:
                out[f.name] = None
        return out
    if isinstance(obj, dict):
        out = {}
        # ★ list() 스냅샷 — "dictionary changed size during iteration" 방지
        #   (계획 Phase 1 잠재 버그 #2 대응)
        for k, v in list(obj.items()):
            try:
                out[str(k)] = to_jsonable(v, _depth + 1)
            except Exception:
                out[str(k)] = None
        return out
    if isinstance(obj, (set, frozenset)):
        return [to_jsonable(v, _depth + 1) for v in obj]
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(v, _depth + 1) for v in obj]
    to_dict = getattr(obj, "to_dict", None)
    if callable(to_dict):
        try:
            return to_jsonable(to_dict(), _depth + 1)
        except Exception:
            pass
    return str(obj)

"""autocomplete.* — 검색어 자동완성 / 메일주소 인라인 자동완성 후보."""

import logging
import re

from sidecar.serialize import to_jsonable

logger = logging.getLogger("sidecar.handlers.autocomplete")

_EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")


def register(dispatcher):
    dispatcher.register("autocomplete.suggest", suggest)
    dispatcher.register("autocomplete.emails", emails)


def suggest(state, params, ctx):
    prefix = str(params.get("prefix", "") or "")
    limit = params.get("limit")
    limit = int(limit) if limit else None

    def work(conn):
        from core.autocomplete import AutocompleteEngine
        engine = AutocompleteEngine(conn)
        items = engine.get_suggestions(prefix, limit=limit) if prefix else engine.get_recent(limit=limit)
        return {"suggestions": [to_jsonable(i) for i in items]}

    return state.in_db(work)


def emails(state, params, ctx):
    """DB에서 메일주소 후보 수집 (legacy main_window._load_email_suggestions 이식)."""

    def work(conn):
        found = set()
        rows = conn.execute("""
            SELECT sender_email, recipients, cc
            FROM emails
            WHERE sender_email != '' OR recipients != '' OR cc != ''
        """).fetchall()
        for row in list(rows):  # 스냅샷 순회
            for col in ("sender_email", "recipients", "cc"):
                value = row[col] or ""
                found.update(_EMAIL_PATTERN.findall(value))
        return {"emails": sorted(found), "count": len(found)}

    return state.in_db(work)

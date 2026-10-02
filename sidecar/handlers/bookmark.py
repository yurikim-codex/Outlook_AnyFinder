"""bookmark.* — 검색어 북마크 CRUD (core/bookmark_manager 무수정 재사용)."""

import json
import logging

from sidecar.async_runner import require_int, require_str
from sidecar.protocol import ErrorCode, SidecarError
from sidecar.serialize import to_jsonable

logger = logging.getLogger("sidecar.handlers.bookmark")


def register(dispatcher):
    dispatcher.register("bookmark.list", list_bookmarks)
    dispatcher.register("bookmark.add", add)
    dispatcher.register("bookmark.remove", remove)
    dispatcher.register("bookmark.toggle", toggle)
    dispatcher.register("bookmark.rename", rename)


def _item(bm):
    data = to_jsonable(bm)
    try:
        data["filters"] = json.loads(bm.filters) if bm.filters else {}
    except Exception:
        data["filters"] = {}
    return data


def list_bookmarks(state, params, ctx):
    def work(conn):
        from core.bookmark_manager import BookmarkManager
        items = BookmarkManager(conn).get_all()
        return {"items": [_item(b) for b in items], "count": len(items)}

    return state.in_db(work)


def add(state, params, ctx):
    query = require_str(params, "query")
    name = str(params.get("name") or "").strip() or query
    filters = params.get("filters")
    if filters is not None and not isinstance(filters, dict):
        raise SidecarError(ErrorCode.INVALID_PARAMS, "filters는 JSON 객체여야 합니다")

    def work(conn):
        from core.bookmark_manager import BookmarkManager
        return BookmarkManager(conn).add(name, query=query, filters=filters or {})

    bid = state.in_db(work)
    if bid is None or bid < 0:
        raise SidecarError(ErrorCode.DB_ERROR, "북마크 추가에 실패했습니다")
    return {"id": bid, "name": name, "query": query}


def remove(state, params, ctx):
    bid = require_int(params, "id")

    def work(conn):
        from core.bookmark_manager import BookmarkManager
        return BookmarkManager(conn).delete(bid)

    removed = state.in_db(work)
    # ★ 없는 ID 삭제는 removed=False (계획 Phase 1 잠재 버그 #1 수정 반영)
    return {"removed": bool(removed), "id": bid}


def toggle(state, params, ctx):
    query = require_str(params, "query")
    filters = params.get("filters")
    if filters is not None and not isinstance(filters, dict):
        raise SidecarError(ErrorCode.INVALID_PARAMS, "filters는 JSON 객체여야 합니다")

    def work(conn):
        from core.bookmark_manager import BookmarkManager
        return BookmarkManager(conn).toggle(query, filters or {})

    bookmarked = state.in_db(work)
    return {"bookmarked": bool(bookmarked), "query": query}


def rename(state, params, ctx):
    bid = require_int(params, "id")
    name = require_str(params, "name")

    def work(conn):
        from core.bookmark_manager import BookmarkManager
        return BookmarkManager(conn).update_name(bid, name)

    ok = state.in_db(work)
    return {"ok": bool(ok), "id": bid, "name": name}

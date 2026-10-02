"""search.* — 검색 / 폴더 카운트 / 검색 기록 / 연관 검색어.

★ 검색은 Outlook COM을 사용하지 않는다 → 동기화 중에도 즉시 응답한다.
"""

import logging

from sidecar.protocol import ErrorCode, SidecarError
from sidecar.serialize import to_jsonable

logger = logging.getLogger("sidecar.handlers.search")

# Outlook 환경별 폴더명 차이 흡수 (legacy main.py와 동일한 별칭 테이블)
FOLDER_ALIASES = {
    "받은편지함": ["받은편지함", "받은 편지함", "Inbox"],
    "보낸편지함": ["보낸편지함", "보낸 편지함", "Sent Items", "Sent"],
    "임시보관함": ["임시보관함", "임시 보관함", "Drafts"],
    "지운편지함": ["지운편지함", "지운 편지함", "Deleted Items", "Trash"],
}

# 역방향 별칭 → 정규 그룹 (예: "Inbox" 입력 → 받은편지함 전체 별칭으로 확장)
_ALIAS_TO_GROUP = {}
for _group in FOLDER_ALIASES.values():
    for _alias in _group:
        _ALIAS_TO_GROUP[_alias] = _group
        _ALIAS_TO_GROUP[_alias.lower()] = _group

_VALID_SORTS = {"rank", "received_at_desc", "received_at_asc", "newest", "oldest"}
_MAX_PER_PAGE = 500


def register(dispatcher):
    dispatcher.register("search.query", query)
    dispatcher.register("search.folders", folders)
    dispatcher.register("search.record", record)
    dispatcher.register("search.history", history)
    dispatcher.register("search.related", related)


def _folder_or_clause(folder_names):
    """다중 폴더 필터는 OR 결합이다 (계획 Phase 1 잠재 버그 #3 수정).

    legacy PyQt6판은 받은/보낸 동시 선택 시 AND로 결합되어 결과가 비는 잠재 버그가 있었다.
    """
    all_names = []
    for name in folder_names:
        name = str(name).strip()
        if not name:
            continue
        group = FOLDER_ALIASES.get(name) or _ALIAS_TO_GROUP.get(name) or _ALIAS_TO_GROUP.get(name.lower())
        all_names.extend(group or [name])
    if not all_names:
        return None
    # 중복 제거 (순서 유지)
    all_names = list(dict.fromkeys(all_names))
    placeholders = ",".join("?" for _ in all_names)
    return (f"folder_name IN ({placeholders})", all_names)


def _normalize_sort(sort_by):
    sort_by = str(sort_by or "rank")
    mapping = {"newest": "received_at_desc", "oldest": "received_at_asc"}
    sort_by = mapping.get(sort_by, sort_by)
    if sort_by not in _VALID_SORTS:
        raise SidecarError(ErrorCode.INVALID_PARAMS,
                           f"sort_by는 {sorted(_VALID_SORTS)} 중 하나여야 합니다: {sort_by!r}")
    return sort_by


def query(state, params, ctx):
    from core.search_engine import SearchEngine

    text = str(params.get("query", "") or "")
    page = max(1, int(params.get("page", 1) or 1))
    per_page = min(max(1, int(params.get("per_page", 20) or 20)), _MAX_PER_PAGE)
    sort_by = _normalize_sort(params.get("sort_by", "rank") if text else params.get("sort_by", "received_at_desc"))
    contains = bool(params.get("contains_search", False))

    extra = []
    folder_clause = _folder_or_clause(params.get("folders") or [])
    if folder_clause:
        extra.append(folder_clause)

    attachment = params.get("attachment")
    if attachment == "has":
        extra.append(("has_attachments = ?", [1]))
    elif attachment == "none":
        extra.append(("has_attachments = ?", [0]))
    elif isinstance(attachment, str) and attachment.strip():
        extra.append(("attachment_types LIKE ?", [f"%{attachment.strip().lower()}%"]))

    date_from = params.get("date_from")
    date_to = params.get("date_to")
    if isinstance(date_from, str) and date_from.strip():
        extra.append(("received_at >= ?", [date_from.strip()]))
    if isinstance(date_to, str) and date_to.strip():
        extra.append(("received_at <= ?", [date_to.strip()]))

    def work(conn):
        engine = SearchEngine(conn)
        resp = engine.search(
            query=text, page=page, per_page=per_page, sort_by=sort_by,
            extra_where=extra or None, contains_search=contains,
        )
        items = [
            {
                "email": to_jsonable(r.email),
                "rank_score": r.rank_score,
                "title_snippet": r.title_snippet,
                "body_snippet": r.body_snippet,
            }
            for r in resp.results
        ]
        total_db = engine.get_total_count()
        if params.get("record_history") and text.strip():
            try:
                from core.autocomplete import AutocompleteEngine
                AutocompleteEngine(conn).record_search(text.strip())
            except Exception as e:
                logger.debug(f"검색 기록 실패(무시): {e}")
        return {
            "items": items,
            "total_count": resp.total_count,
            "total_db_count": total_db,
            "page": resp.page,
            "per_page": per_page,
            "total_pages": resp.total_pages,
            "has_next": resp.has_next,
            "has_prev": resp.has_prev,
            "elapsed_ms": resp.elapsed_ms,
            "query": text,
            "sort_by": sort_by,
        }

    return state.in_db(work)


def folders(state, params, ctx):
    from core.search_engine import SearchEngine

    def work(conn):
        engine = SearchEngine(conn)
        counts = engine.get_folder_counts()
        return {"counts": counts, "total": sum(counts.values())}

    return state.in_db(work)


def record(state, params, ctx):
    keyword = str(params.get("keyword", "") or "").strip()
    if not keyword:
        raise SidecarError(ErrorCode.INVALID_PARAMS, "keyword가 비어 있습니다")

    def work(conn):
        from core.autocomplete import AutocompleteEngine
        AutocompleteEngine(conn).record_search(keyword)
        return {"ok": True, "keyword": keyword}

    return state.in_db(work)


def history(state, params, ctx):
    limit = min(max(1, int(params.get("limit", 20) or 20)), 100)

    def work(conn):
        from core.autocomplete import AutocompleteEngine
        items = AutocompleteEngine(conn).get_recent(limit=limit)
        return {"items": [to_jsonable(i) for i in items]}

    return state.in_db(work)


def related(state, params, ctx):
    keyword = str(params.get("keyword", "") or "").strip()
    if not keyword:
        raise SidecarError(ErrorCode.INVALID_PARAMS, "keyword가 비어 있습니다")
    limit = params.get("limit")
    limit = int(limit) if limit else None

    def work(conn):
        from core.related_keywords import RelatedKeywordsEngine
        engine = RelatedKeywordsEngine(conn)
        return {"keywords": engine.get_related(keyword, limit=limit)}

    return state.in_db(work)

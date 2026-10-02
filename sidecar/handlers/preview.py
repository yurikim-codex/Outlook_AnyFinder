"""preview.* — HTML 본문 정리 / 메일 상세 미리보기 데이터."""

import logging

from sidecar.async_runner import require_str
from sidecar.protocol import ErrorCode, SidecarError
from sidecar.serialize import to_jsonable

logger = logging.getLogger("sidecar.handlers.preview")


def register(dispatcher):
    dispatcher.register("preview.html", html)
    dispatcher.register("preview.mail", mail)


def html(state, params, ctx):
    """HTML → 평문 변환 (utils/html_cleaner 무수정 재사용)."""
    raw = params.get("html")
    if raw is None:
        raise SidecarError(ErrorCode.INVALID_PARAMS, "html 파라미터가 필요합니다")
    from utils.html_cleaner import strip_html
    text = strip_html(str(raw))
    return {"text": text, "char_count": len(text)}


def mail(state, params, ctx):
    """entry_id로 DB에서 메일 상세(미리보기 패널용) 조회."""
    entry_id = require_str(params, "entry_id")

    def work(conn):
        row = conn.execute("SELECT * FROM emails WHERE entry_id=?", (entry_id,)).fetchone()
        if row is None:
            raise SidecarError(ErrorCode.INVALID_PARAMS,
                               f"메일을 찾을 수 없습니다: {entry_id}",
                               details={"entry_id": entry_id})
        data = to_jsonable(row)
        names = (data.get("attachment_names") or "").strip()
        types = (data.get("attachment_types") or "").strip()
        data["attachments"] = [n.strip() for n in names.split(",") if n.strip()] if names else []
        data["attachment_type_list"] = [t.strip() for t in types.split(",") if t.strip()] if types else []
        return {"email": data}

    return state.in_db(work)

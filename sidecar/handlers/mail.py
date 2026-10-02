"""mail.* — Outlook에서 메일 열기 / .msg 내보내기 (COM 스레드 경유)."""

import logging
import os

from sidecar.async_runner import require_str, run_on_com
from sidecar.protocol import ErrorCode, SidecarError

logger = logging.getLogger("sidecar.handlers.mail")

_OL_MSG = 3  # olMSG


def register(dispatcher):
    dispatcher.register("mail.open", open_mail)
    dispatcher.register("mail.export", export)


def open_mail(state, params, ctx):
    entry_id = require_str(params, "entry_id")

    def job():
        connector = state.com.get_connector()
        connector.open_mail_in_outlook(entry_id)
        return {"ok": True, "entry_id": entry_id, "mock": state.use_mock}

    return run_on_com(ctx, job)


def export(state, params, ctx):
    """메일을 .msg 파일로 저장 (실 Outlook 모드 전용)."""
    entry_id = require_str(params, "entry_id")
    dest = require_str(params, "dest_path")
    dest = os.path.expanduser(dest)

    if state.use_mock:
        raise SidecarError(ErrorCode.NOT_SUPPORTED, "Mock 모드에서는 mail.export를 지원하지 않습니다")

    def job():
        connector = state.com.get_connector()
        mapi = getattr(connector, "mapi", None)
        if mapi is None:
            raise SidecarError(ErrorCode.OUTLOOK_CONNECT_FAILED, "Outlook MAPI 세션을 사용할 수 없습니다")
        item = mapi.GetItemFromID(entry_id)
        parent = os.path.dirname(dest)
        if parent:
            os.makedirs(parent, exist_ok=True)
        item.SaveAs(dest, _OL_MSG)
        return {"path": dest, "size": os.path.getsize(dest) if os.path.exists(dest) else None}

    return run_on_com(ctx, job)

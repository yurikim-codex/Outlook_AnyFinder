"""outlook.* — Outlook COM 진단 / 폴더 목록 (outlook_com_check.py 기능 이식)."""

import logging

from sidecar.async_runner import run_on_com

logger = logging.getLogger("sidecar.handlers.outlook")


def register(dispatcher):
    dispatcher.register("outlook.check", check)
    dispatcher.register("outlook.folders", folders)
    dispatcher.register("outlook.default_folders", default_folders)


def check(state, params, ctx):
    """Outlook COM 연결 진단 — 배포 현장 문제해결 가이드의 1차 도구."""

    def job():
        info = {"mock": state.use_mock, "ok": False, "connected": False,
                "pywin32_imported": None, "version": "", "message": ""}
        if state.use_mock:
            state.com.get_connector()
            info.update(ok=True, connected=True,
                        message="Mock 커넥터 활성 — 실 Outlook 진단은 Windows에서만 가능합니다")
            return info

        from core.outlook_connector import HAS_WIN32, WIN32_IMPORT_ERROR
        info["pywin32_imported"] = bool(HAS_WIN32)
        if not HAS_WIN32:
            info["message"] = f"FAIL: pywin32 import 실패 — {WIN32_IMPORT_ERROR}"
            return info
        try:
            connector = state.com.get_connector()
            info["connected"] = True
            try:
                info["version"] = str(connector.outlook.Version)
            except Exception:
                pass
            try:
                inbox = connector.mapi.GetDefaultFolder(6)
                info["inbox_name"] = str(getattr(inbox, "Name", ""))
                info["inbox_count"] = int(getattr(inbox.Items, "Count", 0) or 0)
            except Exception:
                pass
            info["ok"] = True
            info["message"] = "OK: Outlook COM connected"
        except Exception as e:
            info["message"] = f"FAIL: Outlook COM 연결 실패 — {e}"
        return info

    return run_on_com(ctx, job)


def folders(state, params, ctx):
    """Outlook 실제 폴더 목록(건수 포함)."""

    def job():
        connector = state.com.get_connector()
        return {"folders": connector.get_folder_list()}

    return run_on_com(ctx, job)


def default_folders(state, params, ctx):
    """OlDefaultFolders 정적 매핑 — UI 폴더 선택지 구성용 (COM 불필요)."""
    from core.outlook_connector import OlDefaultFolders
    folders = [{"id": fid, "name": name} for fid, name in sorted(OlDefaultFolders.NAMES.items())]
    return {"folders": folders, "selectable": [6, 5, 16, 3]}

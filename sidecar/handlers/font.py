"""font.* — 시스템 폰트 목록 (React 폰트 설정 UI 지원, best-effort)."""

import logging
import sys

logger = logging.getLogger("sidecar.handlers.font")

# 조회 실패 시 폴백 — 한국어 환경 공통 폰트 중심
_FALLBACK_FAMILIES = [
    "Pretendard Variable", "Pretendard",
    "Malgun Gothic", "맑은 고딕",
    "Nanum Gothic", "나눔고딕", "NanumSquare",
    "Segoe UI", "Arial", "Tahoma",
]


def register(dispatcher):
    dispatcher.register("font.list", list_fonts)


def _windows_registry_families():
    import winreg
    families = set()
    keys = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"),
    ]
    for hive, path in keys:
        try:
            with winreg.OpenKey(hive, path) as key:
                i = 0
                while True:
                    try:
                        name, _value, _type = winreg.EnumValue(key, i)
                        i += 1
                    except OSError:
                        break
                    # "Malgun Gothic (TrueType)" → "Malgun Gothic"
                    family = name.split("(")[0].strip()
                    if family:
                        families.add(family)
        except OSError:
            continue
    return sorted(families)


def list_fonts(state, params, ctx):
    if sys.platform == "win32":
        try:
            families = _windows_registry_families()
            if families:
                return {"families": families, "count": len(families), "source": "registry"}
        except Exception as e:
            logger.debug(f"폰트 레지스트리 조회 실패 — 폴백 사용: {e}")
    return {"families": list(_FALLBACK_FAMILIES), "count": len(_FALLBACK_FAMILIES), "source": "fallback"}

"""settings.* — config.json 조회/부분 갱신 (utils/config 무수정 재사용 + 깊은 머지)."""

import logging

from sidecar.protocol import ErrorCode, SidecarError
from sidecar.state import deep_merge

logger = logging.getLogger("sidecar.handlers.settings")


def register(dispatcher):
    dispatcher.register("settings.get", get)
    dispatcher.register("settings.set", set_)


def get(state, params, ctx):
    return {"settings": state.load_settings(), "path": str(state.config_path)}


def set_(state, params, ctx):
    """patch(부분 객체)를 현재 설정에 깊은 머지하여 저장한다.

    예: {"patch": {"ui": {"theme": "warm-dark"}}} → ui.theme만 변경, 나머지 보존.
    """
    patch = params.get("patch")
    if not isinstance(patch, dict) or not patch:
        raise SidecarError(ErrorCode.INVALID_PARAMS, "patch는 비어있지 않은 JSON 객체여야 합니다")
    current = state.load_settings()
    merged = deep_merge(current, patch)
    try:
        state.save_settings(merged)
    except Exception as e:
        raise SidecarError(ErrorCode.INTERNAL, f"설정 저장 실패: {e}")
    logger.info(f"설정 저장: patch keys={list(patch.keys())}")
    return {"settings": merged, "path": str(state.config_path)}

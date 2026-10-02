"""
cmd → handler 라우팅 테이블.

handler 시그니처: fn(state: SidecarState, params: dict, ctx: dict) -> dict | ASYNC
    ctx = {"id", "channel", "server", "state", "dispatcher"}
"""

import logging

from .protocol import ErrorCode, SidecarError

logger = logging.getLogger("sidecar.dispatcher")


class Dispatcher:
    def __init__(self):
        self._routes = {}

    def register(self, cmd: str, fn):
        if cmd in self._routes:
            logger.warning(f"명령 중복 등록(덮어씀): {cmd}")
        self._routes[cmd] = fn

    def register_module(self, module):
        """handlers 모듈의 register(dispatcher)를 호출한다."""
        module.register(self)

    def dispatch(self, cmd: str, params: dict, ctx: dict):
        fn = self._routes.get(cmd)
        if fn is None:
            raise SidecarError(
                ErrorCode.UNKNOWN_COMMAND,
                f"알 수 없는 명령: {cmd} — system.commands로 목록을 확인하세요",
                details={"cmd": cmd},
            )
        return fn(ctx["state"], params, ctx)

    def commands(self):
        return sorted(self._routes.keys())

    def __len__(self):
        return len(self._routes)

    def __contains__(self, cmd):
        return cmd in self._routes

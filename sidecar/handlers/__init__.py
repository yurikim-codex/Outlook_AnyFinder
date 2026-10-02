"""
사이드카 명령 핸들러 패키지.

각 모듈은 register(dispatcher) 함수를 exposing 하며,
register_all()이 전체 명령 라우팅 테이블을 구성한다.

명령 전체 목록/계약: sidecar/README.md
"""

from . import (
    autocomplete,
    bookmark,
    db,
    font,
    index,
    mail,
    outlook,
    preview,
    search,
    settings,
    sync,
    system,
)

_MODULES = [
    system, db, search, autocomplete, sync, index,
    bookmark, settings, preview, mail, outlook, font,
]


def register_all(dispatcher):
    for module in _MODULES:
        dispatcher.register_module(module)
    return dispatcher

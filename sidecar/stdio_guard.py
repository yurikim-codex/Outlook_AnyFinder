"""
stdio 가드 — ① UTF-8 강제 ② stdout 오염 차단

① UTF-8 강제 (계획 §8 Phase 1 Windows 치명 버그 #1 대응)
   Python은 파이프 표준 스트림을 locale.getpreferredencoding()으로 처리한다.
   한국어 Windows = cp949 → Rust가 보낸 UTF-8 JSON을 stdin에서 읽다
   UnicodeDecodeError로 사이드카가 즉사한다.
   PYTHONIOENCODING/PYTHONUTF8 환경변수에 의존하지 않고 스스로 강제해야 한다.

② stdout 오염 차단 (계획 §5 리스크 2 대응)
   stdout(fd 1)은 JSON Lines 프로토콜 전용 채널이다.
   - fd 1을 dup하여 진짜 프로토콜 채널을 보존
   - fd 1 자체를 devnull로 교체 (네이티브/C 레벨 출력까지 차단)
   - sys.stdout → sys.stderr로 돌려 Python print는 로그로 보냄
"""

import io
import os
import sys


def force_utf8_io() -> dict:
    """stdin/stdout/stderr를 UTF-8으로 강제 재설정한다.

    Returns:
        {"stdin": "reconfigured|already-utf8|wrapped|missing|skipped", ...}
    """
    report = {}
    specs = {
        "stdin": "replace",           # 입력은 어떤 바이트가 와도 죽으면 안 된다
        "stdout": "backslashreplace",
        "stderr": "backslashreplace",
    }
    for name, errors in specs.items():
        stream = getattr(sys, name, None)
        if stream is None:
            # PyInstaller windowed 모드 등에서 스트림이 None일 수 있음
            report[name] = "missing"
            continue
        encoding = (getattr(stream, "encoding", "") or "").lower().replace("-", "")
        if encoding == "utf8":
            report[name] = "already-utf8"
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors=errors)
            report[name] = "reconfigured"
        except Exception:
            # reconfigure 불가 스트림은 buffer 위에 TextIOWrapper를 다시 감는다
            buffer = getattr(stream, "buffer", None)
            if buffer is not None:
                try:
                    wrapped = io.TextIOWrapper(
                        buffer, encoding="utf-8", errors=errors,
                        line_buffering=(name != "stdin"),
                    )
                    setattr(sys, name, wrapped)
                    report[name] = "wrapped"
                    continue
                except Exception as exc:
                    report[name] = f"failed:{exc}"
            else:
                report[name] = "skipped"
    return report


def protect_stdout(enabled: bool = True):
    """프로토콜 전용 채널(텍스트 스트림)을 반환하고 stdout을 봉인한다.

    enabled=True  : fd 레벨 분리. 어떤 print/네이티브 출력도 프로토콜을 오염시킬 수 없음.
    enabled=False : 디버그 모드. sys.stdout을 그대로 사용 (오염 허용, 서버는 생존해야 함).
    """
    if not enabled:
        return sys.stdout

    try:
        sys.stdout.flush()
    except Exception:
        pass

    proto = None
    try:
        # 1) 진짜 stdout 파이프를 새 fd로 보존
        proto_fd = os.dup(1)
        # 2) fd 1을 devnull로 교체 — 네이티브 레벨 출력 차단
        devnull_fd = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull_fd, 1)
        os.close(devnull_fd)
        # 3) 보존한 fd 위에 UTF-8 라인 버퍼링 텍스트 스트림 생성 (프로토콜 전용)
        proto = os.fdopen(
            proto_fd, "w", encoding="utf-8", errors="backslashreplace",
            newline="\n", buffering=1, closefd=True,
        )
    except Exception:
        # fd 수술이 불가능한 환경(일부 캡처 환경)에서는 객체-level 분리로 degraded
        proto = sys.stdout

    # 4) Python 레벨 print는 로그(stderr)로 보낸다
    sys.stdout = sys.stderr
    return proto

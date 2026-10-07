r"""사이드카 급사 재현 프로브 — Tauri 셸의 spawn 조건을 정확히 모사 (Track B 실측 9호).

배경: 동결 사이드카는 콘솔 단독 실행(R8)과 dev_client(R1~R6)에서 실 Outlook
동기화까지 완전히 정상. 급사는 설치본(Tauri 셸이 spawn)에서만 발생.
셸과 외부 실행의 차이는 다음뿐이다:
  1. creation flags : CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP
  2. 콘솔 부재 + stdout/stderr 파이프 (stdio_guard fd 수술 대상)
  3. env: PYTHONUTF8=1, PYTHONIOENCODING=utf-8 (셸이 명시 주입)
  4. 셸이 15초마다 system.ping (헬스체크)
이 프로브는 1~4를 전부 재현하고, 급사 시점·exit code·마지막 stderr를 보고한다.

실행 (저장소 루트에서):
    python tools\probe_spawn_flags.py                    # 기본: 리포 사이드카 exe, 300초 관찰
    python tools\probe_spawn_flags.py --seconds 600      # 관찰 시간 변경
    python tools\probe_spawn_flags.py --exe "C:\...\OutlookAnyFinderSidecar.exe"
    python tools\probe_spawn_flags.py --sync             # 관찰 중 sync.run 1회 주입(실 Outlook)
"""
from __future__ import annotations

import argparse
import json
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_EXE = ROOT / "src-tauri" / "resources" / "sidecar" / "OutlookAnyFinderSidecar.exe"

CREATE_NO_WINDOW = 0x08000000
CREATE_NEW_PROCESS_GROUP = 0x00000200  # 셸(sidecar.rs apply_platform_flags)과 동일


def stamp() -> str:
    return time.strftime("%H:%M:%S")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=str(DEFAULT_EXE))
    ap.add_argument("--seconds", type=int, default=300)
    ap.add_argument("--sync", action="store_true", help="관찰 중 sync.run(folder 6, full) 1회 주입")
    args = ap.parse_args()

    exe = Path(args.exe)
    if not exe.exists():
        print(f"exe 없음: {exe}")
        return 2

    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"            # 셸이 주입하는 값 그대로
    env["PYTHONIOENCODING"] = "utf-8"

    print(f"[{stamp()}] spawn: {exe}")
    print(f"[{stamp()}] flags: CREATE_NO_WINDOW|CREATE_NEW_PROCESS_GROUP, env: PYTHONUTF8=1,PYTHONIOENCODING=utf-8")
    t0 = time.time()
    proc = subprocess.Popen(
        [str(exe)],
        cwd=str(ROOT),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        creationflags=CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP,
    )

    lines: queue.Queue = queue.Queue()

    def reader(stream, tag):
        try:
            for raw in stream:
                lines.put((tag, raw.decode("utf-8", errors="replace").rstrip()))
        except Exception:
            pass
        lines.put((tag, None))  # EOF

    threading.Thread(target=reader, args=(proc.stdout, "out"), daemon=True).start()
    threading.Thread(target=reader, args=(proc.stderr, "err"), daemon=True).start()

    # 셸 헬스 루프 모사: 15초마다 system.ping
    ping_id = [0]

    def send(cmd: str, params: dict | None = None):
        ping_id[0] += 1
        req = {"id": ping_id[0], "cmd": cmd, "params": params or {}}
        try:
            proc.stdin.write((json.dumps(req, ensure_ascii=False) + "\n").encode("utf-8"))
            proc.stdin.flush()
            print(f"[{stamp()}] → {cmd} (id={ping_id[0]})")
        except Exception as e:
            print(f"[{stamp()}] → {cmd} 쓰기 실패: {e}")

    next_ping = t0 + 15.0
    sync_sent = not args.sync  # --sync 없으면 보낸 것 취급(스킵)
    eof_seen = False
    exit_code = None

    while True:
        elapsed = time.time() - t0
        # 큐 drained
        drained = False
        while True:
            try:
                tag, text = lines.get_nowait()
            except queue.Empty:
                break
            drained = True
            if text is None:
                if tag == "out" and not eof_seen:
                    eof_seen = True
                    print(f"[{stamp()}] ★ stdout EOF 감지 (+{elapsed:.0f}s) — 프로세스 종료 여부 확인 중...")
                    code = proc.poll()
                    print(f"[{stamp()}]   poll() = {code} (None이면 stdout만 닫히고 생존)")
            else:
                print(f"[{stamp()}] [{tag}] {text}")
        if eof_seen and not drained:
            code = proc.poll()
            if code is not None:
                exit_code = code
                break

        if elapsed >= args.seconds:
            print(f"[{stamp()}] 관찰 시간 {args.seconds}s 도달 — 프로세스는 생존 상태")
            break

        if not sync_sent and elapsed >= 30:
            send("sync.run", {"folder_ids": [6], "incremental": False})
            sync_sent = True

        if time.time() >= next_ping:
            if proc.poll() is not None:
                exit_code = proc.poll()
                break
            send("system.ping")
            next_ping += 15.0

        code = proc.poll()
        if code is not None:
            exit_code = code
            print(f"[{stamp()}] ★ 프로세스 종료 감지 (+{elapsed:.0f}s)")
            break
        time.sleep(0.2)

    # 남은 로그 drain
    time.sleep(0.5)
    while True:
        try:
            tag, text = lines.get_nowait()
        except queue.Empty:
            break
        if text is not None:
            print(f"[{stamp()}] [{tag}] {text}")

    if exit_code is None:
        exit_code = proc.poll()
    print(f"[{stamp()}] === 결과: exit code = {exit_code}"
          + (f" (0x{exit_code & 0xFFFFFFFF:08x})" if isinstance(exit_code, int) else "")
          + f", 생존 {time.time() - t0:.0f}s ===")
    try:
        proc.kill()
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())

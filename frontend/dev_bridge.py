"""브라우저 개발 모드 IPC 브리지 — Python 표준 라이브러리만 사용.

Tauri 없이 브라우저에서만 UI를 개발할 때, Vite 프록시(/sidecar/*)를 통해
실제 사이드카 프로세스와 JSON Lines 프로토콜로 연결한다.

엔드포인트:
  POST /invoke   {"cmd": ..., "params": {...}} → 사이드카 응답 엔벨로프 그대로 반환
  GET  /events   SSE — 사이드카 이벤트(ready/sync.progress/index.progress/...) 스트림
  GET  /status   {"ready":..., "running":..., "restarts":...}
  POST /restart  사이드카 재시작
  GET  /health   {"alive": true}

사용법:
  python frontend/dev_bridge.py          (Mock 모드 기본)
  ANYFINDER_BRIDGE_MOCK=0 python ...     (실제 Outlook 연결 시도 — Windows에서만)

포트: 127.0.0.1:8765 (vite.config.ts 프록시와 쌍)
"""
from __future__ import annotations

import json
import os
import queue
import signal
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOST, PORT = "127.0.0.1", 8765
REQUEST_TIMEOUT = 300.0


class Bridge:
    """사이드카 자식 프로세스 + id 매칭 + 이벤트 팬아웃."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.child: subprocess.Popen | None = None
        self.next_id = 1
        self.waiters: dict[int, threading.Event] = {}
        self.results: dict[int, dict] = {}
        self.subscribers: list[queue.Queue] = []
        self.ready = False
        self.restarts = 0
        self.exited = False

    # ── 프로세스 ──

    def use_mock(self) -> bool:
        return os.environ.get("ANYFINDER_BRIDGE_MOCK", "1") != "0"

    def spawn(self) -> None:
        args = [sys.executable, "-m", "sidecar"]
        if self.use_mock():
            args.append("--mock")
        env = dict(os.environ)
        env["PYTHONUTF8"] = "1"
        env.pop("PYTHONIOENCODING", None)
        kwargs: dict = {}
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
        else:
            kwargs["start_new_session"] = True
        self.child = subprocess.Popen(
            args,
            cwd=str(REPO_ROOT),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            **kwargs,
        )
        self.exited = False
        threading.Thread(target=self._reader, daemon=True).start()
        threading.Thread(target=self._stderr, daemon=True).start()
        print(f"[bridge] sidecar spawned pid={self.child.pid} args={args}", flush=True)

    def _stderr(self) -> None:
        assert self.child and self.child.stderr
        for line in self.child.stderr:
            text = line.decode("utf-8", "replace").rstrip()
            if text:
                print(f"[sidecar] {text}", flush=True)

    def _reader(self) -> None:
        assert self.child and self.child.stdout
        for raw in self.child.stdout:
            line = raw.decode("utf-8", "replace").strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except ValueError:
                print(f"[bridge] non-JSON line ignored: {line[:120]}", flush=True)
                continue
            if not isinstance(msg, dict):
                continue
            if "event" in msg and "ok" not in msg:
                if msg.get("event") == "ready":
                    self.ready = True
                self._broadcast(msg)
                continue
            msg_id = msg.get("id")
            if isinstance(msg_id, int) and "ok" in msg:
                with self.lock:
                    ev = self.waiters.pop(msg_id, None)
                if ev is not None:
                    self.results[msg_id] = msg
                    ev.set()
        # EOF
        self.ready = False
        self.exited = True
        self._broadcast({"event": "bridge.sidecar_exited", "data": {}})
        print("[bridge] sidecar stdout EOF", flush=True)

    def _broadcast(self, msg: dict) -> None:
        with self.lock:
            subs = list(self.subscribers)
        for q in subs:
            try:
                q.put_nowait(msg)
            except queue.Full:
                pass

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=512)
        with self.lock:
            self.subscribers.append(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self.lock:
            if q in self.subscribers:
                self.subscribers.remove(q)

    # ── 요청 ──

    def invoke(self, cmd: str, params: dict) -> dict:
        with self.lock:
            child_alive = self.child is not None and self.child.poll() is None
            if not child_alive:
                return {
                    "id": None,
                    "ok": False,
                    "error": {
                        "code": "SIDECAR_NOT_RUNNING",
                        "message": "사이드카가 실행 중이 아닙니다 (브리지 재시작 필요)",
                        "retryable": True,
                    },
                }
            req_id = self.next_id
            self.next_id += 1
            ev = threading.Event()
            self.waiters[req_id] = ev
        line = json.dumps({"id": req_id, "cmd": cmd, "params": params}, ensure_ascii=False)
        try:
            assert self.child and self.child.stdin
            self.child.stdin.write((line + "\n").encode("utf-8"))
            self.child.stdin.flush()
        except (BrokenPipeError, OSError) as e:
            with self.lock:
                self.waiters.pop(req_id, None)
            return {
                "id": req_id,
                "ok": False,
                "error": {"code": "SIDECAR_IO", "message": f"stdin 쓰기 실패: {e}", "retryable": True},
            }
        if not ev.wait(REQUEST_TIMEOUT):
            with self.lock:
                self.waiters.pop(req_id, None)
            return {
                "id": req_id,
                "ok": False,
                "error": {"code": "SIDECAR_TIMEOUT", "message": f"응답 시간 초과 ({REQUEST_TIMEOUT}s)"},
            }
        return self.results.pop(req_id, {"id": req_id, "ok": False, "error": {"code": "INTERNAL", "message": "응답 유실"}})

    def restart(self) -> None:
        self.kill()
        self.restarts += 1
        self.spawn()

    def kill(self) -> None:
        child = self.child
        self.child = None
        if child is None:
            return
        try:
            if child.poll() is None:
                if os.name == "nt":
                    child.send_signal(signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
                    try:
                        child.wait(2)
                    except subprocess.TimeoutExpired:
                        child.kill()
                else:
                    child.terminate()
                    try:
                        child.wait(2)
                    except subprocess.TimeoutExpired:
                        child.kill()
        except Exception as e:  # noqa: BLE001
            print(f"[bridge] kill warning: {e}", flush=True)

    def status(self) -> dict:
        running = self.child is not None and self.child.poll() is None
        return {
            "ready": self.ready,
            "running": running,
            "restarts": self.restarts,
            "state": "bridge",
        }


BRIDGE = Bridge()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "AnyFinderDevBridge/1.0"

    def log_message(self, fmt, *args):  # noqa: A003
        pass  # 조용히 — 사이드카 stderr만 표시

    def _send(self, code: int, body: bytes, content_type: str = "application/json; charset=utf-8") -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._send(200, json.dumps({"alive": True}).encode())
        elif self.path == "/status":
            self._send(200, json.dumps(BRIDGE.status()).encode())
        elif self.path == "/events":
            self._sse()
        else:
            self._send(404, json.dumps({"error": "not found"}).encode())

    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/invoke":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            try:
                payload = json.loads(raw.decode("utf-8"))
                cmd = str(payload.get("cmd", ""))
                params = payload.get("params") or {}
            except ValueError:
                self._send(400, json.dumps({"id": None, "ok": False, "error": {"code": "PARSE_ERROR", "message": "브리지 요청 JSON 파싱 실패"}}).encode())
                return
            result = BRIDGE.invoke(cmd, params if isinstance(params, dict) else {})
            self._send(200, json.dumps(result, ensure_ascii=False).encode())
        elif self.path == "/restart":
            BRIDGE.restart()
            self._send(200, json.dumps({"ok": True}).encode())
        else:
            self._send(404, json.dumps({"error": "not found"}).encode())

    def _sse(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        q = BRIDGE.subscribe()
        try:
            # 연결 확인용 첫 메시지
            self.wfile.write(b"data: {\"event\":\"bridge.connected\",\"data\":{}}\n\n")
            self.wfile.flush()
            while True:
                try:
                    msg = q.get(timeout=20)
                except queue.Empty:
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
                    continue
                data = json.dumps(msg, ensure_ascii=False)
                self.wfile.write(f"data: {data}\n\n".encode("utf-8"))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            BRIDGE.unsubscribe(q)


def main() -> None:
    BRIDGE.spawn()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    server.daemon_threads = True
    print(f"[bridge] listening on http://{HOST}:{PORT} (mock={BRIDGE.use_mock()})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        BRIDGE.kill()
        server.server_close()
        print("[bridge] shutdown", flush=True)


if __name__ == "__main__":
    main()

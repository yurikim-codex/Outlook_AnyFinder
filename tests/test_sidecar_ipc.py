"""
OutLook AnyFinder — Sidecar IPC 프로토콜 단위/통합 회귀 테스트 (MIGRATION_PLAN Phase 1)

범주:
  1) 단위   : stdio_guard / serialize / protocol / dispatcher / jobs / dev_client 인수 파싱
  2) 통합   : 실제 subprocess spawn (`python -m sidecar --mock`) + JSON Lines 왕복
  3) 회귀   : 계획서 Phase 1에서 고정한 Windows/cp949/오염/좀비 버그 재발 방지
              (test_07, test_08, test_14 ~ test_18 이름은 계획서와 대응)

★ 통합 테스트는 PYTHONIOENCODING/PYTHONUTF8를 일부러 제거한 환경에서 실행한다.
  사이드카가 스스로 UTF-8을 강제하는지 진짜로 검증하기 위함이다.
"""

import dataclasses
import io
import json
import os
import queue
import shutil
import signal
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

REPO_ROOT = Path(__file__).resolve().parent.parent
MOCK_TOTAL = 15          # Mock 메일 총 건수 (받은 10 + 보낸 5)
MOCK_INBOX = 10
MOCK_SENT = 5


# ═══════════════════════════════════════════════════════════════
# 통합 테스트용 사이드카 프로세스 헬퍼
# ═══════════════════════════════════════════════════════════════

class SidecarProcess:
    """`python -m sidecar --mock` 자식 프로세스 + JSON Lines 클라이언트.

    - stdout/stderr는 바이너리로 받아 직접 UTF-8 디코딩한다
      (계획 Phase 1 Windows 버그 #2/#3 — subprocess 텍스트 모드 디코딩 실패 방지)
    - stderr는 drain 스레드가 계속 비운다 (파이프 버퍼 블로킹 방지 — Windows 교훈 #5)
    """

    def __init__(self, data_dir=None, extra_args=(), env_extra=None, keep_env_io=False,
                 keep_dir=False):
        self.data_dir = Path(data_dir or tempfile.mkdtemp(prefix="anyfinder-sc-test-"))
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.keep_dir = keep_dir  # True면 close() 시 디렉터리를 보존 (재기동 테스트용)
        self.events = []
        self.junk_lines = []
        self.stderr_bytes = []
        self._q = queue.Queue()
        self._id = 0
        self._closed = False

        env = dict(os.environ)
        if not keep_env_io:
            # ★ 회귀 테스트 원칙: 인코딩 환경변수를 제거해 자가 강제 UTF-8을 검증한다
            env.pop("PYTHONIOENCODING", None)
            env.pop("PYTHONUTF8", None)
        if env_extra:
            env.update(env_extra)

        args = [sys.executable, "-m", "sidecar", "--mock",
                "--data-dir", str(self.data_dir), *extra_args]
        popen_kwargs = {}
        if sys.platform == "win32":
            # 프로덕션 Rust(src-tauri/sidecar.rs)와 동일한 생성 플래그.
            # CREATE_NEW_PROCESS_GROUP이 없으면 test_08의 CTRL_BREAK_EVENT가
            # pytest/PowerShell이 속한 프로세스 그룹 전체로 브로드캐스트되어
            # 테스트 러너 자체가 중단된다 (Windows 실측 결함, Track B).
            # CREATE_NO_WINDOW는 pytest 중 콘솔 창 깜빡임 방지.
            popen_kwargs["creationflags"] = (
                subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
            )
        self.proc = subprocess.Popen(
            args, cwd=str(REPO_ROOT),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=env, **popen_kwargs,
        )
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()

    def _read_stdout(self):
        try:
            for line in self.proc.stdout:
                self._q.put(line)
        except Exception:
            pass
        self._q.put(None)

    def _read_stderr(self):
        try:
            for line in self.proc.stderr:
                self.stderr_bytes.append(line)
        except Exception:
            pass

    # ── 전송/수신 ──

    def send_raw(self, data: bytes):
        self.proc.stdin.write(data)
        self.proc.stdin.flush()

    def send(self, obj: dict):
        self.send_raw(json.dumps(obj, ensure_ascii=False).encode("utf-8") + b"\n")

    def _next_message(self, timeout):
        raw = self._q.get(timeout=timeout)
        if raw is None:
            raise EOFError("사이드카 stdout 종료")
        text = raw.decode("utf-8", errors="replace").strip()
        if not text:
            return None
        try:
            msg = json.loads(text)
        except Exception:
            self.junk_lines.append(text)
            return None
        if isinstance(msg, dict) and "event" in msg and "ok" not in msg:
            self.events.append(msg)
        return msg

    def request(self, cmd, params=None, timeout=20):
        self._id += 1
        req_id = self._id
        self.send({"id": req_id, "cmd": cmd, "params": params or {}})
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                msg = self._next_message(timeout=max(0.2, deadline - time.time()))
            except queue.Empty:
                break
            if msg is None:
                continue
            if msg.get("id") == req_id and "ok" in msg:
                return msg
        raise TimeoutError(f"{cmd} 응답 시간 초과 ({timeout}s)")

    def wait_event(self, name, timeout=20):
        deadline = time.time() + timeout
        while time.time() < deadline:
            for ev in list(self.events):
                if ev.get("event") == name:
                    return ev
            try:
                self._next_message(timeout=max(0.2, deadline - time.time()))
            except (queue.Empty, EOFError):
                break
        return None

    def wait_ready(self, timeout=20):
        ev = self.wait_event("ready", timeout=timeout)
        assert ev is not None, "ready 이벤트를 받지 못함"
        return ev

    def stderr_text(self) -> str:
        return b"".join(self.stderr_bytes).decode("utf-8", errors="replace")

    def exit_code(self, timeout=10):
        return self.proc.wait(timeout=timeout)

    def alive(self) -> bool:
        return self.proc.poll() is None

    def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            if self.alive():
                self.proc.kill()
                self.proc.wait(timeout=5)
        except Exception:
            pass
        if not self.keep_dir:
            shutil.rmtree(self.data_dir, ignore_errors=True)


@pytest.fixture
def sc():
    """신선한 데이터 디렉터리의 function-scoped 사이드카."""
    proc = SidecarProcess()
    proc.wait_ready()
    yield proc
    proc.close()


@pytest.fixture(scope="module")
def indexed():
    """Mock 메일 15건이 인덱싱된 module-scoped 사이드카 (검색 계열 공유).

    ★ range_months(기간 필터)를 쓰지 않는다 — Mock 샘플 날짜는 2026-05-27 기준
      고정값이라 기간 필터를 사용하면 시간이 지난 뒤 테스트가 깨진다(타임밤).
    """
    proc = SidecarProcess()
    proc.wait_ready()
    r = proc.request("index.build", {"folder_ids": [6, 5]}, timeout=60)
    assert r["ok"], f"index.build 실패: {r.get('error')}"
    assert r["result"]["added"] == MOCK_TOTAL
    yield proc
    proc.close()


# ═══════════════════════════════════════════════════════════════
# 1) 단위 테스트
# ═══════════════════════════════════════════════════════════════

class TestStdioGuard:
    """sidecar/stdio_guard.py 단위 테스트."""

    def test_18_stdio_guard_unit(self, monkeypatch):
        """force_utf8_io()가 cp949 스트림을 utf-8로 실제 전환한다 (계획 회귀 test_18)."""
        from sidecar.stdio_guard import force_utf8_io

        saved = (sys.stdin, sys.stdout, sys.stderr)
        try:
            fake = {}
            for name in ("stdin", "stdout", "stderr"):
                buf = io.BytesIO()
                wrapper = io.TextIOWrapper(buf, encoding="cp949", errors="strict")
                fake[name] = wrapper
                monkeypatch.setattr(sys, name, wrapper)

            report = force_utf8_io()

            for name in ("stdin", "stdout", "stderr"):
                assert fake[name].encoding.lower().replace("-", "") == "utf8", \
                    f"{name} 인코딩이 utf-8로 전환되지 않음: {fake[name].encoding}"
                assert report[name] == "reconfigured"
        finally:
            sys.stdin, sys.stdout, sys.stderr = saved

    def test_missing_streams_reported(self, monkeypatch):
        """스트림이 None(--noconsole류)이어도 예외 없이 report만 남긴다."""
        from sidecar.stdio_guard import force_utf8_io
        saved = (sys.stdin, sys.stdout, sys.stderr)
        try:
            monkeypatch.setattr(sys, "stdin", None)
            monkeypatch.setattr(sys, "stdout", None)
            monkeypatch.setattr(sys, "stderr", None)
            report = force_utf8_io()
            assert report == {"stdin": "missing", "stdout": "missing", "stderr": "missing"}
        finally:
            sys.stdin, sys.stdout, sys.stderr = saved

    def test_protect_stdout_disabled_returns_sys_stdout(self):
        from sidecar.stdio_guard import protect_stdout
        assert protect_stdout(enabled=False) is sys.stdout


class TestSerialize:
    """sidecar/serialize.py — 예외 불가침 직렬화."""

    def test_primitives(self):
        from sidecar.serialize import to_jsonable
        assert to_jsonable(None) is None
        assert to_jsonable(True) is True
        assert to_jsonable(42) == 42
        assert to_jsonable("한글") == "한글"

    def test_nan_inf_to_none(self):
        from sidecar.serialize import to_jsonable
        assert to_jsonable(float("nan")) is None
        assert to_jsonable(float("inf")) is None

    def test_datetime(self):
        from datetime import datetime
        from sidecar.serialize import to_jsonable
        dt = datetime(2026, 10, 2, 9, 30, 0)
        assert to_jsonable(dt).startswith("2026-10-02T09:30:00")

    def test_sqlite_row(self):
        from sidecar.serialize import to_jsonable
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT 1 as a, '한글' as b").fetchone()
        out = to_jsonable(row)
        assert out == {"a": 1, "b": "한글"}
        conn.close()

    def test_dataclass(self):
        from sidecar.serialize import to_jsonable

        @dataclasses.dataclass
        class Sample:
            x: int = 1
            y: str = "한글"

        assert to_jsonable(Sample()) == {"x": 1, "y": "한글"}

    def test_dict_snapshot_no_mutation_error(self):
        """순회 중 dict가 변경되어도 스냅샷으로 방어 (계획 잠재 버그 #2)."""
        from sidecar.serialize import to_jsonable

        class BadDict(dict):
            def items(self):
                # 실제 순회 중 크기 변경을 시뮬레이션
                yield "a", 1
                self["injected"] = True
                yield "b", 2

        out = to_jsonable(BadDict(a=0, b=2))
        assert isinstance(out, dict)

    def test_set_bytes_path_fallback(self):
        from sidecar.serialize import to_jsonable
        assert sorted(to_jsonable({"b", "a"})) == ["a", "b"]
        assert to_jsonable("한글".encode("utf-8")) == "한글"
        assert to_jsonable(Path("x") / "y") == str(Path("x") / "y")
        assert to_jsonable(object) .startswith("<class")  # 폴백 str

    def test_depth_guard(self):
        from sidecar.serialize import to_jsonable
        deep = current = {}
        for _ in range(30):
            current["n"] = {}
            current = current["n"]
        out = to_jsonable(deep)  # 예외 없이 str 폴백으로 수렴
        assert isinstance(out, dict)


class TestProtocol:
    """sidecar/protocol.py — 메시지 형태 고정."""

    def test_ok_response_shape(self):
        from sidecar.protocol import ok_response
        assert ok_response(7, {"a": 1}) == {"id": 7, "ok": True, "result": {"a": 1}}

    def test_error_response_shape(self):
        from sidecar.protocol import error_response
        msg = error_response(7, "JOB_NOT_RUNNING", "없음", retryable=False, details={"k": 1})
        assert msg["ok"] is False
        assert msg["error"] == {"code": "JOB_NOT_RUNNING", "message": "없음",
                                "retryable": False, "details": {"k": 1}}

    def test_event_shape_no_id(self):
        from sidecar.protocol import event_message
        msg = event_message("sync.progress", {"done": 1})
        assert "id" not in msg and msg["event"] == "sync.progress" and msg["data"] == {"done": 1}

    def test_sidecar_error_default_retryable(self):
        from sidecar.protocol import ErrorCode, SidecarError
        assert SidecarError(ErrorCode.OUTLOOK_CONNECT_FAILED, "x").retryable is True
        assert SidecarError(ErrorCode.UNKNOWN_COMMAND, "x").retryable is False

    def test_classify_outlook_connection_error(self):
        # core.outlook_connector는 Windows가 아니어도 import 가능
        from core.outlook_connector import OutlookConnectionError
        from sidecar.protocol import ErrorCode, classify_exception
        err = classify_exception(OutlookConnectionError("연결 실패"))
        assert err.code == ErrorCode.OUTLOOK_CONNECT_FAILED
        assert err.retryable is True

    def test_classify_generic_exception(self):
        from sidecar.protocol import ErrorCode, classify_exception
        err = classify_exception(ValueError("boom"))
        assert err.code == ErrorCode.INTERNAL
        assert "boom" in err.message


class TestDispatcher:
    def test_register_and_dispatch(self):
        from sidecar.dispatcher import Dispatcher
        d = Dispatcher()
        d.register("x.y", lambda state, params, ctx: {"echo": params.get("v")})
        out = d.dispatch("x.y", {"v": 1}, {"state": None})
        assert out == {"echo": 1}

    def test_unknown_command(self):
        from sidecar.dispatcher import Dispatcher
        from sidecar.protocol import ErrorCode, SidecarError
        d = Dispatcher()
        with pytest.raises(SidecarError) as ei:
            d.dispatch("no.such", {}, {"state": None})
        assert ei.value.code == ErrorCode.UNKNOWN_COMMAND

    def test_commands_sorted(self):
        from sidecar.dispatcher import Dispatcher
        d = Dispatcher()
        d.register("b.cmd", lambda *a: None)
        d.register("a.cmd", lambda *a: None)
        assert d.commands() == ["a.cmd", "b.cmd"]
        assert len(d) == 2


class TestJobRegistry:
    def test_begin_finish_cancel(self):
        from sidecar.jobs import JobRegistry
        reg = JobRegistry()
        job = reg.begin("sync.plan", req_id=1)
        assert reg.current() is job
        assert job.should_stop() is False
        reg.cancel()
        assert job.should_stop() is True
        reg.finish(job)
        assert reg.current() is None

    def test_already_running(self):
        from sidecar.jobs import JobRegistry
        from sidecar.protocol import ErrorCode, SidecarError
        reg = JobRegistry()
        reg.begin("sync.plan")
        with pytest.raises(SidecarError) as ei:
            reg.begin("index.build")
        assert ei.value.code == ErrorCode.JOB_ALREADY_RUNNING
        assert ei.value.retryable is True

    def test_cancel_idle_raises(self):
        from sidecar.jobs import JobRegistry
        from sidecar.protocol import ErrorCode, SidecarError
        reg = JobRegistry()
        with pytest.raises(SidecarError) as ei:
            reg.cancel()
        assert ei.value.code == ErrorCode.JOB_NOT_RUNNING


class TestDevClientArgs:
    """dev_client 인수 파싱 — PowerShell 4가지 입력 형식 고정 (계획 Phase 1)."""

    def parse(self, *tokens):
        from sidecar.dev_client import parse_command_args
        return parse_command_args(list(tokens))

    def test_no_args(self):
        cmd, params, err = self.parse()
        assert cmd is None and err

    def test_command_only(self):
        assert self.parse("system.hello") == ("system.hello", None, None)

    def test_key_value_korean(self):
        cmd, params, err = self.parse("search.record", "keyword=계약서")
        assert (cmd, err) == ("search.record", None)
        assert params == {"keyword": "계약서"}

    def test_key_value_coercion(self):
        _, params, _ = self.parse("c", "a=1", "b=2.5", "c=true", "d=null", "e=한글")
        assert params == {"a": 1, "b": 2.5, "c": True, "d": None, "e": "한글"}

    def test_key_value_multiple_and_equals_in_value(self):
        _, params, err = self.parse("c", "q=a=b")
        assert err is None and params == {"q": "a=b"}

    def test_key_value_missing_equals(self):
        _, _, err = self.parse("c", "oops")
        assert err and "key=value" in err

    def test_json_token(self):
        cmd, params, err = self.parse("search.query", '{"query":"보고서","per_page":5}')
        assert (cmd, err) == ("search.query", None)
        assert params == {"query": "보고서", "per_page": 5}

    def test_json_token_split_across_argv(self):
        # PowerShell이 공백 포함 JSON을 여러 argv로 쪼개는 경우
        cmd, params, err = self.parse("search.query", '{"query":', '"보고서"}')
        assert err is None and params == {"query": "보고서"}

    def test_single_token_form(self):
        cmd, params, err = self.parse('search.query {"query":"보고서"}')
        assert (cmd, err) == ("search.query", None)
        assert params == {"query": "보고서"}

    def test_json_only_no_command(self):
        _, _, err = self.parse('{"a":1}')
        assert err and "명령명" in err

    def test_invalid_json(self):
        _, _, err = self.parse("c", "{not json")
        assert err and "JSON" in err

    def test_json_non_object(self):
        _, _, err = self.parse("c", "[1,2]")
        assert err and "객체" in err

    def test_coerce_value(self):
        from sidecar.dev_client import coerce_value
        assert coerce_value("5") == 5
        assert coerce_value("true") is True
        assert coerce_value("계약서") == "계약서"
        assert coerce_value("kim@company.com") == "kim@company.com"


# ═══════════════════════════════════════════════════════════════
# 2) 통합 테스트 — 실제 프로세스 spawn
# ═══════════════════════════════════════════════════════════════

class TestSidecarLifecycle:

    def test_01_ready_event(self, sc):
        ev = next(e for e in sc.events if e["event"] == "ready")
        data = ev["data"]
        assert data["use_mock"] is True
        assert data["db_ok"] is True
        assert data["commands_count"] >= 30
        assert data["pid"] == sc.proc.pid

    def test_02_hello_without_env_vars(self, sc):
        """test_17 대응: PYTHONIOENCODING/PYTHONUTF8 없이도 UTF-8 자가 강제."""
        r = sc.request("system.hello")
        assert r["ok"] is True
        res = r["result"]
        assert res["db_ok"] is True
        assert res["outlook_ok"] is True  # mock
        for stream in ("stdin", "stdout", "stderr"):
            assert res["utf8_io"][stream] in ("reconfigured", "already-utf8", "wrapped"), \
                f"{stream} UTF-8 강제 실패: {res['utf8_io']}"

    def test_03_ping_and_commands(self, sc):
        r = sc.request("system.ping")
        assert r["result"]["pong"] is True
        r = sc.request("system.commands")
        cmds = r["result"]["commands"]
        assert r["result"]["count"] == len(cmds) >= 30
        # 계약서(§6.2) 핵심 명령이 모두 등록되어 있어야 한다
        for required in ("system.hello", "system.shutdown", "db.stats", "db.reset",
                         "db.clear_history", "db.reset_all", "system.info",
                         "search.query", "search.folders", "search.related",
                         "autocomplete.suggest", "sync.plan", "sync.execute", "sync.cancel",
                         "bookmark.list", "bookmark.add", "bookmark.remove",
                         "preview.html", "mail.open", "mail.export",
                         "settings.get", "settings.set", "outlook.check", "font.list"):
            assert required in cmds, f"계약 명령 누락: {required}"

    def test_04_unknown_command_error_shape(self, sc):
        r = sc.request("no.such_command")
        assert r["ok"] is False
        err = r["error"]
        assert err["code"] == "UNKNOWN_COMMAND"
        assert err["retryable"] is False
        assert "no.such_command" in err["message"]

    def test_05_invalid_params_not_dict(self, sc):
        sc._id += 1
        sc.send({"id": sc._id, "cmd": "system.ping", "params": [1, 2]})
        deadline = time.time() + 10
        got = None
        while time.time() < deadline and got is None:
            try:
                msg = sc._next_message(timeout=2)
            except queue.Empty:
                break
            if msg and msg.get("id") == sc._id:
                got = msg
        assert got and got["ok"] is False
        assert got["error"]["code"] == "INVALID_PARAMS"

    def test_06_malformed_line_defensive_parser(self, sc):
        """비-JSON 줄 → PARSE_ERROR(id=null) + 서버 생존 (계획 §5 리스크 2)."""
        sc.send_raw(b"{ this is not json !!!\n")
        sc.send_raw(b"\xff\xfe binary garbage\n")
        # PARSE_ERROR 응답(id=null) 수신
        found_parse_error = False
        deadline = time.time() + 10
        while time.time() < deadline and not found_parse_error:
            try:
                msg = sc._next_message(timeout=2)
            except queue.Empty:
                break
            if msg and msg.get("ok") is False and msg.get("error", {}).get("code") == "PARSE_ERROR":
                found_parse_error = True
        assert found_parse_error, "PARSE_ERROR 응답을 받지 못함"
        # 서버는 계속 살아 있어야 한다
        r = sc.request("system.ping")
        assert r["ok"] is True

    def test_07_shutdown_while_blocked_on_stdin(self, sc):
        """stdin을 열어둔 채 종료 요청 → 즉시 정상 종료 (좀비 방지, 계획 회귀 test_07)."""
        start = time.time()
        r = sc.request("system.shutdown")
        assert r["ok"] is True
        code = sc.exit_code(timeout=10)
        assert code == 0, f"비정상 종료 코드: {code}"
        assert time.time() - start < 8, "종료가 즉시 이루어지지 않음"
        assert sc.alive() is False

    def test_08_signal_terminates_process(self):
        """시그널 → 정상 정리 후 종료 (플랫폼별 경로 분리, 계획 회귀 test_08)."""
        proc = SidecarProcess()
        try:
            proc.wait_ready()
            if sys.platform == "win32":
                # Windows: SIGTERM은 TerminateProcess라 잡을 수 없다 → CTRL_BREAK_EVENT 사용
                import ctypes
                kernel32 = ctypes.windll.kernel32
                CTRL_BREAK_EVENT = 1
                assert kernel32.GenerateConsoleCtrlEvent(CTRL_BREAK_EVENT, proc.proc.pid) != 0
            else:
                proc.proc.send_signal(signal.SIGTERM)
            code = proc.exit_code(timeout=10)
            assert code == 0, f"시그널 후 비정상 종료 코드: {code}"
        finally:
            proc.close()

    def test_09_stdin_eof_terminates(self, sc):
        """부모 프로세스 사망(stdin EOF) → 사이드카 자진 종료 (좀비 방지)."""
        sc.proc.stdin.close()
        code = sc.exit_code(timeout=10)
        assert code == 0

    def test_10_stdout_pollution_protection(self, sc):
        """print()/fd write 오염 시도에도 stdout은 순수 JSON만 (계획 §5 리스크 2)."""
        r = sc.request("system.debug.print", {"text": "오염테스트 🚨 contamination"})
        assert r["ok"] is True and r["result"]["stdout_protected"] is True
        # 이후 프로토콜이 계속 동작해야 한다
        r2 = sc.request("system.ping")
        assert r2["ok"] is True
        r3 = sc.request("search.query", {"query": ""})
        assert r3["ok"] is True
        # stdout에 비-JSON 줄이 단 한 줄도 없어야 한다
        assert sc.junk_lines == [], f"stdout 오염 발견: {sc.junk_lines[:3]}"


class TestSidecarDbAndSettings:

    def test_11_db_stats_fresh(self, sc):
        r = sc.request("db.stats")
        assert r["ok"]
        res = r["result"]
        assert res["email_count"] == 0
        assert res["schema_version"] in (1, "1")
        assert res["db_path"].endswith("anyfinder.db")

    def test_12_settings_deep_merge_roundtrip(self, sc):
        r = sc.request("settings.get")
        assert r["ok"] and r["result"]["settings"]["ui"]["theme"] == "dark"

        r = sc.request("settings.set", {"patch": {"ui": {"theme": "warm-dark"}}})
        assert r["ok"]
        assert r["result"]["settings"]["ui"]["theme"] == "warm-dark"
        # 깊은 머지: 같은 섹션의 다른 키는 보존
        assert r["result"]["settings"]["ui"]["sidebar_width"] == 230
        # 파일에 실제 저장됨
        on_disk = json.loads((sc.data_dir / "config.json").read_text(encoding="utf-8"))
        assert on_disk["ui"]["theme"] == "warm-dark"

        r = sc.request("settings.get")
        assert r["result"]["settings"]["ui"]["theme"] == "warm-dark"

    def test_13_settings_set_invalid_patch(self, sc):
        r = sc.request("settings.set", {"patch": "not-a-dict"})
        assert r["ok"] is False and r["error"]["code"] == "INVALID_PARAMS"
        r = sc.request("settings.set", {})
        assert r["ok"] is False and r["error"]["code"] == "INVALID_PARAMS"

    def test_14_db_backup_and_integrity(self, sc):
        r = sc.request("db.backup", {"suffix": "test-backup"})
        assert r["ok"], r.get("error")
        backup = Path(r["result"]["path"])
        assert backup.exists() and backup.stat().st_size > 0
        assert backup.name == "anyfinder.db.test-backup"

        r = sc.request("db.integrity")
        assert r["ok"] and r["result"]["ok"] is True

    def test_15_db_reset_purges_mock(self, indexed):
        """index.build(mock) 후 db.reset → Mock 메일 전부 제거."""
        r = indexed.request("db.stats")
        assert r["result"]["mock_count"] == MOCK_TOTAL
        r = indexed.request("db.reset")
        assert r["ok"] and r["result"]["removed"] == MOCK_TOTAL
        r = indexed.request("db.stats")
        assert r["result"]["email_count"] == 0
        # 테스트 격리를 위해 다시 인덱싱 (module-scoped fixture 공유)
        r = indexed.request("index.build", {"folder_ids": [6, 5]}, timeout=60)
        assert r["ok"] and r["result"]["added"] == MOCK_TOTAL

    def test_16_clear_history_keeps_bookmarks(self, sc):
        sc.request("search.record", {"keyword": "히스토리테스트"})
        sc.request("bookmark.add", {"name": "유지북마크", "query": "keep"})
        r = sc.request("db.clear_history")
        assert r["ok"] and r["result"]["cleared_history"] >= 1
        assert sc.request("search.history")["result"]["items"] == []
        # 북마크는 유지된다
        assert sc.request("bookmark.list")["result"]["count"] == 1

    def test_17_reset_all_requires_confirm(self, indexed):
        """db.reset_all은 confirm=true 없으면 거부 — 전체 초기화 후 상태 검증."""
        r = indexed.request("db.reset_all", {})
        assert r["ok"] is False and r["error"]["code"] == "INVALID_PARAMS"

        indexed.request("bookmark.add", {"name": "삭제대상", "query": "x"})
        r = indexed.request("db.reset_all", {"confirm": True})
        assert r["ok"] and r["result"]["ok"] is True and r["result"]["email_count"] == 0

        stats = indexed.request("db.stats")["result"]
        assert stats["email_count"] == 0 and stats["bookmark_count"] == 0
        assert stats["schema_version"] in (1, "1")  # reset 후에도 schema_version 재기록
        # first_run_completed=false가 설정 파일에 기록됨
        cfg = json.loads((indexed.data_dir / "config.json").read_text(encoding="utf-8"))
        assert cfg["first_run_completed"] is False
        # 검색/인덱싱이 다시 정상 동작해야 한다 (module fixture 복구)
        r = indexed.request("index.build", {"folder_ids": [6, 5]}, timeout=60)
        assert r["ok"] and r["result"]["added"] == MOCK_TOTAL


class TestSidecarSearch:
    """indexed fixture 사용 — Mock 15건 인덱싱 완료 상태."""

    def test_20_search_all(self, indexed):
        r = indexed.request("search.query", {"query": ""})
        assert r["ok"]
        res = r["result"]
        assert res["total_count"] == MOCK_TOTAL
        assert len(res["items"]) == MOCK_TOTAL
        assert res["elapsed_ms"] >= 0
        item = res["items"][0]
        assert set(item.keys()) >= {"email", "rank_score", "title_snippet", "body_snippet"}
        assert item["email"]["subject"]

    def test_21_search_korean_keyword(self, indexed):
        r = indexed.request("search.query", {"query": "견적서"})
        assert r["ok"] and r["result"]["total_count"] > 0
        subjects = " | ".join(i["email"]["subject"] for i in r["result"]["items"])
        assert "견적서" in subjects

    def test_22_search_pagination(self, indexed):
        r1 = indexed.request("search.query", {"query": "", "page": 1, "per_page": 5})
        assert r1["result"]["total_pages"] == 3
        assert r1["result"]["has_next"] is True and r1["result"]["has_prev"] is False
        r2 = indexed.request("search.query", {"query": "", "page": 3, "per_page": 5})
        assert r2["result"]["has_next"] is False and len(r2["result"]["items"]) == MOCK_TOTAL - 10

    def test_23_search_folders_or_combination(self, indexed):
        """다중 폴더 필터는 OR 결합 (계획 잠재 버그 #3 고정)."""
        both = indexed.request("search.query", {"query": "", "folders": ["받은편지함", "보낸편지함"], "per_page": 100})
        inbox = indexed.request("search.query", {"query": "", "folders": ["받은편지함"], "per_page": 100})
        sent = indexed.request("search.query", {"query": "", "folders": ["보낸편지함"], "per_page": 100})
        assert inbox["result"]["total_count"] == MOCK_INBOX
        assert sent["result"]["total_count"] == MOCK_SENT
        assert both["result"]["total_count"] == MOCK_INBOX + MOCK_SENT, \
            "다중 폴더가 OR가 아닌 AND로 결합됨 (잠재 버그 #3 재발)"

    def test_24_search_folder_alias(self, indexed):
        """영문 별칭(Inbox)으로도 한글 폴더명(받은편지함)이 검색된다."""
        r = indexed.request("search.query", {"query": "", "folders": ["Inbox"], "per_page": 100})
        assert r["result"]["total_count"] == MOCK_INBOX

    def test_25_search_email_address(self, indexed):
        r = indexed.request("search.query", {"query": "kim.cs@company.com"})
        assert r["ok"] and r["result"]["total_count"] > 0

    def test_26_search_attachment_filter(self, indexed):
        r = indexed.request("search.query", {"query": "", "attachment": "xlsx", "per_page": 100})
        assert r["ok"] and r["result"]["total_count"] > 0
        r2 = indexed.request("search.query", {"query": "", "attachment": "none", "per_page": 100})
        assert r2["ok"] and r2["result"]["total_count"] + r["result"]["total_count"] <= MOCK_TOTAL

    def test_27_search_sort_validation(self, indexed):
        r = indexed.request("search.query", {"query": "", "sort_by": "bogus"})
        assert r["ok"] is False and r["error"]["code"] == "INVALID_PARAMS"

    def test_28_search_folders_counts(self, indexed):
        r = indexed.request("search.folders")
        assert r["ok"]
        assert r["result"]["counts"].get("받은편지함") == MOCK_INBOX
        assert r["result"]["counts"].get("보낸편지함") == MOCK_SENT
        assert r["result"]["total"] == MOCK_TOTAL

    def test_29_history_and_suggest(self, indexed):
        r = indexed.request("search.record", {"keyword": "주간보고"})
        assert r["ok"]
        r = indexed.request("search.history", {"limit": 10})
        assert "주간보고" in [i["keyword"] for i in r["result"]["items"]]
        r = indexed.request("autocomplete.suggest", {"prefix": "주간"})
        assert "주간보고" in [s["keyword"] for s in r["result"]["suggestions"]]
        r = indexed.request("search.record", {"keyword": ""})
        assert r["ok"] is False and r["error"]["code"] == "INVALID_PARAMS"

    def test_30_autocomplete_emails(self, indexed):
        r = indexed.request("autocomplete.emails")
        assert r["ok"] and r["result"]["count"] > 0
        assert "kim.cs@company.com" in r["result"]["emails"]

    def test_31_search_record_history_flag(self, indexed):
        r = indexed.request("search.query", {"query": "인사발령", "record_history": True})
        assert r["ok"]
        r = indexed.request("search.history", {"limit": 10})
        assert "인사발령" in [i["keyword"] for i in r["result"]["items"]]


class TestSidecarBookmarks:

    def test_40_bookmark_crud_korean(self, sc):
        r = sc.request("bookmark.add", {"name": "견적서 검색", "query": "견적서",
                                        "filters": {"folder": "받은편지함"}})
        assert r["ok"] and r["result"]["id"] > 0
        bid = r["result"]["id"]

        r = sc.request("bookmark.list")
        items = r["result"]["items"]
        assert len(items) == 1
        assert items[0]["name"] == "견적서 검색"
        assert items[0]["filters"] == {"folder": "받은편지함"}  # JSON 문자열이 아닌 객체

        r = sc.request("bookmark.rename", {"id": bid, "name": "새 이름"})
        assert r["ok"] and r["result"]["ok"] is True

        r = sc.request("bookmark.remove", {"id": bid})
        assert r["ok"] and r["result"]["removed"] is True
        assert sc.request("bookmark.list")["result"]["count"] == 0

    def test_41_bookmark_remove_missing_returns_false(self, sc):
        """없는 ID 삭제 → removed=False (계획 잠재 버그 #1 고정)."""
        r = sc.request("bookmark.remove", {"id": 987654})
        assert r["ok"] is True
        assert r["result"]["removed"] is False

    def test_42_bookmark_toggle(self, sc):
        r = sc.request("bookmark.toggle", {"query": "계약서"})
        assert r["result"]["bookmarked"] is True
        r = sc.request("bookmark.toggle", {"query": "계약서"})
        assert r["result"]["bookmarked"] is False

    def test_43_bookmark_add_requires_query(self, sc):
        r = sc.request("bookmark.add", {"name": "이름만"})
        assert r["ok"] is False and r["error"]["code"] == "INVALID_PARAMS"


class TestSidecarPreview:

    def test_50_preview_html(self, sc):
        r = sc.request("preview.html", {"html": "<p>안녕하세요<br><b>세계</b></p><script>x()</script>"})
        assert r["ok"]
        text = r["result"]["text"]
        assert "안녕하세요" in text and "세계" in text
        assert "<" not in text and "script" not in text

    def test_51_preview_html_requires_param(self, sc):
        r = sc.request("preview.html", {})
        assert r["ok"] is False and r["error"]["code"] == "INVALID_PARAMS"

    def test_52_preview_mail(self, indexed):
        r = indexed.request("search.query", {"query": "", "per_page": 1})
        entry_id = r["result"]["items"][0]["email"]["entry_id"]
        r = indexed.request("preview.mail", {"entry_id": entry_id})
        assert r["ok"]
        email = r["result"]["email"]
        assert email["entry_id"] == entry_id
        assert isinstance(email["attachments"], list)

    def test_53_preview_mail_missing(self, indexed):
        r = indexed.request("preview.mail", {"entry_id": "NO_SUCH_ID"})
        assert r["ok"] is False and r["error"]["code"] == "INVALID_PARAMS"


class TestSidecarSync:

    def test_60_plan_execute_approval_flow(self):
        """sync.plan → (승인) → sync.execute 전체 플로우 + 메타 기록.

        range_months=0(전체) 사용 — Mock 고정 날짜에 의존하지 않는 결정적 테스트.
        """
        proc = SidecarProcess()
        try:
            proc.wait_ready()
            r = proc.request("sync.plan", {"folder_ids": [6, 5], "range_months": 0}, timeout=60)
            assert r["ok"], r.get("error")
            plan = r["result"]
            assert plan["plan_id"]
            assert plan["new_count"] == MOCK_TOTAL
            assert plan["has_changes"] is True
            assert plan["total_db"] == 0
            assert len(plan["new_ids_preview"]) <= 100
            assert "새 메일" in plan["changes_summary"]
            # 스캔 진행 이벤트가 스트리밍되었어야 한다
            assert proc.wait_event("sync.plan.progress", timeout=5) is not None

            r = proc.request("sync.execute",
                             {"plan_id": plan["plan_id"], "folder_ids": [6, 5], "range_months": 0},
                             timeout=60)
            assert r["ok"], r.get("error")
            stats = r["result"]
            assert stats["added"] == MOCK_TOTAL
            assert stats["errors"] == 0

            r = proc.request("sync.meta")
            assert r["result"]["last_sync_time"]
            assert r["result"]["indexed_range_months"] == 0  # 전체 범위 기록
            r = proc.request("db.stats")
            assert r["result"]["email_count"] == MOCK_TOTAL
        finally:
            proc.close()

    def test_61_second_plan_no_changes(self, indexed):
        """인덱싱 후 동일 데이터 plan → 변경 없음."""
        r = indexed.request("sync.plan", {"folder_ids": [6, 5]}, timeout=60)
        assert r["ok"]
        assert r["result"]["has_changes"] is False
        assert r["result"]["skipped_count"] == MOCK_TOTAL

    def test_62_execute_unknown_plan_id(self, sc):
        r = sc.request("sync.execute", {"plan_id": "does-not-exist"})
        assert r["ok"] is False and r["error"]["code"] == "PLAN_NOT_FOUND"

    def test_63_execute_requires_plan_id(self, sc):
        r = sc.request("sync.execute", {})
        assert r["ok"] is False and r["error"]["code"] == "INVALID_PARAMS"

    def test_64_sync_run_one_shot(self):
        """sync.run — 승인 없는 1회성 자동 동기화 (legacy SyncWorker 대체)."""
        proc = SidecarProcess()
        try:
            proc.wait_ready()
            r = proc.request("sync.run", {"folder_ids": [6, 5], "incremental": False}, timeout=60)
            assert r["ok"], r.get("error")
            assert r["result"]["added"] == MOCK_TOTAL
            # 2회차: 변경 없음
            r = proc.request("sync.run", {"folder_ids": [6, 5]}, timeout=60)
            assert r["ok"]
            assert r["result"]["added"] == 0
            assert "변경 없음" in r["result"]["message"]
        finally:
            proc.close()

    def test_65_sync_cancel_idle(self, sc):
        r = sc.request("sync.cancel")
        assert r["ok"] is False and r["error"]["code"] == "JOB_NOT_RUNNING"

    def test_66_sync_status_idle(self, sc):
        r = sc.request("sync.status")
        assert r["ok"] and r["result"]["running"] is False and r["result"]["job"] is None


class TestSidecarIndex:

    def test_70_index_build_events_and_meta(self):
        """받은편지함만 인덱싱 + 전체 범위(0) 메타 기록.

        ★ range_months=3 같은 기간 필터는 Mock 고정 날짜(2026-05-27) 때문에
          시간이 지나면 0건이 되는 타임밤 → 0(전체)으로 결정적으로 테스트한다.
        """
        proc = SidecarProcess()
        try:
            proc.wait_ready()
            r = proc.request("index.build", {"folder_ids": [6], "range_months": 0}, timeout=60)
            assert r["ok"], r.get("error")
            assert r["result"]["added"] == MOCK_INBOX
            assert r["result"]["stopped"] is False
            assert proc.wait_event("index.progress", timeout=5) is not None
            r = proc.request("db.stats")
            assert r["result"]["email_count"] == MOCK_INBOX
            assert r["result"]["indexed_range_months"] in ("0", 0)
        finally:
            proc.close()

    def test_71_index_rebuild_fts(self, indexed):
        r = indexed.request("index.rebuild_fts", timeout=60)
        assert r["ok"] and r["result"]["ok"] is True
        # 재구축 후에도 검색이 동작해야 한다
        r = indexed.request("search.query", {"query": "견적서"})
        assert r["ok"] and r["result"]["total_count"] > 0


class TestSidecarOutlookMock:

    def test_80_outlook_check(self, sc):
        r = sc.request("outlook.check", timeout=30)
        assert r["ok"]
        res = r["result"]
        assert res["mock"] is True and res["ok"] is True and res["connected"] is True

    def test_81_outlook_folders(self, sc):
        r = sc.request("outlook.folders")
        assert r["ok"]
        names = {f["name"] for f in r["result"]["folders"]}
        assert {"받은편지함", "보낸편지함"} <= names

    def test_82_default_folders_static(self, sc):
        r = sc.request("outlook.default_folders")
        assert r["ok"]
        assert r["result"]["selectable"] == [3, 5, 6, 16] or set(r["result"]["selectable"]) == {6, 5, 16, 3}

    def test_83_mail_open_mock(self, indexed):
        eid = indexed.request("search.query", {"query": "", "per_page": 1})["result"]["items"][0]["email"]["entry_id"]
        r = indexed.request("mail.open", {"entry_id": eid})
        assert r["ok"] and r["result"]["mock"] is True

    def test_84_mail_export_not_supported_in_mock(self, sc):
        r = sc.request("mail.export", {"entry_id": "X", "dest_path": str(sc.data_dir / "out.msg")})
        assert r["ok"] is False and r["error"]["code"] == "NOT_SUPPORTED"

    def test_85_font_list(self, sc):
        r = sc.request("font.list")
        assert r["ok"] and r["result"]["count"] > 0


# ═══════════════════════════════════════════════════════════════
# 3) 인코딩/환경 회귀 테스트 (계획 Phase 1 Windows 치명 버그 고정)
# ═══════════════════════════════════════════════════════════════

class TestSidecarEncoding:

    def test_14_utf8_forced_under_cp949_locale(self):
        """PYTHONIOENCODING=cp949:strict에서도 사이드카가 스스로 UTF-8 강제 (계획 회귀 test_14)."""
        proc = SidecarProcess(keep_env_io=True,
                              env_extra={"PYTHONIOENCODING": "cp949:strict"})
        try:
            ev = proc.wait_ready()
            assert ev is not None, "cp949 환경에서 ready 실패 — UTF-8 자가 강제 미동작"
            r = proc.request("system.hello")
            assert r["ok"]
            assert r["result"]["utf8_io"]["stdin"] in ("reconfigured", "wrapped", "already-utf8")
            # 한글 왕복이 cp949 환경에서도 동작해야 한다
            r = proc.request("bookmark.add", {"name": "한글이름", "query": "한글검색어"})
            assert r["ok"], r.get("error")
            r = proc.request("bookmark.list")
            assert r["result"]["items"][0]["name"] == "한글이름"
        finally:
            proc.close()

    def test_15_korean_search_response_preserved(self, indexed):
        """한글 검색어 → 한글 결과(제목·폴더명) 왕복 보존 (계획 회귀 test_15)."""
        r = indexed.request("search.query", {"query": "견적서"})
        assert r["ok"] and r["result"]["total_count"] > 0
        item = r["result"]["items"][0]
        assert any("\uac00" <= ch <= "\ud7a3" for ch in item["email"]["subject"])
        assert item["email"]["folder_name"] in ("받은편지함", "보낸편지함")
        assert r["result"]["query"] == "견적서"

    def test_16_stderr_logs_are_utf8(self, sc):
        """한국어 로그가 cp949가 아닌 UTF-8로 나간다 (계획 회귀 test_16)."""
        sc.request("bookmark.add", {"name": "로그테스트", "query": "로그"})
        sc.request("system.shutdown")
        try:
            sc.exit_code(timeout=10)
        except Exception:
            pass
        time.sleep(0.3)
        raw = b"".join(sc.stderr_bytes)
        # 엄격 UTF-8 디코딩이 실패하면 안 된다 (cp949 바이트 혼입 검출)
        text = raw.decode("utf-8")  # UnicodeDecodeError 시 테스트 실패
        assert "북마크 추가" in text or "사이드카" in text

        # 파일 로그도 UTF-8
        log_file = sc.data_dir / "logs" / "sidecar.log"
        assert log_file.exists()
        content = log_file.read_text(encoding="utf-8")
        assert "사이드카" in content

    def test_17_utf8_forced_without_pythonioencoding(self):
        """환경변수 없이 기본 spawn에서도 UTF-8 (계획 회귀 test_17)."""
        env = dict(os.environ)
        assert "PYTHONIOENCODING" not in env or True  # SidecarProcess가 제거함
        proc = SidecarProcess()
        try:
            ev = proc.wait_ready()
            r = proc.request("system.hello")
            assert r["ok"]
            for stream in ("stdin", "stdout", "stderr"):
                assert r["result"]["utf8_io"][stream] in ("reconfigured", "already-utf8", "wrapped")
        finally:
            proc.close()


class TestSidecarDbFailure:

    def test_90_hello_survives_broken_db(self):
        """DB를 열 수 없어도 system.hello는 성공 (계획 Phase 1 완료 기준)."""
        with tempfile.NamedTemporaryFile(delete=False) as blocker:
            blocker_path = Path(blocker.name)  # 파일인데 디렉터리처럼 사용 → open 불가
        try:
            bad_db = blocker_path / "sub" / "anyfinder.db"
            proc = SidecarProcess(extra_args=("--db-path", str(bad_db)))
            try:
                ev = proc.wait_ready()
                assert ev is not None
                assert ev["data"]["db_ok"] is False
                r = proc.request("system.hello")
                assert r["ok"] is True and r["result"]["db_ok"] is False
                assert r["result"]["db_error"]
                # DB 명령은 계약된 오류 코드로 실패
                r = proc.request("db.stats")
                assert r["ok"] is False
                assert r["error"]["code"] == "DB_NOT_AVAILABLE"
                assert r["error"]["retryable"] is True
                # DB 불필요 명령은 계속 동작
                r = proc.request("settings.get")
                assert r["ok"] is True
                r = proc.request("preview.html", {"html": "<b>x</b>"})
                assert r["ok"] is True
            finally:
                proc.close()
        finally:
            blocker_path.unlink(missing_ok=True)


# ═══════════════════════════════════════════════════════════════
# Phase 4 — Parity / 마이그레이션 회귀
# ═══════════════════════════════════════════════════════════════

class TestPhase4Parity:
    """4-2 재색인 없음 / 4-3 레거시 config 단일 스키마 / 4-4 버전 계약."""

    def test_18_system_info_version_contract(self, sc):
        r = sc.request("system.info")
        assert r["ok"] is True
        info = r["result"]
        for key in ("sidecar_version", "protocol_version", "schema_version",
                    "commands_count", "python", "platform", "mock", "data_dir", "db_path"):
            assert key in info, f"system.info 필드 누락: {key}"
        assert info["protocol_version"] == "1.0"
        parts = [int(x) for x in info["sidecar_version"].split(".")]
        assert parts >= [1, 1, 0], "사이드카 버전은 프런트 최소 지원 버전(1.1.0) 이상"
        cmds = sc.request("system.commands")["result"]
        assert info["commands_count"] == cmds["count"] == len(cmds["commands"])
        assert info["mock"] is True

    def test_19_legacy_config_single_schema(self):
        """레거시(utils/config.py) 스키마 config.json을 사이드카가 그대로 읽고,
        로드시 파일을 재작성하지 않으며(롤백 안전), 누락 키만 기본값 보강."""
        legacy = {
            "indexing": {"folders": ["받은편지함"], "folder_ids": [6],
                         "include_subfolders": False, "range_months": 3},
            "sync": {"auto_sync": True, "interval_minutes": 5},
            "search": {"results_per_page": 20, "default_sort": "newest"},
            "ui": {"theme": "light"},
            "first_run_completed": True,
        }
        with tempfile.TemporaryDirectory(prefix="anyfinder-cfg-") as td:
            dd = Path(td)
            cfg = dd / "config.json"
            cfg.write_text(json.dumps(legacy, ensure_ascii=False), encoding="utf-8")
            before = cfg.read_text(encoding="utf-8")
            proc = SidecarProcess(data_dir=dd)
            try:
                proc.wait_ready()
                st = proc.request("settings.get")["result"]["settings"]
                # 레거시 키 보존 (단일 스키마 — 키 이름 변경 금지)
                assert st["indexing"]["folder_ids"] == [6]
                assert st["indexing"]["include_subfolders"] is False
                assert st["indexing"]["range_months"] == 3
                assert st["sync"]["interval_minutes"] == 5
                assert st["ui"]["theme"] == "light"
                assert st["first_run_completed"] is True
                # 누락 키는 DEFAULT_CONFIG로 보강 (깊은 머지)
                assert st["search"]["max_autocomplete_items"] == 8
                assert st["sync"]["auto_sync"] is True
                # 로드만으로는 파일을 재작성하지 않는다 (레거시와 공존 가능)
                assert cfg.read_text(encoding="utf-8") == before
            finally:
                proc.close()

    def test_20_existing_index_reused_without_reindex(self):
        """4-2 완료 기준: 기존 사용자 DB로 재색인 없이 검색 동작."""
        with tempfile.TemporaryDirectory(prefix="anyfinder-reidx-") as td:
            dd = Path(td)
            first = SidecarProcess(data_dir=dd, keep_dir=True)
            try:
                first.wait_ready()
                built = first.request("index.build")["result"]
                assert built["added"] == MOCK_TOTAL
                stats = first.request("db.stats")["result"]
                assert stats["email_count"] == MOCK_TOTAL
            finally:
                first.close()

            second = SidecarProcess(data_dir=dd)
            try:
                second.wait_ready()
                stats2 = second.request("db.stats")["result"]
                assert stats2["email_count"] == MOCK_TOTAL, "기존 인덱스가 그대로 보여야 한다"
                q = second.request("search.query", {"query": "", "per_page": 5})["result"]
                assert q["total_count"] == MOCK_TOTAL, "재색인 없이 검색 가능"
                assert q["total_db_count"] == MOCK_TOTAL
            finally:
                second.close()

r"""
dev_client — Rust(Tauri) 없이 사이드카를 테스트하는 REPL/진단 도구.

실행 (저장소 루트에서):
    py -3 sidecar\dev_client.py system.hello
    py -3 sidecar\dev_client.py --doctor            # 자동 진단 체크리스트
    py -3 sidecar\dev_client.py --repl              # 대화형 REPL

★ 입력 형식 4가지 (PowerShell 따옴표 문제 대응 — MIGRATION_PLAN Phase 1):
    # 1. key=value — 따옴표 불필요
    py sidecar\dev_client.py search.record keyword=계약서

    # 2. 작은따옴표 JSON
    py sidecar\dev_client.py search.query '{"query":"보고서","per_page":5}'

    # 3. 한 토큰으로
    py sidecar\dev_client.py 'search.query {"query":"보고서"}'

    # 4. stdin 파이프 (복잡한 JSON)
    '{"patch":{"ui":{"theme":"warm-dark"}}}' | py sidecar\dev_client.py --stdin-json settings.set

    ※ Bash 스타일 \" 이스케이프는 PowerShell에서 동작하지 않는다 — 위 형식을 쓸 것.

옵션:
    --no-mock        실 Outlook 모드 (Windows 전용, 기본은 --mock)
    --exe PATH       python -m sidecar 대신 빌드된 사이드카 실행 파일 사용
    --data-dir PATH  데이터 디렉터리 (doctor는 미지정 시 임시 디렉터리 사용)
    --timeout SEC    응답 대기 (기본 30)
"""

import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


# ═══ 인수 파싱 (단위 테스트 가능 순수 함수) ═══

def coerce_value(text: str):
    """key=value의 value를 JSON 스칼라로 시도하고 실패하면 문자열로 둔다."""
    try:
        return json.loads(text)
    except Exception:
        return text


def parse_command_args(tokens):
    """명령 토큰 → (cmd, params|None, error|None).

    지원 형식:
        ["search.query"]                          → ("search.query", None, None)
        ["search.record", "keyword=계약서"]        → key=value
        ["search.query", '{"query":"보고서"}']     → JSON 토큰(들)
        ['search.query {"query":"보고서"}']        → 한 토큰 (cmd + 공백 + JSON)
    """
    if not tokens:
        return None, None, "명령이 없습니다. 예: system.hello"

    first = str(tokens[0])
    if first.startswith("{"):
        return None, None, "명령명이 없습니다. 예: search.query '{...}'"

    # 형식 3: 한 토큰에 cmd + JSON
    if " " in first.strip():
        head, _, rest = first.strip().partition(" ")
        payload = " ".join([rest] + [str(t) for t in tokens[1:]]).strip()
        return _parse_payload(head.strip(), payload)

    cmd = first.strip()
    rest = [str(t) for t in tokens[1:]]
    if not rest:
        return cmd, None, None
    return _parse_payload(cmd, " ".join(rest).strip())


def _parse_payload(cmd: str, payload: str):
    if not payload:
        return cmd, None, None
    # 형식 2: JSON 토큰
    if payload.startswith("{") or payload.startswith("["):
        try:
            params = json.loads(payload)
        except Exception as e:
            return cmd, None, f"JSON 파싱 실패: {e}"
        if not isinstance(params, dict):
            return cmd, None, "params는 JSON 객체여야 합니다"
        return cmd, params, None
    # 형식 1: key=value ...
    params = {}
    for token in payload.split():
        key, sep, value = token.partition("=")
        if not sep or not key:
            return cmd, None, f"key=value 형식이 아닙니다: {token!r}"
        params[key] = coerce_value(value)
    return cmd, params, None


# ═══ 사이드카 클라이언트 ═══

class DevClient:
    """사이드카 프로세스 spawn + JSON Lines 요청/응답."""

    def __init__(self, mock=True, exe=None, data_dir=None, timeout=30):
        self.timeout = timeout
        args = [str(exe)] if exe else [sys.executable, "-m", "sidecar"]
        if mock:
            args.append("--mock")
        if data_dir:
            args += ["--data-dir", str(data_dir)]

        env = dict(os.environ)
        env.pop("PYTHONIOENCODING", None)
        env.pop("PYTHONUTF8", None)

        kwargs = {}
        if os.name == "nt":
            # 콘솔 창 숨김 (Plan §5 리스크 3 — CREATE_NO_WINDOW)
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

        self.proc = subprocess.Popen(
            args, cwd=str(REPO_ROOT),
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=env, **kwargs,
        )
        self.events = []
        self.junk_lines = []
        self._q = queue.Queue()
        self._err = []
        self._id_counter = 0
        threading.Thread(target=self._read_stdout, daemon=True).start()
        # stderr drain 스레드 — 파이프 버퍼 블로킹 방지 (계획 Phase 1 Windows 교훈 #5)
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
                self._err.append(line)
        except Exception:
            pass

    def _next_message(self, timeout=None):
        raw = self._q.get(timeout=timeout or self.timeout)
        if raw is None:
            raise EOFError("사이드카 stdout이 닫혔습니다 (프로세스 종료?)")
        text = raw.decode("utf-8", errors="replace").strip()
        if not text:
            return None
        try:
            msg = json.loads(text)
        except Exception:
            self.junk_lines.append(text)  # 방어: 비-JSON 줄은 기록하고 계속
            return None
        if isinstance(msg, dict) and "event" in msg and "ok" not in msg:
            self.events.append(msg)
        return msg

    def wait_event(self, name, timeout=None):
        deadline = time.time() + (timeout or self.timeout)
        while time.time() < deadline:
            for ev in list(self.events):
                if ev.get("event") == name:
                    return ev
            try:
                self._next_message(timeout=max(0.1, deadline - time.time()))
            except (queue.Empty, EOFError):
                break
        return None

    def request(self, cmd, params=None, timeout=None):
        """응답(id 매칭)이 올 때까지 읽는다. 오는 이벤트는 수집한다."""
        self._id_counter += 1
        req_id = self._id_counter
        line = json.dumps({"id": req_id, "cmd": cmd, "params": params or {}}, ensure_ascii=False)
        self.proc.stdin.write((line + "\n").encode("utf-8"))
        self.proc.stdin.flush()
        deadline = time.time() + (timeout or self.timeout)
        while time.time() < deadline:
            try:
                msg = self._next_message(timeout=max(0.1, deadline - time.time()))
            except queue.Empty:
                break
            if msg is None:
                continue
            if msg.get("id") == req_id and "ok" in msg:
                return msg
        raise TimeoutError(f"{cmd} 응답 대기 시간 초과 ({timeout or self.timeout}s)")

    def send_raw(self, data: bytes):
        self.proc.stdin.write(data)
        self.proc.stdin.flush()

    def shutdown(self, timeout=10):
        try:
            self.request("system.shutdown", timeout=5)
        except Exception:
            pass
        try:
            return self.proc.wait(timeout=timeout)
        except Exception:
            self.proc.kill()
            return self.proc.wait(timeout=5)

    def kill(self):
        try:
            self.proc.kill()
            self.proc.wait(timeout=5)
        except Exception:
            pass


# ═══ --doctor 자동 진단 ═══

def run_doctor(mock=True, exe=None, data_dir=None, timeout=30, verbose=True):
    """체크리스트를 순서대로 실행하고 (passed, total, results)를 반환한다."""
    results = []
    tmp_dir = None

    def check(name, fn):
        try:
            detail = fn()
            results.append((name, True, detail or ""))
            if verbose:
                print(f"  ✅ {name}" + (f" — {detail}" if detail else ""))
        except AssertionError as e:
            results.append((name, False, str(e)))
            if verbose:
                print(f"  ❌ {name} — {e}")
        except Exception as e:
            results.append((name, False, f"{type(e).__name__}: {e}"))
            if verbose:
                print(f"  ❌ {name} — {type(e).__name__}: {e}")

    def must(cond, msg):
        if not cond:
            raise AssertionError(msg)

    if data_dir is None:
        tmp_dir = tempfile.mkdtemp(prefix="anyfinder-doctor-")
        data_dir = tmp_dir

    if verbose:
        print("=" * 62)
        print("OutLook AnyFinder Sidecar Doctor")
        print("=" * 62)

    client = DevClient(mock=mock, exe=exe, data_dir=data_dir, timeout=timeout)
    try:
        ready = client.wait_event("ready", timeout=timeout)

        def c_ready():
            must(ready is not None, "ready 이벤트를 받지 못함")
            return f"pid={ready['data'].get('pid')}, cmds={ready['data'].get('commands_count')}"
        check("01 ready 이벤트", c_ready)

        def c_hello():
            r = client.request("system.hello")
            must(r["ok"], f"hello 실패: {r.get('error')}")
            res = r["result"]
            must(res.get("sidecar_version") and res.get("db_path"), "필수 필드 누락")
            return f"v{res['sidecar_version']}, db_ok={res['db_ok']}, commands={res['commands_count']}"
        check("02 system.hello", c_hello)

        def c_ping():
            r = client.request("system.ping")
            must(r["ok"] and r["result"]["pong"], "ping 실패")
            return "pong"
        check("03 system.ping", c_ping)

        def c_commands():
            r = client.request("system.commands")
            must(r["ok"] and r["result"]["count"] >= 30, f"명령 수 부족: {r['result'].get('count')}")
            return f"{r['result']['count']}개 등록"
        check("04 system.commands ≥ 30", c_commands)

        def c_db_stats():
            r = client.request("db.stats")
            must(r["ok"], f"db.stats 실패: {r.get('error')}")
            return f"emails={r['result']['email_count']}"
        check("05 db.stats", c_db_stats)

        def c_schema():
            r = client.request("db.schema_version")
            must(r["ok"] and r["result"]["schema_version"] >= 1, "schema_version 이상")
            return f"v{r['result']['schema_version']}"
        check("06 db.schema_version", c_schema)

        def c_settings_get():
            r = client.request("settings.get")
            must(r["ok"] and "ui" in r["result"]["settings"], "settings 구조 이상")
            return "ok"
        check("07 settings.get", c_settings_get)

        def c_settings_roundtrip():
            r = client.request("settings.set", {"patch": {"ui": {"theme": "light"}}})
            must(r["ok"] and r["result"]["settings"]["ui"]["theme"] == "light", "patch 미반영")
            r2 = client.request("settings.get")
            must(r2["result"]["settings"]["ui"]["theme"] == "light", "저장 안 됨")
            must("sidebar_width" in r2["result"]["settings"]["ui"], "깊은 머지 실패 — 기존 키 유실")
            client.request("settings.set", {"patch": {"ui": {"theme": "dark"}}})
            return "깊은 머지 round-trip ok"
        check("08 settings.set/get 왕복", c_settings_roundtrip)

        state_box = {}

        def c_bm_add():
            r = client.request("bookmark.add", {"name": "견적서 검색", "query": "견적서"})
            must(r["ok"] and r["result"]["id"] > 0, f"북마크 추가 실패: {r.get('error')}")
            state_box["bm_id"] = r["result"]["id"]
            return f"id={state_box['bm_id']}"
        check("09 bookmark.add (한글)", c_bm_add)

        def c_bm_list():
            r = client.request("bookmark.list")
            names = [b["name"] for b in r["result"]["items"]]
            must("견적서 검색" in names, f"한글 북마크 누락: {names}")
            return "한글 보존 ok"
        check("10 bookmark.list 한글 보존", c_bm_list)

        def c_bm_remove():
            r = client.request("bookmark.remove", {"id": state_box["bm_id"]})
            must(r["ok"] and r["result"]["removed"] is True, "존재 ID 삭제 실패")
            return "removed=True"
        check("11 bookmark.remove 존재 ID", c_bm_remove)

        def c_bm_remove_missing():
            r = client.request("bookmark.remove", {"id": 987654})
            must(r["ok"] and r["result"]["removed"] is False, "없는 ID에 removed=True (잠재 버그 #1 재발)")
            return "잠재 버그 #1 수정 확인"
        check("12 bookmark.remove 없는 ID → False", c_bm_remove_missing)

        if mock:
            def c_index_build():
                # range_months 미지정(전체) — Mock 샘플 날짜는 고정값이라 기간 필터를 쓰면
                # 시간이 지난 뒤 검사 실패(타임밤)가 된다.
                r = client.request("index.build", {"folder_ids": [6, 5]}, timeout=timeout * 4)
                must(r["ok"], f"index.build 실패: {r.get('error')}")
                must(r["result"]["added"] > 0, f"인덱싱 0건: {r['result']}")
                return r["result"]["message"]
            check("13 index.build (mock)", c_index_build)

            def c_stats_after():
                r = client.request("db.stats")
                must(r["result"]["email_count"] > 0, "메일 0건")
                return f"emails={r['result']['email_count']}"
            check("14 db.stats 인덱싱 확인", c_stats_after)

            def c_search_all():
                r = client.request("search.query", {"query": ""})
                must(r["ok"] and r["result"]["total_count"] > 0, "전체 목록 0건")
                return f"total={r['result']['total_count']}, {r['result']['elapsed_ms']}ms"
            check("15 search.query 전체", c_search_all)

            def c_search_korean():
                r = client.request("search.query", {"query": "견적서"})
                must(r["ok"] and r["result"]["total_count"] > 0, "한글 검색 0건")
                subj = r["result"]["items"][0]["email"]["subject"]
                must(any("\uac00" <= ch <= "\ud7a3" for ch in subj), f"한글 깨짐: {subj!r}")
                return f"'견적서' → {r['result']['total_count']}건, 첫 결과: {subj[:30]}"
            check("16 search.query 한글 왕복", c_search_korean)

            def c_search_email():
                r = client.request("search.query", {"query": "kim.cs@company.com"})
                must(r["ok"] and r["result"]["total_count"] > 0, "메일주소 검색 0건")
                return f"{r['result']['total_count']}건"
            check("17 search.query 메일주소", c_search_email)

            def c_search_folders_or():
                both = client.request("search.query", {"query": "", "folders": ["받은편지함", "보낸편지함"], "per_page": 200})
                inbox = client.request("search.query", {"query": "", "folders": ["받은편지함"], "per_page": 200})
                sent = client.request("search.query", {"query": "", "folders": ["보낸편지함"], "per_page": 200})
                must(both["result"]["total_count"] == inbox["result"]["total_count"] + sent["result"]["total_count"],
                     "다중 폴더 OR 결합 아님 (잠재 버그 #3)")
                return f"받은 {inbox['result']['total_count']} + 보낸 {sent['result']['total_count']} = {both['result']['total_count']}"
            check("18 search.query 다중 폴더 OR", c_search_folders_or)

            def c_search_folders():
                r = client.request("search.folders")
                must(r["ok"] and r["result"]["total"] > 0, "폴더 카운트 0")
                return str(r["result"]["counts"])
            check("19 search.folders", c_search_folders)

            def c_history():
                client.request("search.record", {"keyword": "주간보고"})
                r = client.request("search.history", {"limit": 5})
                kws = [i["keyword"] for i in r["result"]["items"]]
                must("주간보고" in kws, f"기록 누락: {kws}")
                return "기록/조회 ok"
            check("20 search.record + history", c_history)

            def c_suggest():
                r = client.request("autocomplete.suggest", {"prefix": "주간"})
                kws = [s["keyword"] for s in r["result"]["suggestions"]]
                must("주간보고" in kws, f"제안 누락: {kws}")
                return "prefix 제안 ok"
            check("21 autocomplete.suggest", c_suggest)

            def c_emails():
                r = client.request("autocomplete.emails")
                must(r["result"]["count"] > 0 and any("@" in e for e in r["result"]["emails"]), "메일주소 후보 없음")
                return f"{r['result']['count']}개"
            check("22 autocomplete.emails", c_emails)
        elif verbose:
            print("  ⏭ 13~22 mock 전용 체크 생략 (--no-mock)")

        def c_sync_meta():
            r = client.request("sync.meta")
            must(r["ok"], f"sync.meta 실패: {r.get('error')}")
            return str(r["result"])
        check("23 sync.meta", c_sync_meta)

        def c_sync_plan():
            r = client.request("sync.plan", {"folder_ids": [6, 5]}, timeout=timeout * 4)
            must(r["ok"], f"sync.plan 실패: {r.get('error')}")
            must(r["result"]["plan_id"], "plan_id 없음")
            state_box["plan_id"] = r["result"]["plan_id"]
            return r["result"]["changes_summary"]
        check("24 sync.plan", c_sync_plan)

        def c_sync_execute():
            r = client.request("sync.execute",
                               {"plan_id": state_box["plan_id"], "folder_ids": [6, 5], "range_months": 6},
                               timeout=timeout * 4)
            must(r["ok"], f"sync.execute 실패: {r.get('error')}")
            return r["result"]["message"]
        check("25 sync.execute", c_sync_execute)

        def c_sync_execute_bad_plan():
            r = client.request("sync.execute", {"plan_id": "no-such-plan"})
            must(not r["ok"] and r["error"]["code"] == "PLAN_NOT_FOUND", f"기대: PLAN_NOT_FOUND, 실제: {r}")
            return "ok"
        check("26 sync.execute 만료 plan_id", c_sync_execute_bad_plan)

        def c_sync_cancel_idle():
            r = client.request("sync.cancel")
            must(not r["ok"] and r["error"]["code"] == "JOB_NOT_RUNNING", f"기대: JOB_NOT_RUNNING, 실제: {r}")
            return "idle 취소 → JOB_NOT_RUNNING ok"
        check("27 sync.cancel (idle)", c_sync_cancel_idle)

        def c_outlook_check():
            r = client.request("outlook.check", timeout=timeout * 2)
            must(r["ok"], f"outlook.check 실패: {r.get('error')}")
            return r["result"]["message"][:60]
        check("28 outlook.check", c_outlook_check)

        def c_preview():
            r = client.request("preview.html", {"html": "<p>안녕<br>세계</p>"})
            must(r["ok"] and "안녕" in r["result"]["text"] and "<" not in r["result"]["text"], f"preview 이상: {r}")
            return repr(r["result"]["text"])
        check("29 preview.html", c_preview)

        def c_unknown():
            r = client.request("no.such_command")
            must(not r["ok"] and r["error"]["code"] == "UNKNOWN_COMMAND", f"기대: UNKNOWN_COMMAND, 실제: {r}")
            return "ok"
        check("30 unknown → UNKNOWN_COMMAND", c_unknown)

        def c_malformed():
            client.send_raw(b"{ this is not json !!!\n")
            time.sleep(0.3)
            r = client.request("system.ping")
            must(r["ok"], "malformed 줄 이후 서버 죽음")
            return "서버 생존"
        check("31 malformed line 생존", c_malformed)

        def c_pollution():
            r = client.request("system.debug.print", {"text": "오염테스트 contamination!"})
            must(r["ok"], f"debug.print 실패: {r.get('error')}")
            r2 = client.request("system.ping")
            must(r2["ok"], "print 오염 후 채널 손상")
            must(not client.junk_lines, f"stdout에 비-JSON 줄 발견: {client.junk_lines[:2]}")
            return "stdout = 순수 JSON만"
        check("32 print 오염 방어", c_pollution)

        def c_backup():
            r = client.request("db.backup", {"suffix": "doctor-test"})
            must(r["ok"] and Path(r["result"]["path"]).exists(), f"백업 실패: {r}")
            Path(r["result"]["path"]).unlink(missing_ok=True)
            return Path(r["result"]["path"]).name
        check("33 db.backup", c_backup)

        code = client.shutdown(timeout=10)

        def c_shutdown():
            must(code == 0, f"비정상 종료 코드: {code}")
            return "정상 종료"
        check("34 shutdown → exit 0", c_shutdown)
    finally:
        client.kill()
        if tmp_dir:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    if verbose:
        print("-" * 62)
        print(f"결과: {passed}/{total} 통과" + (" 🎉" if passed == total else " ⚠️ 실패 항목 확인 필요"))
    return passed, total, results


# ═══ REPL / 단발 명령 ═══

def run_repl(client):
    print("사이드카 REPL — 'cmd [key=value | {json}]', :events, :quit")
    while True:
        try:
            line = input("sidecar> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not line:
            continue
        if line in (":quit", ":q", "exit"):
            break
        if line == ":events":
            for ev in client.events[-20:]:
                print(json.dumps(ev, ensure_ascii=False))
            continue
        cmd, params, err = parse_command_args([line])
        if err:
            print(f"⚠ {err}")
            continue
        try:
            resp = client.request(cmd, params)
            print(json.dumps(resp, ensure_ascii=False, indent=2))
        except Exception as e:
            print(f"⚠ {type(e).__name__}: {e}")
    client.shutdown()


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)

    mock = "--no-mock" not in argv
    argv = [a for a in argv if a not in ("--mock", "--no-mock")]

    def take_option(name):
        if name in argv:
            i = argv.index(name)
            value = argv[i + 1] if i + 1 < len(argv) else None
            del argv[i:i + 2]
            return value
        return None

    exe = take_option("--exe")
    data_dir = take_option("--data-dir")
    timeout_raw = take_option("--timeout")
    try:
        timeout = int(timeout_raw) if timeout_raw else 30
    except ValueError:
        timeout = 30

    if "--doctor" in argv:
        passed, total, _ = run_doctor(mock=mock, exe=exe, data_dir=data_dir, timeout=timeout)
        return 0 if passed == total else 1

    stdin_json = "--stdin-json" in argv
    argv = [a for a in argv if a != "--stdin-json"]

    if not argv or "--repl" in argv:
        client = DevClient(mock=mock, exe=exe, data_dir=data_dir, timeout=timeout)
        client.wait_event("ready", timeout=timeout)
        run_repl(client)
        return 0

    if stdin_json:
        cmd = argv[0]
        raw = sys.stdin.read()
        try:
            params = json.loads(raw) if raw.strip() else {}
        except Exception as e:
            print(f"⚠ stdin JSON 파싱 실패: {e}", file=sys.stderr)
            return 2
        if not isinstance(params, dict):
            print("⚠ stdin JSON은 객체여야 합니다", file=sys.stderr)
            return 2
    else:
        cmd, params, err = parse_command_args(argv)
        if err:
            print(f"⚠ {err}", file=sys.stderr)
            return 2

    client = DevClient(mock=mock, exe=exe, data_dir=data_dir, timeout=timeout)
    try:
        client.wait_event("ready", timeout=timeout)
        resp = client.request(cmd, params)
        print(json.dumps(resp, ensure_ascii=False, indent=2))
        return 0 if resp.get("ok") else 1
    except Exception as e:
        print(f"⚠ {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    finally:
        client.kill()


if __name__ == "__main__":
    sys.exit(main())

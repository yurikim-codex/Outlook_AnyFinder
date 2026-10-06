"""IPC 계약 정합성 감사 (Phase 4 연장 — A2 발견 계약 버그 클래스의 체계적 방지).

배경: A2 jsdom 하네스가 실버그 3건을 잡았으나, 그 중 2건은
"사이드카 핸들러가 읽는 파라미터/반환 필드 ≠ 프런트엔드 래퍼가 송수신하는 이름"
이라는 *계약 불일치* 클래스였다(autocomplete.suggest, bookmark.*).
수동 시나리오만으로는 43개 명령 전수를 덮기 어려워, 정적 감사를 추가한다:

  1) sidecar/handlers/*.py 를 AST 파싱 → 명령별 required(require_str/require_int)
     / optional(params.get, params[...]) 파라미터 키 수집
  2) frontend/src/lib/api.ts 를 파싱 → 래퍼가 정적으로 송신하는 파라미터 키 수집
  3) 대조:
     - api.ts의 모든 명령은 사이드카에 등록돼 있어야 함 (미등록 = FAIL)
     - required 키는 래퍼가 항상 송신해야 함 (누락 = FAIL)
     - 래퍼가 보내는 키 중 핸들러가 전혀 읽지 않는 키 = 오타 의심 (FAIL)
     - 사이드카에만 있는 명령은 정보성(하네스/레거시 직접 호출 가능)

실행: pytest tests/test_ipc_contract_audit.py -q
"""

from __future__ import annotations

import ast
import json
import pathlib
import re

REPO = pathlib.Path(__file__).resolve().parent.parent
HANDLERS_DIR = REPO / "sidecar" / "handlers"
API_TS = REPO / "frontend" / "src" / "lib" / "api.ts"

# 하네스/스크립트가 직접 invoke하는 명령(프런트 래퍼 없음 허용)
DIRECT_INVOKE_ONLY = {
    "db.reset_all",  # scenarios.mjs / 롤백 드릴
    "system.info",  # store 부트스트랩은 래퍼 보유 — 중복 허용
}


# ────────────────────────── 1) 사이드카 핸들러 파싱 ──────────────────────────


def _param_reads(fn: ast.FunctionDef) -> tuple[set[str], set[str]]:
    """함수 본문에서 require_*(required) / params.get·params[](optional) 키 수집."""
    required: set[str] = set()
    optional: set[str] = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Call):
            fname = node.func.id if isinstance(node.func, ast.Name) else ""
            if fname in ("require_str", "require_int") and len(node.args) >= 2:
                lit = node.args[1]
                if isinstance(lit, ast.Constant) and isinstance(lit.value, str):
                    required.add(lit.value)
            # params.get("k", ...)
            func = node.func
            if (
                isinstance(func, ast.Attribute)
                and func.attr == "get"
                and isinstance(func.value, ast.Name)
                and func.value.id == "params"
                and node.args
                and isinstance(node.args[0], ast.Constant)
            ):
                optional.add(node.args[0].value)
        # params["k"]
        if (
            isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Name)
            and node.value.id == "params"
            and isinstance(node.slice, ast.Constant)
            and isinstance(node.slice.value, str)
        ):
            optional.add(node.slice.value)
    return required, optional


def load_sidecar_contract() -> dict[str, dict]:
    """cmd → {required, optional, file}"""
    contract: dict[str, dict] = {}
    for py in sorted(HANDLERS_DIR.glob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        funcs = {
            n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
        }
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "register"
                and len(node.args) >= 2
                and isinstance(node.args[0], ast.Constant)
            ):
                cmd = node.args[0].value
                target = node.args[1]
                fn = funcs.get(target.id if isinstance(target, ast.Name) else "")
                if fn is None:
                    continue
                req, opt = _param_reads(fn)
                contract[cmd] = {
                    "required": req,
                    "optional": opt | req,
                    "file": py.name,
                }
    return contract


# ────────────────────────── 2) api.ts 래퍼 파싱 ──────────────────────────

def _iter_request_calls(src: str):
    """.request<...>( "cmd" ... 호출 위치 열거 — 제네릭 내 ';'·개행 허용(균형 괄호)."""
    idx = 0
    while True:
        i = src.find(".request", idx)
        if i < 0:
            return
        j = i + len(".request")
        # 옵션 제네릭 <...> 균형 슂
        while j < len(src) and src[j] in " \t\r\n":
            j += 1
        if j < len(src) and src[j] == "<":
            depth = 0
            while j < len(src):
                if src[j] == "<":
                    depth += 1
                elif src[j] == ">":
                    depth -= 1
                    if depth == 0:
                        j += 1
                        break
                j += 1
        while j < len(src) and src[j] in " \t\r\n":
            j += 1
        if j < len(src) and src[j] == "(":
            k = j + 1
            while k < len(src) and src[k] in " \t\r\n":
                k += 1
            if k < len(src) and src[k] == '"':
                end = src.index('"', k + 1)
                yield src[k + 1 : end], end + 1
        idx = j


def _extract_object_keys(src: str, start: int) -> tuple[set[str], bool, int]:
    """src[start] == '{' 가정. depth-1 키 수집. 스프레드 발견 시 dynamic=True."""
    keys: set[str] = set()
    dynamic = False
    depth = 0
    i = start
    end = len(src)
    while i < end:
        c = src[i]
        if c == "{":
            depth += 1
            i += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return keys, dynamic, i + 1
            i += 1
        elif c == "." and src[i : i + 3] == "...":
            if depth == 1:
                dynamic = True
            i += 3
        elif c in "\"'`":
            # 문자열 리터럴 슂
            q = c
            i += 1
            while i < end and src[i] != q:
                if src[i] == "\\":
                    i += 1
                i += 1
            i += 1
        elif depth == 1 and (c.isalpha() or c in "_$"):
            j = i
            while j < end and (src[j].isalnum() or src[j] in "_$"):
                j += 1
            word = src[i:j]
            k = j
            while k < end and src[k] in " \t\r\n":
                k += 1
            if k < end and src[k] == ":":
                keys.add(word)
                i = _skip_value(src, k + 1)
            elif k < end and src[k] in ",}" and word not in ("true", "false", "null", "undefined"):
                keys.add(word)  # shorthand { query }
                i = j
            else:
                i = j
        else:
            i += 1
    raise AssertionError("api.ts 객체 리터럴 불균형")


def _skip_value(src: str, i: int) -> int:
    """depth-0(객체 기준 depth-1) ',' 또는 '}' 직전까지 값 표현식 슂."""
    depth = 0
    end = len(src)
    while i < end:
        c = src[i]
        if c in "{[(":
            depth += 1
        elif c in "}])":
            if depth == 0:
                return i
            depth -= 1
        elif c == "," and depth == 0:
            return i
        elif c in "\"'`":
            q = c
            i += 1
            while i < end and src[i] != q:
                if src[i] == "\\":
                    i += 1
                i += 1
        i += 1
    return end


def load_frontend_calls() -> dict[str, dict]:
    """cmd → {keys, dynamic}"""
    src = API_TS.read_text(encoding="utf-8")
    calls: dict[str, dict] = {}
    for cmd, after in _iter_request_calls(src):
        entry = calls.setdefault(cmd, {"keys": set(), "dynamic": False})
        rest = src[after:]
        k = 0
        while k < len(rest) and rest[k] in " \t\r\n":
            k += 1
        if k < len(rest) and rest[k] == ",":
            k += 1
            while k < len(rest) and rest[k] in " \t\r\n":
                k += 1
        if k < len(rest) and rest[k] == "{":
            keys, dynamic, _ = _extract_object_keys(rest, k)
            entry["keys"] |= keys
            entry["dynamic"] = entry["dynamic"] or dynamic
        elif k < len(rest) and (rest[k].isalpha() or rest[k] in "_$({"):
            # 변수/표현식을 params로 전달 → 동적
            entry["dynamic"] = True
    return calls


# ────────────────────────── 3) 대조 ──────────────────────────


def _contracts():
    sidecar = load_sidecar_contract()
    frontend = load_frontend_calls()
    return sidecar, frontend


def test_sidecar_contract_has_commands():
    sidecar, _ = _contracts()
    assert len(sidecar) >= 40, f"사이드카 명령 수집 부족: {len(sidecar)}"


def test_frontend_calls_all_registered():
    sidecar, frontend = _contracts()
    unknown = [c for c in frontend if c not in sidecar]
    assert not unknown, f"사이드카에 미등록 명령을 프런트가 호출: {unknown}"


def test_required_params_always_sent():
    sidecar, frontend = _contracts()
    problems = []
    for cmd, fe in frontend.items():
        sc = sidecar.get(cmd)
        if not sc or fe["dynamic"]:
            continue
        missing = sc["required"] - fe["keys"]
        if missing:
            problems.append(f"{cmd}: required 누락 {sorted(missing)}")
    assert not problems, "필수 파라미터 누락:\n" + "\n".join(problems)


def test_no_typo_params():
    """래퍼가 보내지만 핸들러가 전혀 읽지 않는 키 = 오타/계약 드리프트."""
    sidecar, frontend = _contracts()
    problems = []
    for cmd, fe in frontend.items():
        sc = sidecar.get(cmd)
        if not sc or fe["dynamic"]:
            continue
        unread = fe["keys"] - sc["optional"]
        if unread:
            problems.append(f"{cmd}: 핸들러가 읽지 않는 키 {sorted(unread)}")
    assert not problems, "계약 드리프트(오타 파라미터):\n" + "\n".join(problems)


def test_sidecar_only_commands_documented():
    """프런트 래퍼 없는 명령은 하네스/레거시용임을 명시(정보성 asserting set equality는 하지 않음)."""
    sidecar, frontend = _contracts()
    only = {c for c in sidecar if c not in frontend} - DIRECT_INVOKE_ONLY
    # 실패가 아닌 출력으로 남겨 추후 래퍼 추가 판단 자료로 쓴다
    print("\n[contract-audit] 프런트 래퍼 없는 사이드카 명령:", json.dumps(sorted(only), ensure_ascii=False))


def test_result_field_spots():
    """A2가 잡은 필드류 회귀 방지: 주요 명령의 결과 필드 이름을 래퍼 타입과 대조.

    정적 한계로, 과거 결함 2건의 '현재正しい 계약'을 고정 표본으로 asserting.
    """
    src = API_TS.read_text(encoding="utf-8")
    assert "suggestions: { keyword: string; search_count: number; last_searched_at: string }[]" in src, (
        "autocomplete.suggest 계약 회귀(객체 배열)"
    )
    assert 't.request<{ bookmarked: boolean; query: string }>("bookmark.toggle", { query })' in src, (
        "bookmark.toggle 계약 회귀(query/bookmarked)"
    )
    assert '("bookmark.add", {' in src and "query," in src, "bookmark.add 계약 회귀(query)"

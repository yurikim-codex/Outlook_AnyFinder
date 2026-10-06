"""IPC 런타임 계약 프로브 — 사이드카 전 명령(43) 빈 파라미터 호출 검사.

목적: 각 명령이 "빈 파라미터"에 대해 *적절한* 응답(OK 또는 INVALID_PARAMS 등
계약된 에러 코드)을반환하는지 확인. INTERNAL / PARSE_ERROR / 크래시(무응답)는
핸들러 검증 결함 또는 계약 붕괴 신호이므로 실패로 취급.

사용:
  1) 개발 브리지 기동:  python frontend/dev_bridge.py   (또는 Tauri dev)
  2) python tools/contract_probe.py [--url http://127.0.0.1:8765/invoke]

Windows 검증 런북 Step 3 보조 수단: mock 모드에서 전 명령 워게임에 쓴다.
위험 명령(system.shutdown, db.reset*)은 기본 제외(--include-dangerous 로 허용).
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import urllib.error
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from tests.test_ipc_contract_audit import load_sidecar_contract  # noqa: E402

BAD_CODES = {"INTERNAL", "PARSE_ERROR"}
DEFAULT_SKIP = {"system.shutdown", "db.reset_all", "db.reset"}


def invoke(url: str, cmd: str, params: dict | None = None, timeout: int = 60) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps({"cmd": cmd, "params": params or {}}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8765/invoke")
    ap.add_argument("--include-dangerous", action="store_true")
    args = ap.parse_args()

    cmds = sorted(load_sidecar_contract())
    skip = set() if args.include_dangerous else DEFAULT_SKIP
    print(f"[probe] {args.url} — 명령 {len(cmds)}개 (제외: {sorted(skip) or '없음'})")

    bad: list[str] = []
    for cmd in cmds:
        if cmd in skip:
            continue
        try:
            resp = invoke(args.url, cmd)
        except urllib.error.URLError as e:
            print(f"  CRASH(무응답) {cmd}: {e}")
            bad.append(cmd)
            continue
        except Exception as e:  # noqa: BLE001
            print(f"  CRASH {cmd}: {type(e).__name__}: {e}")
            bad.append(cmd)
            continue
        if resp.get("ok"):
            code = "OK"
        else:
            code = (resp.get("error") or {}).get("code", "?")
        mark = "  <<< 부적절" if code in BAD_CODES else ""
        if code in BAD_CODES:
            bad.append(cmd)
        print(f"  {code:20s} {cmd}{mark}")

    if bad:
        print(f"\n[probe] FAIL — 부적절 응답: {bad}")
        return 1
    print("\n[probe] PROBE_OK — 전 명령 적절한 응답")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""실 Outlook COM 프로브 — 사이드카 급사 지점 단계별 특정 (Track B 실측 8호).

배경: 설치본 사이드카가 실 Outlook 동기화 중 exit code -1로 급사하는데
  - Windows 이벤트 로그에 크래시 기록 없음 (WER 미생성 = 네이티브 ExitProcess 계열)
  - Python 종료 정리 로그 없음 (finally 미실행 = 인터프리터 정상 종료 아님)
  - 콘솔 Python에서는 Dispatch/GetNamespace/GetDefaultFolder가 정상 (P1~P3 통과)
  - 단, P3에서 보낸 편지함 Items.Count = 0 (O365 사용 중인데 0건 = 의심)

실행 (저장소 루트에서, Outlook 실행 상태):
    python -X faulthandler tools\probe_outlook_com.py

각 단계마다 줄버퍼링 로그를 남기므로, 급사 시 "마지막으로 찍힌 줄"이
크래시 직전 단계다. 네이티브 크래시면 faulthandler가 스택을 덤프한다.
"""
from __future__ import annotations

import sys
import threading
import time

sys.path.insert(0, ".")
try:
    sys.stdout.reconfigure(line_buffering=True)
except Exception:
    pass


def log(*args) -> None:
    print(time.strftime("%H:%M:%S"), *args, flush=True)


def worker() -> None:
    # 사이드카 ComWorker와 동일 조건: 별도 스레드 + STA
    import pythoncom

    pythoncom.CoInitialize()
    log("[1] CoInitialize OK (STA worker thread)")

    from core.outlook_connector import OutlookConnector

    connector = OutlookConnector()
    log("[2] OutlookConnector 생성 OK")

    ok = connector.connect()
    log("[3] connect() ->", ok)

    mapi = connector.mapi
    try:
        stores = [s.DisplayName for s in mapi.Stores]
    except Exception as e:
        stores = f"Stores 열거 실패: {type(e).__name__}: {e}"
    log("[4] Stores:", stores)

    for fid in (6, 5):  # 6=받은 편지함, 5=보낸 편지함
        folder = connector.get_default_folder(fid)
        if folder is None:
            log(f"[5] folder[{fid}] = None (폴더 접근 실패)")
            continue
        try:
            count = folder.Items.Count
        except Exception as e:
            count = f"Count 실패: {type(e).__name__}: {e}"
        log(f"[5] folder[{fid}] = {folder.Name!r}, Items.Count = {count}")

        # sync.plan의 실제 스캔 경로와 동일한 iter_mails 열거 (최대 3건)
        try:
            n = 0
            for _raw in connector.iter_mails(fid, False, after_date=None, incremental=False):
                n += 1
                if n >= 3:
                    break
            log(f"[6] iter_mails[{fid}] 첫 {n}건 열거 OK")
        except Exception as e:
            log(f"[6] iter_mails[{fid}] 예외: {type(e).__name__}: {e}")

    # 하위 폴더 재귀 (include_subfolders=True 경로) — 폴더 트리 전체 열거
    try:
        n = 0
        for _raw in connector.iter_mails(5, True, after_date=None, incremental=False):
            n += 1
            if n >= 3:
                break
        log("[7] iter_mails[5, subfolders=True] 첫", n, "건 OK")
    except Exception as e:
        log("[7] iter_mails(subfolders) 예외:", type(e).__name__, e)

    pythoncom.CoUninitialize()
    log("[8] CoUninitialize + worker 정상 종료")


def main() -> int:
    log("=== Outlook COM 프로브 시작 (faulthandler 활성 권장) ===")
    log("python:", sys.version)
    t = threading.Thread(target=worker, name="ProbeCOM", daemon=False)
    t.start()
    t.join()
    log("=== MAIN DONE — 급사 없이 전 단계 통과 ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())

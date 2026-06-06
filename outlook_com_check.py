"""
OutLook AnyFinder Outlook COM 진단 스크립트

빌드 PC 또는 사용자 PC에서 Outlook COM 연결 가능 여부를 확인합니다.
실행:
    py -3 outlook_com_check.py
또는:
    python outlook_com_check.py
"""

import sys
import traceback

print("=" * 70)
print("OutLook AnyFinder - Outlook COM Check")
print("=" * 70)
print(f"Python: {sys.executable}")
print(f"Version: {sys.version}")
print(f"Platform: {sys.platform}")

try:
    import pythoncom
    import win32com.client
    import pywintypes
    import win32timezone  # noqa
    print("OK: pywin32 modules imported")
except Exception as e:
    print("FAIL: pywin32 import failed")
    print(e)
    traceback.print_exc()
    raise SystemExit(1)

try:
    pythoncom.CoInitialize()
    outlook = win32com.client.Dispatch("Outlook.Application")
    mapi = outlook.GetNamespace("MAPI")
    inbox = mapi.GetDefaultFolder(6)
    print("OK: Outlook COM connected")
    print(f"Inbox: {getattr(inbox, 'Name', '')}, Count: {getattr(inbox.Items, 'Count', '?')}")
except Exception as e:
    print("FAIL: Outlook COM connection failed")
    print(e)
    traceback.print_exc()
    raise SystemExit(2)
finally:
    try:
        pythoncom.CoUninitialize()
    except Exception:
        pass

print("=" * 70)
print("Outlook COM check completed successfully")
print("=" * 70)

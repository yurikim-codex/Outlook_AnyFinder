"""
OutLook AnyFinder Ver0.9 for SESUNG Team
PyInstaller .exe 빌드 스크립트

사용법:
    python build_exe.py

결과:
    dist/OutLookAnyFinder.exe  (단일 실행 파일)
"""

import subprocess
import sys
import os


def build():
    print("=" * 60)
    print("🔨 OutLook AnyFinder Ver0.9 — .exe 빌드")
    print("=" * 60)

    # PyInstaller 확인
    try:
        import PyInstaller
        print(f"✅ PyInstaller {PyInstaller.__version__}")
    except ImportError:
        print("📦 PyInstaller 설치 중...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    # 빌드 명령어
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",                          # 단일 .exe
        "--windowed",                         # 콘솔 창 숨김
        "--name", "OutLookAnyFinder",         # 실행 파일 이름
        "--clean",                            # 캐시 정리
        "--add-data", "ui;ui",                # UI 모듈 포함
        "--add-data", "core;core",            # Core 모듈 포함
        "--add-data", "data;data",            # Data 모듈 포함
        "--add-data", "utils;utils",          # Utils 모듈 포함
        "--add-data", "workers;workers",      # Workers 모듈 포함
        "--hidden-import", "PyQt6",
        "--hidden-import", "PyQt6.QtWidgets",
        "--hidden-import", "PyQt6.QtCore",
        "--hidden-import", "PyQt6.QtGui",
        "--hidden-import", "win32com",
        "--hidden-import", "win32com.client",
        "--hidden-import", "bs4",
        # "--icon", "resources/icon.ico",     # 아이콘 (있을 경우)
        "main.py"
    ]

    print(f"\n🚀 빌드 시작...\n")

    result = subprocess.run(cmd, cwd=os.path.dirname(os.path.abspath(__file__)))

    if result.returncode == 0:
        exe_path = os.path.join("dist", "OutLookAnyFinder.exe")
        if os.path.exists(exe_path):
            size_mb = os.path.getsize(exe_path) / (1024 * 1024)
            print(f"\n{'=' * 60}")
            print(f"✅ 빌드 성공!")
            print(f"📁 파일: {exe_path}")
            print(f"📦 크기: {size_mb:.1f}MB")
            print(f"{'=' * 60}")
        else:
            print(f"\n✅ 빌드 완료 (dist/ 폴더 확인)")
    else:
        print(f"\n❌ 빌드 실패 (종료 코드: {result.returncode})")
        print("  위의 에러 메시지를 확인하세요.")


if __name__ == "__main__":
    build()

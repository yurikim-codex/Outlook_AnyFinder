"""
OutLook AnyFinder Ver0.9 for SESUNG Team
사내 배포용 .exe 빌드 스크립트

권장 사용법:
    python build_exe.py

기본 결과:
    release/OutLookAnyFinder_v0.9_YYYYMMDD_HHMM.zip

옵션:
    python build_exe.py --onefile   # 단일 exe 방식
"""

import argparse
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent
VERSION = "0.9"


def run(cmd, **kwargs):
    print(" ".join(str(c) for c in cmd))
    subprocess.check_call(cmd, cwd=ROOT, **kwargs)


def ensure_pip():
    """현재 Python 실행환경에 pip가 없으면 ensurepip로 복구를 시도한다."""
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "--version"],
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return
    except Exception:
        print("⚠️ 현재 Python 환경에 pip가 없습니다. ensurepip 복구를 시도합니다...")

    try:
        run([sys.executable, "-m", "ensurepip", "--upgrade"])
    except Exception as e:
        raise SystemExit(
            "\n❌ pip를 사용할 수 없습니다.\n"
            f"현재 Python: {sys.executable}\n\n"
            "해결 방법:\n"
            "  1) PowerShell에서 py -3 --version 으로 일반 Python이 잡히는지 확인\n"
            "  2) py -3 -m ensurepip --upgrade 실행\n"
            "  3) py -3 build_exe.py 실행\n\n"
            "또는 python.org에서 Python을 설치하고 'Add python.exe to PATH'를 체크하세요.\n"
        ) from e


def ensure_pyinstaller():
    ensure_pip()
    try:
        import PyInstaller  # noqa
        print(f"✅ PyInstaller {PyInstaller.__version__}")
    except Exception:
        print("📦 PyInstaller 설치 중...")
        run([sys.executable, "-m", "pip", "install", "pyinstaller"])


def ensure_requirements():
    ensure_pip()
    print("📦 requirements 설치/확인 중...")
    run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])


def clean():
    for name in ["build", "dist"]:
        p = ROOT / name
        if p.exists():
            shutil.rmtree(p)


def build_onedir():
    run([sys.executable, "-m", "PyInstaller", "--clean", "OutLookAnyFinder.spec"])
    return ROOT / "dist" / "OutLookAnyFinder"


def build_onefile():
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--windowed",
        "--name", "OutLookAnyFinder",
        "--clean",
        "--version-file", "version_info.txt",
        "--hidden-import", "pythoncom",
        "--hidden-import", "pywintypes",
        "--hidden-import", "win32timezone",
        "--hidden-import", "win32com",
        "--hidden-import", "win32com.client",
        "--hidden-import", "bs4",
        "--collect-submodules", "win32com",
        "--collect-data", "win32com",
        "--collect-binaries", "pywin32_system32",
        "main.py",
    ]
    run(cmd)
    return ROOT / "dist" / "OutLookAnyFinder.exe"


def make_release(built_path: Path, onefile: bool):
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    release_root = ROOT / "release"
    package_dir = release_root / f"OutLookAnyFinder_v{VERSION}_{stamp}"
    release_root.mkdir(exist_ok=True)
    if package_dir.exists():
        shutil.rmtree(package_dir)
    package_dir.mkdir(parents=True)

    if onefile:
        shutil.copy2(built_path, package_dir / "OutLookAnyFinder.exe")
    else:
        shutil.copytree(built_path, package_dir / "OutLookAnyFinder")

    docs = ROOT / "release_docs"
    for doc in ["README_사내배포.txt", "실행_가이드.txt", "문제해결_가이드.txt", "배포담당자_체크리스트.txt"]:
        shutil.copy2(docs / doc, package_dir / doc)

    zip_base = release_root / package_dir.name
    zip_path = shutil.make_archive(str(zip_base), "zip", package_dir)
    return package_dir, Path(zip_path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--onefile", action="store_true", help="단일 exe로 빌드")
    args = parser.parse_args()

    print("=" * 70)
    print("🔨 OutLook AnyFinder 사내 배포 패키지 빌드")
    print("=" * 70)

    ensure_pyinstaller()
    ensure_requirements()
    clean()

    built = build_onefile() if args.onefile else build_onedir()
    if not built.exists():
        raise SystemExit(f"❌ 빌드 결과를 찾을 수 없습니다: {built}")

    package_dir, zip_path = make_release(built, args.onefile)
    print("=" * 70)
    print("✅ 배포 패키지 생성 완료")
    print(f"📁 폴더: {package_dir}")
    print(f"📦 ZIP : {zip_path}")
    print("=" * 70)


if __name__ == "__main__":
    main()

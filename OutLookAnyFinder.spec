# -*- mode: python ; coding: utf-8 -*-
"""
OutLook AnyFinder 사내 배포용 PyInstaller spec

권장 빌드 방식: onedir
결과물: dist/OutLookAnyFinder/OutLookAnyFinder.exe

빌드:
    pyinstaller --clean OutLookAnyFinder.spec
"""

from PyInstaller.utils.hooks import collect_submodules, collect_dynamic_libs, collect_data_files

block_cipher = None

hiddenimports = []
hiddenimports += collect_submodules('win32com')
hiddenimports += [
    'pythoncom',
    'pywintypes',
    'win32timezone',
    'win32com.client',
    'PyQt6',
    'PyQt6.QtCore',
    'PyQt6.QtGui',
    'PyQt6.QtWidgets',
    'bs4',
]

# 소스 폴더는 import로 포함되지만, 내부 배포 안정성을 위해 함께 수집합니다.
datas = [
    ('ui', 'ui'),
    ('core', 'core'),
    ('data', 'data'),
    ('utils', 'utils'),
    ('workers', 'workers'),
]

# pywin32 COM DLL이 누락되면 배포본에서 Outlook 동기화가 Mock처럼 보이거나 실패할 수 있습니다.
binaries = []
try:
    binaries += collect_dynamic_libs('pywin32_system32')
except Exception:
    pass
try:
    datas += collect_data_files('win32com')
except Exception:
    pass

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'pytest',
        'tests',
        'tkinter',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='OutLookAnyFinder',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version='version_info.txt',
    # icon='resources/icon.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='OutLookAnyFinder',
)

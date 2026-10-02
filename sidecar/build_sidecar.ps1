<#
.SYNOPSIS
    OutLook AnyFinder Python Sidecar 빌드 스크립트 (PyInstaller --onedir)

.DESCRIPTION
    MIGRATION_PLAN.md §5 리스크 3 대응:
      - --onefile 금지 (콜드 스타트 3~5초, 백신 오탐) → --onedir 사용
      - --console 필수 (windowed 모드에서 stdout/stderr가 None이 되는 문제 방지)
        창 숨김은 Rust 쪽 CREATE_NO_WINDOW 플래그로 처리한다.
      - 빌드 결과는 src-tauri\resources\sidecar\ 로 복사된다
        (externalBin 대신 리소스 디렉터리 방식 — DocuFinder bundle-kordoc 패턴)

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File sidecar\build_sidecar.ps1
    powershell -ExecutionPolicy Bypass -File sidecar\build_sidecar.ps1 -SkipCopy
#>

param(
    [string]$Python = "py -3",
    [switch]$SkipCopy,
    [switch]$NoClean
)

$ErrorActionPreference = "Stop"

$SidecarDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $SidecarDir
$DistDir = Join-Path $ProjectRoot "dist\OutlookAnyFinderSidecar"
$TauriResources = Join-Path $ProjectRoot "src-tauri\resources\sidecar"

Set-Location $ProjectRoot

Write-Host "=== OutLook AnyFinder Sidecar Build ===" -ForegroundColor Cyan
Write-Host "Project root : $ProjectRoot"

# 1) PyInstaller 확인/설치
$pyinstallerCheck = & $Python.Split(" ")[0] $Python.Split(" ")[1..($Python.Split(" ").Length-1)] -m PyInstaller --version 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing PyInstaller..." -ForegroundColor Yellow
    Invoke-Expression "$Python -m pip install pyinstaller"
}

# 2) 빌드 (--onedir + --console)
$cleanFlag = if ($NoClean) { @() } else { @("--clean") }
Write-Host "Building sidecar (onedir)..." -ForegroundColor Yellow

$pyiArgs = @(
    "-m", "PyInstaller",
    "--noconfirm"
) + $cleanFlag + @(
    "--onedir",
    "--console",
    "--name", "OutlookAnyFinderSidecar",
    "--paths", $ProjectRoot,
    "--hidden-import", "pythoncom",
    "--hidden-import", "pywintypes",
    "--hidden-import", "win32timezone",
    "--hidden-import", "win32com",
    "--hidden-import", "win32com.client",
    "--hidden-import", "bs4",
    "--collect-submodules", "win32com",
    "--collect-data", "win32com",
    "--collect-binaries", "pywin32_system32",
    "--exclude-module", "PyQt6",
    "--exclude-module", "pytest",
    (Join-Path $SidecarDir "__main__.py")
)

Invoke-Expression "$Python $($pyiArgs | ForEach-Object { if ($_ -match '\s') { '\"' + $_ + '\"' } else { $_ } })"
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed" }

if (-not (Test-Path $DistDir)) { throw "Build output not found: $DistDir" }

$exePath = Join-Path $DistDir "OutlookAnyFinderSidecar.exe"
$sizeMB = [math]::Round((Get-ChildItem $DistDir -Recurse | Measure-Object Length -Sum).Sum / 1MB, 1)
Write-Host "Build OK: $exePath ($sizeMB MB)" -ForegroundColor Green

# 3) Tauri 리소스로 복사
if (-not $SkipCopy) {
    if (Test-Path $TauriResources) { Remove-Item $TauriResources -Recurse -Force }
    New-Item -ItemType Directory -Force -Path $TauriResources | Out-Null
    Copy-Item -Path (Join-Path $DistDir "*") -Destination $TauriResources -Recurse -Force
    Write-Host "Copied to: $TauriResources" -ForegroundColor Green
} else {
    Write-Host "Skipped copy to src-tauri (-SkipCopy)" -ForegroundColor Yellow
}

# 4) 스모크 테스트 (빌드된 exe로 doctor 실행)
Write-Host "Running smoke test with built exe..." -ForegroundColor Yellow
& $exePath --mock --version
if ($LASTEXITCODE -eq 0) {
    Write-Host "Smoke test OK" -ForegroundColor Green
} else {
    Write-Host "WARNING: smoke test failed (exit $LASTEXITCODE)" -ForegroundColor Red
}

Write-Host "=== Done ===" -ForegroundColor Cyan

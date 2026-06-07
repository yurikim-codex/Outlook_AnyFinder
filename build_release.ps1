<#
OutLook AnyFinder 사내 배포용 빌드 스크립트

실행 위치: 프로젝트 루트
실행 예:
    powershell -ExecutionPolicy Bypass -File .\build_release.ps1

결과:
    release\OutLookAnyFinder_v0.9.1_YYYYMMDD_HHMM.zip
#>

param(
    [string]$Version = "0.9.1",
    [switch]$OneFile
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "OutLook AnyFinder 사내 배포 패키지 빌드" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

function Ensure-PipPackage($PackageName, $ImportName = $PackageName) {
    try {
        python -c "import $ImportName" 2>$null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "OK: $PackageName" -ForegroundColor Green
            return
        }
    } catch {}
    Write-Host "Installing: $PackageName" -ForegroundColor Yellow
    python -m pip install $PackageName
}

Ensure-PipPackage "pyinstaller" "PyInstaller"

Write-Host "Installing project requirements..." -ForegroundColor Yellow
python -m pip install -r requirements.txt

Write-Host "Cleaning previous build artifacts..." -ForegroundColor Yellow
Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue

if ($OneFile) {
    Write-Host "Building onefile exe..." -ForegroundColor Yellow
    python -m PyInstaller `
        --name OutLookAnyFinder `
        --windowed `
        --onefile `
        --clean `
        --version-file version_info.txt `
        --hidden-import pythoncom `
        --hidden-import pywintypes `
        --hidden-import win32timezone `
        --hidden-import win32com `
        --hidden-import win32com.client `
        --hidden-import bs4 `
        main.py
    $BuiltPath = Join-Path $ProjectRoot "dist\OutLookAnyFinder.exe"
} else {
    Write-Host "Building onedir package using OutLookAnyFinder.spec..." -ForegroundColor Yellow
    python -m PyInstaller --clean OutLookAnyFinder.spec
    $BuiltPath = Join-Path $ProjectRoot "dist\OutLookAnyFinder"
}

if (!(Test-Path $BuiltPath)) {
    throw "Build output not found: $BuiltPath"
}

$Stamp = Get-Date -Format "yyyyMMdd_HHmm"
$ReleaseRoot = Join-Path $ProjectRoot "release"
$PackageName = "OutLookAnyFinder_v$Version`_$Stamp"
$PackageDir = Join-Path $ReleaseRoot $PackageName

Write-Host "Creating release package: $PackageDir" -ForegroundColor Yellow
Remove-Item -Recurse -Force $PackageDir -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $PackageDir | Out-Null

if ($OneFile) {
    Copy-Item $BuiltPath (Join-Path $PackageDir "OutLookAnyFinder.exe") -Force
} else {
    Copy-Item $BuiltPath (Join-Path $PackageDir "OutLookAnyFinder") -Recurse -Force
}

Copy-Item "release_docs\README_사내배포.txt" $PackageDir -Force
Copy-Item "release_docs\실행_가이드.txt" $PackageDir -Force
Copy-Item "release_docs\문제해결_가이드.txt" $PackageDir -Force
Copy-Item "release_docs\배포담당자_체크리스트.txt" $PackageDir -Force

$ZipPath = Join-Path $ReleaseRoot "$PackageName.zip"
Remove-Item -Force $ZipPath -ErrorAction SilentlyContinue
Compress-Archive -Path (Join-Path $PackageDir "*") -DestinationPath $ZipPath -Force

Write-Host "============================================================" -ForegroundColor Green
Write-Host "Build completed" -ForegroundColor Green
Write-Host "Package folder: $PackageDir" -ForegroundColor Green
Write-Host "Zip package   : $ZipPath" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green

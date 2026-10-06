<#
.SYNOPSIS
  OutLook AnyFinder — React+Tauri 판에서 legacy PyQt6 판으로 즉시 롤백 (Phase 4-6).
.DESCRIPTION
  데이터(DB/설정/북마크)는 신구 버전이 같은 파일·스키마를 공유하므로
  롤백 = 프로세스 중지 + legacy 빌드 실행 뿐이다. 전/후 무결성 검사를 자동 수행한다.
.NOTES
  - 신버전 설치본(NSIS) 제거는 별개: 설정>앱 또는 uninstaller 사용 (데이터는 유지됨).
  - -SkipBuild : 기존 dist\OutLookAnyFinder 빌드를 재사용.
#>
param(
  [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $Script:MyInvocation.MyCommand.Path | Split-Path -Parent

Write-Host "==> 1/5 신버전 프로세스 중지" -ForegroundColor Cyan
Get-Process -Name "OutlookAnyFinderSidecar" -ErrorAction SilentlyContinue | Stop-Process -Force
Get-Process | Where-Object { $_.MainWindowTitle -like "*OutLook AnyFinder*" } | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1

Write-Host "==> 2/5 롤백 전 데이터 무결성 검사" -ForegroundColor Cyan
python (Join-Path $Root "tools\rollback_check.py")
if ($LASTEXITCODE -ne 0) { throw "데이터 무결성 검사 실패 — 롤백을 중단합니다" }

if (-not $SkipBuild) {
  Write-Host "==> 3/5 legacy PyQt6 빌드 (build_exe.py)" -ForegroundColor Cyan
  Push-Location $Root
  try { python build_exe.py } finally { Pop-Location }
  if ($LASTEXITCODE -ne 0) { throw "legacy 빌드 실패" }
} else {
  Write-Host "==> 3/5 기존 빌드 재사용 (-SkipBuild)" -ForegroundColor Cyan
}

$legacyExe = Join-Path $Root "dist\OutLookAnyFinder\OutLookAnyFinder.exe"
if (-not (Test-Path $legacyExe)) { throw "legacy 실행파일 없음: $legacyExe" }

Write-Host "==> 4/5 legacy 기동" -ForegroundColor Cyan
Start-Process $legacyExe

Write-Host "==> 5/5 롤백 후 데이터 무결성 재확인" -ForegroundColor Cyan
python (Join-Path $Root "tools\rollback_check.py")
if ($LASTEXITCODE -ne 0) { throw "롤백 후 데이터 검사 실패 — 수동 확인 필요" }

Write-Host "`n롤백 완료 — legacy PyQt6 판이 실행 중입니다. 데이터는 그대로입니다." -ForegroundColor Green

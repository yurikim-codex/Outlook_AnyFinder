<#
.SYNOPSIS
  빌드 산출물 코드 서명 (Phase 5-5). signtool(Windows SDK) 필요.
.DESCRIPTION
  대상:
    1) src-tauri\resources\sidecar\OutlookAnyFinderSidecar.exe  (사이드카 — 백신 오탐 저감 핵심)
    2) src-tauri\target\release\OutLook AnyFinder.exe            (Tauri 셸)
    3) src-tauri\target\release\bundle\nsis\*.exe                (NSIS 설치본 — 마지막에 서명)
  순서 중요: 내포된 바이너리(사이드카) → 셸 → 설치본 순으로 서명해야 설치본 해시에 모두 포함된다.
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File tools\sign.ps1
  powershell -ExecutionPolicy Bypass -File tools\sign.ps1 -Pfx C:\keys\commercial.pfx -PasswordFile C:\keys\pw.txt
#>
param(
    [string]$Pfx = "tools\certs\sesung-codesign.pfx",
    [string]$Password = "sesung123",
    [string]$Timestamp = "http://timestamp.sectigo.com"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $Script:MyInvocation.MyCommand.Path | Split-Path -Parent
Set-Location $Root

if (-not (Test-Path $Pfx)) { throw "PFX 없음: $Pfx — 먼저 tools\create-cert.ps1 실행" }

# signtool 탐색 (Windows SDK)
$signtool = Get-Command signtool -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source
if (-not $signtool) {
    $candidate = Get-ChildItem "C:\Program Files (x86)\Windows Kits\10\bin\*\x64\signtool.exe" -ErrorAction SilentlyContinue | Select-Object -Last 1
    if (-not $candidate) { throw "signtool 없음 — Windows SDK 설치 필요" }
    $signtool = $candidate.FullName
}

$targets = @()
$sidecar = "src-tauri\resources\sidecar\OutlookAnyFinderSidecar.exe"
$appExe  = "src-tauri\target\release\OutLook AnyFinder.exe"
if (Test-Path $sidecar) { $targets += $sidecar }
if (Test-Path $appExe)  { $targets += $appExe }
$nsis = Get-ChildItem "src-tauri\target\release\bundle\nsis\*.exe" -ErrorAction SilentlyContinue
if ($nsis) { $targets += $nsis.FullName }

if ($targets.Count -eq 0) { throw "서명할 파일 없음 — 먼저 build_sidecar.ps1 / npm run build 실행" }

foreach ($t in $targets) {
    Write-Host "서명: $t" -ForegroundColor Cyan
    & $signtool sign /f $Pfx /p $Password /fd SHA256 /tr $Timestamp /td SHA256 /v $t
    if ($LASTEXITCODE -ne 0) { throw "서명 실패: $t" }
    & $signtool verify /pa /v $t
}

Write-Host "✔ 서명 완료 ($($targets.Count)개 파일)" -ForegroundColor Green

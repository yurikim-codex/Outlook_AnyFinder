<#
.SYNOPSIS
  tauri build signCommand 래퍼 — 빌드 중 각 바이너리/설치본을 1개씩 서명 (Phase 5-5).
.DESCRIPTION
  tauri.conf.json bundle.windows.signCommand 가 파일 1개(%1)씩 넘긴다.
  빌드 내부에서 서명되므로 업데이터 latest.json/.sig 와 해시 일관성이 보장된다.

  인증서 없음(개발 빌드) → 경고만 하고 exit 0 (서명 없이 빌드 진행).
  환경변수: SIGN_PFX, SIGN_PASSWORD (기본: tools\certs\sesung-codesign.pfx / sesung123)
#>
param([Parameter(Position = 0)][string]$Target)

$ErrorActionPreference = "Continue"   # native stderr가 Stop을 만나면 스크립트 즉사 (PS 5.1 함정)
$Root = Split-Path -Parent $Script:MyInvocation.MyCommand.Path | Split-Path -Parent

$pfx = $env:SIGN_PFX
if (-not $pfx) { $pfx = Join-Path $Root "tools\certs\sesung-codesign.pfx" }
$password = $env:SIGN_PASSWORD
if (-not $password) { $password = "sesung123" }
$timestamp = $env:SIGN_TIMESTAMP
if (-not $timestamp) { $timestamp = "http://timestamp.sectigo.com" }

if (-not (Test-Path $pfx)) {
    Write-Host "[sign-one] SKIP (인증서 없음): $Target" -ForegroundColor Yellow
    exit 0
}

$signtool = Get-Command signtool -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source
if (-not $signtool) {
    $candidate = Get-ChildItem "C:\Program Files (x86)\Windows Kits\10\bin\*\x64\signtool.exe" -ErrorAction SilentlyContinue | Select-Object -Last 1
    if (-not $candidate) {
        Write-Host "[sign-one] SKIP (signtool 없음): $Target" -ForegroundColor Yellow
        exit 0
    }
    $signtool = $candidate.FullName
}

# tauri 번들러는 signCommand 출력을 캡처해 실패 시 "failed to run powershell"만
# 보여준다 — 실 진단은 %TEMP%\anyfinder-sign-one.log 에 남긴다 (Track B 실측 5호).
$logFile = Join-Path $env:TEMP "anyfinder-sign-one.log"
"[$(Get-Date -Format s)] Target=$Target pfx=$pfx signtool=$signtool" | Add-Content -Path $logFile -Encoding UTF8

& $signtool sign /f $pfx /p $password /fd SHA256 /tr $timestamp /td SHA256 $Target 2>&1 |
  ForEach-Object { "$_" } | Tee-Object -FilePath $logFile -Append
if ($LASTEXITCODE -ne 0) {
  # 타임스탬프 서버(외부망) 차단 환경 대응: 자체서명 사내 배포는 타임스탬프 없이도 유효
  Write-Host "[sign-one] 타임스탬프 서명 실패 → /tr 없이 재시도" -ForegroundColor Yellow
  "[$(Get-Date -Format s)] retry without timestamp (prev exit=$LASTEXITCODE)" | Add-Content -Path $logFile -Encoding UTF8
  & $signtool sign /f $pfx /p $password /fd SHA256 $Target 2>&1 |
    ForEach-Object { "$_" } | Tee-Object -FilePath $logFile -Append
}
if ($LASTEXITCODE -ne 0) {
    Write-Host "[sign-one] 서명 실패: $Target" -ForegroundColor Red
    "[$(Get-Date -Format s)] FAILED exit=$LASTEXITCODE" | Add-Content -Path $logFile -Encoding UTF8
    exit 1
}
Write-Host "[sign-one] ✔ $Target" -ForegroundColor Green
"[$(Get-Date -Format s)] OK" | Add-Content -Path $logFile -Encoding UTF8
exit 0

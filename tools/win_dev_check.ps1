<#
.SYNOPSIS
  Windows 개발 머신 원샷 검증 — Track B(런북 Step 0~3 보조) 게이트를 한 번에.

.DESCRIPTION
  순서: 0) 의존성 부트스트랩(pytest/npm ci) 1) pytest(계약 감사 포함)
        2) 프런트 tsc+build 3) 브리지+Vite 기동
        4) smoke 5) UI 시나리오 14+1종 6) IPC 런타임 프로브 7) (옵션) cargo test
        8) (옵션) 캡처  → 종료 후 요약표. 실패 항목이 있으면 exit 1.

  Rust(cargo test)는 스파이크 A 관문이라 기본 포함(--skip-cargo 로 제외).
  실 Outlook 연동(S12/S18/S19/S20)은 이 스크립트 범위가 아님 — 런북 Step 4 참고.

.PARAMETER SkipCargo
  cargo test 생략 (Rust 미설치 머신용)

.PARAMETER Capture
  UI 캡처(screenshots/)까지 실행

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File tools\win_dev_check.ps1
  powershell -ExecutionPolicy Bypass -File tools\win_dev_check.ps1 -SkipCargo -Capture
#>
param(
  [switch]$SkipCargo,
  [switch]$Capture
)

# PS 5.1 함정 주의: native 명령(npm/cargo/git)의 stderr는 EAP=Stop + 2>&1 조합에서
# NativeCommandError로 스크립트 전체를 중단시킨다. 각 단계는 종료코드/HTTP 프로브로
# 판정하므로 EAP는 Continue로 두고 실패는 Add-Result로 기록한다.
$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$results = @()
function Add-Result($name, $ok, $note = "") {
  $script:results += [pscustomobject]@{ Name = $name; OK = $ok; Note = $note }
  $mark = if ($ok) { "PASS" } else { "FAIL" }
  Write-Host ("[{0}] {1} {2}" -f $mark, $name, $note)
}

# python 해석기: 프로젝트 venv 우선
$Py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) { $Py = "python" }

# 0) 의존성 부트스트랩 (fresh clone 대응 — Track B 실측 2호)
Write-Host "`n== 0/7 의존성 부트스트랩 =="
& $Py -m pytest --version 1>$null 2>$null
if ($LASTEXITCODE -ne 0) {
  Write-Host "pytest 없음 → pip install pytest"
  & $Py -m pip install --quiet pytest 2>&1 | Select-Object -Last 1
  & $Py -m pytest --version 1>$null 2>$null
}
Add-Result "pytest 준비" ($LASTEXITCODE -eq 0)

Push-Location frontend
if (-not (Test-Path node_modules)) {
  # fresh clone: tsc/vite/jsdom 전부 여기 들어 있음. 없으면 npx가 엉뚱한
  # tsc@2.x 가짜 패키지를 받아 실패한다 (Track B 실측 2호).
  Write-Host "frontend/node_modules 없음 → npm ci (1~3분)"
  npm ci 2>&1 | Select-Object -Last 3
  Add-Result "npm ci" ($LASTEXITCODE -eq 0)
} else {
  Add-Result "npm 의존성" $true "node_modules 존재"
}
Pop-Location

# 1) pytest (계약 감사 포함)
Write-Host "`n== 1/7 pytest =="
& $Py -m pytest -q 2>&1 | Select-Object -Last 3
Add-Result "pytest" ($LASTEXITCODE -eq 0)

# 2) 프런트 타입체크 + 빌드
Write-Host "`n== 2/7 tsc + build =="
Push-Location frontend
npx tsc --noEmit
Add-Result "tsc --noEmit" ($LASTEXITCODE -eq 0)
npm run build 2>&1 | Select-Object -Last 1
Add-Result "vite build" ($LASTEXITCODE -eq 0)
Pop-Location

# 3) 브리지 + Vite 기동
Write-Host "`n== 3/7 bridge + vite =="
$bridgeOut = Join-Path $env:TEMP "anyfinder-bridge.out.log"
$bridgeErr = Join-Path $env:TEMP "anyfinder-bridge.err.log"
$viteOut = Join-Path $env:TEMP "anyfinder-vite.out.log"
$viteErr = Join-Path $env:TEMP "anyfinder-vite.err.log"
$bridgeProc = Start-Process -FilePath $Py -ArgumentList "frontend\dev_bridge.py" -WorkingDirectory $Root -RedirectStandardOutput $bridgeOut -RedirectStandardError $bridgeErr -PassThru -WindowStyle Hidden
$viteProc = Start-Process -FilePath "cmd.exe" -ArgumentList "/c", "npm run dev --prefix frontend" -WorkingDirectory $Root -RedirectStandardOutput $viteOut -RedirectStandardError $viteErr -PassThru -WindowStyle Hidden

function Wait-Http($url, $sec) {
  $deadline = (Get-Date).AddSeconds($sec)
  while ((Get-Date) -lt $deadline) {
    try { $null = Invoke-RestMethod -Uri $url -TimeoutSec 2; return $true } catch { Start-Sleep -Milliseconds 500 }
  }
  return $false
}
$bridgeUp = Wait-Http "http://127.0.0.1:8765/health" 30
$viteUp = Wait-Http "http://127.0.0.1:5173/" 60
Add-Result "bridge up" $bridgeUp
Add-Result "vite up" $viteUp

try {
  # 4) smoke
  Write-Host "`n== 4/7 smoke =="
  if ($bridgeUp -and $viteUp) {
    Push-Location frontend
    node smoke.mjs 2>&1 | Select-Object -Last 2
    Add-Result "smoke" ($LASTEXITCODE -eq 0)
    Pop-Location
  } else { Add-Result "smoke" $false "서버 미기동" }

  # 5) UI 시나리오
  Write-Host "`n== 5/7 scenarios =="
  if ($bridgeUp -and $viteUp) {
    Push-Location frontend
    npm run scenarios 2>&1 | Select-Object -Last 6
    Add-Result "scenarios(14+1)" ($LASTEXITCODE -eq 0)
    Pop-Location
  } else { Add-Result "scenarios" $false "서버 미기동" }

  # 6) IPC 프로브
  Write-Host "`n== 6/7 contract probe =="
  if ($bridgeUp) {
    & $Py tools\contract_probe.py 2>&1 | Select-Object -Last 2
    Add-Result "contract_probe" ($LASTEXITCODE -eq 0)
  } else { Add-Result "contract_probe" $false "브리지 미기동" }

  # 6.5) 캡처(옵션)
  if ($Capture -and $bridgeUp -and $viteUp) {
    Write-Host "`n== 6.5 capture =="
    Push-Location frontend
    npm run capture 2>&1 | Select-Object -Last 2
    Add-Result "capture" ($LASTEXITCODE -eq 0)
    Pop-Location
  }
}
finally {
  # 7) cargo test (스파이크 A)
  Write-Host "`n== 7/7 cargo test =="
  if (-not $SkipCargo) {
    $cargo = Get-Command cargo -ErrorAction SilentlyContinue
    if ($cargo) {
      Push-Location src-tauri
      cargo test 2>&1 | Select-Object -Last 5
      Add-Result "cargo test" ($LASTEXITCODE -eq 0)
      Pop-Location
    } else {
      Add-Result "cargo test" $false "cargo 없음 (-SkipCargo 권장)"
    }
  } else {
    Add-Result "cargo test" $true "skip"
  }

  # 정리
  foreach ($p in @($bridgeProc, $viteProc)) {
    try {
      if ($p -and -not $p.HasExited) { taskkill /PID $p.Id /T /F 2>$null | Out-Null }
    } catch { }
  }
}

Write-Host "`n================ 요약 ================"
$results | Format-Table -AutoSize | Out-String | Write-Host
$failed = @($results | Where-Object { -not $_.OK })
if ($failed.Count -gt 0) {
  Write-Host ("FAIL {0}건: {1}" -f $failed.Count, ($failed.Name -join ", "))
  exit 1
}
Write-Host "WIN_DEV_CHECK_OK — 모든 게이트 통과"
exit 0

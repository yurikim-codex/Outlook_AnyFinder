<#
.SYNOPSIS
  Track B 사전 준비물 점검 — Git / Node / Python / Rust(+MSVC) / WebView2 설치 여부·버전 확인.

.DESCRIPTION
 各项目 최소 요구:
    - Git for Windows   : 아무 최신 버전
    - Node.js           : 20 이상
    - Python            : 3.11 이상 (3.11~3.12 권장)
    - Rust              : rustup + stable (cargo)
    - MSVC 빌드 도구    : Rust/Tauri 링크에 필요 (VS Build Tools C++ 워크로드)
    - WebView2          : Tauri 런타임 (Win10/11 기본 탑재)

  부족 항목은 winget 설치 명령을 함께 출력한다. 전부 OK면 exit 0, 아니면 exit 1.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File tools\check_env.ps1
#>

$ErrorActionPreference = "SilentlyContinue"
$rows = @()

function Add-Row($name, $state, $ver, $hint) {
  $script:rows += [pscustomobject]@{ Tool = $name; State = $state; Version = $ver; Hint = $hint }
}

function Ver-Of($raw, $pattern) {
  if ($raw -match $pattern) { return [int]$Matches[1] }
  return -1
}

# ── Git ─
$gitRaw = (git --version 2>$null) | Select-Object -First 1
if ($gitRaw -match "git version (\d+)\.(\d+)") {
  Add-Row "Git" "OK" $gitRaw.Trim() ""
} else {
  Add-Row "Git" "MISSING" "-" "winget install Git.Git"
}

# ── Node ─
$nodeRaw = (node --version 2>$null) | Select-Object -First 1
$nodeMajor = Ver-Of $nodeRaw '^v(\d+)'
if ($nodeMajor -ge 20) {
  Add-Row "Node" "OK" $nodeRaw.Trim() ""
} elseif ($nodeMajor -ge 0) {
  Add-Row "Node" "OLD" $nodeRaw.Trim() "winget install OpenJS.NodeJS.LTS"
} else {
  Add-Row "Node" "MISSING" "-" "winget install OpenJS.NodeJS.LTS"
}

# ── Python ──
$pyRaw = $null
foreach ($cc in @(@("python", "--version"), @("py", "-3", "--version"))) {
  $t = (& $cc[0] @($cc[1..($cc.Length - 1)]) 2>$null) | Select-Object -First 1
  if ($t -match "Python (\d+)\.(\d+)") { $pyRaw = $t; break }
}
if ($pyRaw -match "Python (\d+)\.(\d+)") {
  $major = [int]$Matches[1]; $minor = [int]$Matches[2]
  if ($major -gt 3 -or ($major -eq 3 -and $minor -ge 11)) {
    Add-Row "Python" "OK" $pyRaw.Trim() ""
  } else {
    Add-Row "Python" "OLD" $pyRaw.Trim() "winget install Python.Python.3.11"
  }
} else {
  Add-Row "Python" "MISSING" "-" "winget install Python.Python.3.11"
}

# ── Rust (rustup + cargo) ──
$rustupRaw = (rustup --version 2>$null) | Select-Object -First 1
$cargoRaw = (cargo --version 2>$null) | Select-Object -First 1
if ($rustupRaw -and $cargoRaw) {
  Add-Row "Rust" "OK" ($cargoRaw.Trim() -replace "cargo ", "") ""
} elseif ($cargoRaw) {
  Add-Row "Rust" "OK(no-rustup)" ($cargoRaw.Trim() -replace "cargo ", "") "rustup 권장: winget install Rustlang.Rustup"
} else {
  Add-Row "Rust" "MISSING" "-" "winget install Rustlang.Rustup"
}

# ── MSVC 빌드 도구 (C++ 워크로드) ──
$vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
$msvc = $false
if (Test-Path $vswhere) {
  $inst = & $vswhere -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
  if ($inst) { $msvc = $true }
}
if ($msvc) {
  Add-Row "MSVC BuildTools" "OK" "VC++ workload" ""
} else {
  Add-Row "MSVC BuildTools" "MISSING" "-" "winget install Microsoft.VisualStudio.2022.BuildTools --override `"--add Microsoft.VisualStudio.Workload.VCTools --includeRecommended --passive`""
}

# ── WebView2 ──
$wv2 = Get-ItemProperty "HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" -ErrorAction SilentlyContinue
if (-not $wv2) { $wv2 = Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" -ErrorAction SilentlyContinue }
if ($wv2 -and $wv2.pv) {
  Add-Row "WebView2" "OK" $wv2.pv ""
} else {
  Add-Row "WebView2" "MISSING" "-" "winget install Microsoft.EdgeWebView2Runtime (Win10/11은 보통 기본 탑재)"
}

# ── 요약 ──
Write-Host ""
$rows | Format-Table -AutoSize | Out-String | Write-Host
$bad = @($rows | Where-Object { $_.State -eq "MISSING" -or $_.State -eq "OLD" })
if ($bad.Count -gt 0) {
  Write-Host "== 설치 명령 (관리자 터미널 권장) =="
  $bad | ForEach-Object { Write-Host ("  # {0}`n  {1}`n" -f $_.Tool, $_.Hint) }
  Write-Host "설치 후 터미널을 새로 열고 이 스크립트를 재실행하세요."
  exit 1
}
Write-Host "CHECK_ENV_OK — Track B 준비물 완비. 다음: powershell -File tools\win_dev_check.ps1"
exit 0

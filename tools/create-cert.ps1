<#
.SYNOPSIS
  사내 코드 서명용 자기서명 인증서 생성 (Phase 5-5, DocuFinder create-cert.ps1 패턴).
.DESCRIPTION
  - CurrentUser 스토어에 CodeSigning 인증서 생성 + PFX/CER 내보내기
  - CER는 클린 VM/동료 PC에 설치하면 SmartScreen/Defender 신뢰 경로에 도움
  - ★ 사내 배포용입니다. 대외 배포 시 상용 코드서명 인증서로 교체하세요 (RELEASE.md)
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File tools\create-cert.ps1
  powershell -ExecutionPolicy Bypass -File tools\create-cert.ps1 -Password "other-pw"
#>
param(
    [string]$OutDir = "tools\certs",
    [string]$Password = "sesung123",
    [int]$Years = 3,
    [string]$Subject = "CN=SESUNG Team Code Signing, O=SESUNG, C=KR"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $Script:MyInvocation.MyCommand.Path | Split-Path -Parent
Set-Location $Root

$out = Join-Path $Root $OutDir
New-Item -ItemType Directory -Force -Path $out | Out-Null

$existing = Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert | Where-Object { $_.Subject -eq $Subject } | Select-Object -First 1
if ($existing) {
    Write-Host "기존 인증서 재사용: $($existing.Thumbprint)" -ForegroundColor Yellow
    $cert = $existing
} else {
    Write-Host "코드 서명 인증서 생성 중…" -ForegroundColor Cyan
    $cert = New-SelfSignedCertificate `
        -Type CodeSigningCert `
        -Subject $Subject `
        -CertStoreLocation "Cert:\CurrentUser\My" `
        -NotAfter (Get-Date).AddYears($Years) `
        -KeyUsage DigitalSignature `
        -TextExtension @("2.5.29.37={text}1.3.6.1.5.5.7.3.3")
}

$sec = ConvertTo-SecureString -String $Password -Force -AsPlainText
$pfx = Join-Path $out "sesung-codesign.pfx"
$cer = Join-Path $out "sesung-codesign.cer"
Export-PfxCertificate -Cert $cert -FilePath $pfx -Password $sec | Out-Null
Export-Certificate -Cert $cert -FilePath $cer | Out-Null

Write-Host "✔ PFX: $pfx (비밀번호: $Password)" -ForegroundColor Green
Write-Host "✔ CER: $cer (대상 PC의 신뢰된 루트/게시자 저장소에 설치)" -ForegroundColor Green
Write-Host "다음: tools\sign.ps1 로 실행파일 서명" -ForegroundColor Cyan

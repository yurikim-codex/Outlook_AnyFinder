; OutLook AnyFinder NSIS 커스텀 훅 (Phase 5-3)
; tauri.conf.json bundle.windows.nsis.installerHooks 에서 참조.
;
; 목적:
;  1) 설치/제거 전 실행 중인 프로세스 종료 — 파일 잠금·좀비 프로세스 0건 (완료 기준)
;  2) 제거 시 사용자 데이터(~\.outlook_anyfinder) 보존 — 롤백/재설치 가능(ROLLBACK.md)

!macro NSIS_HOOK_PREINSTALL
  DetailPrint "실행 중인 OutLook AnyFinder 프로세스를 종료합니다..."
  nsExec::ExecToLog 'taskkill /IM OutlookAnyFinderSidecar.exe /F'
  nsExec::ExecToLog 'taskkill /IM "OutLook AnyFinder.exe" /F'
  Sleep 500
!macroend

!macro NSIS_HOOK_PREUNINSTALL
  DetailPrint "실행 중인 OutLook AnyFinder 프로세스를 종료합니다..."
  nsExec::ExecToLog 'taskkill /IM OutlookAnyFinderSidecar.exe /F'
  nsExec::ExecToLog 'taskkill /IM "OutLook AnyFinder.exe" /F'
  Sleep 500
!macroend

!macro NSIS_HOOK_POSTUNINSTALL
  ; 데이터는 의도적으로 지우지 않는다 (DB/설정/북마크 보존)
  DetailPrint "사용자 데이터(%USERPROFILE%\.outlook_anyfinder)는 보존되었습니다."
!macroend

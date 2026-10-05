//! 프론트엔드(TS)에 노출하는 Tauri 명령들.
//!
//! ★ 설계 결정 (MIGRATION_PLAN 부록 C 참고):
//! 계획서는 commands/{search,mail,index,sync,system}.rs의 "타입 명시 래퍼"를 제시했으나,
//! IPC 계약(sidecar/README.md)이 이미 단일 진실 공급원이고 파라미터가 자주 진화하므로
//! Rust 쪽은 **제네릭 패스스루 1개(sidecar_request)** 로 통일하고,
//! 타입 안정성은 TypeScript 쪽(Phase 3에서 정의)에서 확보한다.
//! 이로써 Rust 코드 변경 없이 사이드카 명령 추가가 가능해진다 (42→N 확장 비용 0).

use serde_json::Value;
use tauri::AppHandle;

use crate::error::CommandError;
use crate::logging;
use crate::sidecar::{SidecarHandle, REQUEST_TIMEOUT, SIDECAR_STATUS_EVENT};
use std::sync::Arc;
use tauri::Emitter;

/// 사이드카 임의 명령 호출 — {"ok":true,"result":..} 또는 {"ok":false,"error":{code,message,..}}
/// 그대로 반환한다. 해석(예외 던지기)은 TS 래퍼가 담당.
#[tauri::command]
pub async fn sidecar_request(
    handle: tauri::State<'_, Arc<SidecarHandle>>,
    cmd: String,
    params: Value,
) -> Result<Value, CommandError> {
    let params = if params.is_null() { Value::Object(Default::default()) } else { params };
    match handle.request(&cmd, params, REQUEST_TIMEOUT).await {
        Ok(response) => Ok(response),
        // 전송 계층 실패 — 사이드카 자체 오류 포맷과 동일한 모양으로 내려준다
        Err(app_err) => {
            let ce: CommandError = app_err.into();
            handle.log(&format!("sidecar_request({cmd}) 전송 실패: {}", ce.message));
            Err(ce)
        }
    }
}

/// 사이드카 상태 조회 (ready/running/restarts)
#[tauri::command]
pub fn sidecar_status(handle: tauri::State<'_, Arc<SidecarHandle>>) -> Value {
    handle.status_payload()
}

/// 수동 재시작 (설정 화면 "사이드카 재시작")
#[tauri::command]
pub fn sidecar_restart(
    app: AppHandle,
    handle: tauri::State<'_, Arc<SidecarHandle>>,
) -> Result<(), CommandError> {
    logging::log(&app, "사용자 요청으로 사이드카 재시작");
    handle.kill_child();
    handle.spawn().map_err(|e| {
        let _ = app.emit(
            SIDECAR_STATUS_EVENT,
            serde_json::json!({"state": "restart_failed", "detail": e}),
        );
        CommandError {
            code: "SPAWN_FAILED".into(),
            message: e,
        }
    })
}

/// 프론트엔드 로그를 desktop.log로 수신 (사용자 환경 문제 추적)
#[tauri::command]
pub fn frontend_log(app: AppHandle, message: String) {
    logging::log_frontend(&app, &message);
}

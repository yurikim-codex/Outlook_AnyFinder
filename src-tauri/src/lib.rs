//! OutLook AnyFinder — Tauri 2 Rust 코어.
//!
//! 역할(MIGRATION_PLAN Phase 2): 사이드카 프로세스 관리 + IPC 중계 + 윈도우/트레이.
//! ★ 비즈니스 로직은 전부 Python 사이드카에 있다 — 여기서 SQL/검색/Outlook COM 금지.

mod commands;
mod error;
mod logging;
mod protocol;
mod sidecar;
mod tray;

use std::sync::Arc;

use tauri::Manager;
use tauri_plugin_single_instance;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        // 단일 인스턴스 — 두 번째 실행 시 기존 창 집중 (반드시 첫 번째 플러그인)
        .plugin(single_instance::init(|app, _args, _cwd| {
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.show();
                let _ = window.unminimize();
                let _ = window.set_focus();
            }
        }))
        // 창 크기/위치 기억
        .plugin(tauri_plugin_window_state::Builder::default().build())
        .setup(|app| {
            let handle = app.handle().clone();
            logging::init(&handle);
            logging::log(&handle, "OutLook AnyFinder (Tauri 2) 시작");

            // ★ 사이드카 spawn을 창 표시와 병렬로 — 기동 직렬 대기 금지 (리스크 5)
            sidecar::SidecarHandle::init(&handle);

            tray::create_tray(&handle)?;
            Ok(())
        })
        // 닫기 = 트레이로 숨김 (트레이 "종료"가 실제 종료 — Phase 2-7 패턴)
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                if window.label() == "main" {
                    api.prevent_close();
                    let _ = window.hide();
                }
            }
        })
        .invoke_handler(tauri::generate_handler![
            commands::sidecar_request,
            commands::sidecar_status,
            commands::sidecar_restart,
            commands::frontend_log,
        ])
        .build(tauri::generate_context!())
        .expect("Tauri 애플리케이션 빌드 실패")
        .run(|app_handle, event| {
            // 앱 종료 시 사이드카 graceful shutdown — 좀비 프로세스 0건 (Phase 2-8)
            if let tauri::RunEvent::Exit = event {
                if let Some(handle) = app_handle.try_state::<Arc<sidecar::SidecarHandle>>() {
                    handle.shutdown_blocking();
                }
            }
        });
}

//! 시스템 트레이 (Phase 2-7 최소 버전: 열기 / 지금 동기화 / 종료)
//!
//! "지금 동기화"는 실제 작업을 Rust에서 수행하지 않고 —
//! `tray://sync` 이벤트를 프런트로 브로드캐스트해 React가 사이드카 sync.run을 호출한다.
//! (비즈니스 로직은 언제나 Python — MIGRATION_PLAN 아키텍처 원칙)

use tauri::menu::{Menu, MenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Emitter, Manager};

use crate::logging;

pub const TRAY_SYNC_EVENT: &str = "tray://sync";

pub fn create_tray(app: &AppHandle) -> tauri::Result<()> {
    let open_item = MenuItem::with_id(app, "open", "열기", true, None::<&str>)?;
    let sync_item = MenuItem::with_id(app, "sync", "지금 동기화", true, None::<&str>)?;
    let quit_item = MenuItem::with_id(app, "quit", "종료", true, None::<&str>)?;
    let menu = Menu::with_items(app, &[&open_item, &sync_item, &quit_item])?;

    let handle = app.clone();
    TrayIconBuilder::with_id("main-tray")
        .tooltip("OutLook AnyFinder")
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_menu_event(move |app, event| {
            match event.id.as_ref() {
                "open" => show_main_window(app),
                "sync" => {
                    logging::log(app, "트레이: 지금 동기화 → 프런트로 이벤트 브리지");
                    let _ = app.emit(TRAY_SYNC_EVENT, ());
                    show_main_window(app);
                }
                "quit" => {
                    logging::log(app, "트레이: 종료 요청");
                    app.exit(0); // RunEvent::Exit에서 사이드카 정리 수행
                }
                _ => {}
            }
            let _ = &handle;
        })
        .on_tray_icon_event(|tray, event| {
            // 좌클릭 = 창 열기
            if let TrayIconEvent::Click {
                button: MouseButton::Left,
                button_state: MouseButtonState::Up,
                ..
            } = event
            {
                show_main_window(tray.app_handle());
            }
        })
        .build(app)?;
    Ok(())
}

fn show_main_window(app: &AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.show();
        let _ = window.unminimize();
        let _ = window.set_focus();
    }
}

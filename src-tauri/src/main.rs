//! Windows 배포 빌드 엔트리 — 콘솔 창 방지.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    outlook_anyfinder_lib::run();
}

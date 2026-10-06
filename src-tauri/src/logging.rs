//! 최소 파일 로깅 — {앱 로그 디렉터리}/desktop.log
//!
//! MIGRATION_PLAN Phase 2-3: 로깅·크래시 리포트 파일 위치.
//! 사이드카의 logs/sidecar.log와 나란히 두어 문제 추적을 쌍으로 맞춘다.
//! (간결성을 위해 tauri-plugin-log 대신 std 구현 — 로테이션 5MB×1백업)

use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::sync::Mutex;

use tauri::{AppHandle, Manager};

static LOG_PATH: Mutex<Option<PathBuf>> = Mutex::new(None);
const MAX_SIZE: u64 = 5 * 1024 * 1024;

/// 앱 setup에서 1회 초기화.
pub fn init(app: &AppHandle) {
    let path = log_dir(app).join("desktop.log");
    if let Some(parent) = path.parent() {
        let _ = fs::create_dir_all(parent);
    }
    *LOG_PATH.lock().unwrap() = Some(path);
}

pub fn log_dir(app: &AppHandle) -> PathBuf {
    app.path()
        .app_log_dir()
        .unwrap_or_else(|_| PathBuf::from("logs"))
}

/// UNIX epoch 초 — chrono 의존 없이 로그 순서 보장용
fn timestamp() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0)
}

fn append(target: &str, line: &str) {
    let guard = LOG_PATH.lock().unwrap();
    let Some(path) = guard.as_ref() else {
        eprintln!("[{target}] {line}");
        return;
    };
    rotate_if_needed(path);
    if let Ok(mut file) = fs::OpenOptions::new().create(true).append(true).open(path) {
        let _ = writeln!(file, "[{}] [{target}] {line}", timestamp());
    }
}

fn rotate_if_needed(path: &Path) {
    if let Ok(meta) = fs::metadata(path) {
        if meta.len() > MAX_SIZE {
            let backup = path.with_extension("log.1");
            let _ = fs::remove_file(&backup);
            let _ = fs::rename(path, &backup);
        }
    }
}

/// Rust 코어 로그
pub fn log(_app: &AppHandle, line: &str) {
    append("core", line);
}

/// 사이드카 stderr 전달 로그
pub fn log_sidecar(_app: &AppHandle, line: &str) {
    append("sidecar", line);
}

/// 프론트엔드 console 전달 로그 (devtools 없이 사용자 문제 파악용)
pub fn log_frontend(_app: &AppHandle, line: &str) {
    append("frontend", line);
}

//! Python 사이드카 프로세스 생명주기 + JSON Lines IPC 중계.
//!
//! MIGRATION_PLAN.md Phase 2 (2-2, 2-4, 2-6, 2-8):
//! - spawn: CREATE_NO_WINDOW + CREATE_NEW_PROCESS_GROUP (Windows)
//! - reader 스레드: 라인 단위 방어 파싱 → 응답(id 매칭) / 이벤트(emit)
//! - health-check: 15초 주기 system.ping, 3회 연속 실패 시 자동 재시작 (최대 5회)
//! - 종료: system.shutdown → 3초 대기 → CTRL_BREAK_EVENT → kill 폴백 (좀비 0건)
//!
//! ★ Rust는 프로세스 관리 + IPC 중계만 담당한다. 비즈니스 로직/SQL 재구현 금지.

use std::collections::HashMap;
use std::io::{BufRead, BufReader, Write};
use std::path::PathBuf;
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::atomic::{AtomicBool, AtomicU32, AtomicU64, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use serde_json::{json, Value};
use tauri::{AppHandle, Emitter, Manager};
use tokio::sync::oneshot;

use crate::error::AppError;
use crate::logging;
use crate::protocol::{self, Incoming};

/// 사이드카가 보낸 이벤트(ready/sync.progress/...)를 프론트로 브리지하는 Tauri 이벤트명
pub const SIDECAR_EVENT: &str = "sidecar://event";
/// 사이드카 상태 변화(기동/준비/재시작/치명오류) 알림 이벤트명
pub const SIDECAR_STATUS_EVENT: &str = "sidecar://status";

/// 일반 요청 기본 타임아웃 — sync.plan/index.build 같은 장기 작업 포함
pub const REQUEST_TIMEOUT: Duration = Duration::from_secs(300);
const HEALTH_INTERVAL: Duration = Duration::from_secs(15);
const HEALTH_TIMEOUT: Duration = Duration::from_secs(5);
const MAX_RESTARTS: u32 = 5;

pub struct SidecarHandle {
    inner: Arc<Inner>,
}

struct Inner {
    app: AppHandle,
    child: Mutex<Option<Child>>,
    stdin: Mutex<Option<ChildStdin>>,
    pending: Mutex<HashMap<u64, oneshot::Sender<Value>>>,
    next_id: AtomicU64,
    ready: AtomicBool,
    shutting_down: AtomicBool,
    restarts: AtomicU32,
    health_fails: AtomicU32,
}

impl SidecarHandle {
    /// 앱 기동 시 1회 호출 — 상태 등록 + 사이드카 spawn + 헬스 모니터 시작.
    /// 창 표시와 "동시에" spawn한다 (리스크 5: 직렬 대기 금지 — 기동 체감 속도).
    pub fn init(app: &AppHandle) -> Arc<SidecarHandle> {
        let handle = Arc::new(SidecarHandle {
            inner: Arc::new(Inner {
                app: app.clone(),
                child: Mutex::new(None),
                stdin: Mutex::new(None),
                pending: Mutex::new(HashMap::new()),
                next_id: AtomicU64::new(1),
                ready: AtomicBool::new(false),
                shutting_down: AtomicBool::new(false),
                restarts: AtomicU32::new(0),
                health_fails: AtomicU32::new(0),
            }),
        });
        app.manage(handle.clone());

        // 기동 스레드: setup()을 블로킹하지 않는다
        let boot = handle.clone();
        std::thread::spawn(move || {
            if let Err(e) = boot.spawn() {
                logging::log(&boot.inner.app, &format!("사이드카 기동 실패: {e}"));
                boot.emit_status("spawn_failed", Some(&e.to_string()));
            }
        });

        // 헬스 모니터 스레드
        let monitor = handle.clone();
        std::thread::spawn(move || monitor.health_loop());

        handle
    }

    // ── spawn / 재시작 ──

    pub fn spawn(&self) -> Result<(), String> {
        let inner = &self.inner;
        let (program, args, cwd) = resolve_sidecar_command(&inner.app);
        logging::log(
            &inner.app,
            &format!("사이드카 spawn: {} {:?} (cwd={:?})", program.display(), args, cwd),
        );

        let mut cmd = Command::new(&program);
        cmd.args(&args)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            // ★ 환경변수 UTF-8는 이중 안전장치일 뿐 — 사이드카 스스로 강제한다
            .env("PYTHONUTF8", "1")
            .env("PYTHONIOENCODING", "utf-8");
        if let Some(dir) = &cwd {
            cmd.current_dir(dir);
        }
        apply_platform_flags(&mut cmd);

        let mut child = cmd.spawn().map_err(|e| format!("spawn 실패: {e}"))?;
        let stdout = child.stdout.take().ok_or("stdout 파이프 없음")?;
        let stderr = child.stderr.take().ok_or("stderr 파이프 없음")?;
        let stdin = child.stdin.take().ok_or("stdin 파이프 없음")?;

        *inner.child.lock().unwrap() = Some(child);
        *inner.stdin.lock().unwrap() = Some(stdin);
        inner.ready.store(false, Ordering::SeqCst);

        // stdout reader 스레드 — JSON Lines 방어 파싱 + id 매칭 + 이벤트 브리지
        let reader_inner = inner.clone();
        std::thread::Builder::new()
            .name("sidecar-reader".into())
            .spawn(move || reader_loop(reader_inner, stdout))
            .map_err(|e| format!("reader 스레드 실패: {e}"))?;

        // stderr drain 스레드 — 사이드카 로그를 파일로 (파이프 버퍼 블로킹 방지)
        let log_app = inner.app.clone();
        std::thread::Builder::new()
            .name("sidecar-stderr".into())
            .spawn(move || {
                let reader = BufReader::new(stderr);
                for line in reader.lines() {
                    match line {
                        Ok(text) if !text.trim().is_empty() => {
                            logging::log_sidecar(&log_app, &text)
                        }
                        Ok(_) => {}
                        Err(_) => break,
                    }
                }
            })
            .map_err(|e| format!("stderr 스레드 실패: {e}"))?;

        self.emit_status("spawned", None);
        Ok(())
    }

    fn restart(&self, reason: &str) {
        if self.inner.shutting_down.load(Ordering::SeqCst) {
            return;
        }
        let count = self.inner.restarts.fetch_add(1, Ordering::SeqCst) + 1;
        logging::log(&self.inner.app, &format!("사이드카 재시작 {count}/{MAX_RESTARTS}: {reason}"));
        if count > MAX_RESTARTS {
            self.emit_status(
                "fatal",
                Some(&format!("사이드카가 반복 종료되어 자동 재시작을 중단합니다 ({reason})")),
            );
            return;
        }
        self.kill_child();
        self.emit_status("restarting", Some(reason));
        if let Err(e) = self.spawn() {
            logging::log(&self.inner.app, &format!("재시작 실패: {e}"));
            self.emit_status("restart_failed", Some(&e.to_string()));
        }
    }

    /// 코어 로그 편의 메서드
    pub fn log(&self, msg: &str) {
        logging::log(&self.inner.app, msg);
    }

    pub fn app(&self) -> &AppHandle {
        &self.inner.app
    }

    pub fn kill_child(&self) {
        self.inner.ready.store(false, Ordering::SeqCst);
        *self.inner.stdin.lock().unwrap() = None;
        let mut child_opt = self.inner.child.lock().unwrap();
        if let Some(mut child) = child_opt.take() {
            let _ = child.kill();
            let _ = child.wait();
        }
        // 대기 중인 요청 전부 실패 처리
        let mut pending = self.inner.pending.lock().unwrap();
        pending.clear(); // Sender drop → 수신측은 RecvError로 실패 처리됨
    }

    // ── 요청/응답 ──

    /// 비동기 요청 — 프론트엔드 invoke("sidecar_request")가 사용.
    pub async fn request(
        &self,
        cmd: &str,
        params: Value,
        timeout: Duration,
    ) -> Result<Value, AppError> {
        let inner = &self.inner;
        if inner.shutting_down.load(Ordering::SeqCst) {
            return Err(AppError::SidecarNotRunning);
        }
        let id = inner.next_id.fetch_add(1, Ordering::SeqCst);
        let (tx, rx) = oneshot::channel();

        // ★ 응답이 등록보다 먼저 오는 레이스 방지: 등록 → 쓰기 순서 고정
        inner.pending.lock().unwrap().insert(id, tx);

        let line = protocol::make_request(id, cmd, params);
        {
            let mut guard = inner.stdin.lock().unwrap();
            let stdin = guard.as_mut().ok_or(AppError::SidecarNotRunning)?;
            if let Err(e) = stdin.write_all(line.as_bytes()) {
                guard.take();
                inner.pending.lock().unwrap().remove(&id);
                return Err(AppError::Io(format!("stdin 쓰기 실패: {e}")));
            }
            if let Err(e) = stdin.write_all(b"\n") {
                guard.take();
                inner.pending.lock().unwrap().remove(&id);
                return Err(AppError::Io(format!("stdin 쓰기 실패: {e}")));
            }
            let _ = stdin.flush();
        }

        match tokio::time::timeout(timeout, rx).await {
            Ok(Ok(value)) => Ok(value),
            Ok(Err(_)) => Err(AppError::SidecarNotRunning), // sender dropped (재시작/종료)
            Err(_) => {
                inner.pending.lock().unwrap().remove(&id);
                Err(AppError::Timeout(timeout))
            }
        }
    }

    /// 동기(블로킹) 요청 — 헬스 모니터 등 비-async 스레드용.
    fn request_blocking(&self, cmd: &str, timeout: Duration) -> Result<Value, AppError> {
        let id = self.inner.next_id.fetch_add(1, Ordering::SeqCst);
        let (tx, rx) = oneshot::channel();
        self.inner.pending.lock().unwrap().insert(id, tx);

        let line = protocol::make_request(id, cmd, json!({}));
        {
            let mut guard = self.inner.stdin.lock().unwrap();
            let stdin = guard.as_mut().ok_or(AppError::SidecarNotRunning)?;
            if stdin.write_all(format!("{line}\n").as_bytes()).is_err() {
                guard.take();
                self.inner.pending.lock().unwrap().remove(&id);
                return Err(AppError::SidecarNotRunning);
            }
            let _ = stdin.flush();
        }

        // 타임아웃 포함 블로킹 대기 — 스레드를 무한정 묶지 않는다
        let deadline = Instant::now() + timeout;
        loop {
            match rx.try_recv() {
                Ok(value) => return Ok(value),
                Err(oneshot::error::TryRecvError::Empty) => {
                    if Instant::now() >= deadline {
                        self.inner.pending.lock().unwrap().remove(&id);
                        return Err(AppError::Timeout(timeout));
                    }
                    std::thread::sleep(Duration::from_millis(25));
                }
                Err(oneshot::error::TryRecvError::Closed) => {
                    return Err(AppError::SidecarNotRunning)
                }
            }
        }
    }

    // ── 헬스 모니터 ──

    fn health_loop(&self) {
        std::thread::sleep(Duration::from_secs(10)); // 기동 여유
        loop {
            std::thread::sleep(HEALTH_INTERVAL);
            if self.inner.shutting_down.load(Ordering::SeqCst) {
                break;
            }

            // 1) 프로세스 사망 여부
            let exited = {
                let mut guard = self.inner.child.lock().unwrap();
                match guard.as_mut() {
                    Some(child) => match child.try_wait() {
                        Ok(Some(status)) => {
                            logging::log(&self.inner.app, &format!("사이드카 종료 감지: {status}"));
                            true
                        }
                        Ok(None) => false,
                        Err(_) => true,
                    },
                    None => true,
                }
            };
            if exited {
                self.restart("프로세스 종료 감지");
                continue;
            }

            // 2) ready 전에는 ping 생략 (기동 중 오탐 방지)
            if !self.inner.ready.load(Ordering::SeqCst) {
                continue;
            }

            // 3) ping 건강 검사
            match self.request_blocking("system.ping", HEALTH_TIMEOUT) {
                Ok(v) if v.get("ok").and_then(Value::as_bool) == Some(true) => {
                    self.inner.health_fails.store(0, Ordering::SeqCst);
                }
                _ => {
                    let fails = self.inner.health_fails.fetch_add(1, Ordering::SeqCst) + 1;
                    logging::log(&self.inner.app, &format!("헬스체크 실패 {fails}/3"));
                    if fails >= 3 {
                        self.restart("헬스체크 3회 연속 실패");
                    }
                }
            }
        }
    }

    // ── 상태 브로드캐스트 ──

    pub fn status_payload(&self) -> Value {
        let running = self
            .inner
            .child
            .lock()
            .unwrap()
            .as_mut()
            .map(|c| matches!(c.try_wait(), Ok(None)))
            .unwrap_or(false);
        json!({
            "ready": self.inner.ready.load(Ordering::SeqCst),
            "running": running,
            "restarts": self.inner.restarts.load(Ordering::SeqCst),
        })
    }

    fn emit_status(&self, state: &str, detail: Option<&str>) {
        let mut payload = self.status_payload();
        if let Some(obj) = payload.as_object_mut() {
            obj.insert("state".into(), json!(state));
            if let Some(d) = detail {
                obj.insert("detail".into(), json!(d));
            }
        }
        let _ = self.inner.app.emit(SIDECAR_STATUS_EVENT, payload);
    }

    pub fn is_ready(&self) -> bool {
        self.inner.ready.load(Ordering::SeqCst)
    }

    // ── 정상 종료 (앱 Exit 이벤트에서 호출 — 좀비 프로세스 0건 보장) ──

    pub fn shutdown_blocking(&self) {
        if self.inner.shutting_down.swap(true, Ordering::SeqCst) {
            return; // 이미 종료 진행
        }
        logging::log(&self.inner.app, "앱 종료 — 사이드카 graceful shutdown 시작");

        // 1) system.shutdown 요청
        let requested = {
            let mut guard = self.inner.stdin.lock().unwrap();
            match guard.as_mut() {
                Some(stdin) => {
                    let id = self.inner.next_id.fetch_add(1, Ordering::SeqCst);
                    let line = protocol::make_request(id, "system.shutdown", json!({}));
                    stdin.write_all(format!("{line}\n").as_bytes()).is_ok()
                }
                None => false,
            }
        };

        // 2) 최대 3초 종료 대기
        if requested {
            let deadline = Instant::now() + Duration::from_secs(3);
            loop {
                let done = {
                    let mut guard = self.inner.child.lock().unwrap();
                    match guard.as_mut() {
                        Some(child) => matches!(child.try_wait(), Ok(Some(_))),
                        None => true,
                    }
                };
                if done || Instant::now() >= deadline {
                    break;
                }
                std::thread::sleep(Duration::from_millis(100));
            }
        }

        // 3) Windows 폴백: CTRL_BREAK_EVENT (SIGBREAK 핸들러가 정리 수행)
        #[cfg(windows)]
        {
            let still_alive = {
                let mut guard = self.inner.child.lock().unwrap();
                guard
                    .as_mut()
                    .map(|c| matches!(c.try_wait(), Ok(None)))
                    .unwrap_or(false)
            };
            if still_alive {
                if let Some(pid) = self.child_pid() {
                    send_ctrl_break(pid);
                    let deadline = Instant::now() + Duration::from_secs(2);
                    while Instant::now() < deadline {
                        let done = {
                            let mut guard = self.inner.child.lock().unwrap();
                            guard
                                .as_mut()
                                .map(|c| !matches!(c.try_wait(), Ok(None)))
                                .unwrap_or(true)
                        };
                        if done {
                            break;
                        }
                        std::thread::sleep(Duration::from_millis(100));
                    }
                }
            }
        }

        // 4) 최후 폴백: kill
        self.kill_child();
        logging::log(&self.inner.app, "사이드카 종료 완료");
    }

    fn child_pid(&self) -> Option<u32> {
        self.inner.child.lock().unwrap().as_ref().map(|c| c.id())
    }
}

// ── reader 스레드 ──

fn reader_loop(inner: Arc<Inner>, stdout: impl std::io::Read + Send + 'static) {
    let reader = BufReader::new(stdout);
    let app = inner.app.clone();
    for line in reader.lines() {
        let line = match line {
            Ok(l) => l,
            Err(e) => {
                logging::log(&app, &format!("사이드카 stdout 읽기 오류: {e}"));
                break;
            }
        };
        match protocol::parse_line(&line) {
            Incoming::Event(value) => {
                if value.get("event").and_then(Value::as_str) == Some("ready") {
                    inner.ready.store(true, Ordering::SeqCst);
                    inner.health_fails.store(0, Ordering::SeqCst);
                    logging::log(&app, "사이드카 ready — 검색 엔진 활성화");
                }
                let _ = app.emit(SIDECAR_EVENT, value);
            }
            Incoming::Response { id, message } => {
                let maybe_sender = inner.pending.lock().unwrap().remove(&id);
                if let Some(sender) = maybe_sender {
                    let _ = sender.send(message);
                } else {
                    logging::log(&app, &format!("대기자 없는 응답 수신 (id={id}) — 무시"));
                }
            }
            Incoming::Junk(text) => {
                // ★ 방어 파서: 파싱 실패 줄은 로그로 흘려보내고 계속 진행 (크래시 금지)
                if !text.is_empty() {
                    logging::log(&app, &format!("사이드카 비-JSON 줄 무시: {text}"));
                }
            }
        }
    }

    // EOF — 사이드카 stdout 종료(프로세스 죽음)
    inner.ready.store(false, Ordering::SeqCst);
    if !inner.shutting_down.load(Ordering::SeqCst) {
        logging::log(&app, "사이드카 stdout EOF — 재시작 검토");
        // 프로세스 실제 종료 확인 후 재시작 (헬스 루프와 중복 재시작 방지를 위해 즉시 검사)
        let exited = {
            let mut guard = inner.child.lock().unwrap();
            match guard.as_mut() {
                Some(child) => !matches!(child.try_wait(), Ok(None)),
                None => true,
            }
        };
        if exited {
            // Inner만으로는 SidecarHandle 메서드(restart)를 부를 수 없으므로
            // 헬스 루프가 다음 주기에 감지해 재시작한다. 즉각 복구가 필요하면 여기서 spawn:
            let handle = app.state::<Arc<SidecarHandle>>();
            handle.restart("stdout EOF (프로세스 종료)");
        }
    }
}

// ── 플랫폼별 spawn 플래그 ──

#[cfg(windows)]
fn apply_platform_flags(cmd: &mut Command) {
    use std::os::windows::process::CommandExt;
    const CREATE_NO_WINDOW: u32 = 0x0800_0000; // 콘솔 창 숨김 (리스크 3)
    const CREATE_NEW_PROCESS_GROUP: u32 = 0x0000_0200; // CTRL_BREAK_EVENT 대상 그룹
    cmd.creation_flags(CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP);
}

#[cfg(not(windows))]
fn apply_platform_flags(_cmd: &mut Command) {}

#[cfg(windows)]
fn send_ctrl_break(pid: u32) -> bool {
    use windows_sys::Win32::System::Console::{GenerateConsoleCtrlEvent, CTRL_BREAK_EVENT};
    let ok = unsafe { GenerateConsoleCtrlEvent(CTRL_BREAK_EVENT, pid) } != 0;
    if !ok {
        // 같은 그룹에 속하지 않은 프로세스에는 전달 실패할 수 있음 — kill 폴백이 처리
    }
    ok
}

// ── 사이드카 실행 파일 해석 ──

/// 실행 순서 (MIGRATION_PLAN 리스크 3 — 리소스 디렉터리 방식):
/// 1. ANYFINDER_SIDECAR_CMD 환경변수 (개발 오버라이드, 공백 구분)
/// 2. resource_dir()/resources/sidecar/OutlookAnyFinderSidecar(.exe) — 배포본
/// 3. {repo}/dist/OutlookAnyFinderSidecar/OutlookAnyFinderSidecar(.exe) — 로컬 빌드
/// 4. python -m sidecar (개발 폴백, cwd={repo})
fn resolve_sidecar_command(app: &AppHandle) -> (PathBuf, Vec<String>, Option<PathBuf>) {
    let exe_name = if cfg!(windows) {
        "OutlookAnyFinderSidecar.exe"
    } else {
        "OutlookAnyFinderSidecar"
    };

    // 1) 환경변수 오버라이드
    if let Some(cmd_line) = std::env::var_os("ANYFINDER_SIDECAR_CMD") {
        let parts: Vec<String> = cmd_line
            .to_string_lossy()
            .split_whitespace()
            .map(String::from)
            .collect();
        if let Some((first, rest)) = parts.split_first() {
            return (PathBuf::from(first), rest.to_vec(), Some(repo_root()));
        }
    }

    // 2) 번들 리소스 (배포본)
    if let Ok(resource_dir) = app.path().resource_dir() {
        let candidate = resource_dir.join("resources").join("sidecar").join(exe_name);
        if candidate.exists() {
            return (candidate, vec![], None);
        }
    }

    // 3) 로컬 PyInstaller 빌드 결과 (개발 머신)
    let local_build = repo_root().join("dist").join("OutlookAnyFinderSidecar").join(exe_name);
    if local_build.exists() {
        return (local_build, vec![], None);
    }

    // 4) Python 폴백 (개발) — Mock 여부는 ANYFINDER_MOCK 환경변수가 사이드카에서 처리
    if cfg!(windows) {
        return (
            PathBuf::from("py"),
            vec!["-3".into(), "-m".into(), "sidecar".into()],
            Some(repo_root()),
        );
    }
    (
        PathBuf::from("python3"),
        vec!["-m".into(), "sidecar".into()],
        Some(repo_root()),
    )
}

/// 개발 폴백용 저장소 루트 — 컴파일 시점 src-tauri/ 기준으로 결정.
fn repo_root() -> PathBuf {
    if let Ok(manifest) = std::env::var("CARGO_MANIFEST_DIR") {
        return PathBuf::from(manifest).join("..");
    }
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..")
}

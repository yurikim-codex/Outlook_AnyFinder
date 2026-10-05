//! 애플리케이션 오류 타입.

use serde::Serialize;

#[derive(Debug, thiserror::Error)]
pub enum AppError {
    #[error("사이드카가 실행 중이 아닙니다")]
    SidecarNotRunning,

    #[error("사이드카 IO 오류: {0}")]
    Io(String),

    #[error("사이드카 응답 시간 초과 ({0:?})")]
    Timeout(std::time::Duration),

    #[error("프로토콜 오류: {0}")]
    Protocol(String),

    #[error("사이드카 요청 실패: {0}")]
    Request(String),
}

/// 프론트엔드(TS)로 구조화되어 전달되는 명령 오류.
/// invoke() Promise rejection payload = { code, message }
#[derive(Debug, Serialize, Clone)]
pub struct CommandError {
    pub code: String,
    pub message: String,
}

impl From<AppError> for CommandError {
    fn from(e: AppError) -> Self {
        let code = match &e {
            AppError::SidecarNotRunning => "SIDECAR_NOT_RUNNING",
            AppError::Io(_) => "SIDECAR_IO",
            AppError::Timeout(_) => "SIDECAR_TIMEOUT",
            AppError::Protocol(_) => "PROTOCOL",
            AppError::Request(_) => "REQUEST_FAILED",
        };
        CommandError {
            code: code.to_string(),
            message: e.to_string(),
        }
    }
}

//! JSON Lines IPC 프로토콜 타입 (계약: sidecar/README.md §4).
//!
//! Request  : {"id":42,"cmd":"search.query","params":{...}}
//! Response : {"id":42,"ok":true,"result":{...}} | {"id":42,"ok":false,"error":{...}}
//! Event    : {"event":"sync.progress","data":{...}}

use serde_json::{json, Value};

/// 사이드카로 보낼 요청 라인 생성.
pub fn make_request(id: u64, cmd: &str, params: Value) -> String {
    let params = if params.is_null() { json!({}) } else { params };
    json!({ "id": id, "cmd": cmd, "params": params }).to_string()
}

/// 수신 라인 분류 결과.
#[derive(Debug)]
pub enum Incoming {
    /// {"event": ..., "data": ...}
    Event(Value),
    /// {"id": ..., "ok": ..., ...} — id 매칭 대기자에게 전달
    Response { id: u64, message: Value },
    /// 파싱 불가/형태 불명 — 로그 후 무시 (방어 파서, 크래시 금지)
    Junk(String),
}

/// 한 줄을 방어적으로 파싱한다. 어떤 입력에도 panic 하지 않는다.
pub fn parse_line(line: &str) -> Incoming {
    let trimmed = line.trim();
    if trimmed.is_empty() {
        return Incoming::Junk(String::new());
    }
    let value: Value = match serde_json::from_str(trimmed) {
        Ok(v) => v,
        Err(_) => return Incoming::Junk(trimmed.chars().take(200).collect()),
    };
    let obj = match value.as_object() {
        Some(o) => o,
        None => return Incoming::Junk(trimmed.chars().take(200).collect()),
    };

    // 이벤트: "event" 키가 있고 "ok"가 없는 객체
    if obj.contains_key("event") && !obj.contains_key("ok") {
        return Incoming::Event(value);
    }
    // 응답: 숫자 id + ok
    if let Some(id) = obj.get("id").and_then(Value::as_u64) {
        if obj.contains_key("ok") {
            return Incoming::Response { id, message: value };
        }
    }
    // id=null 오류 응답(PARSE_ERROR 등)은 이벤트성으로 취급
    if obj.get("id").map(Value::is_null).unwrap_or(false) && obj.contains_key("ok") {
        return Incoming::Event(value);
    }
    Incoming::Junk(trimmed.chars().take(200).collect())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_event() {
        match parse_line(r#"{"event":"ready","data":{"pid":1}}"#) {
            Incoming::Event(v) => assert_eq!(v["event"], "ready"),
            other => panic!("expected event, got {:?}", other),
        }
    }

    #[test]
    fn parse_response() {
        match parse_line(r#"{"id":42,"ok":true,"result":{"a":1}}"#) {
            Incoming::Response { id, message } => {
                assert_eq!(id, 42);
                assert_eq!(message["result"]["a"], 1);
            }
            other => panic!("expected response, got {:?}", other),
        }
    }

    #[test]
    fn parse_junk_never_panics() {
        for junk in ["", "   ", "not json {{{", "[1,2]", "\"str\"", "42", "\u{fffd}\u{fffd}"] {
            match parse_line(junk) {
                Incoming::Junk(_) | Incoming::Event(_) => {}
                other => panic!("unexpected: {:?} for {:?}", other, junk),
            }
        }
    }

    #[test]
    fn parse_null_id_error_is_event() {
        match parse_line(r#"{"id":null,"ok":false,"error":{"code":"PARSE_ERROR"}}"#) {
            Incoming::Event(_) => {}
            other => panic!("expected event, got {:?}", other),
        }
    }

    #[test]
    fn request_line_roundtrip() {
        let line = make_request(7, "search.query", json!({"query": "계약서"}));
        match parse_line(&line) {
            Incoming::Junk(_) => {}
            _ => panic!("request line should not parse as incoming"),
        }
        assert!(line.contains("\"id\":7"));
    }
}

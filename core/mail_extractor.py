"""
OutLook AnyFinder Ver0.9 for SESUNG Team
[M02] 메일 데이터 정제 & 변환

Outlook에서 추출한 raw dict → EmailRecord 변환
HTML 본문 → 평문 변환, 데이터 정제
"""

import logging
from typing import Optional

from data.models import EmailRecord
from utils.html_cleaner import strip_html

logger = logging.getLogger(__name__)


def extract_to_record(raw: dict) -> Optional[EmailRecord]:
    """
    Outlook 커넥터에서 반환한 raw dict를 EmailRecord로 변환

    Args:
        raw: OutlookConnector._extract_mail_data() 또는 MockOutlookConnector 반환값

    Returns:
        EmailRecord 또는 None (변환 실패 시)
    """
    try:
        entry_id = raw.get("entry_id", "")
        if not entry_id:
            logger.warning("entry_id가 없는 메일 건너뜀")
            return None

        # 본문 처리: HTML이 있으면 HTML→평문, 없으면 plain text
        body = raw.get("body_text", "")
        html_body = raw.get("html_body", "")
        if html_body:
            body = strip_html(html_body)
        elif body:
            body = _clean_plain_text(body)

        # 본문 길이 제한 (100KB 이상이면 트리밍)
        MAX_BODY_LENGTH = 100_000
        if len(body) > MAX_BODY_LENGTH:
            body = body[:MAX_BODY_LENGTH] + "\n... (본문이 길어 일부만 인덱싱됨)"

        return EmailRecord(
            entry_id=entry_id,
            subject=_clean_text(raw.get("subject", "")),
            sender_name=_clean_text(raw.get("sender_name", "")),
            sender_email=_clean_text(raw.get("sender_email", "")),
            recipients=_clean_text(raw.get("recipients", "")),
            cc=_clean_text(raw.get("cc", "")),
            body_text=body,
            folder_name=raw.get("folder_name", ""),
            received_at=raw.get("received_at", ""),
            sent_at=raw.get("sent_at", ""),
            has_attachments=int(raw.get("has_attachments", 0)),
            attachment_count=int(raw.get("attachment_count", 0)),
            attachment_names=_clean_text(raw.get("attachment_names", "")),
            attachment_types=_clean_text(raw.get("attachment_types", "")),
            importance=int(raw.get("importance", 1)),
            is_read=int(raw.get("is_read", 1)),
            categories=_clean_text(raw.get("categories", "")),
            conversation_id=raw.get("conversation_id", ""),
        )

    except Exception as e:
        logger.error(f"메일 변환 실패: {e}")
        return None


def _clean_text(text: str) -> str:
    """기본 텍스트 정제"""
    if not text:
        return ""
    # NULL 문자 제거
    text = text.replace("\x00", "")
    # 앞뒤 공백 제거
    text = text.strip()
    return text


def _clean_plain_text(text: str) -> str:
    """평문 본문 정제"""
    if not text:
        return ""
    import re
    text = text.replace("\x00", "")
    text = text.replace("\r\n", "\n")
    text = text.replace("\r", "\n")
    # 연속 빈 줄 정리
    text = re.sub(r'\n{4,}', '\n\n\n', text)
    return text.strip()

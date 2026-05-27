"""
OutLook AnyFinder Ver0.9 for SESUNG Team
[M11] 데이터 모델 정의
"""

from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime


@dataclass
class EmailRecord:
    """메일 한 건의 데이터 모델"""
    entry_id: str
    subject: str = ""
    sender_name: str = ""
    sender_email: str = ""
    recipients: str = ""
    cc: str = ""
    body_text: str = ""
    folder_name: str = ""
    received_at: str = ""
    sent_at: str = ""
    has_attachments: int = 0
    attachment_count: int = 0
    attachment_names: str = ""
    attachment_types: str = ""
    importance: int = 1          # 0=낮음, 1=보통, 2=높음
    is_read: int = 1
    categories: str = ""
    conversation_id: str = ""
    # DB에서 조회 시 추가되는 필드
    id: Optional[int] = None
    indexed_at: str = ""

    def to_insert_tuple(self) -> tuple:
        """INSERT용 튜플 반환"""
        return (
            self.entry_id, self.subject, self.sender_name, self.sender_email,
            self.recipients, self.cc, self.body_text, self.folder_name,
            self.received_at, self.sent_at,
            self.has_attachments, self.attachment_count,
            self.attachment_names, self.attachment_types,
            self.importance, self.is_read, self.categories, self.conversation_id
        )

    @staticmethod
    def insert_sql() -> str:
        return """
            INSERT OR IGNORE INTO emails (
                entry_id, subject, sender_name, sender_email,
                recipients, cc, body_text, folder_name,
                received_at, sent_at,
                has_attachments, attachment_count,
                attachment_names, attachment_types,
                importance, is_read, categories, conversation_id
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """

    @staticmethod
    def from_row(row) -> 'EmailRecord':
        """sqlite3.Row → EmailRecord 변환"""
        return EmailRecord(
            id=row["id"],
            entry_id=row["entry_id"],
            subject=row["subject"],
            sender_name=row["sender_name"],
            sender_email=row["sender_email"],
            recipients=row["recipients"],
            cc=row["cc"],
            body_text=row["body_text"],
            folder_name=row["folder_name"],
            received_at=row["received_at"] or "",
            sent_at=row["sent_at"] or "",
            has_attachments=row["has_attachments"],
            attachment_count=row["attachment_count"],
            attachment_names=row["attachment_names"],
            attachment_types=row["attachment_types"],
            importance=row["importance"],
            is_read=row["is_read"],
            categories=row["categories"],
            conversation_id=row["conversation_id"],
            indexed_at=row["indexed_at"] or "",
        )


@dataclass
class SearchResult:
    """검색 결과 한 건 (EmailRecord + 검색 메타)"""
    email: EmailRecord
    rank_score: float = 0.0
    title_snippet: str = ""
    body_snippet: str = ""


@dataclass
class Bookmark:
    """검색어 북마크"""
    id: Optional[int] = None
    name: str = ""
    query: str = ""
    filters: str = "{}"
    position: int = 0
    created_at: str = ""

    @staticmethod
    def from_row(row) -> 'Bookmark':
        return Bookmark(
            id=row["id"],
            name=row["name"],
            query=row["query"],
            filters=row["filters"],
            position=row["position"],
            created_at=row["created_at"] or "",
        )


@dataclass
class SearchHistoryItem:
    """검색 히스토리 항목 (자동완성용)"""
    id: Optional[int] = None
    keyword: str = ""
    search_count: int = 0
    last_searched_at: str = ""

    @staticmethod
    def from_row(row) -> 'SearchHistoryItem':
        return SearchHistoryItem(
            id=row["id"],
            keyword=row["keyword"],
            search_count=row["search_count"],
            last_searched_at=row["last_searched_at"] or "",
        )

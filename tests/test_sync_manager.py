"""
OutLook AnyFinder Ver0.9 for SESUNG Team
스마트 증분 동기화 테스트 — SyncManager / SyncPlan / SyncResult
"""

import pytest
import tempfile
from pathlib import Path
from copy import deepcopy

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from data.database import init_db, get_email_count, set_meta
from core.outlook_connector import MockOutlookConnector, OlDefaultFolders
from core.index_builder import IndexBuilder
from core.sync_manager import MockSyncManager, SyncPlan


@pytest.fixture
def env():
    """Mock 데이터로 최초 인덱싱 완료된 환경"""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    conn = init_db(db_path)

    mock = MockOutlookConnector()
    mock.connect()

    # 최초 전체 인덱싱
    builder = IndexBuilder(conn)
    inbox = list(mock.iter_mails(OlDefaultFolders.INBOX))
    sent = list(mock.iter_mails(OlDefaultFolders.SENT))
    all_mails = inbox + sent
    builder.build_from_iterator(iter(all_mails), len(all_mails))

    sm = MockSyncManager(conn, mock)

    yield {
        "conn": conn, "mock": mock, "sm": sm,
        "total": len(all_mails),
        "inbox_count": len(inbox),
    }

    conn.close()
    db_path.unlink(missing_ok=True)


class TestSyncPlan:

    def test_01_no_changes_plan(self, env):
        """변경 없으면 has_changes=False, 전체 스킵"""
        plan = env["sm"].create_plan(folder_ids=[6, 5])

        assert plan.has_changes is False
        assert plan.skipped_count == env["total"]
        assert len(plan.new_ids) == 0
        assert len(plan.updated_ids) == 0
        assert len(plan.deleted_ids) == 0

    def test_02_no_changes_summary(self, env):
        """변경 없을 때 요약 메시지"""
        plan = env["sm"].create_plan(folder_ids=[6, 5])
        summary = plan.changes_summary
        assert "스킵" in summary
        assert "변경 없음" not in summary  # 스킵 건수가 있으므로

    def test_03_new_mail_detected(self, env):
        """새 메일이 추가되면 new_ids에 포함"""
        # Mock에 새 메일 추가
        env["mock"]._sample_emails.append({
            "entry_id": "NEW_MAIL_001",
            "subject": "완전히 새로운 메일",
            "sender_name": "신규발신자",
            "sender_email": "new@test.com",
            "recipients": "나",
            "cc": "",
            "body_text": "새 메일 본문입니다.",
            "html_body": "",
            "folder_name": "받은편지함",
            "received_at": "2026-05-28 10:00:00",
            "sent_at": "2026-05-28 09:59:00",
            "has_attachments": 0,
            "attachment_count": 0,
            "attachment_names": "",
            "attachment_types": "",
            "importance": 1,
            "is_read": 0,
            "categories": "",
            "conversation_id": "NEW_CONV",
        })

        plan = env["sm"].create_plan(folder_ids=[6, 5])

        assert "NEW_MAIL_001" in plan.new_ids
        assert plan.has_changes is True

    def test_04_deleted_mail_detected(self, env):
        """Outlook에서 삭제된 메일이 deleted_ids에 포함"""
        # Mock에서 메일 하나 제거
        removed = env["mock"]._sample_emails.pop(0)
        removed_eid = removed["entry_id"]

        plan = env["sm"].create_plan(folder_ids=[6, 5])

        assert removed_eid in plan.deleted_ids
        assert plan.has_changes is True

    def test_05_plan_total_counts(self, env):
        """total_outlook, total_db 정확"""
        plan = env["sm"].create_plan(folder_ids=[6, 5])
        assert plan.total_outlook == env["total"]
        assert plan.total_db == env["total"]


class TestSyncExecution:

    def test_06_execute_no_changes(self, env):
        """변경 없을 때 execute하면 모두 스킵"""
        plan = env["sm"].create_plan(folder_ids=[6, 5])
        result = env["sm"].execute_plan(plan, folder_ids=[6, 5])

        assert result.added == 0
        assert result.updated == 0
        assert result.deleted == 0
        assert result.skipped == env["total"]
        assert result.errors == 0

    def test_07_execute_add_new(self, env):
        """새 메일 추가 실행"""
        env["mock"]._sample_emails.append({
            "entry_id": "EXEC_NEW_001",
            "subject": "실행 테스트 새 메일",
            "sender_name": "테스터",
            "sender_email": "test@test.com",
            "recipients": "나",
            "cc": "",
            "body_text": "실행 테스트 본문",
            "html_body": "",
            "folder_name": "받은편지함",
            "received_at": "2026-05-28 11:00:00",
            "sent_at": "2026-05-28 11:00:00",
            "has_attachments": 0,
            "attachment_count": 0,
            "attachment_names": "",
            "attachment_types": "",
            "importance": 1,
            "is_read": 1,
            "categories": "",
            "conversation_id": "EXEC_CONV",
        })

        plan = env["sm"].create_plan(folder_ids=[6, 5])
        assert len(plan.new_ids) == 1

        before = get_email_count(env["conn"])
        result = env["sm"].execute_plan(plan, folder_ids=[6, 5])
        after = get_email_count(env["conn"])

        assert result.added == 1
        assert after == before + 1

        # 검색 가능 확인
        rows = env["conn"].execute(
            "SELECT rowid FROM emails_fts WHERE emails_fts MATCH '실행 테스트'"
        ).fetchall()
        assert len(rows) >= 1

    def test_08_execute_delete(self, env):
        """삭제된 메일 DB에서 제거"""
        removed = env["mock"]._sample_emails.pop(0)

        plan = env["sm"].create_plan(folder_ids=[6, 5])
        assert len(plan.deleted_ids) == 1

        before = get_email_count(env["conn"])
        result = env["sm"].execute_plan(plan, folder_ids=[6, 5])
        after = get_email_count(env["conn"])

        assert result.deleted == 1
        assert after == before - 1

    def test_09_execute_with_stop(self, env):
        """실행 중 중단"""
        # 여러 개 새 메일 추가
        for i in range(5):
            env["mock"]._sample_emails.append({
                "entry_id": f"STOP_TEST_{i:03d}",
                "subject": f"중단 테스트 {i}",
                "sender_name": "테스터",
                "sender_email": "test@test.com",
                "recipients": "나", "cc": "",
                "body_text": f"중단 테스트 본문 {i}",
                "html_body": "",
                "folder_name": "받은편지함",
                "received_at": f"2026-05-28 1{i}:00:00",
                "sent_at": f"2026-05-28 1{i}:00:00",
                "has_attachments": 0, "attachment_count": 0,
                "attachment_names": "", "attachment_types": "",
                "importance": 1, "is_read": 1,
                "categories": "", "conversation_id": f"STOP_{i}",
            })

        plan = env["sm"].create_plan(folder_ids=[6, 5])

        call_count = [0]
        def should_stop():
            call_count[0] += 1
            return call_count[0] > 2

        result = env["sm"].execute_plan(plan, folder_ids=[6, 5], should_stop=should_stop)
        # 중단되었으므로 전부 추가되지 않았을 수 있음
        assert result.added <= 5

    def test_10_sync_meta_updated(self, env):
        """동기화 후 sync_meta 갱신"""
        from data.database import get_meta

        env["mock"]._sample_emails.append({
            "entry_id": "META_TEST_001",
            "subject": "메타 테스트",
            "sender_name": "테스터",
            "sender_email": "test@test.com",
            "recipients": "나", "cc": "",
            "body_text": "메타 테스트 본문",
            "html_body": "",
            "folder_name": "받은편지함",
            "received_at": "2026-05-28 12:00:00",
            "sent_at": "2026-05-28 12:00:00",
            "has_attachments": 0, "attachment_count": 0,
            "attachment_names": "", "attachment_types": "",
            "importance": 1, "is_read": 1,
            "categories": "", "conversation_id": "META_CONV",
        })

        plan = env["sm"].create_plan(folder_ids=[6, 5])
        env["sm"].execute_plan(plan, folder_ids=[6, 5])

        assert get_meta(env["conn"], "last_sync_time") is not None
        assert get_meta(env["conn"], "indexing_state") == "completed"

    def test_11_result_summary(self, env):
        """SyncResult.summary 포맷"""
        env["mock"]._sample_emails.append({
            "entry_id": "SUMMARY_001",
            "subject": "요약 테스트",
            "sender_name": "테스터",
            "sender_email": "test@test.com",
            "recipients": "나", "cc": "",
            "body_text": "요약",
            "html_body": "",
            "folder_name": "받은편지함",
            "received_at": "2026-05-28 13:00:00",
            "sent_at": "2026-05-28 13:00:00",
            "has_attachments": 0, "attachment_count": 0,
            "attachment_names": "", "attachment_types": "",
            "importance": 1, "is_read": 1,
            "categories": "", "conversation_id": "SUM",
        })

        plan = env["sm"].create_plan(folder_ids=[6, 5])
        result = env["sm"].execute_plan(plan, folder_ids=[6, 5])

        assert "추가" in result.summary
        assert "초" in result.summary

    def test_12_double_sync_idempotent(self, env):
        """동일한 동기화를 두 번 실행해도 안전"""
        # 새 메일 추가 → 1차 동기화
        env["mock"]._sample_emails.append({
            "entry_id": "IDEMPOTENT_001",
            "subject": "멱등성 테스트",
            "sender_name": "테스터",
            "sender_email": "test@test.com",
            "recipients": "나", "cc": "",
            "body_text": "멱등성",
            "html_body": "",
            "folder_name": "받은편지함",
            "received_at": "2026-05-28 14:00:00",
            "sent_at": "2026-05-28 14:00:00",
            "has_attachments": 0, "attachment_count": 0,
            "attachment_names": "", "attachment_types": "",
            "importance": 1, "is_read": 1,
            "categories": "", "conversation_id": "IDEMP",
        })

        plan1 = env["sm"].create_plan(folder_ids=[6, 5])
        result1 = env["sm"].execute_plan(plan1, folder_ids=[6, 5])
        count1 = get_email_count(env["conn"])

        # 2차 동기화 (변경 없음)
        plan2 = env["sm"].create_plan(folder_ids=[6, 5])
        assert plan2.has_changes is False

        result2 = env["sm"].execute_plan(plan2, folder_ids=[6, 5])
        count2 = get_email_count(env["conn"])

        assert count1 == count2  # DB 건수 동일
        assert result2.added == 0
        assert result2.deleted == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

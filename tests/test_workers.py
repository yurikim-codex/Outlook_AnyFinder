"""
OutLook AnyFinder Ver0.9 for SESUNG Team
[C03] 인덱싱 QThread 워커 테스트

GUI 이벤트 루프 없이 워커의 핵심 로직을 검증합니다.
QThread.run()을 직접 호출하여 시그널 동작을 테스트합니다.
"""

import pytest
import tempfile
import time
from pathlib import Path

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from data.database import init_db, get_email_count, get_meta
from core.outlook_connector import MockOutlookConnector, OlDefaultFolders


# ── QThread 시그널 테스트를 위한 헬퍼 ──

class SignalCapture:
    """시그널 수신을 기록하는 헬퍼"""
    def __init__(self):
        self.calls = []

    def __call__(self, *args):
        self.calls.append(args)

    @property
    def count(self):
        return len(self.calls)

    @property
    def last(self):
        return self.calls[-1] if self.calls else None


@pytest.fixture
def db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    conn = init_db(db_path)
    yield conn
    conn.close()
    db_path.unlink(missing_ok=True)


@pytest.fixture
def mock_connector():
    conn = MockOutlookConnector()
    conn.connect()
    return conn


class TestIndexingWorkerLogic:
    """IndexingWorker의 핵심 로직 테스트 (QThread 없이 직접 호출)"""

    def test_01_build_with_progress_callback(self, db, mock_connector):
        """진행률 콜백이 호출되어야 한다"""
        from core.index_builder import IndexBuilder

        builder = IndexBuilder(db)
        progress_log = []

        def on_progress(done, total, subject):
            progress_log.append({"done": done, "total": total, "subject": subject})

        mails = list(mock_connector.iter_mails(OlDefaultFolders.INBOX))
        stats = builder.build_from_iterator(
            mail_iterator=iter(mails),
            total_count=len(mails),
            on_progress=on_progress,
        )

        assert stats["indexed"] > 0
        assert len(progress_log) > 0
        # 마지막 콜백은 "완료" subject
        assert progress_log[-1]["subject"] == "완료"

    def test_02_pause_resume_logic(self, db, mock_connector):
        """일시정지/재개 플래그 동작 확인"""
        from core.index_builder import IndexBuilder

        builder = IndexBuilder(db)
        mails = list(mock_connector.iter_mails(OlDefaultFolders.INBOX))

        pause_flag = [False]
        resume_count = [0]

        def is_paused():
            if pause_flag[0]:
                pause_flag[0] = False  # 자동 재개 (테스트에서는)
                resume_count[0] += 1
                return True
            return False

        # 3번째 메일에서 일시정지 트리거
        call_count = [0]
        original_extract = __import__('core.mail_extractor', fromlist=['extract_to_record']).extract_to_record

        def counting_progress(done, total, subject):
            nonlocal call_count
            call_count[0] += 1
            if call_count[0] == 3:
                pause_flag[0] = True

        stats = builder.build_from_iterator(
            mail_iterator=iter(mails),
            total_count=len(mails),
            on_progress=counting_progress,
            is_paused=is_paused,
        )

        # 모든 메일이 인덱싱되어야 함 (일시정지→재개 후 계속)
        assert stats["indexed"] == len(mails)

    def test_03_stop_preserves_data(self, db, mock_connector):
        """중단해도 이미 인덱싱된 데이터가 유지되어야 한다"""
        from core.index_builder import IndexBuilder

        builder = IndexBuilder(db)
        mails = list(mock_connector.iter_mails(OlDefaultFolders.INBOX))

        stop_after = 3
        processed = [0]

        def should_stop():
            return processed[0] >= stop_after

        def on_progress(done, total, subject):
            processed[0] = done

        stats = builder.build_from_iterator(
            mail_iterator=iter(mails),
            total_count=len(mails),
            on_progress=on_progress,
            should_stop=should_stop,
        )

        count = get_email_count(db)
        assert count > 0
        assert count <= len(mails)
        # 인덱싱된 건 검색 가능해야 함
        rows = db.execute("SELECT COUNT(*) as cnt FROM emails").fetchone()
        assert rows["cnt"] == count

    def test_04_multi_folder_indexing(self, db, mock_connector):
        """여러 폴더를 연속으로 인덱싱"""
        from core.index_builder import IndexBuilder

        builder = IndexBuilder(db)

        folder_progress = {}

        for fid in [OlDefaultFolders.INBOX, OlDefaultFolders.SENT]:
            folder_name = OlDefaultFolders.NAMES[fid]
            mails = list(mock_connector.iter_mails(fid))

            stats = builder.build_from_iterator(
                mail_iterator=iter(mails),
                total_count=len(mails),
            )
            folder_progress[folder_name] = stats["indexed"]

        assert folder_progress["받은편지함"] > 0
        assert folder_progress["보낸편지함"] > 0
        total = get_email_count(db)
        assert total == sum(folder_progress.values())

    def test_05_speed_calculation(self, db, mock_connector):
        """인덱싱 속도가 합리적인 범위여야 한다"""
        from core.index_builder import IndexBuilder

        builder = IndexBuilder(db)
        mails = list(mock_connector.iter_mails(OlDefaultFolders.INBOX))

        start = time.time()
        stats = builder.build_from_iterator(iter(mails), len(mails))
        elapsed = time.time() - start

        if elapsed > 0:
            speed = stats["indexed"] / elapsed
            assert speed > 1  # 최소 1건/초 이상
            print(f"  인덱싱 속도: {speed:.1f} 건/초 ({stats['indexed']}건 / {elapsed:.2f}초)")

    def test_06_sync_meta_after_indexing(self, db, mock_connector):
        """인덱싱 후 sync_meta에 상태가 기록되어야 한다"""
        from core.index_builder import IndexBuilder

        builder = IndexBuilder(db)
        mails = list(mock_connector.iter_mails(OlDefaultFolders.INBOX))
        builder.build_from_iterator(iter(mails), len(mails))

        assert get_meta(db, "last_sync_time") is not None
        assert get_meta(db, "indexing_state") == "completed"
        assert int(get_meta(db, "total_indexed", "0")) > 0


class TestSyncWorkerLogic:
    """SyncWorker의 핵심 로직 테스트"""

    def test_07_incremental_sync(self, db, mock_connector):
        """증분 동기화: 새 메일만 추가"""
        from core.index_builder import IndexBuilder
        from data.database import set_meta

        builder = IndexBuilder(db)

        # 1차: 전체 인덱싱
        inbox = list(mock_connector.iter_mails(OlDefaultFolders.INBOX))
        stats1 = builder.build_from_iterator(iter(inbox), len(inbox))
        first_count = get_email_count(db)

        # 동기화 시점 기록
        set_meta(db, "last_sync_time", "2026-05-27T00:00:00")

        # 2차: 증분 동기화 (동일 데이터 → 전부 건너뜀)
        stats2 = builder.build_from_iterator(iter(inbox), len(inbox))
        second_count = get_email_count(db)

        assert second_count == first_count
        assert stats2["skipped"] == len(inbox)

    def test_08_no_sync_history(self, db, mock_connector):
        """동기화 이력 없으면 전체 인덱싱 필요 상태"""
        from data.database import get_meta

        last_sync = get_meta(db, "last_sync_time")
        assert last_sync is None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

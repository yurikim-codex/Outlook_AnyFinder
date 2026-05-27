"""
OutLook AnyFinder Ver0.9 for SESUNG Team
[M03] FTS5 인덱스 구축 (v3 — email_hashes 테이블 기반)
"""

import sqlite3
import logging
import time
from typing import Callable, Optional, Generator

from data.database import email_exists, set_meta, set_hash
from data.models import EmailRecord
from core.mail_extractor import extract_to_record

logger = logging.getLogger(__name__)


class IndexBuilder:

    BATCH_SIZE = 50
    THROTTLE_INTERVAL = 50
    THROTTLE_SLEEP = 0.05

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def build_from_iterator(self, mail_iterator, total_count=0,
                             on_progress=None, should_stop=None, is_paused=None) -> dict:
        from core.sync_manager import compute_mail_hash

        stats = {"indexed": 0, "skipped": 0, "errors": 0, "elapsed_sec": 0}
        start = time.time()
        batch = []

        for raw in mail_iterator:
            if should_stop and should_stop(): break
            if is_paused:
                while is_paused():
                    if should_stop and should_stop(): break
                    time.sleep(0.2)

            record = extract_to_record(raw)
            if not record:
                stats["errors"] += 1
                continue

            if email_exists(self.conn, record.entry_id):
                stats["skipped"] += 1
                continue

            batch.append((record, raw))

            if len(batch) >= self.BATCH_SIZE:
                inserted = self._flush_batch(batch)
                stats["indexed"] += inserted
                stats["errors"] += len(batch) - inserted
                batch.clear()

            processed = stats["indexed"] + stats["skipped"] + stats["errors"]
            if on_progress and processed % 10 == 0:
                on_progress(processed, total_count, record.subject)
            if processed % self.THROTTLE_INTERVAL == 0:
                time.sleep(self.THROTTLE_SLEEP)

        if batch:
            inserted = self._flush_batch(batch)
            stats["indexed"] += inserted
            stats["errors"] += len(batch) - inserted

        stats["elapsed_sec"] = round(time.time() - start, 2)

        from datetime import datetime
        set_meta(self.conn, "last_sync_time", datetime.now().isoformat()[:19])
        set_meta(self.conn, "total_indexed", str(stats["indexed"]))
        set_meta(self.conn, "indexing_state", "completed")

        if on_progress:
            on_progress(stats["indexed"] + stats["skipped"] + stats["errors"], total_count, "완료")

        logger.info(f"인덱싱 완료: {stats['indexed']}건, 스킵={stats['skipped']}, 오류={stats['errors']}, {stats['elapsed_sec']}초")
        return stats

    def _flush_batch(self, batch):
        from core.sync_manager import compute_mail_hash
        inserted = 0
        try:
            cur = self.conn.cursor()
            for record, raw in batch:
                try:
                    cur.execute(EmailRecord.insert_sql(), record.to_insert_tuple())
                    set_hash(self.conn, record.entry_id, compute_mail_hash(raw))
                    inserted += 1
                except sqlite3.IntegrityError: pass
                except Exception as e: logger.debug(f"INSERT 실패: {e}")
            self.conn.commit()
        except Exception as e:
            logger.error(f"배치 오류: {e}")
            try: self.conn.rollback()
            except: pass
        return inserted

    def rebuild_fts_index(self):
        try:
            self.conn.execute("INSERT INTO emails_fts(emails_fts) VALUES('rebuild')")
            self.conn.commit()
        except Exception as e: logger.error(f"FTS5 재구축 실패: {e}")

    def optimize_fts_index(self):
        try:
            self.conn.execute("INSERT INTO emails_fts(emails_fts) VALUES('optimize')")
            self.conn.commit()
        except Exception as e: logger.error(f"FTS5 최적화 실패: {e}")

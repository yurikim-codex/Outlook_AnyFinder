"""
OutLook AnyFinder Ver0.9 for SESUNG Team
[M06] 스마트 증분 동기화 (v3 — email_hashes 테이블 기반)
"""

import sqlite3
import hashlib
import logging
import time
from typing import List, Dict, Set, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime

from data.database import get_all_hashes, set_hash, delete_hash, set_meta

logger = logging.getLogger(__name__)


@dataclass
class SyncPlan:
    total_outlook: int = 0
    total_db: int = 0
    new_ids: List[str] = field(default_factory=list)
    updated_ids: List[str] = field(default_factory=list)
    deleted_ids: List[str] = field(default_factory=list)
    skipped_count: int = 0

    @property
    def has_changes(self):
        return len(self.new_ids) > 0 or len(self.updated_ids) > 0 or len(self.deleted_ids) > 0

    @property
    def changes_summary(self):
        parts = []
        if self.new_ids: parts.append(f"새 메일 {len(self.new_ids)}건 추가")
        if self.updated_ids: parts.append(f"{len(self.updated_ids)}건 업데이트")
        if self.deleted_ids: parts.append(f"{len(self.deleted_ids)}건 삭제")
        if self.skipped_count > 0: parts.append(f"{self.skipped_count:,}건 동일 (스킵)")
        return ", ".join(parts) if parts else "변경 사항 없음"


@dataclass
class SyncResult:
    added: int = 0
    updated: int = 0
    deleted: int = 0
    skipped: int = 0
    errors: int = 0
    elapsed_sec: float = 0.0
    plan: Optional[SyncPlan] = None

    @property
    def summary(self):
        parts = []
        if self.added: parts.append(f"{self.added}건 추가")
        if self.updated: parts.append(f"{self.updated}건 업데이트")
        if self.deleted: parts.append(f"{self.deleted}건 삭제")
        if self.skipped: parts.append(f"{self.skipped:,}건 스킵")
        if self.errors: parts.append(f"{self.errors}건 오류")
        parts.append(f"{self.elapsed_sec:.1f}초")
        return " · ".join(parts)


def compute_mail_hash(mail_data: dict) -> str:
    """메일 핵심 필드 해시 (변경 감지용)"""
    key = (
        str(mail_data.get("subject", "")) +
        str(mail_data.get("sender_name", "")) +
        str(mail_data.get("recipients", "")) +
        str(mail_data.get("body_text", ""))[:500] +
        str(mail_data.get("has_attachments", 0)) +
        str(mail_data.get("attachment_names", "")) +
        str(mail_data.get("is_read", 1))
    )
    return hashlib.md5(key.encode("utf-8", errors="ignore")).hexdigest()[:12]


class SyncManager:
    """스마트 증분 동기화 — email_hashes 테이블 기반"""

    def __init__(self, conn: sqlite3.Connection, connector):
        self.conn = conn
        self.connector = connector

    def create_plan(self, folder_ids=None, include_subfolders=True,
                     on_status=None) -> SyncPlan:
        folder_ids = folder_ids or [6, 5]
        plan = SyncPlan()

        if on_status: on_status("Outlook 메일 목록 스캔 중...")

        # 1단계: Outlook에서 entry_id + 해시 수집
        outlook_entries = {}
        for fid in folder_ids:
            try:
                outlook_entries.update(self._scan_folder(fid, include_subfolders))
            except Exception as e:
                logger.error(f"폴더 스캔 오류 (ID={fid}): {e}")

        plan.total_outlook = len(outlook_entries)
        if on_status: on_status(f"Outlook {plan.total_outlook:,}건 스캔, DB와 비교 중...")

        # 2단계: DB와 비교 (email_hashes 테이블 사용)
        db_entry_ids = self._get_db_entry_ids()
        saved_hashes = get_all_hashes(self.conn)  # {entry_id: hash} — O(1) 조회
        plan.total_db = len(db_entry_ids)

        outlook_ids = set(outlook_entries.keys())

        plan.new_ids = list(outlook_ids - db_entry_ids)
        plan.deleted_ids = list(db_entry_ids - outlook_ids)

        common = outlook_ids & db_entry_ids
        for eid in common:
            new_hash = outlook_entries.get(eid, "")
            old_hash = saved_hashes.get(eid, "")
            if old_hash and new_hash and new_hash != old_hash:
                plan.updated_ids.append(eid)

        plan.skipped_count = len(common) - len(plan.updated_ids)

        if on_status: on_status(f"비교 완료: {plan.changes_summary}")
        logger.info(f"동기화 계획: 새={len(plan.new_ids)}, 수정={len(plan.updated_ids)}, 삭제={len(plan.deleted_ids)}, 스킵={plan.skipped_count}")
        return plan

    def execute_plan(self, plan, folder_ids=None, include_subfolders=True,
                      on_progress=None, should_stop=None) -> SyncResult:
        folder_ids = folder_ids or [6, 5]
        result = SyncResult(plan=plan)
        start = time.time()
        total_work = len(plan.new_ids) + len(plan.updated_ids) + len(plan.deleted_ids)
        done = 0

        if not plan.has_changes:
            result.skipped = plan.skipped_count
            return result

        from core.mail_extractor import extract_to_record
        from data.models import EmailRecord

        # 삭제
        if plan.deleted_ids:
            if on_progress: on_progress(done, total_work, f"삭제 {len(plan.deleted_ids)}건 정리 중...")
            for eid in plan.deleted_ids:
                self.conn.execute("DELETE FROM emails WHERE entry_id=?", (eid,))
                delete_hash(self.conn, eid)
            self.conn.commit()
            result.deleted = len(plan.deleted_ids)
            done += len(plan.deleted_ids)

        # 추가 + 업데이트
        target_ids = set(plan.new_ids) | set(plan.updated_ids)
        if target_ids:
            for fid in folder_ids:
                if should_stop and should_stop(): break
                for raw in self.connector.iter_mails(fid, include_subfolders):
                    if should_stop and should_stop(): break
                    eid = raw.get("entry_id", "")
                    if eid not in target_ids: continue

                    record = extract_to_record(raw)
                    if record:
                        try:
                            if eid in plan.updated_ids:
                                self.conn.execute("DELETE FROM emails WHERE entry_id=?", (eid,))
                            self.conn.execute(EmailRecord.insert_sql(), record.to_insert_tuple())
                            set_hash(self.conn, eid, compute_mail_hash(raw))
                            if eid in plan.updated_ids:
                                result.updated += 1
                            else:
                                result.added += 1
                        except Exception as e:
                            logger.debug(f"처리 실패 ({eid}): {e}")
                            result.errors += 1

                    target_ids.discard(eid)
                    done += 1
                    if on_progress and done % 5 == 0:
                        on_progress(done, total_work, f"처리 중... ({result.added}추가, {result.updated}업데이트)")
                    if not target_ids: break

            self.conn.commit()

        result.skipped = plan.skipped_count
        result.elapsed_sec = round(time.time() - start, 2)

        set_meta(self.conn, "last_sync_time", datetime.now().isoformat()[:19])
        set_meta(self.conn, "indexing_state", "completed")

        if on_progress: on_progress(total_work, total_work, f"동기화 완료: {result.summary}")
        logger.info(f"동기화 완료: {result.summary}")
        return result

    # ── 내부 ──

    def _scan_folder(self, folder_id, include_subfolders):
        entries = {}
        folder = self.connector.get_default_folder(folder_id)
        if not folder: return entries
        self._scan_items(folder, entries)
        if include_subfolders: self._scan_subs(folder, entries)
        return entries

    def _scan_items(self, folder, entries):
        try:
            for msg in folder.Items:
                try:
                    if msg.Class == 43:
                        eid = msg.EntryID
                        mod = str(getattr(msg, "LastModificationTime", ""))[:19]
                        read = str(not getattr(msg, "UnRead", False))
                        entries[eid] = hashlib.md5((mod + read).encode()).hexdigest()[:12]
                except Exception: continue
        except Exception: pass

    def _scan_subs(self, parent, entries):
        try:
            for i in range(1, parent.Folders.Count + 1):
                sub = parent.Folders.Item(i)
                self._scan_items(sub, entries)
                self._scan_subs(sub, entries)
        except Exception: pass

    def _get_db_entry_ids(self) -> Set[str]:
        rows = self.conn.execute("SELECT entry_id FROM emails").fetchall()
        return {r["entry_id"] for r in rows}


class MockSyncManager(SyncManager):
    def _scan_folder(self, folder_id, include_subfolders):
        entries = {}
        for mail in self.connector.iter_mails(folder_id, include_subfolders):
            eid = mail.get("entry_id", "")
            if eid: entries[eid] = compute_mail_hash(mail)
        return entries

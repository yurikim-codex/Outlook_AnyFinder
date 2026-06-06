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
from datetime import datetime, timedelta

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
    outlook_hashes: Dict[str, str] = field(default_factory=dict)  # entry_id -> scan hash
    sync_started_at: str = ""          # 동기화 기준 시각. 완료 시 last_sync_time으로 저장
    scan_after_date: Optional[str] = None  # 증분 스캔에 실제 사용한 overlap 적용 기준일

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


def _normalize_read_value(is_read) -> int:
    """읽음 상태를 0/1로 정규화한다."""
    if isinstance(is_read, bool):
        return 1 if is_read else 0
    text = str(is_read).strip().lower()
    if text in ("1", "true", "yes", "read"):
        return 1
    if text in ("0", "false", "no", "unread"):
        return 0
    return 1 if is_read else 0


def compute_scan_hash(last_modified: str, is_read) -> str:
    """Outlook 빠른 스캔용 해시: 최종 수정시각 + 읽음 상태."""
    key = str(last_modified or "")[:19] + str(_normalize_read_value(is_read))
    return hashlib.md5(key.encode("utf-8", errors="ignore")).hexdigest()[:12]


def compute_mail_hash(mail_data: dict) -> str:
    """메일 변경 감지용 해시.

    Outlook에서 last_modified가 제공되면 빠른 스캔 해시와 동일한 형식으로 저장한다.
    구버전/Mock 데이터처럼 last_modified가 없으면 기존 내용 기반 해시로 폴백한다.
    """
    if mail_data.get("last_modified"):
        return compute_scan_hash(mail_data.get("last_modified", ""), mail_data.get("is_read", 1))
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

    INCREMENTAL_OVERLAP_MINUTES = 10

    def __init__(self, conn: sqlite3.Connection, connector):
        self.conn = conn
        self.connector = connector

    def _with_incremental_overlap(self, after_date: Optional[str]) -> Optional[str]:
        """시간 정밀도/동기화 중 수신 메일 누락 방지를 위한 overlap 적용."""
        if not after_date:
            return after_date
        try:
            dt = datetime.fromisoformat(str(after_date)[:19])
            return (dt - timedelta(minutes=self.INCREMENTAL_OVERLAP_MINUTES)).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return after_date

    def create_plan(self, folder_ids=None, include_subfolders=True,
                     on_status=None, should_stop=None, after_date=None,
                     on_scan_progress=None, incremental=False,
                     mail_after_date=None) -> SyncPlan:
        folder_ids = folder_ids or [6, 5]
        plan = SyncPlan()
        plan.sync_started_at = datetime.now().isoformat()[:19]
        plan.scan_after_date = self._with_incremental_overlap(after_date) if incremental else after_date

        if on_status: on_status("Outlook 메일 목록 스캔 중...")

        # 선택한 폴더의 전체 메일 수를 기준으로 스캔 진행률을 표시한다.
        scan_total = 0
        try:
            scan_total = self.connector.get_total_mail_count(
                folder_ids=folder_ids,
                include_subfolders=include_subfolders,
                after_date=plan.scan_after_date if incremental else None,
                incremental=incremental,
                mail_after_date=mail_after_date,
            )
        except Exception:
            scan_total = 0
        scan_state = {"done": 0, "total": scan_total, "last_emit": 0}
        if on_scan_progress:
            on_scan_progress(0, scan_total, "Outlook 메일 스캔 시작...", "")

        # 1단계: Outlook에서 entry_id + 해시 수집
        outlook_entries = {}
        for fid in folder_ids:
            if should_stop and should_stop():
                break
            try:
                outlook_entries.update(self._scan_folder(
                    fid, include_subfolders,
                    should_stop=should_stop,
                    after_date=plan.scan_after_date,
                    scan_state=scan_state,
                    on_scan_progress=on_scan_progress,
                    incremental=incremental,
                    mail_after_date=mail_after_date,
                ))
            except Exception as e:
                logger.error(f"폴더 스캔 오류 (ID={fid}): {e}")

        plan.total_outlook = len(outlook_entries)
        plan.outlook_hashes = dict(outlook_entries)
        if on_scan_progress:
            on_scan_progress(scan_state["done"], scan_total, f"Outlook {plan.total_outlook:,}건 스캔 완료", "")
        if on_status: on_status(f"Outlook {plan.total_outlook:,}건 스캔, DB와 비교 중...")

        # 2단계: DB와 비교 (email_hashes 테이블 사용)
        # 자동 증분 동기화는 변경/추가분만 스캔하므로 DB 비교 대상은 선택 폴더 전체로 잡고,
        # 삭제 감지는 수행하지 않는다. 삭제 감지는 수동 전체/범위 동기화에서 처리한다.
        db_entry_ids = self._get_db_entry_ids(after_date=None if incremental else after_date, folder_ids=folder_ids)
        saved_hashes = get_all_hashes(self.conn)  # {entry_id: hash} — O(1) 조회
        plan.total_db = len(db_entry_ids)

        outlook_ids = set(outlook_entries.keys())

        plan.new_ids = list(outlook_ids - db_entry_ids)
        plan.deleted_ids = [] if incremental else list(db_entry_ids - outlook_ids)

        common = outlook_ids & db_entry_ids
        for eid in common:
            new_hash = outlook_entries.get(eid, "")
            old_hash = saved_hashes.get(eid, "")
            if new_hash and (not old_hash or new_hash != old_hash):
                # legacy DB처럼 해시가 없거나 기준이 다른 경우에는 한 번 업데이트하여
                # 이후 증분 동기화에서 안정적으로 변경 감지되도록 한다.
                plan.updated_ids.append(eid)

        plan.skipped_count = len(common) - len(plan.updated_ids)

        if on_status: on_status(f"비교 완료: {plan.changes_summary}")
        logger.info(f"동기화 계획: 새={len(plan.new_ids)}, 수정={len(plan.updated_ids)}, 삭제={len(plan.deleted_ids)}, 스킵={plan.skipped_count}")
        return plan

    def execute_plan(self, plan, folder_ids=None, include_subfolders=True,
                      on_progress=None, should_stop=None, after_date=None,
                      incremental=False) -> SyncResult:
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
                if should_stop and should_stop():
                    break
                self.conn.execute("DELETE FROM emails WHERE entry_id=?", (eid,))
                delete_hash(self.conn, eid)
                result.deleted += 1
                done += 1
                if on_progress and done % 20 == 0:
                    on_progress(done, total_work, f"삭제 중... ({result.deleted}건)")
            self.conn.commit()
            if should_stop and should_stop():
                result.elapsed_sec = round(time.time() - start, 2)
                if on_progress: on_progress(done, total_work, "동기화가 중지되었습니다")
                return result

        # 추가 + 업데이트
        target_ids = set(plan.new_ids) | set(plan.updated_ids)
        effective_after_date = plan.scan_after_date if incremental and getattr(plan, "scan_after_date", None) else after_date
        if target_ids:
            for fid in folder_ids:
                if should_stop and should_stop(): break
                for raw in self.connector.iter_mails(fid, include_subfolders, after_date=effective_after_date, incremental=incremental):
                    if should_stop and should_stop(): break
                    eid = raw.get("entry_id", "")
                    if eid not in target_ids: continue

                    record = extract_to_record(raw)
                    if record:
                        try:
                            if eid in plan.updated_ids:
                                self.conn.execute("DELETE FROM emails WHERE entry_id=?", (eid,))
                            self.conn.execute(EmailRecord.insert_sql(), record.to_insert_tuple())
                            set_hash(self.conn, eid, plan.outlook_hashes.get(eid) or compute_mail_hash(raw))
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

        if should_stop and should_stop():
            if on_progress: on_progress(done, total_work, "동기화가 중지되었습니다")
            return result

        set_meta(self.conn, "last_sync_time", plan.sync_started_at or datetime.now().isoformat()[:19])
        set_meta(self.conn, "indexing_state", "completed")

        if on_progress: on_progress(total_work, total_work, f"동기화 완료: {result.summary}")
        logger.info(f"동기화 완료: {result.summary}")
        return result

    # ── 내부 ──

    def _scan_folder(self, folder_id, include_subfolders, should_stop=None, after_date=None,
                     scan_state=None, on_scan_progress=None, incremental=False,
                     mail_after_date=None):
        entries = {}
        folder = self.connector.get_default_folder(folder_id)
        if not folder: return entries
        date_basis = "sent" if folder_id == 5 else "received"
        self._scan_items(folder, entries, should_stop=should_stop, after_date=after_date,
                         scan_state=scan_state, on_scan_progress=on_scan_progress,
                         incremental=incremental, date_basis=date_basis,
                         mail_after_date=mail_after_date)
        if include_subfolders and not (should_stop and should_stop()):
            self._scan_subs(folder, entries, should_stop=should_stop, after_date=after_date,
                            scan_state=scan_state, on_scan_progress=on_scan_progress,
                            incremental=incremental, date_basis=date_basis,
                            mail_after_date=mail_after_date)
        return entries

    def _to_datetime(self, value):
        if not value:
            return None
        try:
            if hasattr(value, "year") and hasattr(value, "month"):
                return datetime(value.year, value.month, value.day, value.hour, value.minute, value.second)
        except Exception:
            pass
        text = str(value)[:19]
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%m/%d/%y %H:%M:%S", "%m/%d/%Y %H:%M:%S"):
            try:
                return datetime.strptime(text, fmt)
            except Exception:
                continue
        try:
            return datetime.fromisoformat(text)
        except Exception:
            return None

    def _msg_in_range(self, msg, after_date: str, incremental=False, folder_name="", date_basis="received") -> bool:
        base_dt = self._to_datetime(after_date)
        if not base_dt:
            return True
        if incremental:
            attrs = ("LastModificationTime",)
        elif date_basis == "sent" or folder_name in ("보낸편지함", "보낸 편지함", "Sent Items", "Sent"):
            attrs = ("SentOn", "ReceivedTime")
        else:
            attrs = ("ReceivedTime", "SentOn")
        for attr in attrs:
            try:
                dt = self._to_datetime(getattr(msg, attr, None))
                if dt:
                    return dt >= base_dt
            except Exception:
                continue
        return True

    def _emit_scan_progress(self, scan_state, on_scan_progress, message, folder_name="", force=False):
        if not scan_state or not on_scan_progress:
            return
        done = scan_state.get("done", 0)
        total = scan_state.get("total", 0)
        # 너무 잦은 UI 업데이트 방지
        if force or done == 0 or done - scan_state.get("last_emit", 0) >= 25:
            scan_state["last_emit"] = done
            on_scan_progress(done, total, message, folder_name)

    def _scan_items(self, folder, entries, should_stop=None, after_date=None,
                    scan_state=None, on_scan_progress=None, incremental=False,
                    date_basis="received", mail_after_date=None):
        try:
            items = folder.Items
            break_on_old_incremental = False
            if after_date and incremental:
                try:
                    items = items.Restrict(f"[LastModificationTime] > '{after_date}'")
                except Exception:
                    # Restrict 실패 시 LastModificationTime 내림차순으로 정렬하고 오래된 항목에서 중단
                    try:
                        items.Sort("[LastModificationTime]", True)
                        break_on_old_incremental = True
                    except Exception:
                        pass
            # 필요한 속성만 로딩하도록 힌트를 주어 COM 속성 접근 비용을 줄인다.
            # Outlook/스토어 종류에 따라 실패할 수 있으므로 실패해도 기존 방식으로 진행한다.
            try:
                items.SetColumns("EntryID,LastModificationTime,ReceivedTime,SentOn,UnRead,Class")
            except Exception:
                pass

            folder_name = str(getattr(folder, "Name", ""))
            self._emit_scan_progress(scan_state, on_scan_progress, "스캔 중...", folder_name, force=True)
            for msg in items:
                if should_stop and should_stop():
                    break
                try:
                    if scan_state is not None:
                        scan_state["done"] = scan_state.get("done", 0) + 1
                    if msg.Class == 43:
                        if after_date and incremental:
                            mod_dt = self._to_datetime(getattr(msg, "LastModificationTime", None))
                            base_dt = self._to_datetime(after_date)
                            if mod_dt and base_dt and mod_dt < base_dt:
                                if break_on_old_incremental:
                                    break
                                self._emit_scan_progress(scan_state, on_scan_progress, "범위 외 메일 확인 중...", folder_name)
                                continue
                        elif after_date and not self._msg_in_range(msg, after_date, incremental=incremental, folder_name=folder_name, date_basis=date_basis):
                            self._emit_scan_progress(scan_state, on_scan_progress, "범위 외 메일 확인 중...", folder_name)
                            continue
                        if mail_after_date and not self._msg_in_range(msg, mail_after_date, incremental=False, folder_name=folder_name, date_basis=date_basis):
                            self._emit_scan_progress(scan_state, on_scan_progress, "기간 범위 외 메일 확인 중...", folder_name)
                            continue
                        eid = msg.EntryID
                        mod = str(getattr(msg, "LastModificationTime", ""))[:19]
                        read = 0 if getattr(msg, "UnRead", False) else 1
                        entries[eid] = compute_scan_hash(mod, read)
                    self._emit_scan_progress(scan_state, on_scan_progress, f"스캔 중... ({len(entries):,}건 확인)", folder_name)
                except Exception:
                    self._emit_scan_progress(scan_state, on_scan_progress, "스캔 중...", folder_name)
                    continue
        except Exception: pass

    def _scan_subs(self, parent, entries, should_stop=None, after_date=None,
                   scan_state=None, on_scan_progress=None, incremental=False,
                   date_basis="received", mail_after_date=None):
        try:
            for i in range(1, parent.Folders.Count + 1):
                if should_stop and should_stop():
                    break
                sub = parent.Folders.Item(i)
                self._scan_items(sub, entries, should_stop=should_stop, after_date=after_date,
                                 scan_state=scan_state, on_scan_progress=on_scan_progress,
                                 incremental=incremental, date_basis=date_basis,
                                 mail_after_date=mail_after_date)
                self._scan_subs(sub, entries, should_stop=should_stop, after_date=after_date,
                                scan_state=scan_state, on_scan_progress=on_scan_progress,
                                incremental=incremental, date_basis=date_basis,
                                mail_after_date=mail_after_date)
        except Exception: pass

    def _get_db_entry_ids(self, after_date=None, folder_ids=None) -> Set[str]:
        clauses = []
        params = []
        if after_date:
            clauses.append("COALESCE(NULLIF(received_at, ''), sent_at) >= ?")
            params.append(after_date)
        if folder_ids:
            try:
                from core.outlook_connector import OlDefaultFolders
                names = [OlDefaultFolders.NAMES.get(fid) for fid in folder_ids if OlDefaultFolders.NAMES.get(fid)]
                if names:
                    placeholders = ",".join("?" for _ in names)
                    clauses.append(f"folder_name IN ({placeholders})")
                    params.extend(names)
            except Exception:
                pass
        sql = "SELECT entry_id FROM emails"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        rows = self.conn.execute(sql, params).fetchall()
        return {r["entry_id"] for r in rows}


class MockSyncManager(SyncManager):
    def _scan_folder(self, folder_id, include_subfolders, should_stop=None, after_date=None,
                     scan_state=None, on_scan_progress=None, incremental=False,
                     mail_after_date=None):
        entries = {}
        from core.outlook_connector import OlDefaultFolders
        folder_name = OlDefaultFolders.NAMES.get(folder_id, f"폴더 {folder_id}")
        for mail in self.connector.iter_mails(folder_id, include_subfolders, after_date=after_date, incremental=incremental):
            if should_stop and should_stop():
                break
            if scan_state is not None:
                scan_state["done"] = scan_state.get("done", 0) + 1
            if mail_after_date and mail.get("received_at", "") and mail.get("received_at", "") < mail_after_date:
                continue
            eid = mail.get("entry_id", "")
            if eid:
                entries[eid] = compute_mail_hash(mail)
            self._emit_scan_progress(scan_state, on_scan_progress, f"스캔 중... ({len(entries):,}건 확인)", folder_name)
        return entries

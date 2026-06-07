"""
OutLook AnyFinder Ver0.9.1.1 for SESUNG Team
[M01] Outlook 연결 (v2 — COM 스레드 안전 + 폴더 접근 복구)
"""

import os
import sys
import logging
from typing import List, Optional, Generator
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

WIN32_IMPORT_ERROR = None
try:
    import win32com.client
    import pythoncom  # COM 스레드 초기화 필요
    HAS_WIN32 = True
except Exception as e:
    WIN32_IMPORT_ERROR = e
    HAS_WIN32 = False
    win32com = None
    pythoncom = None


class OlDefaultFolders:
    DELETED = 3
    OUTBOX = 4
    SENT = 5
    INBOX = 6
    DRAFTS = 16
    JUNK = 23

    NAMES = {3: "지운편지함", 4: "보낼편지함", 5: "보낸편지함",
             6: "받은편지함", 16: "임시보관함", 23: "정크메일"}


class OutlookConnectionError(Exception):
    pass


class OutlookConnector:
    def __init__(self):
        self.outlook = None
        self.mapi = None
        self._connected = False
        self._com_initialized = False

    def connect(self) -> bool:
        if not HAS_WIN32:
            raise OutlookConnectionError(
                "Outlook COM 모듈(pywin32)을 사용할 수 없습니다. "
                f"빌드/설치 환경에 pywin32가 포함되어 있는지 확인하세요. 원인: {WIN32_IMPORT_ERROR}"
            )

        try:
            # ★ COM 스레드 초기화 (QThread에서 호출 시 필수)
            pythoncom.CoInitialize()
            self._com_initialized = True

            self.outlook = win32com.client.Dispatch("Outlook.Application")
            self.mapi = self.outlook.GetNamespace("MAPI")

            # 연결 확인: 기본 폴더 접근 테스트
            try:
                _ = self.mapi.GetDefaultFolder(OlDefaultFolders.INBOX)
            except Exception:
                # Outlook 프로필이 로드 안 된 경우 → 로그온 시도
                try:
                    self.mapi.Logon("", "", False, True)
                except Exception:
                    pass

            self._connected = True
            logger.info("Outlook 연결 성공")
            return True
        except Exception as e:
            self._connected = False
            raise OutlookConnectionError(
                "Outlook 연결 실패: Microsoft Outlook 데스크톱(Classic Outlook)이 설치되어 있고 "
                f"로그인되어 있는지 확인하세요. 새 Outlook(웹 기반)은 COM 연동을 지원하지 않을 수 있습니다. 상세: {e}"
            )

    @property
    def is_connected(self):
        return self._connected

    def close(self):
        """COM 참조와 스레드 COM 초기화를 정리한다."""
        self._connected = False
        self.mapi = None
        self.outlook = None
        if HAS_WIN32 and self._com_initialized:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass
            self._com_initialized = False

    def get_default_folder(self, folder_id: int):
        if not self._connected:
            return None
        try:
            return self.mapi.GetDefaultFolder(folder_id)
        except Exception as e:
            logger.warning(f"기본 폴더 접근 실패 (ID={folder_id}), 폴더 탐색 시도...")
            # 폴백: 계정의 폴더를 직접 탐색
            return self._find_folder_by_id(folder_id)

    def _find_folder_by_id(self, folder_id: int):
        """GetDefaultFolder 실패 시 폴더 이름으로 직접 탐색"""
        target_names = {
            6: ["받은 편지함", "Inbox", "받은편지함"],
            5: ["보낸 편지함", "Sent Items", "보낸편지함", "Sent"],
            16: ["임시 보관함", "Drafts", "임시보관함"],
            3: ["지운 편지함", "Deleted Items", "지운편지함", "Trash"],
        }
        names = target_names.get(folder_id, [])
        if not names:
            return None

        try:
            # 모든 계정의 루트 폴더 탐색
            for i in range(1, self.mapi.Folders.Count + 1):
                account_folder = self.mapi.Folders.Item(i)
                for j in range(1, account_folder.Folders.Count + 1):
                    sub = account_folder.Folders.Item(j)
                    if sub.Name in names:
                        logger.info(f"폴더 발견: '{sub.Name}' (계정: {account_folder.Name})")
                        return sub
        except Exception as e:
            logger.error(f"폴더 탐색 실패: {e}")
        return None

    def get_folder_list(self) -> List[dict]:
        if not self._connected:
            return []
        folders = []
        for fid in [OlDefaultFolders.INBOX, OlDefaultFolders.SENT,
                     OlDefaultFolders.DRAFTS, OlDefaultFolders.DELETED]:
            try:
                folder = self.get_default_folder(fid)
                if folder:
                    folders.append({
                        "id": fid,
                        "name": OlDefaultFolders.NAMES.get(fid, folder.Name),
                        "display_name": folder.Name,
                        "count": folder.Items.Count,
                    })
            except Exception as e:
                logger.warning(f"폴더 목록 조회 실패 (ID={fid}): {e}")
        return folders

    def _format_restrict_dates(self, after_date):
        """Outlook Items.Restrict에 사용할 날짜 문자열 후보 생성.

        Outlook Restrict는 ISO 문자열을 환경에 따라 제대로 처리하지 못할 수 있어
        Outlook이 선호하는 US date format 후보를 같이 시도한다.
        """
        dt = self._to_datetime(after_date)
        if not dt:
            return [str(after_date)]
        return [
            dt.strftime("%m/%d/%Y %I:%M %p"),
            dt.strftime("%m/%d/%Y %H:%M"),
            dt.strftime("%Y-%m-%d %H:%M:%S"),
        ]

    def _restrict_items_after(self, items, field: str, after_date):
        """날짜 조건으로 Items.Restrict를 시도하고 실패하면 None 반환."""
        for date_text in self._format_restrict_dates(after_date):
            try:
                return items.Restrict(f"[{field}] >= '{date_text}'")
            except Exception as e:
                logger.debug(f"Restrict 실패 field={field}, date={date_text}: {e}")
        return None

    def get_total_mail_count(self, folder_ids=None, include_subfolders=True,
                             after_date=None, incremental=False, mail_after_date=None):
        folder_ids = folder_ids or [OlDefaultFolders.INBOX, OlDefaultFolders.SENT]
        total = 0
        for fid in folder_ids:
            folder = self.get_default_folder(fid)
            if folder:
                try:
                    date_basis = "sent" if fid == OlDefaultFolders.SENT else "received"
                    fname = OlDefaultFolders.NAMES.get(fid, getattr(folder, "Name", ""))
                    total += self._count_items(folder, after_date=after_date, incremental=incremental, date_basis=date_basis, folder_name=fname, mail_after_date=mail_after_date)
                    if include_subfolders:
                        total += self._count_subs(folder, after_date=after_date, incremental=incremental, date_basis=date_basis, mail_after_date=mail_after_date)
                except Exception:
                    pass
        return total

    def _count_items(self, folder, after_date=None, incremental=False, date_basis="received", folder_name="", mail_after_date=None):
        try:
            items = folder.Items
            need_exact = bool(mail_after_date)
            if after_date:
                field = "LastModificationTime" if incremental else ("SentOn" if date_basis == "sent" else "ReceivedTime")
                restricted = self._restrict_items_after(items, field, after_date)
                if restricted is not None:
                    items = restricted
                    if not need_exact:
                        try:
                            return items.Count
                        except Exception:
                            pass
            elif mail_after_date:
                # 기간 조건만 있는 경우에는 메일 날짜 기준으로 Restrict 시도
                field = "SentOn" if date_basis == "sent" else "ReceivedTime"
                restricted = self._restrict_items_after(items, field, mail_after_date)
                if restricted is not None:
                    items = restricted
                    try:
                        return items.Count
                    except Exception:
                        pass

            # Restrict 실패 또는 증분+기간 교집합 카운트가 필요한 경우 정확히 직접 센다.
            # 증분 동기화는 LastModificationTime 내림차순으로 정렬 후 기준일보다 오래된 항목에서 중단해
            # 매번 폴더 전체를 끝까지 훑지 않도록 한다.
            break_on_old_incremental = False
            if after_date and incremental:
                try:
                    items.Sort("[LastModificationTime]", True)
                    break_on_old_incremental = True
                except Exception:
                    pass
            count = 0
            for msg in items:
                try:
                    if msg.Class != 43:
                        continue
                    if after_date and incremental:
                        mod_dt = self._to_datetime(getattr(msg, "LastModificationTime", None))
                        base_dt = self._to_datetime(after_date)
                        if mod_dt and base_dt and mod_dt < base_dt:
                            if break_on_old_incremental:
                                break
                            continue
                    elif after_date and not self._is_msg_after_date(msg, after_date, incremental=incremental, folder_name=folder_name, date_basis=date_basis):
                        continue
                    if mail_after_date and not self._is_msg_after_date(msg, mail_after_date, incremental=False, folder_name=folder_name, date_basis=date_basis):
                        continue
                    count += 1
                except Exception:
                    continue
            return count
        except Exception:
            return 0

    def _count_subs(self, parent, after_date=None, incremental=False, date_basis="received", mail_after_date=None):
        count = 0
        try:
            for i in range(1, parent.Folders.Count + 1):
                sub = parent.Folders.Item(i)
                count += self._count_items(sub, after_date=after_date, incremental=incremental, date_basis=date_basis, folder_name=getattr(sub, "Name", ""), mail_after_date=mail_after_date)
                count += self._count_subs(sub, after_date=after_date, incremental=incremental, date_basis=date_basis, mail_after_date=mail_after_date)
        except Exception:
            pass
        return count

    def iter_mails(self, folder_id, include_subfolders=True, after_date=None, incremental=False):
        folder = self.get_default_folder(folder_id)
        if not folder:
            logger.warning(f"폴더를 찾을 수 없음 (ID={folder_id})")
            return

        fname = OlDefaultFolders.NAMES.get(folder_id, folder.Name)
        date_basis = "sent" if folder_id == OlDefaultFolders.SENT else "received"
        yield from self._iter_folder(folder, fname, after_date, incremental=incremental, date_basis=date_basis)
        if include_subfolders:
            yield from self._iter_subs(folder, after_date, incremental=incremental, date_basis=date_basis)

    def _iter_subs(self, parent, after_date=None, incremental=False, date_basis="received"):
        try:
            for i in range(1, parent.Folders.Count + 1):
                sub = parent.Folders.Item(i)
                yield from self._iter_folder(sub, sub.Name, after_date, incremental=incremental, date_basis=date_basis)
                yield from self._iter_subs(sub, after_date, incremental=incremental, date_basis=date_basis)
        except Exception:
            pass

    def _iter_folder(self, folder, fname, after_date=None, incremental=False, date_basis="received"):
        try:
            items = folder.Items
            items.Sort("[ReceivedTime]", True)

            break_on_old_incremental = False
            if after_date:
                if incremental:
                    # 증분 동기화: 변경/추가분만 확인
                    field = "LastModificationTime"
                else:
                    # 기간 동기화: 받은편지함은 ReceivedTime, 보낸편지함은 SentOn 중심
                    field = "SentOn" if date_basis == "sent" or fname in ("보낸편지함", "보낸 편지함", "Sent Items", "Sent") else "ReceivedTime"
                restricted = self._restrict_items_after(items, field, after_date)
                if restricted is not None:
                    items = restricted
                elif incremental:
                    # Restrict 실패 시 전체를 끝까지 스캔하지 않도록 최신 수정일 순으로 정렬 후 오래된 항목에서 중단
                    try:
                        items.Sort("[LastModificationTime]", True)
                        break_on_old_incremental = True
                    except Exception:
                        pass

            for msg in items:
                try:
                    if msg.Class == 43:
                        if after_date and incremental:
                            mod_dt = self._to_datetime(getattr(msg, "LastModificationTime", None))
                            base_dt = self._to_datetime(after_date)
                            if mod_dt and base_dt and mod_dt < base_dt:
                                if break_on_old_incremental:
                                    break
                                continue
                        elif after_date and not self._is_msg_after_date(msg, after_date, incremental=incremental, folder_name=fname, date_basis=date_basis):
                            continue
                        data = self._extract(msg, fname)
                        if data:
                            yield data
                except Exception:
                    continue
        except Exception as e:
            logger.error(f"폴더 '{fname}' 순회 오류: {e}")

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

    def _is_msg_after_date(self, msg, after_date: str, incremental=False, folder_name="", date_basis="received") -> bool:
        """증분은 LastModificationTime, 기간 필터는 ReceivedTime/SentOn 기준으로 판단."""
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
        # 날짜를 확인할 수 없으면 누락 방지를 위해 포함
        return True

    def _extract(self, msg, fname):
        try:
            att_names, att_types = [], set()
            html_body = ""
            try:
                html_body = msg.HTMLBody or ""
            except Exception:
                html_body = ""
            try:
                for i in range(1, msg.Attachments.Count + 1):
                    att = msg.Attachments.Item(i)
                    if self._is_inline_or_signature_attachment(att, html_body):
                        continue
                    name = att.FileName or ""
                    ext = os.path.splitext(name)[1].lower() if name else ""
                    if not name:
                        continue
                    att_names.append(name)
                    if ext: att_types.add(ext)
            except Exception:
                pass

            received = ""
            try:
                if msg.ReceivedTime:
                    received = str(msg.ReceivedTime)[:19]
            except Exception:
                pass

            sent = ""
            try:
                if msg.SentOn:
                    sent = str(msg.SentOn)[:19]
            except Exception:
                pass

            return {
                "entry_id": msg.EntryID,
                "subject": msg.Subject or "",
                "sender_name": msg.SenderName or "",
                "sender_email": self._get_sender_email(msg),
                "recipients": msg.To or "",
                "cc": msg.CC or "",
                "body_text": msg.Body or "",
                "html_body": html_body,
                "folder_name": fname,
                "received_at": received,
                "sent_at": sent,
                "has_attachments": 1 if att_names else 0,
                "attachment_count": len(att_names),
                "attachment_names": ", ".join(att_names),
                "attachment_types": ", ".join(sorted(att_types)),
                "importance": msg.Importance,
                "is_read": 0 if msg.UnRead else 1,
                "categories": msg.Categories or "",
                "conversation_id": msg.ConversationID or "",
                "last_modified": str(getattr(msg, "LastModificationTime", ""))[:19],
            }
        except Exception as e:
            logger.debug(f"메일 추출 실패: {e}")
            return None

    def _is_inline_or_signature_attachment(self, att, html_body: str = "") -> bool:
        """서명/본문 삽입 이미지처럼 실제 첨부가 아닌 항목을 제외한다.

        Outlook은 서명 이미지/본문 삽입 이미지를 Attachments에 함께 노출하는 경우가 많다.
        content-id, hidden 속성, HTML cid 참조 등을 이용해 첨부파일 목록에서 제외한다.
        """
        try:
            name = (att.FileName or "").lower()
            ext = os.path.splitext(name)[1].lower()
            is_image = ext in {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff"}
            pa = getattr(att, "PropertyAccessor", None)
            if pa:
                def prop(dasl):
                    try:
                        return pa.GetProperty(dasl)
                    except Exception:
                        return None

                hidden = prop("http://schemas.microsoft.com/mapi/proptag/0x7FFE000B")
                if hidden:
                    return True
                content_id = prop("http://schemas.microsoft.com/mapi/proptag/0x3712001F")
                content_location = prop("http://schemas.microsoft.com/mapi/proptag/0x3713001F")
                if is_image and (content_id or content_location):
                    return True
                if html_body and content_id and f"cid:{str(content_id).strip('<>')}".lower() in html_body.lower():
                    return True
            if is_image and html_body and name and name in html_body.lower():
                return True
            # Outlook 서명 이미지 기본 파일명 패턴
            if is_image and name.startswith(("image00", "image0", "oledata")):
                return True
        except Exception:
            return False
        return False

    def _get_sender_email(self, msg):
        try:
            if msg.SenderEmailType == "EX":
                sender = msg.Sender
                if sender:
                    ex = sender.GetExchangeUser()
                    if ex:
                        return ex.PrimarySmtpAddress or ""
            return msg.SenderEmailAddress or ""
        except Exception:
            try:
                return msg.SenderEmailAddress or ""
            except Exception:
                return ""

    def open_mail_in_outlook(self, entry_id):
        if not self._connected:
            return
        try:
            mail = self.mapi.GetItemFromID(entry_id)
            mail.Display()
        except Exception as e:
            logger.error(f"메일 열기 실패: {e}")


# ═══ Mock ═══

class MockOutlookConnector:
    def __init__(self):
        self._connected = False
        self._sample_emails = self._gen()

    def connect(self):
        self._connected = True
        logger.info("MockOutlookConnector 연결 (테스트 모드)")
        return True

    @property
    def is_connected(self):
        return self._connected

    def close(self):
        self._connected = False

    def get_default_folder(self, folder_id):
        return None  # Mock은 get_default_folder 미사용

    def get_folder_list(self):
        return [
            {"id": 6, "name": "받은편지함", "display_name": "받은 편지함", "count": 150},
            {"id": 5, "name": "보낸편지함", "display_name": "보낸 편지함", "count": 80},
            {"id": 16, "name": "임시보관함", "display_name": "임시 보관함", "count": 5},
            {"id": 3, "name": "지운편지함", "display_name": "지운 편지함", "count": 30},
        ]

    def _format_restrict_dates(self, after_date):
        """Outlook Items.Restrict에 사용할 날짜 문자열 후보 생성.

        Outlook Restrict는 ISO 문자열을 환경에 따라 제대로 처리하지 못할 수 있어
        Outlook이 선호하는 US date format 후보를 같이 시도한다.
        """
        dt = self._to_datetime(after_date)
        if not dt:
            return [str(after_date)]
        return [
            dt.strftime("%m/%d/%Y %I:%M %p"),
            dt.strftime("%m/%d/%Y %H:%M"),
            dt.strftime("%Y-%m-%d %H:%M:%S"),
        ]

    def _restrict_items_after(self, items, field: str, after_date):
        """날짜 조건으로 Items.Restrict를 시도하고 실패하면 None 반환."""
        for date_text in self._format_restrict_dates(after_date):
            try:
                return items.Restrict(f"[{field}] >= '{date_text}'")
            except Exception as e:
                logger.debug(f"Restrict 실패 field={field}, date={date_text}: {e}")
        return None

    def get_total_mail_count(self, folder_ids=None, include_subfolders=True,
                             after_date=None, incremental=False, mail_after_date=None):
        target_date = after_date or mail_after_date
        if target_date:
            return sum(1 for fid in (folder_ids or [6, 5]) for _ in self.iter_mails(fid, include_subfolders, after_date=target_date, incremental=incremental))
        return len(self._sample_emails)

    def iter_mails(self, folder_id, include_subfolders=True, after_date=None, incremental=False):
        fname = OlDefaultFolders.NAMES.get(folder_id, "기타")
        for e in self._sample_emails:
            if e["folder_name"] == fname:
                if after_date:
                    if incremental:
                        if e.get("last_modified", e.get("received_at", "")) < after_date:
                            continue
                    elif e["received_at"] < after_date:
                        continue
                yield e

    def open_mail_in_outlook(self, entry_id):
        logger.info(f"[Mock] 메일 열기: {entry_id}")

    def _gen(self):
        samples = []
        senders = [("김철수","kim.cs@company.com"),("이영희","lee.yh@company.com"),
                    ("박지현","park.jh@company.com"),("인사팀","hr@company.com"),
                    ("IT운영팀","it-ops@company.com"),("재무팀","finance@company.com"),
                    ("마케팅팀","marketing@company.com")]

        inbox_data = [
            ("RE: 2분기 OO프로젝트 진행 보고서","2분기 프로젝트 진행상황을 보고드립니다.\n첨부된 견적서를 참고하시어 검토 부탁드립니다.\n\n1. 프로젝트 일정: 예정대로 진행 중\n2. 예산 현황: 집행률 68%\n3. 주요 이슈: 인력 충원 필요",True,[("견적서_2분기.xlsx",".xlsx"),("진행보고서.pdf",".pdf")]),
            ("2026년 하반기 사업계획 회의 안내","하반기 사업계획 수립을 위한 회의를 안내드립니다.\n\n일시: 2026년 6월 3일(수) 14:00~16:00\n장소: 본사 10층 대회의실",True,[("회의안건.docx",".docx"),("사업계획_템플릿.pptx",".pptx")]),
            ("RE: 인사발령 통보","2026년 6월 1일자 인사발령을 통보드립니다.",True,[("인사발령_통보서.pdf",".pdf")]),
            ("서버 점검 안내 (5/30 02:00~06:00)","정기 서버 점검이 예정되어 있어 안내드립니다.",False,[]),
            ("월간 매출 현황 보고","5월 매출 현황을 보고드립니다. 전월 대비 12% 증가.",True,[("5월_매출현황.xlsx",".xlsx")]),
            ("보안 교육 필수 이수 안내","연례 정보보안 교육을 실시합니다. 기한 내 필수 이수.",False,[]),
            ("RE: 고객사 미팅 일정 조율","고객사 미팅 일정을 확정하였습니다. 6월 5일(금) 10:00",False,[]),
            ("FW: 견적서 검토 요청","아래 견적서 검토 부탁드립니다. 다음 주 수요일까지 피드백.",True,[("견적서_수정본.xlsx",".xlsx")]),
            ("2026년 상반기 성과평가 안내","상반기 성과평가 일정 안내. 자기평가 기간: 6/10~6/20",True,[("성과평가_양식.docx",".docx")]),
            ("RE: 신규 프로젝트 킥오프 미팅","신규 프로젝트 킥오프 미팅 참석 가능 여부를 회신 부탁.",False,[]),
        ]
        sent_data = [
            ("금주 주간 업무 보고","금주 업무 보고드립니다.\n1. OO 프로젝트: 개발 70% 완료\n2. 고객 미팅: 3건 완료",False,[]),
            ("FW: 견적서 검토 결과","검토 결과 첨부드립니다. 수정 사항 반영 부탁.",True,[("견적서_검토의견.xlsx",".xlsx")]),
            ("RE: 회의 참석 확인","회의 참석 확인합니다. 준비 자료 사전 공유하겠습니다.",False,[]),
            ("출장 보고서 제출","지난주 출장 보고서를 제출합니다.",True,[("출장보고서_0523.pdf",".pdf")]),
            ("RE: 예산 재편성 요청","예산 재편성 검토 의견 드립니다.",True,[("예산_재편성_의견.xlsx",".xlsx")]),
        ]

        base = datetime(2026, 5, 27, 14, 30)
        for i, (subj,body,has_att,atts) in enumerate(inbox_data):
            s = senders[i % len(senders)]
            dt = base - timedelta(hours=i*8+1, minutes=i*13)
            samples.append({"entry_id":f"MOCK_INBOX_{i:04d}","subject":subj,"sender_name":s[0],"sender_email":s[1],
                "recipients":"나","cc":"" if i%3!=0 else senders[(i+1)%len(senders)][0],
                "body_text":body,"html_body":"","folder_name":"받은편지함",
                "received_at":dt.strftime("%Y-%m-%d %H:%M:%S"),"sent_at":(dt-timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S"),
                "has_attachments":1 if has_att else 0,"attachment_count":len(atts),
                "attachment_names":", ".join(a[0] for a in atts),"attachment_types":", ".join(set(a[1] for a in atts)),
                "importance":2 if i<2 else 1,"is_read":0 if i==2 else 1,"categories":"","conversation_id":f"CONV_{i:04d}","last_modified":dt.strftime("%Y-%m-%d %H:%M:%S")})

        for i, (subj,body,has_att,atts) in enumerate(sent_data):
            r = senders[i % len(senders)]
            dt = base - timedelta(hours=i*12+3, minutes=i*7)
            samples.append({"entry_id":f"MOCK_SENT_{i:04d}","subject":subj,"sender_name":"나","sender_email":"me@company.com",
                "recipients":r[0],"cc":"","body_text":body,"html_body":"","folder_name":"보낸편지함",
                "received_at":dt.strftime("%Y-%m-%d %H:%M:%S"),"sent_at":dt.strftime("%Y-%m-%d %H:%M:%S"),
                "has_attachments":1 if has_att else 0,"attachment_count":len(atts),
                "attachment_names":", ".join(a[0] for a in atts),"attachment_types":", ".join(set(a[1] for a in atts)),
                "importance":1,"is_read":1,"categories":"","conversation_id":f"CONV_SENT_{i:04d}","last_modified":dt.strftime("%Y-%m-%d %H:%M:%S")})
        return samples


def create_connector(use_mock=False):
    if use_mock:
        logger.info("Mock 모드로 OutlookConnector 생성")
        return MockOutlookConnector()
    if not HAS_WIN32:
        # Windows 배포본에서 조용히 Mock으로 전환되면 사용자가 실제 Outlook 동기화 실패를 알 수 없다.
        # 따라서 Windows에서는 명시적으로 오류를 발생시켜 원인을 UI/로그에 표시한다.
        if sys.platform == "win32":
            raise OutlookConnectionError(
                "pywin32/win32com 모듈이 없어 Outlook 동기화를 사용할 수 없습니다. "
                f"원인: {WIN32_IMPORT_ERROR}"
            )
        return MockOutlookConnector()
    return OutlookConnector()

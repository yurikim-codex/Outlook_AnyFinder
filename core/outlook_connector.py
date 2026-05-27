"""
OutLook AnyFinder Ver0.9 for SESUNG Team
[M01] Outlook 연결 (v2 — COM 스레드 안전 + 폴더 접근 복구)
"""

import os
import sys
import logging
from typing import List, Optional, Generator
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

try:
    import win32com.client
    import pythoncom  # COM 스레드 초기화 필요
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False


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

    def connect(self) -> bool:
        if not HAS_WIN32:
            raise OutlookConnectionError("win32com 미설치")

        try:
            # ★ COM 스레드 초기화 (QThread에서 호출 시 필수)
            pythoncom.CoInitialize()

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
            raise OutlookConnectionError(f"Outlook 연결 실패: {e}")

    @property
    def is_connected(self):
        return self._connected

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

    def get_total_mail_count(self, folder_ids=None, include_subfolders=True):
        folder_ids = folder_ids or [OlDefaultFolders.INBOX, OlDefaultFolders.SENT]
        total = 0
        for fid in folder_ids:
            folder = self.get_default_folder(fid)
            if folder:
                try:
                    total += folder.Items.Count
                    if include_subfolders:
                        total += self._count_subs(folder)
                except Exception:
                    pass
        return total

    def _count_subs(self, parent):
        count = 0
        try:
            for i in range(1, parent.Folders.Count + 1):
                sub = parent.Folders.Item(i)
                count += sub.Items.Count
                count += self._count_subs(sub)
        except Exception:
            pass
        return count

    def iter_mails(self, folder_id, include_subfolders=True, after_date=None):
        folder = self.get_default_folder(folder_id)
        if not folder:
            logger.warning(f"폴더를 찾을 수 없음 (ID={folder_id})")
            return

        fname = OlDefaultFolders.NAMES.get(folder_id, folder.Name)
        yield from self._iter_folder(folder, fname, after_date)
        if include_subfolders:
            yield from self._iter_subs(folder, after_date)

    def _iter_subs(self, parent, after_date=None):
        try:
            for i in range(1, parent.Folders.Count + 1):
                sub = parent.Folders.Item(i)
                yield from self._iter_folder(sub, sub.Name, after_date)
                yield from self._iter_subs(sub, after_date)
        except Exception:
            pass

    def _iter_folder(self, folder, fname, after_date=None):
        try:
            items = folder.Items
            items.Sort("[ReceivedTime]", True)

            if after_date:
                try:
                    items = items.Restrict(f"[ReceivedTime] > '{after_date}'")
                except Exception:
                    pass

            for msg in items:
                try:
                    if msg.Class == 43:
                        data = self._extract(msg, fname)
                        if data:
                            yield data
                except Exception:
                    continue
        except Exception as e:
            logger.error(f"폴더 '{fname}' 순회 오류: {e}")

    def _extract(self, msg, fname):
        try:
            att_names, att_types = [], set()
            try:
                for i in range(1, msg.Attachments.Count + 1):
                    att = msg.Attachments.Item(i)
                    name = att.FileName or ""
                    ext = os.path.splitext(name)[1].lower() if name else ""
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
                "html_body": "",
                "folder_name": fname,
                "received_at": received,
                "sent_at": sent,
                "has_attachments": 1 if msg.Attachments.Count > 0 else 0,
                "attachment_count": msg.Attachments.Count,
                "attachment_names": ", ".join(att_names),
                "attachment_types": ", ".join(sorted(att_types)),
                "importance": msg.Importance,
                "is_read": 0 if msg.UnRead else 1,
                "categories": msg.Categories or "",
                "conversation_id": msg.ConversationID or "",
            }
        except Exception as e:
            logger.debug(f"메일 추출 실패: {e}")
            return None

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

    def get_default_folder(self, folder_id):
        return None  # Mock은 get_default_folder 미사용

    def get_folder_list(self):
        return [
            {"id": 6, "name": "받은편지함", "display_name": "받은 편지함", "count": 150},
            {"id": 5, "name": "보낸편지함", "display_name": "보낸 편지함", "count": 80},
            {"id": 16, "name": "임시보관함", "display_name": "임시 보관함", "count": 5},
            {"id": 3, "name": "지운편지함", "display_name": "지운 편지함", "count": 30},
        ]

    def get_total_mail_count(self, folder_ids=None, include_subfolders=True):
        return len(self._sample_emails)

    def iter_mails(self, folder_id, include_subfolders=True, after_date=None):
        fname = OlDefaultFolders.NAMES.get(folder_id, "기타")
        for e in self._sample_emails:
            if e["folder_name"] == fname:
                if after_date and e["received_at"] < after_date:
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
                "importance":2 if i<2 else 1,"is_read":0 if i==2 else 1,"categories":"","conversation_id":f"CONV_{i:04d}"})

        for i, (subj,body,has_att,atts) in enumerate(sent_data):
            r = senders[i % len(senders)]
            dt = base - timedelta(hours=i*12+3, minutes=i*7)
            samples.append({"entry_id":f"MOCK_SENT_{i:04d}","subject":subj,"sender_name":"나","sender_email":"me@company.com",
                "recipients":r[0],"cc":"","body_text":body,"html_body":"","folder_name":"보낸편지함",
                "received_at":dt.strftime("%Y-%m-%d %H:%M:%S"),"sent_at":dt.strftime("%Y-%m-%d %H:%M:%S"),
                "has_attachments":1 if has_att else 0,"attachment_count":len(atts),
                "attachment_names":", ".join(a[0] for a in atts),"attachment_types":", ".join(set(a[1] for a in atts)),
                "importance":1,"is_read":1,"categories":"","conversation_id":f"CONV_SENT_{i:04d}"})
        return samples


def create_connector(use_mock=False):
    if use_mock or not HAS_WIN32:
        return MockOutlookConnector()
    return OutlookConnector()

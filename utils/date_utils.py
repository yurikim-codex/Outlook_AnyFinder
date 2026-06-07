"""
OutLook AnyFinder Ver0.9.1.1 for SESUNG Team
[T02] 날짜 파싱/포맷 유틸리티
"""

from datetime import datetime, timedelta


def format_outlook_date(com_date) -> str:
    """Outlook COM 날짜 → ISO 8601 문자열"""
    if com_date is None:
        return ""
    try:
        if hasattr(com_date, 'isoformat'):
            return com_date.isoformat()
        # pywintypes.datetime → str
        return str(com_date).replace('+00:00', '')
    except Exception:
        return str(com_date)[:19]


def format_display_date(iso_str: str) -> str:
    """ISO 문자열 → 사용자 친화적 표시"""
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(iso_str[:19])
        now = datetime.now()
        diff = now - dt

        if diff.days == 0:
            return dt.strftime("%H:%M")
        elif diff.days == 1:
            return "어제 " + dt.strftime("%H:%M")
        elif diff.days < 7:
            weekdays = ["월", "화", "수", "목", "금", "토", "일"]
            return f"{weekdays[dt.weekday()]}요일 {dt.strftime('%H:%M')}"
        elif dt.year == now.year:
            return dt.strftime("%m/%d %H:%M")
        else:
            return dt.strftime("%Y-%m-%d")
    except Exception:
        return iso_str[:16]


def get_date_filter_range(filter_name: str) -> tuple:
    """필터 이름 → (start_date, end_date) ISO 문자열"""
    now = datetime.now()

    ranges = {
        "오늘": timedelta(days=1),
        "최근 7일": timedelta(days=7),
        "최근 30일": timedelta(days=30),
        "최근 3개월": timedelta(days=90),
        "최근 6개월": timedelta(days=180),
        "최근 1년": timedelta(days=365),
    }

    if filter_name == "전체 기간":
        return (None, None)

    delta = ranges.get(filter_name)
    if delta:
        start = (now - delta).isoformat()[:19]
        end = now.isoformat()[:19]
        return (start, end)

    return (None, None)

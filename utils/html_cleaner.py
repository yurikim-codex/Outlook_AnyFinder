"""
OutLook AnyFinder Ver0.9 for SESUNG Team
[T01] HTML → 평문 변환 유틸리티
"""

import re
try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False


def strip_html(html: str) -> str:
    """HTML 문자열을 평문 텍스트로 변환"""
    if not html:
        return ""

    if HAS_BS4:
        return _strip_with_bs4(html)
    else:
        return _strip_with_regex(html)


def _strip_with_bs4(html: str) -> str:
    """BeautifulSoup을 사용한 HTML 제거 (권장)"""
    soup = BeautifulSoup(html, "html.parser")

    # <br>, <br/> → 줄바꿈
    for br in soup.find_all("br"):
        br.replace_with("\n")

    # <p>, <div> → 줄바꿈
    for tag in soup.find_all(["p", "div", "tr", "li"]):
        tag.insert_before("\n")

    text = soup.get_text()
    return _clean_whitespace(text)


def _strip_with_regex(html: str) -> str:
    """정규식 기반 HTML 제거 (bs4 없을 때 폴백)"""
    # 스크립트/스타일 제거
    text = re.sub(r'<(script|style)[^>]*>.*?</\1>', '', html, flags=re.DOTALL | re.IGNORECASE)
    # <br> → 줄바꿈
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    # <p>, <div> → 줄바꿈
    text = re.sub(r'</(p|div|tr|li)>', '\n', text, flags=re.IGNORECASE)
    # 모든 태그 제거
    text = re.sub(r'<[^>]+>', '', text)
    # HTML 엔티티 디코딩
    text = _decode_entities(text)
    return _clean_whitespace(text)


def _decode_entities(text: str) -> str:
    """HTML 엔티티 디코딩"""
    import html
    return html.unescape(text)


def _clean_whitespace(text: str) -> str:
    """불필요한 공백/줄바꿈 정리"""
    # 연속 공백 → 단일 공백
    text = re.sub(r'[^\S\n]+', ' ', text)
    # 연속 줄바꿈 → 최대 2개
    text = re.sub(r'\n{3,}', '\n\n', text)
    # 줄 앞뒤 공백 제거
    lines = [line.strip() for line in text.split('\n')]
    text = '\n'.join(lines)
    return text.strip()

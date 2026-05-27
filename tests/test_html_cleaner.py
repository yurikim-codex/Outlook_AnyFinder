"""
OutLook AnyFinder Ver0.9 for SESUNG Team
HTML 변환 테스트
"""

import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.html_cleaner import strip_html


class TestHtmlCleaner:

    def test_01_simple_p_tag(self):
        assert strip_html("<p>Hello</p>").strip() == "Hello"

    def test_02_bold_tag(self):
        result = strip_html("<b>굵은</b> 글씨")
        assert "굵은" in result
        assert "글씨" in result
        assert "<b>" not in result

    def test_03_br_tag(self):
        result = strip_html("줄1<br/>줄2")
        assert "줄1" in result
        assert "줄2" in result

    def test_04_complex_html(self):
        html = "<html><body><table><tr><td>셀1</td><td>셀2</td></tr></table></body></html>"
        result = strip_html(html)
        assert "셀1" in result
        assert "셀2" in result
        assert "<" not in result

    def test_05_none_input(self):
        assert strip_html(None) == ""

    def test_06_empty_string(self):
        assert strip_html("") == ""

    def test_07_html_entities(self):
        result = strip_html("A &amp; B &lt; C")
        assert "&" in result
        assert "<" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

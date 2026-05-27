"""
OutLook AnyFinder Ver0.9 for SESUNG Team
[T03] 설정 파일 관리
"""

import json
from pathlib import Path

CONFIG_DIR = Path.home() / ".outlook_anyfinder"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_CONFIG = {
    "indexing": {
        "folders": ["받은편지함", "보낸편지함"],
        "include_subfolders": True,
        "range_months": 6,
    },
    "sync": {
        "auto_sync": True,
        "interval_minutes": 10,
    },
    "search": {
        "results_per_page": 20,
        "default_sort": "relevance",    # "relevance" | "newest" | "oldest"
        "autocomplete_delay_ms": 300,
        "max_autocomplete_items": 8,
        "max_related_keywords": 6,
    },
    "ui": {
        "theme": "dark",
        "sidebar_width": 230,
        "preview_ratio": 0.5,
    },
    "first_run_completed": False,
}


def load_config() -> dict:
    """설정 파일 로드 (없으면 기본값)"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                user_config = json.load(f)
            # 기본값과 머지 (새 키가 추가됐을 때 대비)
            return _deep_merge(DEFAULT_CONFIG, user_config)
        except (json.JSONDecodeError, Exception):
            return DEFAULT_CONFIG.copy()
    else:
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()


def save_config(config: dict):
    """설정 파일 저장"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def _deep_merge(base: dict, override: dict) -> dict:
    """딕셔너리 깊은 머지"""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result

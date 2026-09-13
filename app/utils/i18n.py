"""i18n: JSON locales (uz default, en, ru). Server-side t() helper."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

LOCALES_DIR = Path(__file__).resolve().parent.parent.parent / "locales"
SUPPORTED = ("uz", "en", "ru")
DEFAULT_LANG = "uz"


@lru_cache(maxsize=8)
def _load(lang: str) -> dict:
    path = LOCALES_DIR / f"{lang}.json"
    if not path.exists():
        path = LOCALES_DIR / f"{DEFAULT_LANG}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def normalize_lang(lang: str | None) -> str:
    lang = (lang or "").lower().split("-")[0].split("_")[0]
    return lang if lang in SUPPORTED else DEFAULT_LANG


def t(key: str, lang: str | None = None, **kwargs) -> str:
    lang = normalize_lang(lang)
    text = _load(lang).get(key)
    if text is None and lang != DEFAULT_LANG:
        text = _load(DEFAULT_LANG).get(key)
    if text is None:
        text = key
    if kwargs:
        try:
            text = text.format(**kwargs)
        except Exception:
            pass
    return text

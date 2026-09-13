"""Server-side i18n: loads locales/*.json, `t(key, lang)` lookup."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

LOCALES_DIR = Path(__file__).resolve().parent.parent.parent / "locales"
SUPPORTED_LANGS = ("uz", "en", "ru")
DEFAULT_LANG = "uz"


@lru_cache(maxsize=8)
def _load(lang: str) -> dict:
    path = LOCALES_DIR / f"{lang}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        if lang != DEFAULT_LANG:
            return _load(DEFAULT_LANG)
        return {}


def normalize_lang(lang: str | None) -> str:
    lang = (lang or "").lower().split("-")[0]
    return lang if lang in SUPPORTED_LANGS else DEFAULT_LANG


def t(key: str, lang: str | None = None, default: str | None = None, **kwargs) -> str:
    lang = normalize_lang(lang)
    data = _load(lang)
    node: object = data
    for part in key.split("."):
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            node = None
            break
    if not isinstance(node, str):
        if lang != DEFAULT_LANG:
            return t(key, DEFAULT_LANG, default=default, **kwargs)
        node = default if default is not None else key
    try:
        return node.format(**kwargs)
    except Exception:
        return node


def get_translator(lang: str | None):
    lang = normalize_lang(lang)

    def _t(key: str, default: str | None = None, **kwargs) -> str:
        return t(key, lang, default=default, **kwargs)

    return _t


def all_strings(lang: str | None = None) -> dict:
    return dict(_load(normalize_lang(lang)))

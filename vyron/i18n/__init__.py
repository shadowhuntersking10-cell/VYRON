"""VYRON internationalization — Uzbek (default), English, Russian.

No UI text is hardcoded in templates/components; everything goes through
t(key, lang) with JSON dictionaries per locale. The selected language persists
in a cookie (and on the user profile when logged in).
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

SUPPORTED_LANGUAGES = ("uz", "en", "ru")
DEFAULT_LANGUAGE = "uz"
LANGUAGE_COOKIE = "vyron_lang"
LANGUAGE_LABELS = {
    "uz": {"flag": "🇺🇿", "native": "O'zbekcha", "english": "Uzbek"},
    "en": {"flag": "🇬🇧", "native": "English", "english": "English"},
    "ru": {"flag": "🇷🇺", "native": "Русский", "english": "Russian"},
}

_LOCALE_DIR = os.path.join(os.path.dirname(__file__), "locales")
_catalogs: Dict[str, Dict[str, Any]] = {}


def _load(lang: str) -> Dict[str, Any]:
    if lang not in _catalogs:
        path = os.path.join(_LOCALE_DIR, f"{lang}.json")
        with open(path, encoding="utf-8") as fh:
            _catalogs[lang] = json.load(fh)
    return _catalogs[lang]


def reload_catalogs() -> None:
    _catalogs.clear()


def normalize_lang(lang: Optional[str]) -> str:
    if not lang:
        return DEFAULT_LANGUAGE
    lang = lang.strip().lower().replace("_", "-")
    if lang.startswith("uz"):
        return "uz"
    if lang.startswith("ru"):
        return "ru"
    if lang.startswith("en"):
        return "en"
    return DEFAULT_LANGUAGE


def t(key: str, lang: Optional[str] = None, **params: Any) -> str:
    """Translate `key` (dot.path) into `lang`, interpolating {params}.

    Falls back: requested lang -> English -> the key itself (visible, never blank).
    """
    language = normalize_lang(lang)
    value = _lookup(key, language)
    if value is None:
        value = _lookup(key, "en")
    if value is None:
        return key
    if params:
        try:
            return value.format(**params)
        except (KeyError, IndexError, ValueError):
            return value
    return value


def _lookup(key: str, lang: str) -> Optional[str]:
    node: Any = _load(lang)
    for part in key.split("."):
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return None
    return node if isinstance(node, str) else None


def catalog(lang: str) -> Dict[str, Any]:
    """Full catalog (used by /api/i18n/{lang} for client-side translation)."""
    return _load(normalize_lang(lang))


def flatten(catalog_dict: Dict[str, Any], prefix: str = "") -> Dict[str, str]:
    flat: Dict[str, str] = {}
    for key, value in catalog_dict.items():
        full = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            flat.update(flatten(value, full))
        else:
            flat[full] = str(value)
    return flat

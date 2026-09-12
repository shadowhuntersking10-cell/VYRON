"""i18n bundle endpoint for JS clients (SSR pages embed their bundle)."""

from __future__ import annotations

from fastapi import APIRouter

from vyron.api.deps import ok
from vyron.i18n import SUPPORTED_LANGUAGES, catalog, normalize_lang

router = APIRouter(prefix="/api/i18n", tags=["i18n"])


@router.get("/{lang}")
def bundle(lang: str):
    language = normalize_lang(lang)
    return ok({"locale": language, "messages": catalog(language), "supported": list(SUPPORTED_LANGUAGES)})

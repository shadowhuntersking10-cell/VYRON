from fastapi import APIRouter

from app.utils.i18n import SUPPORTED_LANGS, all_strings, normalize_lang

router = APIRouter(prefix="/api/locale", tags=["locale"])


@router.get("/{lang}")
async def get_locale(lang: str) -> dict:
    lang = normalize_lang(lang)
    return {"lang": lang, "strings": all_strings(lang), "supported": list(SUPPORTED_LANGS)}

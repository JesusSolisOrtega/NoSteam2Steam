"""Internationalization (i18n) and localization subsystem.

Provides automatic detection of the system locale, lazy-loaded JSON translation catalogs,
manual language override selection, and persistent configuration.
"""

import json
import locale
import logging
import os
from pathlib import Path
import sys
from typing import Any, Dict, Iterator, Optional, Tuple

logger = logging.getLogger(__name__)

SUPPORTED_LANGUAGES: Dict[str, str] = {
    "en": "English",
    "es": "Español",
    "gl": "Galego",
    "eu": "Euskara",
    "ca": "Valencià",
    "de": "Deutsch",
    "fr": "Français",
    "it": "Italiano",
    "pt": "Português",
    "ru": "Русский",
    "tr": "Türkçe",
    "ko": "한국어",
    "ar": "العربية",
    "id": "Bahasa Indonesia",
    "sw": "Kiswahili",
    "hi": "हिन्दी",
    "ur": "اردو",
    "zh": "简体中文",
    "ja": "日本語",
}

DEFAULT_LANGUAGE = "en"
_current_language: Optional[str] = None
LANGUAGE_FILE: Optional[str] = None
_loaded_catalogs: Dict[str, Dict[str, str]] = {}


def get_language_file() -> str:
    """Returns the path to the language configuration file, resolving lazily to avoid circular imports."""
    global LANGUAGE_FILE
    if LANGUAGE_FILE is None:
        try:
            from nosteam2steam.config import LANGUAGE_FILE as _LF

            LANGUAGE_FILE = _LF
        except Exception:
            LANGUAGE_FILE = os.path.expanduser("~/.local/share/noSteam2Steam/language.txt")
    return LANGUAGE_FILE


def get_locale_file_path(lang_code: str) -> Optional[Path]:
    """Resolves the filesystem path for a specific language's JSON catalog."""
    code = lang_code.strip().lower()
    if code in ("val", "valencia", "valencian", "valenciano", "valencià"):
        code = "ca"
    elif code in ("pakistan", "pakistani", "urdu"):
        code = "ur"

    # Check within package directory
    pkg_locale = Path(__file__).resolve().parent / "locales" / f"{code}.json"
    if pkg_locale.is_file():
        return pkg_locale

    # Check PyInstaller frozen bundle (_MEIPASS)
    base_meipass = getattr(sys, "_MEIPASS", None)
    if base_meipass:
        meipass_locale = Path(base_meipass) / "nosteam2steam" / "locales" / f"{code}.json"
        if meipass_locale.is_file():
            return meipass_locale

    return None


def load_locale_catalog(lang_code: str) -> Dict[str, str]:
    """
    Loads and caches the translation dictionary for the specified language code.
    Returns an empty dictionary for the default English locale or if file is missing.
    """
    code = lang_code.strip().lower()
    if code == DEFAULT_LANGUAGE:
        return {}

    if code in _loaded_catalogs:
        return _loaded_catalogs[code]

    path = get_locale_file_path(code)
    if not path or not path.is_file():
        logger.debug(f"Translation catalog for '{code}' not found.")
        _loaded_catalogs[code] = {}
        return _loaded_catalogs[code]

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                _loaded_catalogs[code] = data
                return data
    except Exception as e:
        logger.error(f"Failed to load translation catalog from {path}: {e}")

    _loaded_catalogs[code] = {}
    return _loaded_catalogs[code]


def detect_system_language() -> str:
    """
    Detects the primary system language code from environment variables or standard locale.
    Falls back to DEFAULT_LANGUAGE ('en') if not determinable or unsupported.
    """
    env_vars = ["LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"]
    for var in env_vars:
        val = os.environ.get(var)
        if val:
            low = val.lower()
            if "@valencia" in low or low.startswith("val"):
                return "ca"
            primary = val.split(":")[0].split(".")[0].split("_")[0].split("@")[0].lower()
            if primary == "val":
                return "ca"
            if primary in SUPPORTED_LANGUAGES:
                return primary

    try:
        loc = locale.getlocale(locale.LC_MESSAGES)[0]
        if loc:
            low = loc.lower()
            if "@valencia" in low or low.startswith("val"):
                return "ca"
            primary = loc.split("_")[0].split("@")[0].lower()
            if primary in SUPPORTED_LANGUAGES:
                return primary
    except Exception:
        pass

    try:
        loc = locale.getlocale()[0]
        if loc:
            low = loc.lower()
            if "@valencia" in low or low.startswith("val"):
                return "ca"
            primary = loc.split("_")[0].split("@")[0].lower()
            if primary in SUPPORTED_LANGUAGES:
                return primary
    except Exception:
        pass

    return DEFAULT_LANGUAGE


def get_current_language() -> str:
    """
    Returns the currently active language code, resolving in priority order:
    1. Active runtime session override.
    2. Persisted preference in LANGUAGE_FILE.
    3. Auto-detected system locale.
    """
    global _current_language
    if _current_language and _current_language in SUPPORTED_LANGUAGES:
        return _current_language

    lang_file = get_language_file()
    if os.path.exists(lang_file):
        try:
            with open(lang_file, "r", encoding="utf-8") as f:
                saved = f.read().strip().lower()
                if saved in SUPPORTED_LANGUAGES:
                    _current_language = saved
                    return saved
        except Exception as e:
            logger.debug(f"Could not read language configuration: {e}")

    detected = detect_system_language()
    _current_language = detected
    return detected


def set_language(lang_code: str, persist: bool = True) -> bool:
    """Sets the active runtime language and optionally persists the choice to disk."""
    global _current_language
    code = lang_code.strip().lower()
    if code in ("val", "valencia", "valencian", "valenciano", "valencià"):
        code = "ca"
    elif code in ("pakistan", "pakistani", "urdu"):
        code = "ur"
    elif code in ("pakistan", "pakistani", "urdu"):
        code = "ur"
    if code not in SUPPORTED_LANGUAGES:
        logger.warning(f"Unsupported language code '{code}'. Reverting to '{DEFAULT_LANGUAGE}'.")
        code = DEFAULT_LANGUAGE

    _current_language = code

    if persist:
        lang_file = get_language_file()
        try:
            os.makedirs(os.path.dirname(lang_file), exist_ok=True)
            with open(lang_file, "w", encoding="utf-8") as f:
                f.write(code + "\n")
            logger.info(f"Language preference persisted: {code} ({SUPPORTED_LANGUAGES.get(code)})")
            return True
        except Exception as e:
            logger.error(f"Failed to persist language preference: {e}")
            return False

    return True


class _TranslationsProxy(dict):
    """
    Transparent dictionary proxy for backward-compatible access to translation catalogs,
    loading individual language catalogs lazily from disk.
    """

    def __getitem__(self, lang: str) -> Dict[str, str]:
        return load_locale_catalog(lang)

    def __contains__(self, lang: object) -> bool:
        return isinstance(lang, str) and lang in SUPPORTED_LANGUAGES and lang != DEFAULT_LANGUAGE

    def get(self, lang: str, default: Optional[Dict[str, str]] = None) -> Dict[str, str]:  # type: ignore[override]
        if lang in self:
            return load_locale_catalog(lang)
        return default if default is not None else {}

    def items(self) -> Iterator[Tuple[str, Dict[str, str]]]:  # type: ignore[override]
        for lang in SUPPORTED_LANGUAGES:
            if lang != DEFAULT_LANGUAGE:
                yield lang, load_locale_catalog(lang)

    def keys(self) -> list[str]:  # type: ignore[override]
        return [lang for lang in SUPPORTED_LANGUAGES if lang != DEFAULT_LANGUAGE]


TRANSLATIONS: Dict[str, Dict[str, str]] = _TranslationsProxy()


def _(text: str, **kwargs: Any) -> str:
    """
    Translates a source English text string to the active locale.
    Falls back to original English text formatted with kwargs if translation is missing.
    """
    lang = get_current_language()
    if lang != DEFAULT_LANGUAGE:
        catalog = load_locale_catalog(lang)
        template = catalog.get(text, text)
    else:
        template = text

    if kwargs:
        try:
            return template.format(**kwargs)
        except Exception:
            return template

    return template


def select_language_dialog() -> Optional[str]:
    """Displays a graphical menu allowing the user to select and persist an interface language."""
    from nosteam2steam import ui

    items = [(code, name) for code, name in SUPPORTED_LANGUAGES.items()]
    selected = ui.show_menu(
        title=_("Select Interface Language"),
        text=_("Choose your preferred interface language:"),
        menu_items=items,
        width=380,
        height=380,
    )

    if selected and selected in SUPPORTED_LANGUAGES:
        set_language(selected, persist=True)
        lang_name = SUPPORTED_LANGUAGES[selected]
        ui.show_info(
            title=_("Select Interface Language"),
            text=_("Language updated to {lang}.", lang=lang_name),
            width=320,
        )
        return selected

    return None

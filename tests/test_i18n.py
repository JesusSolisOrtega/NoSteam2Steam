import os
import re
from unittest.mock import patch
import pytest

from nosteam2steam import i18n
from nosteam2steam.i18n import (
    DEFAULT_LANGUAGE,
    SUPPORTED_LANGUAGES,
    TRANSLATIONS,
    _,
    detect_system_language,
    get_current_language,
    select_language_dialog,
    set_language,
)


@pytest.fixture(autouse=True)
def reset_i18n_state(tmp_path, monkeypatch):
    """Resets i18n global state and redirects language file to tmp_path for each test."""
    test_lang_file = str(tmp_path / "language.txt")
    monkeypatch.setattr(i18n, "LANGUAGE_FILE", test_lang_file)
    i18n._current_language = None
    yield
    i18n._current_language = None


class TestLanguageDetection:
    @pytest.mark.parametrize(
        "env_var,locale_str,expected",
        [
            ("LANGUAGE", "es_ES:es", "es"),
            ("LC_ALL", "de_DE.UTF-8", "de"),
            ("LC_MESSAGES", "fr_FR.UTF-8", "fr"),
            ("LANG", "ja_JP.UTF-8", "ja"),
            ("LANG", "zh_CN.UTF-8", "zh"),
            ("LANG", "it_IT.UTF-8", "it"),
            ("LANG", "pt_BR.UTF-8", "pt"),
            ("LANG", "ru_RU.UTF-8", "ru"),
            ("LANG", "ca_ES.UTF-8", "ca"),
            ("LANG", "ca_ES.UTF-8@valencia", "ca"),
            ("LANG", "val_ES.UTF-8", "ca"),
            ("LANG", "gl_ES.UTF-8", "gl"),
            ("LANG", "eu_ES.UTF-8", "eu"),
            ("LANG", "tr_TR.UTF-8", "tr"),
            ("LANG", "ko_KR.UTF-8", "ko"),
            ("LANG", "id_ID.UTF-8", "id"),
            ("LANG", "sw_KE.UTF-8", "sw"),
            ("LANG", "ar_EG.UTF-8", "ar"),
            ("LANG", "hi_IN.UTF-8", "hi"),
            ("LANG", "ur_PK.UTF-8", "ur"),
            ("LANG", "en_US.UTF-8", "en"),
        ],
    )
    def test_detect_system_language_env_vars(self, monkeypatch, env_var, locale_str, expected):
        for var in ["LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"]:
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setenv(env_var, locale_str)
        assert detect_system_language() == expected

    def test_detect_system_language_unsupported_fallback(self, monkeypatch):
        for var in ["LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"]:
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setenv("LANG", "xx_YY.UTF-8")
        assert detect_system_language() == DEFAULT_LANGUAGE


class TestLanguageConfiguration:
    def test_set_and_get_language_in_memory(self):
        set_language("es", persist=False)
        assert get_current_language() == "es"

        set_language("de", persist=False)
        assert get_current_language() == "de"

    def test_set_language_persistence(self, tmp_path):
        test_file = str(tmp_path / "language.txt")
        assert set_language("fr", persist=True) is True
        assert os.path.exists(test_file)
        with open(test_file, "r", encoding="utf-8") as f:
            assert f.read().strip() == "fr"

        # Verify get_current_language reads from file when memory is cleared
        i18n._current_language = None
        assert get_current_language() == "fr"

    def test_set_language_unsupported_reverts_to_default(self):
        set_language("invalid_locale", persist=False)
        assert get_current_language() == DEFAULT_LANGUAGE


class TestTranslationFunction:
    def test_english_translation(self):
        set_language("en", persist=False)
        assert _("Exit") == "Exit"
        assert _("Language updated to {lang}.", lang="English") == "Language updated to English."

    def test_spanish_translation(self):
        set_language("es", persist=False)
        assert _("Exit") == "Salir"
        assert _("Cleanup Options") == "Opciones de Limpieza"
        assert _("Save Manager") == "Gestor de Partidas Guardadas"
        assert _("Rollback") == "Reversión"
        assert _("Direction") == "Dirección"
        assert _("Unidentified Games Detected") == "Juegos No Identificados Detectados"
        assert _("Backup repository -> Local save") == "Repositorio de respaldos -> Partida local"
        assert (
            _("Successfully restored {name} to its previous snapshot.", name="Game.7z")
            == "Se ha restaurado con éxito Game.7z a su copia instantánea previa."
        )
        assert (
            _("Language updated to {lang}.", lang="Español")
            == "Idioma actualizado a Español."
        )

    def test_german_translation(self):
        set_language("de", persist=False)
        assert _("Exit") == "Beenden"
        assert _("Cleanup Options") == "Bereinigungsoptionen"

    def test_french_translation(self):
        set_language("fr", persist=False)
        assert _("Exit") == "Quitter"
        assert _("Cleanup Options") == "Options de Nettoyage"

    def test_valencian_translation(self):
        set_language("ca", persist=False)
        assert _("Exit") == "Eixir"
        assert _("Cleanup Options") == "Opcions de Neteja"
        assert _("Save Manager") == "Gestor de Partides Guardades"
        assert _("Rollback") == "Reversió"
        assert _("Unidentified Games Detected") == "Jocs No Identificats Detectats"

        set_language("val", persist=False)
        assert get_current_language() == "ca"
        assert _("Exit") == "Eixir"
        assert _("Rollback") == "Reversió"

    def test_galician_translation(self):
        set_language("gl", persist=False)
        assert _("Exit") == "Saír"
        assert _("Cleanup Options") == "Opcións de Limpeza"
        assert _("Save Manager") == "Xestor de Partidas Gardadas"

    def test_basque_translation(self):
        set_language("eu", persist=False)
        assert _("Exit") == "Irten"
        assert _("Cleanup Options") == "Garbiketa Aukerak"
        assert _("Save Manager") == "Gordetako Partiden Kudeatzailea"

    def test_turkish_translation(self):
        set_language("tr", persist=False)
        assert _("Exit") == "Çıkış"
        assert _("Cleanup Options") == "Temizleme Seçenekleri"

    def test_korean_translation(self):
        set_language("ko", persist=False)
        assert _("Exit") == "종료"
        assert _("Cleanup Options") == "정리 옵션"

    def test_indonesian_translation(self):
        set_language("id", persist=False)
        assert _("Exit") == "Keluar"
        assert _("Cleanup Options") == "Opsi Pembersihan"

    def test_swahili_translation(self):
        set_language("sw", persist=False)
        assert _("Exit") == "Toka"
        assert _("Cleanup Options") == "Chaguo za Kusafisha"

    def test_arabic_translation(self):
        set_language("ar", persist=False)
        assert _("Exit") == "خروج"
        assert _("Cleanup Options") == "خيارات التنظيف"

    def test_hindi_translation(self):
        set_language("hi", persist=False)
        assert _("Exit") == "बाहर निकलें"
        assert _("Cleanup Options") == "सफ़ाई विकल्प"

    def test_urdu_translation(self):
        set_language("ur", persist=False)
        assert _("Exit") == "باہر نکلیں"
        assert _("Cleanup Options") == "صفائی کے آپشنز"

        set_language("pakistani", persist=False)
        assert get_current_language() == "ur"
        assert _("Exit") == "باہر نکلیں"

    def test_missing_key_falls_back_to_english_template(self):
        set_language("es", persist=False)
        non_existent_key = "This is an uncatalogued string for testing: {foo}"
        assert _(non_existent_key, foo="bar") == "This is an uncatalogued string for testing: bar"

    def test_translation_formatting_error_safety(self):
        set_language("es", persist=False)
        # Passing mismatched kwargs shouldn't raise exception
        result = _("Exit", unexpected_arg="test")
        assert result == "Salir"


class TestCatalogConsistency:
    def test_valencian_ordering_after_euskara(self):
        langs = list(SUPPORTED_LANGUAGES.keys())
        eu_idx = langs.index("eu")
        ca_idx = langs.index("ca")
        assert ca_idx == eu_idx + 1
        assert SUPPORTED_LANGUAGES["ca"] == "Valencià"

    def test_all_supported_languages_have_translation_catalogs(self):
        non_default = [lang for lang in SUPPORTED_LANGUAGES if lang != DEFAULT_LANGUAGE]
        for lang in non_default:
            assert lang in TRANSLATIONS, f"Language {lang} missing from TRANSLATIONS catalog"
            assert len(TRANSLATIONS[lang]) > 30, f"Language {lang} catalog appears incomplete"

    def test_translation_placeholders_match(self):
        """Ensures that all placeholder tokens in source strings match the translated strings."""
        placeholder_pattern = re.compile(r"\{([a-zA-Z0-9_]+)\}")

        for lang, catalog in TRANSLATIONS.items():
            for src_text, trans_text in catalog.items():
                src_tokens = set(placeholder_pattern.findall(src_text))
                trans_tokens = set(placeholder_pattern.findall(trans_text))
                assert src_tokens == trans_tokens, (
                    f"Placeholder mismatch in [{lang}]:\n"
                    f"Source: {src_text} -> Tokens: {src_tokens}\n"
                    f"Trans: {trans_text} -> Tokens: {trans_tokens}"
                )


class TestLanguageDialog:
    def test_select_language_dialog_selection(self):
        with patch("nosteam2steam.ui.show_menu", return_value="es"):
            with patch("nosteam2steam.ui.show_info") as mock_info:
                selected = select_language_dialog()
                assert selected == "es"
                assert get_current_language() == "es"
                assert mock_info.called

    def test_select_language_dialog_cancelled(self):
        set_language("en", persist=False)
        with patch("nosteam2steam.ui.show_menu", return_value=None):
            selected = select_language_dialog()
            assert selected is None
            assert get_current_language() == "en"


class TestLazyLoadingAndResourceResolution:
    def test_load_locale_catalog_caching(self):
        i18n._loaded_catalogs.clear()
        catalog1 = i18n.load_locale_catalog("es")
        assert len(catalog1) > 0
        assert "es" in i18n._loaded_catalogs
        catalog2 = i18n.load_locale_catalog("es")
        assert catalog1 is catalog2

    def test_load_locale_catalog_default_language_empty(self):
        assert i18n.load_locale_catalog("en") == {}

    def test_load_locale_catalog_missing_file(self):
        assert i18n.load_locale_catalog("non_existent_lang") == {}

    def test_pyinstaller_meipass_resolution(self, tmp_path, monkeypatch):
        meipass_dir = tmp_path / "bundle"
        locales_dir = meipass_dir / "nosteam2steam" / "locales"
        locales_dir.mkdir(parents=True)
        test_json = locales_dir / "xx.json"
        test_json.write_text('{"Exit": "Salir_Frozen"}', encoding="utf-8")

        monkeypatch.setattr(i18n.sys, "_MEIPASS", str(meipass_dir), raising=False)
        resolved = i18n.get_locale_file_path("xx")
        assert resolved == test_json


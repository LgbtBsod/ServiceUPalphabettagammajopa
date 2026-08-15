"""I18N - Internationalization Service

Multi-language support with .ini file format.
Follows SRP (Single Responsibility Principle) for localization management.
Thread-safe implementation using ThreadPoolExecutor.

SSOT: All application texts are stored in i18n/*.ini files.
"""

from __future__ import annotations

import configparser
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import ClassVar, Final, Self

logger = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class LocaleInfo:
    """Information about a locale."""

    code: str
    name: str
    native_name: str
    is_default: bool = False


class I18NService:
    """Internationalization service for multi-language support.

    Features:
    - Load translations from .ini files
    - Thread-safe access to translations
    - Runtime language switching
    - Format string interpolation
    - Fallback to default language
    - Lazy loading of locales

    Usage:
        i18n = I18NService()
        i18n.set_language('ru_RU')
        text = i18n.get('button.save')  # "Сохранить"
        text = i18n.get('app.version', version='15.0')  # "Версия 15.0"
    """

    DEFAULT_LOCALE: Final[str] = "ru_RU"
    SUPPORTED_LOCALES: ClassVar[dict[str, LocaleInfo]] = {
        "ru_RU": LocaleInfo("ru_RU", "Russian", "Русский", is_default=True),
        "en_US": LocaleInfo("en_US", "English (US)", "English"),
    }

    def __init__(self, i18n_dir: str | Path | None = None):
        """Initialize I18N service.

        Args:
            i18n_dir: Directory containing .ini translation files.
                     Defaults to ./i18n relative to module.
        """
        if i18n_dir is None:
            i18n_dir = Path(__file__).parent.parent / "i18n"

        self._i18n_dir = Path(i18n_dir)
        self._current_locale: str = self.DEFAULT_LOCALE
        self._translations: dict[str, dict[str, str]] = {}
        self._executor = ThreadPoolExecutor(
            max_workers=2, thread_name_prefix="i18n_loader"
        )
        self._lock = threading.Lock()

        # Pre-load default locale
        self._load_locale(self.DEFAULT_LOCALE)

        logger.info(f"I18NService initialized with directory: {self._i18n_dir}")

    def _load_locale(self, locale: str) -> dict[str, str]:
        """Load translations for a specific locale.

        Args:
            locale: Locale code (e.g., 'ru_RU', 'en_US')

        Returns:
            Dictionary of key-value translations

        Raises:
            FileNotFoundError: If translation file doesn't exist
        """
        if locale in self._translations:
            return self._translations[locale]

        file_path = self._i18n_dir / f"{locale}.ini"

        if not file_path.exists():
            logger.warning(f"Translation file not found: {file_path}")
            if locale != self.DEFAULT_LOCALE:
                logger.info(f"Falling back to default locale: {self.DEFAULT_LOCALE}")
                return self._load_locale(self.DEFAULT_LOCALE)
            return {}

        config = configparser.ConfigParser(
            interpolation=None,
            allow_no_value=True,
            comment_prefixes="#",
        )
        config.read(file_path, encoding="utf-8")

        translations = {}
        for section in config.sections():
            for key, value in config.items(section):
                if value is not None:
                    full_key = f"{section}.{key}" if section else key
                    translations[full_key] = value.strip()

        with self._lock:
            self._translations[locale] = translations

        logger.debug(f"Loaded {len(translations)} translations for {locale}")
        return translations

    def get(self, key: str, **kwargs) -> str:
        """Get translated text by key.

        Supports both short keys (button.save) and full keys (buttons.button.save).
        Automatically tries section-prefixed version if short key not found.

        Args:
            key: Translation key (dot-separated, e.g., 'button.save')
            **kwargs: Format arguments for string interpolation

        Returns:
            Translated text with interpolated values

        Example:
            >>> i18n.get('button.save')
            'Сохранить'
            >>> i18n.get('app.version', version='15.0')
            'Версия 15.0'
            >>> i18n.get('error.min_value', min=10)
            'Значение должно быть не менее 10'
        """
        translations = self._translations.get(self._current_locale, {})

        if not translations:
            translations = self._load_locale(self._current_locale)

        # Try direct key first
        text = translations.get(key)

        # If not found, try with section prefix
        if text is None:
            key_parts = key.split(".")
            if len(key_parts) >= 2:
                # button.save -> buttons.button.save (plural section)
                section = (
                    key_parts[0] + "s"
                    if not key_parts[0].endswith("s")
                    else key_parts[0]
                )
                full_key = f"{section}.{key}"
                text = translations.get(full_key)

        # If still not found, try fallback to default locale
        if text is None and self._current_locale != self.DEFAULT_LOCALE:
            default_translations = self._translations.get(self.DEFAULT_LOCALE, {})
            if not default_translations:
                default_translations = self._load_locale(self.DEFAULT_LOCALE)
            text = default_translations.get(key)
            if text is None:
                key_parts = key.split(".")
                if len(key_parts) >= 2:
                    section = (
                        key_parts[0] + "s"
                        if not key_parts[0].endswith("s")
                        else key_parts[0]
                    )
                    full_key = f"{section}.{key}"
                    text = default_translations.get(full_key)
            logger.debug(f"Using fallback translation for key: {key}")

        # If still not found, return the key itself
        if text is None:
            text = key
            logger.warning(f"Translation key not found: {key}")

        # Format string if arguments provided
        if kwargs and "{" in text:
            try:
                text = text.format(**kwargs)
            except KeyError as e:
                logger.warning(f"Missing format argument {e} for key: {key}")

        return text

    def t(self, key: str, **kwargs) -> str:
        """Alias for get() method - shorter syntax.

        Args:
            key: Translation key
            **kwargs: Format arguments

        Returns:
            Translated text
        """
        return self.get(key, **kwargs)

    def set_language(self, locale: str) -> bool:
        """Set current language/locale.

        Args:
            locale: Locale code (e.g., 'ru_RU', 'en_US')

        Returns:
            True if locale was successfully set, False otherwise
        """
        if locale not in self.SUPPORTED_LOCALES:
            logger.warning(f"Unsupported locale: {locale}")
            return False

        if locale not in self._translations:
            try:
                self._load_locale(locale)
            except Exception as e:
                logger.exception(f"Failed to load locale {locale}: {e}")
                return False

        with self._lock:
            self._current_locale = locale

        logger.info(f"Language switched to: {locale}")
        return True

    def get_current_language(self) -> str:
        """Get current locale code."""
        return self._current_locale

    def get_available_languages(self) -> dict[str, LocaleInfo]:
        """Get dictionary of supported languages."""
        return self.SUPPORTED_LOCALES.copy()

    def get_language_name(self, locale: str | None = None) -> str:
        """Get human-readable name for a locale.

        Args:
            locale: Locale code (defaults to current)

        Returns:
            Native language name
        """
        if locale is None:
            locale = self._current_locale

        info = self.SUPPORTED_LOCALES.get(locale)
        return info.native_name if info else locale

    @lru_cache(maxsize=100)
    def get_cached(self, key: str, **kwargs) -> str:
        """Get translated text with LRU caching.

        Useful for frequently accessed static texts.
        Note: Does not support dynamic kwargs formatting in cache.

        Args:
            key: Translation key

        Returns:
            Translated text
        """
        return self.get(key, **kwargs)

    def reload_all(self) -> None:
        """Reload all translation files from disk."""
        with self._lock:
            self._translations.clear()

        self._load_locale(self._current_locale)
        logger.info("All translations reloaded")

    def shutdown(self, wait: bool = True) -> None:
        """Shutdown the service and release resources.

        Args:
            wait: Wait for pending tasks to complete
        """
        self._executor.shutdown(wait=wait)
        logger.info("I18NService shut down")

    def __enter__(self) -> Self:
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - cleanup resources."""
        self.shutdown(wait=False)


# =============================================================================
# GLOBAL INSTANCE - Singleton pattern for application-wide access
# =============================================================================

_i18n_instance: I18NService | None = None


def get_i18n() -> I18NService:
    """Get global I18N instance (singleton).

    Returns:
        Global I18NService instance
    """
    global _i18n_instance
    if _i18n_instance is None:
        _i18n_instance = I18NService()
    return _i18n_instance


def t(key: str, **kwargs) -> str:
    """Convenience function for translations.

    Usage:
        from i18n.service import t
        label = t('button.save')
        message = t('order.created', id=123)

    Args:
        key: Translation key
        **kwargs: Format arguments

    Returns:
        Translated text
    """
    return get_i18n().t(key, **kwargs)


def set_language(locale: str) -> bool:
    """Set application language.

    Usage:
        from i18n.service import set_language
        set_language('en_US')

    Args:
        locale: Locale code

    Returns:
        True if successful
    """
    return get_i18n().set_language(locale)


# Import threading at module level
import threading

__all__ = [
    "I18NService",
    "LocaleInfo",
    "get_i18n",
    "set_language",
    "t",
]

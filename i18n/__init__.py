"""
I18N Package - Internationalization support

Provides multi-language support for the application.
"""

from .service import (
    I18NService,
    LocaleInfo,
    get_i18n,
    t,
    set_language,
)

__all__ = [
    'I18NService',
    'LocaleInfo',
    'get_i18n',
    't',
    'set_language',
]

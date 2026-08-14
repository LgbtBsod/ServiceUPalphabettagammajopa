#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Утилиты приложения"""

from .formatters import (
    format_phone, format_price, format_date,
    format_order_number_for_display, format_order_number_for_db,
    generate_order_number, get_days_since_receipt,
    normalize_phone, normalize_phone_digits, parse_price_to_float,
)
from .validators import validate_phone, validate_price, validate_required
from .colors import get_colors
from .constants import (
    STATUSES, PRIORITIES, CLIENT_STATUSES, WARRANTIES,
    DICTIONARY_TYPES, DEFAULT_SETTINGS,
)

__all__ = [
    'format_phone', 'format_price', 'format_date',
    'format_order_number_for_display', 'format_order_number_for_db',
    'generate_order_number', 'get_days_since_receipt',
    'normalize_phone', 'normalize_phone_digits', 'parse_price_to_float',
    'validate_phone', 'validate_price', 'validate_required',
    'get_colors',
    'STATUSES', 'PRIORITIES', 'CLIENT_STATUSES', 'WARRANTIES',
    'DICTIONARY_TYPES', 'DEFAULT_SETTINGS',
]

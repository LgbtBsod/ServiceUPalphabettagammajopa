#!/usr/bin/env python3

"""Утилиты приложения"""

from .colors import get_colors
from .constants import DEFAULT_SETTINGS
from .formatters import (
    format_date,
    format_order_number_for_db,
    format_order_number_for_display,
    format_phone,
    format_price,
    generate_order_number,
    get_days_since_receipt,
    normalize_phone,
    normalize_phone_digits,
    parse_price_to_float,
)
from .validators import validate_phone, validate_price, validate_required

__all__ = [
    "DEFAULT_SETTINGS",
    "format_date",
    "format_order_number_for_db",
    "format_order_number_for_display",
    "format_phone",
    "format_price",
    "generate_order_number",
    "get_colors",
    "get_days_since_receipt",
    "normalize_phone",
    "normalize_phone_digits",
    "parse_price_to_float",
    "validate_phone",
    "validate_price",
    "validate_required",
]

"""
Shared Utilities Module - SSOT for all utility functions.

This module consolidates all utility functions from different locations:
- utils/formatters.py
- utils/validators.py  
- shared/kernel.py utilities

Principles applied:
- SSOT (Single Source of Truth): One place for all utilities
- DRY (Don't Repeat Yourself): No duplication across modules
- SOLID: Each function has single responsibility

Usage:
    from shared.utils import normalize_phone, validate_price, format_money
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Optional, Union
from datetime import datetime

import phonenumbers
from phonenumbers import NumberParseException

# =============================================================================
# PHONE UTILITIES - SSOT for phone number handling
# =============================================================================

_PHONE_DIGITS_RE = re.compile(r'\D')


def extract_phone_digits(phone: Optional[str]) -> str:
    """
    Extract only digits from phone number.
    
    Solves search problem: phones can be stored/input in any format
    ('+7 (999) 123-45-67', '89991234567', '7-999-123-45-67'),
    search should work on canonical digits.
    
    Args:
        phone: Phone number in any format
    
    Returns:
        String containing only digits
    """
    if phone is None:
        return ""
    return _PHONE_DIGITS_RE.sub('', str(phone))


def normalize_phone(phone: Optional[str]) -> str:
    """
    Normalize phone to canonical format for storage in DB.
    
    Converts 10/11-digit numbers to '+7 (XXX) XXX-XX-XX' format.
    Guarantees phone is always stored identically.
    
    Args:
        phone: Phone number in any format
    
    Returns:
        Normalized phone string in '+7 (XXX) XXX-XX-XX' format
    """
    if phone is None:
        return ""
    
    digits = extract_phone_digits(phone)
    if not digits:
        return ""
    
    # Normalize to 11 digits with country code
    if len(digits) == 11 and digits[0] in ('7', '8'):
        digits = '7' + digits[1:]
    elif len(digits) == 10:
        digits = '7' + digits
    
    if len(digits) == 11 and digits[0] == '7':
        return f"+7 ({digits[1:4]}) {digits[4:7]}-{digits[7:9]}-{digits[9:11]}"
    
    # Unknown format - return cleaned digits as-is
    return digits


def format_phone(phone: Optional[str]) -> str:
    """
    Format phone number for display (without modifying DB).
    
    Args:
        phone: Phone number in any format
    
    Returns:
        Formatted phone string for UI display
    """
    if not phone:
        return ""
    
    digits = extract_phone_digits(phone)
    
    if len(digits) == 11:
        return f"+{digits[0]} ({digits[1:4]}) {digits[4:7]}-{digits[7:9]}-{digits[9:11]}"
    if len(digits) == 10:
        return f"+7 ({digits[0:3]}) {digits[3:6]}-{digits[6:8]}-{digits[8:10]}"
    
    return str(phone)


def validate_phone(phone: Optional[str]) -> bool:
    """
    Validate phone number using phonenumbers library (Google libphonenumber).
    
    Args:
        phone: Phone number in any format
    
    Returns:
        True if phone is valid, False otherwise
    """
    if not phone or not str(phone).strip():
        return False
    
    try:
        parsed = phonenumbers.parse(str(phone), "RU")
        return phonenumbers.is_valid_number(parsed)
    except NumberParseException:
        return False


def validate_and_normalize_phone(phone: Optional[str]) -> tuple[bool, str]:
    """
    Validate and normalize phone in one call.
    
    Args:
        phone: Phone number to validate and normalize
    
    Returns:
        Tuple of (is_valid, normalized_phone)
        If invalid, returns (False, original_phone)
    """
    if not validate_phone(phone):
        return False, phone or ""
    
    return True, normalize_phone(phone)


# =============================================================================
# PRICE/MONEY UTILITIES - SSOT for monetary values
# =============================================================================

Number = Union[int, float, str, Decimal, None]


def safe_decimal(value: Number, default: Decimal = Decimal('0.00')) -> Decimal:
    """
    Safely convert value to Decimal with proper rounding.
    
    Handles:
    - Strings with comma/dot as decimal separator
    - Strings with spaces/non-breaking spaces as thousand separators
    - Currency symbols (₽, $, €)
    - None values
    
    Args:
        value: Value to convert
        default: Default value if conversion fails
    
    Returns:
        Decimal value rounded to 2 decimal places
    """
    if value is None:
        return default
    
    if isinstance(value, Decimal):
        return value.quantize(Decimal('0.01'))
    
    try:
        if isinstance(value, (int, float)):
            return Decimal(str(value)).quantize(Decimal('0.01'))
        
        # Clean string from formatting
        cleaned = str(value).strip()
        cleaned = cleaned.replace(',', '.').replace(' ', '').replace('\u00a0', '')
        cleaned = cleaned.replace('₽', '').replace('$', '').replace('€', '')
        
        # Remove any non-digit characters except dot
        cleaned = re.sub(r'[^\d.]', '', cleaned)
        
        if not cleaned:
            return default
        
        return Decimal(cleaned).quantize(Decimal('0.01'))
    
    except (InvalidOperation, ValueError, TypeError):
        return default


def parse_price_to_float(price: Number) -> float:
    """
    Safely convert price string to float.
    
    Legacy function for backward compatibility.
    Prefer safe_decimal() for new code.
    
    Args:
        price: Price in any format
    
    Returns:
        Float value, 0.0 on error
    """
    try:
        decimal_value = safe_decimal(price, Decimal('0.00'))
        return float(decimal_value)
    except Exception:
        return 0.0


def format_money(amount: Number, currency: str = '₽') -> str:
    """
    Format monetary value for display.
    
    Uses NBSP (\u00a0) as thousand separator for consistent formatting.
    
    Args:
        amount: Amount to format
        currency: Currency symbol (default: ₽)
    
    Returns:
        Formatted string like "1 234,56 ₽"
    """
    try:
        decimal_amount = safe_decimal(amount, Decimal('0.00'))
        # Format with space as thousand separator
        formatted = f"{decimal_amount:,.2f}".replace(',', ' ')
        return f"{formatted} {currency}"
    except Exception:
        return f"{amount} {currency}"


def validate_price(price: Number) -> bool:
    """
    Validate price value.
    
    Empty strings and None are allowed (price is optional).
    Invalid strings (like "abc") return False.
    
    Args:
        price: Price in any format
    
    Returns:
        True if price is valid or empty, False otherwise
    """
    if price is None:
        return True
    
    if not str(price).strip():
        return True
    
    try:
        original = str(price).strip()
        
        # If no digits after removing all digits - invalid string
        if not re.search(r'\d', original):
            return False
        
        # Try to convert to Decimal
        decimal_value = safe_decimal(price, None)
        return decimal_value is not None and decimal_value >= 0
    
    except Exception:
        return False


# =============================================================================
# STRING UTILITIES
# =============================================================================

def sanitize_string(value: str, max_length: int = 1000) -> str:
    """
    Clean string from extra whitespace and limit length.
    
    Args:
        value: String to sanitize
        max_length: Maximum allowed length
    
    Returns:
        Sanitized string
    """
    if not value:
        return ""
    
    # Replace multiple whitespaces with single space
    sanitized = " ".join(value.split())
    
    # Truncate to max length
    return sanitized[:max_length]


def truncate_text(text: str, max_length: int, suffix: str = "...") -> str:
    """
    Truncate text to maximum length with suffix.
    
    Args:
        text: Text to truncate
        max_length: Maximum length including suffix
        suffix: Suffix to add (default: "...")
    
    Returns:
        Truncated text with suffix if needed
    """
    if not text or len(text) <= max_length:
        return text
    
    return text[:max_length - len(suffix)] + suffix


# =============================================================================
# DATE UTILITIES
# =============================================================================

def format_date(date_obj: Optional[datetime], format_str: str = "%d.%m.%Y") -> str:
    """
    Format datetime object to string.
    
    Args:
        date_obj: Datetime to format
        format_str: strftime format string
    
    Returns:
        Formatted date string, empty if date_obj is None
    """
    if not date_obj:
        return ""
    
    try:
        if isinstance(date_obj, str):
            # Try to parse string date
            if ' ' in date_obj:
                date_obj = datetime.strptime(date_obj[:19], "%Y-%m-%d %H:%M:%S")
            else:
                date_obj = datetime.strptime(date_obj[:10], "%Y-%m-%d")
        
        return date_obj.strftime(format_str)
    
    except (ValueError, TypeError):
        return str(date_obj)[:10] if date_obj else ""


def parse_date(date_str: str, formats: list[str] = None) -> Optional[datetime]:
    """
    Parse string to datetime trying multiple formats.
    
    Args:
        date_str: Date string to parse
        formats: List of formats to try (default: common Russian formats)
    
    Returns:
        datetime object or None if parsing fails
    """
    if not date_str:
        return None
    
    if formats is None:
        formats = [
            "%Y-%m-%d",
            "%Y-%m-%d %H:%M:%S",
            "%d.%m.%Y",
            "%d.%m.%Y %H:%M:%S",
            "%d.%m.%y",
        ]
    
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    
    return None


def get_days_since(date_from: datetime, date_to: datetime = None) -> int:
    """
    Calculate days between two dates.
    
    Args:
        date_from: Start date
        date_to: End date (default: now)
    
    Returns:
        Number of days between dates
    """
    if not date_from:
        return 0
    
    if date_to is None:
        date_to = datetime.now()
    
    delta = date_to - date_from
    return delta.days


# =============================================================================
# VALIDATION UTILITIES
# =============================================================================

def validate_required(value) -> bool:
    """
    Validate that a field is not empty.
    
    Args:
        value: Value to check
    
    Returns:
        True if value is not None/empty string
    """
    if value is None:
        return False
    
    if isinstance(value, str) and not value.strip():
        return False
    
    return True


def validate_email(email: str) -> bool:
    """
    Validate email format.
    
    Args:
        email: Email to validate
    
    Returns:
        True if email format is valid
    """
    if not email:
        return False
    
    # Simple regex validation
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


# =============================================================================
# EXPORTS - All public API
# =============================================================================

__all__ = [
    # Phone utilities
    'extract_phone_digits',
    'normalize_phone',
    'format_phone',
    'validate_phone',
    'validate_and_normalize_phone',
    
    # Money utilities
    'safe_decimal',
    'parse_price_to_float',
    'format_money',
    'validate_price',
    
    # String utilities
    'sanitize_string',
    'truncate_text',
    
    # Date utilities
    'format_date',
    'parse_date',
    'get_days_since',
    
    # Validation utilities
    'validate_required',
    'validate_email',
]

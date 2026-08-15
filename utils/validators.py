#!/usr/bin/env python3

"""Функции валидации данных.

Использует библиотеку phonenumbers для валидации телефонов (Google libphonenumber).
Для цен и обязательных полей - оптимизированные встроенные функции.
"""

import re

try:
    import phonenumbers
    from phonenumbers import NumberParseException

    PHONENUMBERS_AVAILABLE = True
except ImportError:
    PHONENUMBERS_AVAILABLE = False

from .formatters import normalize_phone_digits

Number = int | float | str


def validate_phone(phone: str | None) -> bool:
    """Валидация номера телефона.

    Использует phonenumbers library если доступна, иначе fallback на простую проверку длины.

    Args:
        phone: Номер телефона в любом формате

    Returns:
        True если номер валидный, False иначе
    """
    if not phone or not str(phone).strip():
        return False

    # Используем phonenumbers если библиотека установлена (industry standard)
    if PHONENUMBERS_AVAILABLE:
        try:
            parsed = phonenumbers.parse(str(phone), "RU")
            return phonenumbers.is_valid_number(parsed)
        except NumberParseException:
            return False

    # Fallback: простая проверка длины (10-15 цифр для международных номеров)
    digits = normalize_phone_digits(phone)
    return 10 <= len(digits) <= 15


def validate_price(price: Number | None) -> bool:
    """Валидация цены.

    Пустая строка и None допустимы (цена не обязательна).
    Некорректные строки (например "abc") возвращают False.

    Args:
        price: Цена в любом формате (строка, число)

    Returns:
        True если цена валидная или пустая, False иначе
    """
    if price is None:
        return True
    if not str(price).strip():
        return True

    try:
        original = str(price).strip()

        # Если после удаления всех цифр ничего не осталось - это некорректная строка
        if not re.search(r"\d", original):
            return False

        # Очищаем от форматирования: запятые, пробелы, символ валюты
        cleaned = original.replace(",", ".").replace(" ", "").replace("\u00a0", "")
        # Удаляем символы валют и другие нецифровые символы кроме точки
        cleaned = re.sub(r"[^\d.]", "", cleaned)

        if not cleaned:
            return True

        # Проверяем корректность формата числа (одна точка, не в начале/конце)
        if cleaned.count(".") > 1:
            return False
        if cleaned.startswith(".") or cleaned.endswith("."):
            return False

        float(cleaned)
        return True
    except ValueError, TypeError:
        return False


def validate_required(value: any | None) -> bool:
    """Валидация обязательного поля.

    Args:
        value: Проверяемое значение

    Returns:
        True если значение не пустое, False иначе
    """
    return bool(value and str(value).strip())


def validate_email(email: str | None) -> bool:
    """Валидация email адреса.

    Args:
        email: Email адрес

    Returns:
        True если email валидный, False иначе
    """
    if not email or not str(email).strip():
        return False

    # Простая RFC-compliant валидация
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(pattern, str(email).strip()))


def validate_positive_number(value: Number | None, allow_zero: bool = False) -> bool:
    """Валидация положительного числа.

    Args:
        value: Проверяемое значение
        allow_zero: Разрешить ноль (по умолчанию False)

    Returns:
        True если число положительное, False иначе
    """
    if value is None:
        return False

    try:
        num = float(str(value).replace(",", "."))
        if allow_zero:
            return num >= 0
        return num > 0
    except ValueError, TypeError:
        return False

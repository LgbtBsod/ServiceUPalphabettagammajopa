#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Функции валидации данных.

Использует библиотеку phonenumbers для валидации телефонов (Google libphonenumber).
Для цен и обязательных полей - оптимизированные встроенные функции.
"""

from typing import Optional, Union
import re

try:
    import phonenumbers
    from phonenumbers import NumberParseException
    PHONENUMBERS_AVAILABLE = True
except ImportError:
    PHONENUMBERS_AVAILABLE = False

from .formatters import normalize_phone_digits


Number = Union[int, float, str]


def validate_phone(phone: Optional[str]) -> bool:
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


def validate_price(price: Optional[Number]) -> bool:
    """Валидация цены.
    
    Пустая строка и None допустимы (цена не обязательна).
    
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
        # Очищаем от форматирования: запятые, пробелы, символ валюты
        cleaned = str(price).strip()
        cleaned = cleaned.replace(',', '.').replace(' ', '').replace('\u00a0', '')
        cleaned = re.sub(r'[^\d.]', '', cleaned)  # Оставляем только цифры и точки
        
        if not cleaned:
            return True
            
        float(cleaned)
        return True
    except (ValueError, TypeError):
        return False


def validate_required(value: Optional[any]) -> bool:
    """Валидация обязательного поля.
    
    Args:
        value: Проверяемое значение
        
    Returns:
        True если значение не пустое, False иначе
    """
    return bool(value and str(value).strip())


def validate_email(email: Optional[str]) -> bool:
    """Валидация email адреса.
    
    Args:
        email: Email адрес
        
    Returns:
        True если email валидный, False иначе
    """
    if not email or not str(email).strip():
        return False
    
    # Простая RFC-compliant валидация
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, str(email).strip()))


def validate_positive_number(value: Optional[Number], allow_zero: bool = False) -> bool:
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
        num = float(str(value).replace(',', '.'))
        if allow_zero:
            return num >= 0
        return num > 0
    except (ValueError, TypeError):
        return False

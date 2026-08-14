#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Функции валидации"""

import re

from .formatters import normalize_phone_digits


def validate_phone(phone):
    """Валидация номера телефона (10-11 цифр)"""
    if not phone or not str(phone).strip():
        return False
    digits = normalize_phone_digits(phone)
    return 10 <= len(digits) <= 15


def validate_price(price):
    """Валидация цены (пустая строка допустима)"""
    if price is None:
        return True
    if not str(price).strip():
        return True
    try:
        cleaned = str(price).strip().replace(',', '.').replace(' ', '').replace('\u00a0', '')
        float(cleaned)
        return True
    except (ValueError, TypeError):
        return False


def validate_required(value):
    """Валидация обязательного поля"""
    return bool(value and str(value).strip())

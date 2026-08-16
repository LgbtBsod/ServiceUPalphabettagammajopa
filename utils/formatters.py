#!/usr/bin/env python3

"""Функции форматирования данных"""

import re
from datetime import datetime
from typing import Any

_PHONE_DIGITS_RE = re.compile(r"\D")


def normalize_phone_digits(phone) -> str:
    """Возвращает только цифры из номера телефона.

    Решает проблему поиска: телефон может храниться/вводиться
    в любом формате ('+7 (999) 123-45-67', '89991234567', '7-999-123-45-67'),
    а поиск должен работать по каноничным цифрам.
    """
    if phone is None:
        return ""
    return _PHONE_DIGITS_RE.sub("", str(phone))


def normalize_phone(phone) -> str:
    """Нормализация телефона к единому каноничному формату при сохранении в БД.

    Приводит 10/11-значные номера к '+7 (XXX) XXX-XX-XX', прочие —
    к очищенному от мусора виду. Гарантирует, что телефон всегда хранится
    одинаково (фиксит рассинхронизацию поиска и отображения).
    """
    if phone is None:
        return ""
    digits = normalize_phone_digits(phone)
    if not digits:
        return ""
    # Нормализуем к 11 цифрам с кодом страны
    if len(digits) == 11 and digits[0] in ("7", "8"):
        digits = "7" + digits[1:]
    elif len(digits) == 10:
        digits = "7" + digits
    if len(digits) == 11 and digits[0] == "7":
        return f"+7 ({digits[1:4]}) {digits[4:7]}-{digits[7:9]}-{digits[9:11]}"
    # Неизвестный формат — возвращаем очищенные цифры как есть
    return digits


def format_phone(phone):
    """Форматирование номера телефона для отображения (без изменения БД)"""
    if not phone:
        return ""
    digits = normalize_phone_digits(phone)
    if len(digits) == 11:
        return (
            f"+{digits[0]} ({digits[1:4]}) {digits[4:7]}-{digits[7:9]}-{digits[9:11]}"
        )
    if len(digits) == 10:
        return f"+7 ({digits[0:3]}) {digits[3:6]}-{digits[6:8]}-{digits[8:10]}"
    return str(phone)


def format_price(price):
    """Форматирование цены"""
    if price is None or price == "":
        return "0 ₽"
    try:
        price_str = re.sub(r"[^\d,.]", "", str(price)).replace(",", ".")
        price_val = float(price_str)
        # Используем NBSP (\u00a0) как разделитель тысяч — единый формат
        # во всём приложении, чтобы сортировка/парсинг были согласованы.
        return f"{price_val:,.2f} ₽".replace(",", " ").replace("\xa0", " ")
    except (ValueError, TypeError):
        return f"{price} ₽"


def format_date(date_str):
    """Форматирование даты"""
    if not date_str:
        return ""
    try:
        if " " in str(date_str):
            dt = datetime.strptime(str(date_str)[:19], "%Y-%m-%d %H:%M:%S")
        else:
            dt = datetime.strptime(str(date_str)[:10], "%Y-%m-%d")
        return dt.strftime("%d.%m.%Y")
    except (ValueError, TypeError):
        try:
            return str(date_str)[:10]
        except Exception:
            return str(date_str)


def parse_price_to_float(price) -> float:
    """Безопасное преобразование строки цены в float.

    Учитывает запятую как десятичный разделитель, пробелы/неразрывные пробелы
    как разделители тысяч и символ валюты. Возвращает 0 при ошибке.
    """
    if price is None or price == "":
        return 0.0
    try:
        cleaned = str(price).replace("\u00a0", " ").replace("\xa0", " ")
        cleaned = re.sub(r"[^\d,.]", "", cleaned).replace(",", ".")
        # Если осталось несколько точек — оставляем первую как десятичную
        if cleaned.count(".") > 1:
            parts = cleaned.split(".")
            cleaned = parts[0] + "." + "".join(parts[1:])
        return float(cleaned)
    except (ValueError, TypeError):
        return 0.0


def format_order_number_for_display(order_number):
    """Форматирование номера заказа для отображения"""
    try:
        return str(int(order_number))
    except (ValueError, TypeError):
        return str(order_number)


def format_order_number_for_db(order_number):
    """Форматирование номера заказа для БД"""
    try:
        num = int(order_number)
        return f"{num:05d}"
    except (ValueError, TypeError):
        return str(order_number)


def generate_order_number(counter):
    """Генерация номера заказа"""
    return f"{counter:05d}"


def get_days_since_receipt(receipt_date):
    """Получение количества дней с даты приема"""
    try:
        if not receipt_date:
            return 0
        if isinstance(receipt_date, datetime):
            dt = receipt_date
        elif " " in str(receipt_date):
            dt = datetime.strptime(str(receipt_date)[:19], "%Y-%m-%d %H:%M:%S")
        else:
            dt = datetime.strptime(str(receipt_date)[:10], "%Y-%m-%d")
        delta = datetime.now() - dt
        return delta.days
    except (ValueError, TypeError):
        return 0


def row_matches_search(
    row: dict[str, Any], needle: str, phone_digits: str, order_digits: str
) -> bool:
    """Проверяет, соответствует ли запись (строка устройства) поисковому запросу.

    needle — запрос в нижнем регистре (для общего текстового поиска).
    phone_digits — только цифры из запроса (для поиска по телефону любого формата).
    order_digits — только цифры из запроса (для поиска по номеру заказа).

    Раньше эта логика была приватным static-методом
    database.db_manager.Database._row_matches, и живой facade
    (database/sqlalchemy_database.py) залезал в этот приватный метод другого
    класса через `_LegacyDatabase._row_matches(...)` — нарушение
    инкапсуляции поверх дублирования, см. AUDIT_REPORT_v21.md. Вынесено сюда
    как общая утилита — единственный источник логики поиска для обоих.
    """
    # Поля для общего регистронезависимого поиска по подстроке
    text_fields = (
        "order_number",
        "client_name",
        "phone",
        "model",
        "brand",
        "serial_number",
        "device_type",
        "defect",
        "engineer",
        "status",
    )
    for field in text_fields:
        val = row.get(field)
        if val and needle in str(val).lower():
            return True

    # Поиск по нормализованным цифрам телефона (устойчив к форматам).
    # Дополнительно нормализуем ведущую 8 в 7 (8XXX... -> 7XXX...),
    # т.к. телефон мог быть введён через «8», а хранится через «+7».
    if phone_digits:
        row_phone_digits = normalize_phone_digits(row.get("phone") or "")
        if row_phone_digits:
            # Варианты запроса: как есть и с заменой 8->7 в начале
            q_variants = {phone_digits}
            if phone_digits.startswith("8") and len(phone_digits) == 11:
                q_variants.add("7" + phone_digits[1:])
            if phone_digits.startswith("7") and len(phone_digits) == 11:
                q_variants.add("8" + phone_digits[1:])
            # Варианты записи: как есть, с заменой 8->7 / 7->8, и без кода страны
            row_variants = {row_phone_digits}
            if row_phone_digits.startswith("8") and len(row_phone_digits) == 11:
                row_variants.add("7" + row_phone_digits[1:])
            if row_phone_digits.startswith("7") and len(row_phone_digits) == 11:
                row_variants.add("8" + row_phone_digits[1:])
                # И 10-значный вид без кода страны
                row_variants.add(row_phone_digits[1:])
            # Ищем вхождение любого варианта запроса в любой вариант записи
            for q in q_variants:
                for rv in row_variants:
                    if q and rv and q in rv:
                        return True

    # Поиск по номеру заказа без учёта лидирующих нулей:
    # '1' должно находить '00001'
    if order_digits:
        row_order = str(row.get("order_number") or "")
        # Полное совпадение по цифрам или вхождение
        if order_digits in row_order:
            return True
        # Сравнение как чисел: '1' == int('00001')
        try:
            if int(order_digits) == int(row_order):
                return True
        except (ValueError, TypeError):
            pass

    return False

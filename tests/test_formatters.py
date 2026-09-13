#!/usr/bin/env python3

"""Тесты для utils/formatters.py — три бага, найденные design-review
workflow'ом, ни один из которых до этого не был покрыт тестами:

1. format_phone() показывал невалидный код страны "+8" для номеров,
   сохранённых в обход normalize_phone() (легаси/импортированные данные).
2. row_matches_search() не находил запись, если телефон в БД хранится
   "голым" 10-значным номером без кода страны.
3. format_price() падал на входе с более чем одной точкой, хотя его
   парный parse_price_to_float() тот же самый вход успешно разбирает.
"""

from __future__ import annotations

from utils.formatters import format_phone, format_price, row_matches_search


class TestFormatPhone:
    def test_normalized_phone_with_country_code_7(self):
        assert format_phone("+79991234567") == "+7 (999) 123-45-67"

    def test_raw_phone_starting_with_8_normalizes_to_plus_7(self):
        # Регрессия: раньше возвращало "+8 (999) 123-45-67".
        assert format_phone("89991234567") == "+7 (999) 123-45-67"

    def test_bare_10_digit_phone_gets_plus_7_prefix(self):
        assert format_phone("9991234567") == "+7 (999) 123-45-67"

    def test_empty_or_none_returns_empty_string(self):
        assert format_phone("") == ""
        assert format_phone(None) == ""

    def test_unrecognized_length_returned_as_is(self):
        assert format_phone("12345") == "12345"


class TestFormatPrice:
    def test_simple_price(self):
        assert format_price("1000") == "1 000.00 ₽"

    def test_price_with_comma_decimal(self):
        assert format_price("1000,50") == "1 000.50 ₽"

    def test_price_with_multiple_dots_is_parsed_not_left_raw(self):
        # Регрессия: раньше float("1.234.567") падал, format_price()
        # возвращал "1.234.567 ₽" сырым текстом вместо отформатированного
        # числа — расхождение с parse_price_to_float() на том же входе.
        result = format_price("1.234.567")
        assert result != "1.234.567 ₽"
        assert "₽" in result

    def test_none_or_empty_returns_zero(self):
        assert format_price(None) == "0 ₽"
        assert format_price("") == "0 ₽"


class TestRowMatchesSearchPhoneVariants:
    def _search(self, row_phone: str, query_digits: str) -> bool:
        # needle НЕ должен быть "" — пустая строка тривиально substring
        # везде, и "phone" сам входит в text_fields общего поиска (см.
        # row_matches_search), так что needle="" замкнул бы True ещё до
        # того, как код дойдёт до логики сравнения цифр телефона, которую
        # эти тесты и должны проверять изолированно.
        return row_matches_search(
            {"phone": row_phone},
            needle="zzz-not-a-real-query-zzz",
            phone_digits=query_digits,
            order_digits="",
        )

    def test_bare_10_digit_row_matches_11_digit_query_with_7(self):
        # Регрессия: раньше запись с "голым" 10-значным телефоном (без кода
        # страны — легаси/импортированные данные) никогда не находилась
        # 11-значным поисковым запросом.
        assert self._search("9991234567", "79991234567") is True

    def test_bare_10_digit_row_matches_11_digit_query_with_8(self):
        assert self._search("9991234567", "89991234567") is True

    def test_11_digit_row_matches_bare_10_digit_query(self):
        assert self._search("+79991234567", "9991234567") is True

    def test_normalized_row_matches_8_prefixed_query(self):
        assert self._search("+79991234567", "89991234567") is True

    def test_no_match_for_unrelated_number(self):
        assert self._search("+79991234567", "88005553535") is False

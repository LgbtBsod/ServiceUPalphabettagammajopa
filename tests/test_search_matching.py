#!/usr/bin/env python3

"""Тесты для utils.formatters.row_matches_search — вынесено из приватного
database.db_manager.Database._row_matches, в который раньше лез напрямую
живой facade (database/sqlalchemy_database.py), см. AUDIT_REPORT_v21.md."""

from utils.formatters import row_matches_search


def _row(**overrides):
    row = {
        "order_number": "00042",
        "client_name": "Иван Иванов",
        "phone": "+7 (999) 123-45-67",
        "model": "iPhone 13",
        "brand": "Apple",
        "status": "Диагностика",
    }
    row.update(overrides)
    return row


class TestRowMatchesSearch:
    def test_matches_by_text_field(self):
        assert row_matches_search(_row(), "иванов", "", "") is True

    def test_matches_by_model(self):
        assert row_matches_search(_row(), "iphone", "", "") is True

    def test_no_match_returns_false(self):
        assert row_matches_search(_row(), "nokia", "", "") is False

    def test_matches_phone_regardless_of_leading_8_vs_7(self):
        row = _row(phone="89991234567")
        assert row_matches_search(row, "", "79991234567", "") is True

    def test_matches_phone_without_country_code(self):
        row = _row(phone="+79991234567")
        assert row_matches_search(row, "", "9991234567", "") is True

    def test_matches_order_number_ignoring_leading_zeros(self):
        assert row_matches_search(_row(order_number="00042"), "", "", "42") is True

    def test_empty_query_parts_match_nothing_extra(self):
        assert row_matches_search(_row(), "nomatch", "", "") is False

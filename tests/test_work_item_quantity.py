#!/usr/bin/env python3

"""Regression tests for database/models.py::WorkItem/_safe_int — quantity
<= 0 used to be handled inconsistently between the two GUIs: classic
preserved it as-is (WorkItem.total_price() silently computed 0 ₽ for that
row), while gui_flet/views_orders.py::_WorkItemsEditor independently
clamped it to 1 on load with no log line — the same saved order showed a
different total depending on which UI opened it, and re-saving from Flet
silently rewrote the stored 0 to 1. Fixed by making the clamp-to-1 rule
live once in _safe_int() (the thing both WorkItem.from_dict() and Flet's
_WorkItemsEditor now go through), logged when it actually changes anything."""

import logging

from database.models import WorkItem, WorkItemsManager


class TestWorkItemFromDictClampsQuantity:
    def test_zero_quantity_is_clamped_to_one(self, caplog):
        with caplog.at_level(logging.WARNING):
            item = WorkItem.from_dict({"description": "Чистка", "price": "100", "quantity": 0})

        assert item.quantity == 1
        assert "0" in caplog.text

    def test_negative_quantity_is_clamped_to_one(self):
        item = WorkItem.from_dict({"description": "Чистка", "price": "100", "quantity": -5})
        assert item.quantity == 1

    def test_positive_quantity_is_preserved(self, caplog):
        with caplog.at_level(logging.WARNING):
            item = WorkItem.from_dict({"description": "Чистка", "price": "100", "quantity": 3})

        assert item.quantity == 3
        assert caplog.text == ""  # клэмп не сработал — не должно быть лога

    def test_missing_quantity_defaults_to_one(self):
        item = WorkItem.from_dict({"description": "Чистка", "price": "100"})
        assert item.quantity == 1

    def test_non_numeric_quantity_falls_back_to_default(self):
        item = WorkItem.from_dict({"description": "Чистка", "price": "100", "quantity": "abc"})
        assert item.quantity == 1


class TestWorkItemTotalPriceWithClampedQuantity:
    def test_zero_quantity_no_longer_zeroes_out_the_total(self):
        """Раньше: WorkItem(quantity=0).total_price() == 0 (тихо теряло
        стоимость позиции). Теперь quantity клэмпится к 1 уже в самом
        WorkItem — total_price() больше не может увидеть 0/отрицательное
        количество."""
        item = WorkItem(description="Чистка", price="100", quantity=0)
        assert item.total_price() == 100.0

    def test_manager_get_total_price_sums_clamped_items(self):
        mgr = WorkItemsManager()
        mgr.add_item(WorkItem(description="A", price="100", quantity=0))
        mgr.add_item(WorkItem(description="B", price="50", quantity=2))

        assert mgr.get_total_price() == 100.0 + 100.0

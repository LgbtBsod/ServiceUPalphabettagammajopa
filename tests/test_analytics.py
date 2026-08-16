#!/usr/bin/env python3

"""Тесты для managers/analytics.py::AnalyticsService — единственный модуль,
которому разрешено строить параметризированные аналитические запросы к БД,
делает это ТОЛЬКО через ядро (core.call_module_method('db_access', ...)),
не держит свой движок/сессию. Проверяет и путь через прямой вызов сервиса,
и полный путь через ядро (как реально вызывает GUI/PWA)."""

import os
import tempfile

import pytest

# ВАЖНО: managers/__init__.py импортирует .reports, который через
# reports/report_editor.py -> gui.widgets.modern триггерит предсуществующий
# циклический импорт managers<->gui (см. main.py, AUDIT_REPORT_v20.md).
# Импорт gui первым "прогревает" цикл в рабочем порядке — тот же обходной
# путь, что и в main.py/bootstrap.py.
import gui  # noqa: F401
from core.kernel import get_core, reset_core
from database.db_config import DatabaseConfig
from database.engines.sqlite_engine import SQLiteEngine
from database.sqlalchemy_database import Database
from managers.analytics import AnalyticsRequest, AnalyticsService


@pytest.fixture
def db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = SQLiteEngine(DatabaseConfig(database=path))
    database = Database(engine)
    yield database
    engine.dispose()
    if os.path.exists(path):
        os.remove(path)


def _sample_device(**overrides) -> dict:
    data = {
        "order_number": "00001",
        "receipt_date": "2026-01-01",
        "device_type": "Ноутбук",
        "client_name": "Иван Иванов",
        "phone": "+79991234567",
        "total_price": "1000",
        "status": "Диагностика",
        "priority": "Обычный",
    }
    data.update(overrides)
    return data


class _FakeSettingsApi:
    def __init__(self, **values):
        self._values = values

    def get(self, key, default=None):
        return self._values.get(key, default)


class FakeCore:
    """Минимальная замена ядра — только call_module_method к одному
    зарегистрированному db_access, без полной инициализации ServiceUpCore."""

    def __init__(self, db: Database, settings: _FakeSettingsApi | None = None):
        self._db = db
        self._settings = settings

    def call_module_method(self, module_name, method_name, *args, **kwargs):
        assert module_name == "db_access"
        return getattr(self._db, method_name)(*args, **kwargs)

    def get_module_api(self, name):
        if name == "settings" and self._settings is not None:
            return self._settings
        raise KeyError(name)


class TestAnalyticsServiceDirect:
    def test_run_report_status_breakdown(self, db):
        db.add_device(_sample_device(order_number="00001", status="Диагностика"))
        db.add_device(_sample_device(order_number="00002", status="Готов к выдаче"))
        db.add_device(_sample_device(order_number="00003", status="Диагностика"))

        service = AnalyticsService(FakeCore(db))
        result = service.run_report(AnalyticsRequest(report="status_breakdown"))

        assert result.report == "status_breakdown"
        by_status = {row["status"]: row["count"] for row in result.data}
        assert by_status["Диагностика"] == 2
        assert by_status["Готов к выдаче"] == 1

    def test_run_report_with_params(self, db):
        db.add_device(_sample_device(order_number="00001", receipt_date="2020-01-01"))
        service = AnalyticsService(FakeCore(db))

        result = service.run_report(
            AnalyticsRequest(report="overdue_count", params={"threshold_days": 0})
        )
        assert result.data >= 1

    def test_unknown_report_raises(self, db):
        service = AnalyticsService(FakeCore(db))
        with pytest.raises(ValueError):
            service.run_report(AnalyticsRequest(report="not_a_real_report"))

    def test_available_reports_lists_whitelist(self, db):
        service = AnalyticsService(FakeCore(db))
        reports = service.available_reports()
        assert "status_breakdown" in reports
        assert "overdue_count" in reports

    def test_result_to_json(self, db):
        db.add_device(_sample_device())
        service = AnalyticsService(FakeCore(db))
        result = service.run_report(AnalyticsRequest(report="status_breakdown"))
        json_str = result.to_json()
        assert isinstance(json_str, str)
        assert "Диагностика" in json_str


class TestThresholdDaysFromSettings:
    """Регрессия AUDIT_v25: dashboard_stats/overdue_count/overdue_orders
    игнорировали пользовательскую настройку overdue_days, когда вызывающий
    код (PWA) не передавал threshold_days явно — расходились с desktop-
    виджетом, который сам читает настройку."""

    def test_dashboard_stats_uses_overdue_days_setting_by_default(self, db):
        db.add_device(_sample_device(order_number="00001", receipt_date="2020-01-01"))
        service = AnalyticsService(FakeCore(db, _FakeSettingsApi(overdue_days=0)))

        result = service.run_report(AnalyticsRequest(report="dashboard_stats"))
        assert result.data["overdue"] >= 1

    def test_dashboard_stats_falls_back_to_default_without_settings_module(self, db):
        db.add_device(_sample_device(order_number="00001", receipt_date="2020-01-01"))
        service = AnalyticsService(FakeCore(db))  # без settings

        result = service.run_report(AnalyticsRequest(report="dashboard_stats"))
        assert "overdue" in result.data  # не падает, использует дефолт 14

    def test_explicit_threshold_days_overrides_settings(self, db):
        db.add_device(_sample_device(order_number="00001", receipt_date="2020-01-01"))
        service = AnalyticsService(FakeCore(db, _FakeSettingsApi(overdue_days=9999)))

        # threshold_days=0 передан явно -> не должен подмениться настройкой 9999
        result = service.run_report(
            AnalyticsRequest(report="overdue_count", params={"threshold_days": 0})
        )
        assert result.data >= 1

    def test_status_breakdown_unaffected_by_threshold_resolution(self, db):
        """status_breakdown не в whitelist'е _THRESHOLD_AWARE_REPORTS —
        threshold_days не должен подставляться (иначе TypeError на
        неожиданном kwarg'е у _calc_status_breakdown())."""
        db.add_device(_sample_device())
        service = AnalyticsService(FakeCore(db, _FakeSettingsApi(overdue_days=14)))
        result = service.run_report(AnalyticsRequest(report="status_breakdown"))
        assert result.data  # не упало


class TestReportsWhitelistConsistency:
    """Регрессия AUDIT_v25/Task P: AnalyticsService._REPORTS раньше дублировал
    имена CalculateMixin.calculate() вручную, без способа заметить, если
    один список обновили, а второй забыли (см.
    database/facade/calculate_mixin.py::list_calculations())."""

    def test_every_report_resolves_to_a_real_calculation(self, db):
        known_calculations = set(db.list_calculations())
        for calc_name in AnalyticsService._REPORTS.values():
            assert calc_name in known_calculations, (
                f"AnalyticsService._REPORTS ссылается на {calc_name!r}, "
                f"которого нет среди db.list_calculations()"
            )

    def test_verify_calculations_available_empty_when_in_sync(self, db):
        service = AnalyticsService(FakeCore(db))
        assert service.verify_calculations_available(db.list_calculations()) == []

    def test_verify_calculations_available_reports_drift(self, db):
        """Адверсарная проверка (AUDIT_v25/Task P): verify_calculations_available()
        обязан реально ловить расхождение, а не только совпадать сегодня
        случайно — подсовываем известные вычисления БЕЗ одной из целей
        _REPORTS и проверяем, что соответствующий отчёт назван в ответе."""
        service = AnalyticsService(FakeCore(db))
        missing_target = next(iter(AnalyticsService._REPORTS.values()))
        incomplete_known = set(db.list_calculations()) - {missing_target}

        broken = service.verify_calculations_available(incomplete_known)

        assert broken, "ожидалось хотя бы одно расхождение"
        for report_name in broken:
            assert AnalyticsService._REPORTS[report_name] == missing_target

    def test_threshold_aware_reports_accept_threshold_days_kwarg(self, db):
        """_THRESHOLD_AWARE_REPORTS — второй ручной whitelist (какие отчёты
        принимают threshold_days) без интроспекции сигнатур calc-хендлеров;
        эта проверка ловит расхождение через реальный вызов вместо чтения
        исходников calculate_mixin.py."""
        service = AnalyticsService(FakeCore(db))
        for report_name in AnalyticsService._THRESHOLD_AWARE_REPORTS:
            # Не должно бросить TypeError на неожиданном kwarg'е.
            service.run_report(
                AnalyticsRequest(report=report_name, params={"threshold_days": 0})
            )


class TestAnalyticsThroughRealKernel:
    """Сквозной путь: core.register_module('analytics', ...) ->
    core.call_module_method('analytics', 'run_report', ...) -> AnalyticsService
    -> core.call_module_method('db_access', 'calculate', ...) -> Database.
    Это ровно то, как реально вызывают GUI/PWA."""

    def test_full_path_through_kernel(self, db):
        reset_core()
        core = get_core()
        core.initialize()
        try:
            core.register_module("db_access", db, Database, api=db)
            analytics_svc = AnalyticsService(core)
            core.register_module(
                "analytics", analytics_svc, AnalyticsService, api=analytics_svc
            )

            db.add_device(_sample_device(order_number="00001", priority="Срочный"))
            db.add_device(_sample_device(order_number="00002", priority="Обычный"))

            result = core.call_module_method(
                "analytics",
                "run_report",
                AnalyticsRequest(report="priority_breakdown"),
            )
            by_priority = {row["priority"]: row["count"] for row in result.data}
            assert by_priority["Срочный"] == 1
            assert by_priority["Обычный"] == 1
        finally:
            reset_core()

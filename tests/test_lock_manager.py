#!/usr/bin/env python3

"""Тесты для managers/locking.py::LockManager — бизнес-правила поверх
сырого record_locks CRUD (см. tests/test_locking.py для CRUD-слоя).
Использует fake core (без реального Kernel/БД) — LockManager сам не должен
знать, что core ненастоящий, он общается с ним только через
get_module_api()/call_module_method()."""

from datetime import datetime, timezone

import gui  # noqa: F401  — см. tests/test_analytics.py: без этого managers/__init__.py's
# eager import chain (.reports -> ... -> gui.dialogs.client_history ->
# "from managers import ReportGenerator") падает, застав managers/__init__.py
# ещё не полностью выполненным.

from managers.locking import LockManager, LockResult


class _FakeEmployee:
    def __init__(self, id_, full_name):
        self.id = id_
        self.full_name = full_name


class _FakeEmployeesApi:
    def __init__(self, current=None):
        self._current = current

    def get_current_employee(self):
        return self._current


class _FakeSettingsApi:
    def __init__(self, **values):
        self._values = values

    def get(self, key, default=None):
        return self._values.get(key, default)


class _FakeCore:
    """Достаточно core.get_module_api()/core.call_module_method() —
    остальное LockManager не трогает."""

    def __init__(self, modules=None, db_responses=None, db_raises=None):
        self._modules = modules or {}
        self._db_responses = db_responses or {}
        self._db_raises = db_raises

    def get_module_api(self, name):
        if name not in self._modules:
            raise KeyError(name)
        return self._modules[name]

    def call_module_method(self, module_name, method_name, *args, **kwargs):
        assert module_name == "db_access"
        if self._db_raises is not None:
            raise self._db_raises
        return self._db_responses.get(method_name)


class TestHolderIdentity:
    def test_uses_current_employee_when_selected(self):
        core = _FakeCore(modules={
            "employees": _FakeEmployeesApi(_FakeEmployee(7, "Иван Иванов")),
        })
        mgr = LockManager(core)
        key, label = mgr._holder_identity()
        assert key == "emp:7"
        assert label == "Иван Иванов"

    def test_falls_back_to_session_guid_when_no_employee_selected(self):
        core = _FakeCore(modules={"employees": _FakeEmployeesApi(None)})
        mgr = LockManager(core)
        key, label = mgr._holder_identity()
        assert key.startswith("session:")
        assert label == "Сотрудник не выбран"

    def test_falls_back_when_employees_module_unavailable(self):
        core = _FakeCore(modules={})  # employees не зарегистрирован вовсе
        mgr = LockManager(core)
        key, label = mgr._holder_identity()
        assert key.startswith("session:")

    def test_session_guid_is_stable_across_calls(self):
        core = _FakeCore(modules={})
        mgr = LockManager(core)
        key1, _ = mgr._holder_identity()
        key2, _ = mgr._holder_identity()
        assert key1 == key2


class TestIsEnabledAndTtl:
    def test_is_enabled_reads_setting(self):
        core = _FakeCore(modules={
            "settings": _FakeSettingsApi(pessimistic_locking_enabled=True)
        })
        assert LockManager(core).is_enabled() is True

    def test_is_enabled_defaults_false_when_setting_missing(self):
        core = _FakeCore(modules={"settings": _FakeSettingsApi()})
        assert LockManager(core).is_enabled() is False

    def test_is_enabled_defaults_false_when_settings_module_unavailable(self):
        core = _FakeCore(modules={})
        assert LockManager(core).is_enabled() is False

    def test_ttl_reads_setting(self):
        core = _FakeCore(modules={"settings": _FakeSettingsApi(lock_ttl_seconds=120)})
        assert LockManager(core)._ttl_seconds() == 120

    def test_ttl_falls_back_to_default_when_settings_module_unavailable(self):
        core = _FakeCore(modules={})
        assert LockManager(core)._ttl_seconds() == 300


class TestTryAcquire:
    def test_short_circuits_to_ok_when_disabled(self):
        """Регрессия: is_enabled() проверяется ВНУТРИ try_acquire(), а не
        только вызывающим GUI-кодом (см. AUDIT_REPORT_v25.md)."""
        core = _FakeCore(
            modules={"settings": _FakeSettingsApi(pessimistic_locking_enabled=False)},
            db_responses={"acquire_lock": {"ok": False, "holder_key": "x"}},
        )
        result = LockManager(core).try_acquire("device", 1)
        assert result.ok is True

    def test_parses_iso_started_at_into_datetime(self):
        """Регрессия: Database.acquire_lock() отдаёт started_at строкой
        (.isoformat()) — try_acquire() обязан распарсить её обратно в
        datetime, иначе GUI-баннер не сможет вызвать .strftime()."""
        core = _FakeCore(
            modules={"settings": _FakeSettingsApi(pessimistic_locking_enabled=True)},
            db_responses={
                "acquire_lock": {
                    "ok": False,
                    "holder_key": "emp:1",
                    "holder_label": "Иван Иванов",
                    "started_at": "2026-01-01T10:00:00+00:00",
                }
            },
        )
        result = LockManager(core).try_acquire("device", 1)
        assert isinstance(result.started_at, datetime)
        assert result.started_at == datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)

    def test_fails_closed_on_db_error(self):
        """Регрессия: раньше при исключении try_acquire() отдавал ok=True
        (fail-open) — теперь fail-closed."""
        core = _FakeCore(
            modules={"settings": _FakeSettingsApi(pessimistic_locking_enabled=True)},
            db_raises=RuntimeError("db unavailable"),
        )
        result = LockManager(core).try_acquire("device", 1)
        assert result.ok is False


class TestRefresh:
    def test_short_circuits_to_true_when_disabled(self):
        core = _FakeCore(modules={"settings": _FakeSettingsApi(pessimistic_locking_enabled=False)})
        assert LockManager(core).refresh("device", 1) is True

    def test_returns_false_on_error(self):
        core = _FakeCore(
            modules={"settings": _FakeSettingsApi(pessimistic_locking_enabled=True)},
            db_raises=RuntimeError("db unavailable"),
        )
        assert LockManager(core).refresh("device", 1) is False


class TestReleaseAndGetLockInfo:
    def test_release_does_not_raise_on_error(self):
        """Регрессия: release()/get_lock_info() раньше звали
        safe_execute(default=None), что при default=None пробрасывает
        исключение дальше (see core/base.py) вместо мягкого проглатывания."""
        core = _FakeCore(modules={}, db_raises=RuntimeError("db unavailable"))
        LockManager(core).release("device", 1)  # не должно бросить

    def test_get_lock_info_returns_none_on_error(self):
        core = _FakeCore(modules={}, db_raises=RuntimeError("db unavailable"))
        assert LockManager(core).get_lock_info("device", 1) is None

    def test_get_lock_info_returns_db_result(self):
        core = _FakeCore(modules={}, db_responses={"get_lock": {"holder_key": "emp:1"}})
        assert LockManager(core).get_lock_info("device", 1) == {"holder_key": "emp:1"}

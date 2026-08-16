#!/usr/bin/env python3

"""Тесты для gui/main_window_parts/async_load_mixin.py::AsyncLoadMixin —
общий примитив фоновой загрузки данных БД (см. AUDIT_REPORT_v25.md, Task O).

Никакого реального Tk/customtkinter здесь не поднимается (headless-среда,
как и весь остальной test suite — см. отсутствие ctk.CTk() в других test_*),
поэтому self.root/self._core заменены детерминированными стабами:
  - _StubRoot.after() не выполняет колбэк сразу, а копит его — тест сам
    решает, когда "тикнул" Tk-mainloop (run_pending()), что и позволяет
    воспроизвести гонку "устаревший ответ пришёл позже нового запроса".
  - _SyncCore.create_thread() выполняет target() СИНХРОННО в момент вызова
    (а не в отдельном threading.Thread) — реальная многопоточность и
    Tk-thread-safety (self.root.after(0, ...) — единственный безопасный
    способ трогать Tk из чужого потока) проверены вручную/code review, а не
    этим unit-тестом; здесь проверяется именно логика AsyncLoadMixin
    (генерация, busy-индикатор, success/error маршрутизация)."""

import pytest

from gui.main_window_parts.async_load_mixin import AsyncLoadMixin


class _StubRoot:
    """Заменяет self.root — after(0, fn) копит колбэки вместо немедленного
    вызова, run_pending() выполняет их по порядку постановки (имитирует
    реальный Tk mainloop)."""

    def __init__(self):
        self._queued: list = []

    def after(self, _delay, fn):
        self._queued.append(fn)

    def run_pending(self) -> None:
        pending, self._queued = self._queued, []
        for fn in pending:
            fn()


class _SyncCore:
    """Заменяет core.create_thread()/start_thread()/stop_thread() — выполняет
    target() синхронно, детерминизм для теста. Опциональные fail_on_create/
    fail_on_start позволяют смоделировать сбой запуска фонового потока
    (ValueError на дубле имени / внутренняя ошибка ThreadManager)."""

    def __init__(self, *, fail_on_create: bool = False, fail_on_start: bool = False):
        self.fail_on_create = fail_on_create
        self.fail_on_start = fail_on_start
        self.stopped_thread_ids: list = []

    def create_thread(self, name, target, args=(), kwargs=None, daemon=False):
        if self.fail_on_create:
            raise ValueError(f"Thread '{name}' already exists")
        if not self.fail_on_start:
            target(*(args or ()), **(kwargs or {}))
        return name

    def start_thread(self, thread_id):
        if self.fail_on_start:
            raise RuntimeError("start_thread failed")
        return True

    def stop_thread(self, thread_id, timeout=5.0):
        self.stopped_thread_ids.append(thread_id)
        return True


class _DestroyedRoot(_StubRoot):
    """Имитирует self.root ПОСЛЕ root.destroy() — after() ведёт себя точно
    так же, как настоящий Tk: бросает при попытке запланировать колбэк на
    уже уничтоженный цикл событий."""

    def after(self, _delay, fn):
        raise RuntimeError("main thread is not in main loop")


class _Host(AsyncLoadMixin):
    """Минимальный хост-объект — то, чем в реальности является
    ServiceCenterApp (self._core/self.root)."""

    def __init__(self, *, core=None, root=None):
        self.root = root if root is not None else _StubRoot()
        self._core = core if core is not None else _SyncCore()


class _FakeBusyIndicator:
    def __init__(self):
        self.events: list = []

    def start(self, text):
        self.events.append(("start", text))

    def stop(self, *, error=False):
        self.events.append(("stop", error))


@pytest.fixture
def host():
    return _Host()


class TestRunAsyncHappyPath:
    def test_on_success_receives_fetch_result(self, host):
        received = []
        host._run_async("k", lambda: 42, received.append)
        host.root.run_pending()
        assert received == [42]

    def test_busy_indicator_starts_then_stops_without_error(self, host):
        busy = _FakeBusyIndicator()
        host._run_async("k", lambda: "data", lambda _r: None, busy_indicator=busy, busy_text="Загрузка...")
        # start() вызывается сразу (до фонового потока), stop() — после
        # применения результата на "главном потоке".
        assert busy.events == [("start", "Загрузка...")]
        host.root.run_pending()
        assert busy.events == [("start", "Загрузка..."), ("stop", False)]


class TestRunAsyncErrorPath:
    def test_error_routes_to_on_error_not_on_success(self, host):
        def _boom():
            raise ValueError("db unavailable")

        successes, errors = [], []
        host._run_async("k", _boom, successes.append, on_error=errors.append)
        host.root.run_pending()

        assert successes == []
        assert len(errors) == 1
        assert isinstance(errors[0], ValueError)

    def test_error_stops_busy_indicator_with_error_flag(self, host):
        busy = _FakeBusyIndicator()

        def _boom():
            raise RuntimeError("boom")

        host._run_async("k", _boom, lambda _r: None, on_error=lambda _e: None, busy_indicator=busy)
        host.root.run_pending()
        assert busy.events[-1] == ("stop", True)

    def test_error_without_on_error_does_not_raise(self, host):
        def _boom():
            raise RuntimeError("boom")

        host._run_async("k", _boom, lambda _r: None)
        host.root.run_pending()  # не должно бросить наружу


class TestStaleGenerationGuard:
    """Регрессия того, что должен ловить AsyncLoadMixin: пользователь успел
    переключить фильтр (запрос #2) раньше, чем пришёл ответ на предыдущий
    запрос (#1) той же key — устаревший #1 не должен перетереть #2."""

    def test_later_request_wins_when_earlier_result_arrives_after(self, host):
        first_results, second_results = [], []

        # Оба fetch выполняются немедленно (SyncCore), но применение
        # результата (_apply) копится в host.root и выполняется позже, одним
        # run_pending() — воспроизводит "ответ #1 пришёл после отправки #2".
        host._run_async("devices_table", lambda: "stale-data", first_results.append)
        host._run_async("devices_table", lambda: "fresh-data", second_results.append)

        host.root.run_pending()

        assert first_results == []  # устаревший результат отброшен
        assert second_results == ["fresh-data"]

    def test_different_keys_do_not_interfere(self, host):
        table_results, finance_results = [], []
        host._run_async("devices_table", lambda: "orders", table_results.append)
        host._run_async("finance_tab", lambda: "finances", finance_results.append)

        host.root.run_pending()

        assert table_results == ["orders"]
        assert finance_results == ["finances"]

    def test_repeated_calls_same_key_each_apply_independently_when_sequential(self, host):
        """Если ответы приходят и применяются строго по очереди (не гонка) —
        каждый результат обязан примениться, а не только последний."""
        results = []
        host._run_async("devices_table", lambda: "first", results.append)
        host.root.run_pending()
        host._run_async("devices_table", lambda: "second", results.append)
        host.root.run_pending()

        assert results == ["first", "second"]


class TestThreadManagerCleanup:
    """Регрессия adversarial-проверки: _run_async обязан освобождать запись
    ThreadManager после применения результата (тот же паттерн, что и
    pwa/server.py::PWAServerManager.stop() — core.stop_thread()), иначе
    singleton-словарь ThreadManager._threads растёт бесконечно на каждый
    load_devices/apply_filters/search_devices/update_finance_display."""

    def test_stop_thread_called_after_success(self, host):
        host._run_async("devices_table", lambda: "data", lambda _r: None)
        host.root.run_pending()
        assert len(host._core.stopped_thread_ids) == 1

    def test_stop_thread_called_after_error(self, host):
        def _boom():
            raise RuntimeError("boom")

        host._run_async("devices_table", _boom, lambda _r: None, on_error=lambda _e: None)
        host.root.run_pending()
        assert len(host._core.stopped_thread_ids) == 1

    def test_stop_thread_failure_does_not_break_result_delivery(self, host):
        """core.stop_thread() сам может бросить (например, core ещё не
        инициализирован) — это не должно помешать применить результат."""

        class _BrokenStopCore(_SyncCore):
            def stop_thread(self, thread_id, timeout=5.0):
                raise RuntimeError("core not initialized")

        host = _Host(core=_BrokenStopCore())
        received = []
        host._run_async("devices_table", lambda: 7, received.append)
        host.root.run_pending()
        assert received == [7]


class TestThreadStartFailure:
    """Регрессия adversarial-проверки: если create_thread()/start_thread()
    сами падают (дубль имени / внутренняя ошибка ThreadManager), busy-
    индикатор не должен зависать в состоянии "загрузка" навсегда."""

    def test_create_thread_failure_stops_busy_indicator_and_routes_to_on_error(self):
        host = _Host(core=_SyncCore(fail_on_create=True))
        busy = _FakeBusyIndicator()
        successes, errors = [], []

        host._run_async(
            "devices_table", lambda: "unreached", successes.append,
            on_error=errors.append, busy_indicator=busy,
        )

        assert successes == []
        assert len(errors) == 1 and isinstance(errors[0], ValueError)
        assert busy.events == [("start", "Загрузка..."), ("stop", True)]

    def test_start_thread_failure_stops_busy_indicator_and_routes_to_on_error(self):
        host = _Host(core=_SyncCore(fail_on_start=True))
        busy = _FakeBusyIndicator()
        errors = []

        host._run_async(
            "devices_table", lambda: "unreached", lambda _r: None,
            on_error=errors.append, busy_indicator=busy,
        )

        assert len(errors) == 1 and isinstance(errors[0], RuntimeError)
        assert busy.events[-1] == ("stop", True)

    def test_create_thread_failure_without_on_error_does_not_raise(self):
        host = _Host(core=_SyncCore(fail_on_create=True))
        host._run_async("devices_table", lambda: "unreached", lambda _r: None)  # не должно бросить


class TestShutdownRace:
    """Регрессия adversarial-проверки: если главное окно закрылось
    (root.destroy()) раньше, чем фоновый запрос успел вернуться,
    root.after(0, ...) бросает — это ожидаемо и должно тихо проглатываться,
    а не ронять фоновый поток с необработанным исключением."""

    def test_result_arriving_after_window_closed_is_silently_dropped(self):
        host = _Host(root=_DestroyedRoot())
        received = []
        # Не должно бросить наружу, несмотря на то, что root.after() падает
        # внутри _worker -> _run_async.
        host._run_async("devices_table", lambda: "too-late", received.append)
        assert received == []  # _apply никогда не был вызван — root мёртв

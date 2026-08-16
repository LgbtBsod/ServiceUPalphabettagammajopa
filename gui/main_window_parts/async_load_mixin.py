#!/usr/bin/env python3
"""AsyncLoadMixin — общий примитив фоновой загрузки данных БД без блокировки
Tk-цикла (см. AUDIT_REPORT_v25.md, Task O). Запрос выполняется в потоке
core.create_thread(); результат применяется к виджетам ТОЛЬКО через
self.root.after(0, ...) — Tk не потокобезопасен, трогать виджеты можно
исключительно из главного потока, фоновый поток лишь считает данные.

Используется DevicesTableMixin (таблица заказов/поиск) и FinanceMixin
(вкладка Финансы) — раньше обе делали self.db.method(...) синхронно на
главном потоке, и GUI на время запроса к БД полностью замирал."""

from __future__ import annotations

import itertools
import logging
from typing import Any, Callable

from utils.messages import Msg

logger = logging.getLogger(__name__)

# Общий счётчик на процесс — уникальность имени потока внутри одного
# запущенного приложения, не межпроцессный идентификатор.
_thread_seq = itertools.count(1)


class AsyncLoadMixin:
    """Требует от финального класса ServiceCenterApp: self._core, self.root."""

    def _run_async(
        self,
        key: str,
        fetch_fn: Callable[[], Any],
        on_success: Callable[[Any], None],
        *,
        on_error: Callable[[Exception], None] | None = None,
        busy_indicator=None,
        busy_text: str = Msg.LOADING_GENERIC,
    ) -> None:
        """Выполняет fetch_fn() в фоновом потоке; по готовности вызывает
        on_success(result) либо on_error(exc) — всегда на главном потоке
        (через root.after(0, ...)).

        key — логическое имя операции ("devices_table", "finance_tab", ...).
        Если та же key запрошена повторно до того, как пришёл предыдущий
        ответ (пользователь успел переключить фильтр/период), устаревший
        результат молча отбрасывается по генерации-счётчику — не перетирает
        более новые данные, уже показанные на экране.

        busy_indicator — любой объект с интерфейсом start(text)/stop(error=),
        см. gui/widgets/skeleton.py::BusyIndicator/LoadingOverlay.
        """
        gens = getattr(self, "_async_load_gens", None)
        if gens is None:
            gens = self._async_load_gens = {}
        gen = gens[key] = gens.get(key, 0) + 1

        if busy_indicator is not None:
            busy_indicator.start(busy_text)

        thread_name = f"async-{key}-{next(_thread_seq)}"

        def _worker() -> None:
            try:
                result: Any = fetch_fn()
                error: Exception | None = None
            except Exception as e:
                result = None
                error = e

            def _apply() -> None:
                # Освобождаем запись в ThreadManager сразу после применения
                # результата — тот же паттерн, что и pwa/server.py::stop()
                # (core.stop_thread делает join + cleanup_stopped()). Без
                # этого запись singleton-словаря ThreadManager._threads
                # копится вечно (создаём один "одноразовый" поток на каждый
                # load_devices/apply_filters/search_devices/update_finance_display,
                # см. AUDIT_REPORT_v25.md, Task O verify-пасс).
                try:
                    self._core.stop_thread(thread_name, timeout=0.1)
                except Exception:
                    pass
                if busy_indicator is not None:
                    busy_indicator.stop(error=error is not None)
                if gens.get(key) != gen:
                    return  # устарело — пришёл более новый запрос той же key
                if error is not None:
                    logger.error(
                        f"Фоновая загрузка [{key}] завершилась ошибкой: {error}",
                        exc_info=error,
                    )
                    if on_error is not None:
                        on_error(error)
                    return
                on_success(result)

            try:
                self.root.after(0, _apply)
            except Exception:
                # Главное окно уже закрыто (root.destroy() произошёл раньше,
                # чем фоновый запрос успел вернуться) — планировать колбэк на
                # уничтоженный Tk-цикл нельзя и незачем, приложение и так
                # завершается. Найдено адверсарной проверкой (root.after()
                # после root.destroy() бросает RuntimeError на живом Tk), см.
                # AUDIT_REPORT_v25.md, Task O.
                logger.debug(
                    f"Фоновая загрузка [{key}] вернулась после закрытия окна — результат отброшен"
                )

        try:
            self._core.create_thread(thread_name, _worker, daemon=True)
            self._core.start_thread(thread_name)
        except Exception as e:
            # create_thread() падает ValueError на дубле имени, start_thread()
            # тихо возвращает False при внутренней ошибке — в обоих случаях
            # _worker никогда не запустится, и без этой ветки busy_indicator
            # остался бы навсегда "висеть" в состоянии загрузки (найдено
            # адверсарной проверкой, см. AUDIT_REPORT_v25.md, Task O).
            logger.error(f"Не удалось запустить фоновую загрузку [{key}]: {e}", exc_info=True)
            if busy_indicator is not None:
                busy_indicator.stop(error=True)
            if on_error is not None:
                on_error(e)

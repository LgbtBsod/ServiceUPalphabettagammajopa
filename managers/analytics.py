#!/usr/bin/env python3

"""Модуль аналитики.

Получает запрос из GUI через ядро, строит параметризированный запрос к
db_access ТОЖЕ через ядро (не держит своего движка/сессии БД), собирает
результат в форму, удобную GUI, и попутно готовит JSON — на будущее, если
кроме GUI аналитика понадобится и в вебе (см. pwa/server.py).

В отличие от plugins/clients и plugins/employees (которые владеют СВОЕЙ
таблицей — clients/employees — и поэтому легитимно резолвят свой репозиторий
через DI), Analytics не владеет никакой таблицей: она агрегирует чужие
данные (devices/finances). Поэтому это простой Kernel-модуль (как
SettingsManager/BackupManager), а не плагин — нет второй реализации, которую
нужно было бы подменять через DI, см. AUDIT_REPORT_v21.md о том, что не
каждый модуль обязан быть плагином.
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from core.base import BaseService, PermissionObject

logger = logging.getLogger(__name__)


@dataclass
class AnalyticsRequest:
    """Описание аналитического запроса — приходит из GUI (и в будущем из
    веб/PWA) через ядро: core.call_module_method('analytics', 'run_report', ...)."""

    report: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class AnalyticsResult:
    """Результат отчёта сразу в двух формах: `data` — то, что нужно GUI
    (список словарей / словарь), `to_json()` — для будущего веб-потребителя."""

    report: str
    data: Any

    def to_json(self) -> str:
        return json.dumps(self.data, ensure_ascii=False, default=str)


class AnalyticsService(BaseService):
    """Сервис аналитики — единственная точка построения аналитических
    запросов к БД."""

    permission_object = PermissionObject(name="ANALYTICS", operations=("read",))

    # Имя отчёта (то, что просит GUI/веб) -> имя вычисления в
    # Database.calculate(). Явный whitelist — как и в самом calculate()/
    # query() — вызывающий код не может запросить произвольное вычисление
    # строкой, только то, что здесь объявлено.
    _REPORTS: dict[str, str] = {
        "overdue_count": "overdue_count",
        "overdue_orders": "overdue_orders",
        "dashboard_stats": "dashboard_stats",
        "status_breakdown": "status_breakdown",
        "priority_breakdown": "priority_breakdown",
    }

    # Отчёты, чувствительные к порогу просрочки — если вызывающий код (PWA/
    # внешний потребитель) не прислал свой threshold_days, подставляем
    # пользовательскую настройку "overdue_days" по умолчанию, а не
    # захардкоженную константу Database-слоя. Без этого PWA/веб-дашборд и
    # desktop-виджет (который явно читает overdue_days сам) молча
    # показывали разные числа при нестандартном пороге, см.
    # AUDIT_REPORT_v25.md. Явный whitelist по той же причине, что и
    # _REPORTS: calculate()-хендлеры без threshold_days-параметра (status/
    # priority_breakdown) упадут TypeError'ом на неожиданном kwarg'е, если
    # подставлять его всем подряд.
    _THRESHOLD_AWARE_REPORTS = frozenset({"overdue_count", "overdue_orders", "dashboard_stats"})
    _DEFAULT_OVERDUE_DAYS = 14

    def __init__(self, core):
        # Ядро — единственный путь к db_access. Analytics не владеет своей
        # таблицей, поэтому не резолвит репозиторий через DI (как
        # plugins/clients-employees), а идёт через
        # core.call_module_method('db_access', ...) — так и должен вести
        # себя модуль, которому нужны чужие данные.
        self._core = core

    def _resolve_params(self, report: str, params: dict[str, Any]) -> dict[str, Any]:
        if report not in self._THRESHOLD_AWARE_REPORTS or "threshold_days" in params:
            return params
        try:
            settings_api = self._core.get_module_api("settings")
            threshold = settings_api.get("overdue_days", self._DEFAULT_OVERDUE_DAYS)
        except Exception:
            threshold = self._DEFAULT_OVERDUE_DAYS
        return {**params, "threshold_days": threshold}

    def run_report(self, request: AnalyticsRequest) -> AnalyticsResult:
        """Выполняет именованный отчёт, параметризованный request.params.

        Raises:
            ValueError: неизвестное имя отчёта (нет в whitelist _REPORTS).
        """
        calc_name = self._REPORTS.get(request.report)
        if calc_name is None:
            raise ValueError(
                f"Неизвестный отчёт: {request.report!r}. "
                f"Доступны: {sorted(self._REPORTS)}"
            )
        params = self._resolve_params(request.report, request.params)
        try:
            data = self._core.call_module_method("db_access", "calculate", calc_name, **params)
        except Exception as e:
            logger.error(f"Ошибка построения отчёта {request.report!r}: {e}", exc_info=True)
            raise
        return AnalyticsResult(report=request.report, data=data)

    def available_reports(self) -> list[str]:
        """Список доступных имён отчётов — чтобы GUI/веб не хардкодили их
        отдельно от этого whitelist'а."""
        return sorted(self._REPORTS)

    def verify_calculations_available(self, known_calculations) -> list[str]:
        """Возвращает имена отчётов из _REPORTS, чей calc-target отсутствует
        среди known_calculations (обычно — db.list_calculations(), см.
        database/facade/calculate_mixin.py). Пусто — whitelist не разошёлся.

        Раньше list_calculations() существовал только как интроспекция ДЛЯ
        тестов (tests/test_analytics.py::TestReportsWhitelistConsistency) —
        сам _REPORTS никогда не сверялся с ним в реально работающем
        приложении, только при прогоне test suite. Вызывается из
        bootstrap.py сразу после регистрации db_access/analytics — НЕ из
        __init__, т.к. на момент конструирования AnalyticsService db_access
        может быть ещё не зарегистрирован (порядок регистрации модулей не
        гарантирован извне). См. AUDIT_REPORT_v25.md, Task P verify-пасс."""
        known = set(known_calculations)
        return [
            report for report, calc_name in self._REPORTS.items() if calc_name not in known
        ]

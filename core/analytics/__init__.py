"""
Аналитика обращений к данным (Data Access Analytics)

Отслеживает все обращения к DataAccessManager:
- Кто вызывает (ядро, плагины, модули)
- Тип операции (Command/Query)
- Время выполнения
- Количество затронутых строк
- Кэш хиты/промахи

Интегрируется с ядром для сбора метрик.
"""

from .db_access_analytics import (
    DataAccessMetric,
    DataAccessAnalytics,
    get_analytics,
    track_db_access
)

__all__ = [
    'DataAccessMetric',
    'DataAccessAnalytics',
    'get_analytics',
    'track_db_access'
]
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

import time
import logging
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from functools import wraps
from collections import defaultdict
import threading

logger = logging.getLogger(__name__)


@dataclass
class DataAccessMetric:
    """Метрика одного обращения к БД"""
    caller: str           # Кто вызвал (модуль.класс.метод)
    operation_type: str   # Command/Query
    table_name: str       # Таблица
    method_name: str      # Метод (insert, update, select, etc.)
    duration_ms: float    # Время выполнения в мс
    rows_affected: int    # Количество строк
    cache_hit: bool       # Попали ли в кэш
    timestamp: float = field(default_factory=time.time)
    error: Optional[str] = None


class DataAccessAnalytics:
    """
    Сборщик аналитики обращений к данным.
    
    Работает как обёртка вокруг DataAccessManager.
    Все вызовы проходят через этот класс для логирования.
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._metrics: List[DataAccessMetric] = []
        self._stats_by_caller: Dict[str, Dict] = defaultdict(lambda: {
            'total_calls': 0,
            'commands': 0,
            'queries': 0,
            'total_duration_ms': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'errors': 0
        })
        self._stats_by_table: Dict[str, Dict] = defaultdict(lambda: {
            'reads': 0,
            'writes': 0,
            'total_duration_ms': 0
        })
        self._max_metrics = 10000  # Храним последние N записей
        self._enabled = True
        self._initialized = True
        
        logger.info("DataAccessAnalytics инициализирован")
    
    def enable(self):
        """Включить сбор аналитики"""
        self._enabled = True
        logger.info("Сбор аналитики включён")
    
    def disable(self):
        """Выключить сбор аналитики"""
        self._enabled = False
        logger.info("Сбор аналитики выключен")
    
    def record_access(self, metric: DataAccessMetric):
        """Запись метрики обращения"""
        if not self._enabled:
            return
        
        self._metrics.append(metric)
        
        # Ограничение размера истории
        if len(self._metrics) > self._max_metrics:
            self._metrics = self._metrics[-self._max_metrics:]
        
        # Обновление статистики по вызывающему
        caller_stats = self._stats_by_caller[metric.caller]
        caller_stats['total_calls'] += 1
        
        if metric.operation_type == 'Command':
            caller_stats['commands'] += 1
        else:
            caller_stats['queries'] += 1
        
        caller_stats['total_duration_ms'] += metric.duration_ms
        
        if metric.cache_hit:
            caller_stats['cache_hits'] += 1
        else:
            caller_stats['cache_misses'] += 1
        
        if metric.error:
            caller_stats['errors'] += 1
        
        # Обновление статистики по таблице
        table_stats = self._stats_by_table[metric.table_name]
        if metric.operation_type == 'Command':
            table_stats['writes'] += 1
        else:
            table_stats['reads'] += 1
        
        table_stats['total_duration_ms'] += metric.duration_ms
    
    def get_caller_stats(self, caller: Optional[str] = None) -> Dict[str, Any]:
        """Получение статистики по вызывающему"""
        if caller:
            stats = self._stats_by_caller.get(caller, {})
            return dict(stats)
        return dict(self._stats_by_caller)
    
    def get_table_stats(self, table: Optional[str] = None) -> Dict[str, Any]:
        """Получение статистики по таблице"""
        if table:
            stats = self._stats_by_table.get(table, {})
            return dict(stats)
        return dict(self._stats_by_table)
    
    def get_recent_metrics(self, limit: int = 100) -> List[DataAccessMetric]:
        """Получение последних метрик"""
        return self._metrics[-limit:]
    
    def get_slow_queries(self, threshold_ms: float = 100.0) -> List[DataAccessMetric]:
        """Получение медленных запросов (>threshold_ms)"""
        return [m for m in self._metrics if m.duration_ms > threshold_ms]
    
    def get_error_metrics(self) -> List[DataAccessMetric]:
        """Получение метрик с ошибками"""
        return [m for m in self._metrics if m.error]
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Статистика по кэшу"""
        total_hits = sum(1 for m in self._metrics if m.cache_hit)
        total_misses = sum(1 for m in self._metrics if not m.cache_hit)
        total = total_hits + total_misses
        
        return {
            'hit_rate': (total_hits / total * 100) if total > 0 else 0,
            'total_hits': total_hits,
            'total_misses': total_misses
        }
    
    def reset_stats(self):
        """Сброс статистики"""
        self._metrics.clear()
        self._stats_by_caller.clear()
        self._stats_by_table.clear()
        logger.info("Статистика сброшена")
    
    def export_report(self) -> Dict[str, Any]:
        """Экспорт полного отчёта"""
        return {
            'summary': {
                'total_calls': sum(s['total_calls'] for s in self._stats_by_caller.values()),
                'unique_callers': len(self._stats_by_caller),
                'unique_tables': len(self._stats_by_table),
                'avg_duration_ms': sum(m.duration_ms for m in self._metrics) / len(self._metrics) if self._metrics else 0
            },
            'by_caller': dict(self._stats_by_caller),
            'by_table': dict(self._stats_by_table),
            'cache': self.get_cache_stats(),
            'slow_queries_count': len(self.get_slow_queries()),
            'errors_count': len(self.get_error_metrics())
        }


# Глобальный экземпляр
_analytics: Optional[DataAccessAnalytics] = None

def get_analytics() -> DataAccessAnalytics:
    """Получение глобального экземпляра аналитики"""
    global _analytics
    if _analytics is None:
        _analytics = DataAccessAnalytics()
    return _analytics


def track_db_access(operation_type: str = 'Query', table_name: str = 'unknown'):
    """
    Декоратор для отслеживания обращений к БД.
    
    Использование:
        @track_db_access(operation_type='Command', table_name='orders')
        def create_order(self, data):
            ...
    """
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            analytics = get_analytics()
            
            # Определение вызывающего
            if args and hasattr(args[0], '__class__'):
                caller = f"{args[0].__class__.__module__}.{args[0].__class__.__name__}.{func.__name__}"
            else:
                caller = f"{func.__module__}.{func.__name__}"
            
            start_time = time.time()
            cache_hit = False
            error = None
            rows_affected = 0
            
            try:
                result = func(*args, **kwargs)
                
                # Попытка определить количество строк
                if isinstance(result, list):
                    rows_affected = len(result)
                elif isinstance(result, int):
                    rows_affected = result
                
                # Проверка кэш хита (если есть атрибут)
                if hasattr(func, '_cache_hit'):
                    cache_hit = func._cache_hit
                
                return result
            
            except Exception as e:
                error = str(e)
                raise
            
            finally:
                duration_ms = (time.time() - start_time) * 1000
                
                metric = DataAccessMetric(
                    caller=caller,
                    operation_type=operation_type,
                    table_name=table_name,
                    method_name=func.__name__,
                    duration_ms=duration_ms,
                    rows_affected=rows_affected,
                    cache_hit=cache_hit,
                    error=error
                )
                
                analytics.record_access(metric)
                
                # Логирование медленных запросов
                if duration_ms > 100:
                    logger.warning(f"Медленный запрос: {caller} выполнился за {duration_ms:.2f}ms")
        
        return wrapper
    return decorator

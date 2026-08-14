"""
Analytics Module - Модуль аналитики и отчётности.

Работает ТОЛЬКО через db_access модуль для получения данных.
Не содержит прямой работы с БД.

Принципы:
- Отдельный поток для тяжёлых вычислений
- Генерация JSON для веб-интерфейса
- Кэширование результатов
- Event-driven уведомления о готовности отчётов
"""

from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, Future
import threading
import json
import logging

from core.base import BaseService, LoggableMixin
from core.events import Event, get_event_bus, on_event
from infrastructure.db_access import (
    get_db_access, 
    db_session, 
    db_execute_query,
    Query,
    QueryResult,
)

logger = logging.getLogger(__name__)


@dataclass
class AnalyticsReport:
    """Отчёт аналитики."""
    report_type: str
    generated_at: datetime = field(default_factory=datetime.now)
    data: Dict[str, Any] = field(default_factory=dict)
    filters: Dict[str, Any] = field(default_factory=dict)
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None
    
    def to_json(self, indent: int = 2) -> str:
        """Экспортирует отчёт в JSON."""
        return json.dumps({
            'report_type': self.report_type,
            'generated_at': self.generated_at.isoformat(),
            'period': {
                'start': self.period_start.isoformat() if self.period_start else None,
                'end': self.period_end.isoformat() if self.period_end else None,
            },
            'filters': self.filters,
            'data': self.data,
        }, indent=indent, ensure_ascii=False)
    
    def save_to_file(self, filepath: str) -> None:
        """Сохраняет отчёт в файл."""
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(self.to_json())


@dataclass
class DashboardMetrics:
    """Метрики для дашборда."""
    total_orders: int = 0
    active_orders: int = 0
    completed_orders: int = 0
    cancelled_orders: int = 0
    total_revenue: float = 0.0
    pending_revenue: float = 0.0
    total_clients: int = 0
    new_clients_today: int = 0
    avg_order_value: float = 0.0
    avg_completion_time_hours: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'total_orders': self.total_orders,
            'active_orders': self.active_orders,
            'completed_orders': self.completed_orders,
            'cancelled_orders': self.cancelled_orders,
            'total_revenue': self.total_revenue,
            'pending_revenue': self.pending_revenue,
            'total_clients': self.total_clients,
            'new_clients_today': self.new_clients_today,
            'avg_order_value': self.avg_order_value,
            'avg_completion_time_hours': self.avg_completion_time_hours,
        }


class AnalyticsQuery(Query[Dict[str, Any]]):
    """Базовый класс для аналитических запросов."""
    
    def __init__(self, filters: Optional[Dict[str, Any]] = None):
        self.filters = filters or {}
    
    def execute(self, session) -> Dict[str, Any]:
        raise NotImplementedError


class OrdersAnalyticsQuery(AnalyticsQuery):
    """Аналитический запрос по заказам."""
    
    def execute(self, session) -> Dict[str, Any]:
        from database.sqlalchemy_models import Order, WorkItem
        
        # Фильтры
        date_from = self.filters.get('date_from')
        date_to = self.filters.get('date_to')
        status = self.filters.get('status')
        
        query = session.query(Order)
        
        if date_from:
            query = query.filter(Order.created_at >= date_from)
        if date_to:
            query = query.filter(Order.created_at <= date_to)
        if status:
            query = query.filter(Order.status == status)
        
        orders = query.all()
        
        # Агрегация
        total = len(orders)
        active = sum(1 for o in orders if o.status in ['new', 'in_progress'])
        completed = sum(1 for o in orders if o.status == 'completed')
        cancelled = sum(1 for o in orders if o.status == 'cancelled')
        
        total_revenue = sum(
            float(o.total_amount or 0) 
            for o in orders 
            if o.status == 'completed'
        )
        pending_revenue = sum(
            float(o.total_amount or 0) 
            for o in orders 
            if o.status in ['new', 'in_progress']
        )
        
        avg_order_value = total_revenue / completed if completed > 0 else 0.0
        
        return {
            'total_orders': total,
            'active_orders': active,
            'completed_orders': completed,
            'cancelled_orders': cancelled,
            'total_revenue': total_revenue,
            'pending_revenue': pending_revenue,
            'avg_order_value': avg_order_value,
        }


class ClientsAnalyticsQuery(AnalyticsQuery):
    """Аналитический запрос по клиентам."""
    
    def execute(self, session) -> Dict[str, Any]:
        from database.sqlalchemy_models import Client
        
        today = datetime.now().date()
        
        total_clients = session.query(Client).count()
        new_clients_today = session.query(Client).filter(
            Client.created_at >= today
        ).count()
        
        # Топ клиентов по количеству заказов
        from database.sqlalchemy_models import Order
        top_clients = session.query(
            Client.name,
            Client.phone,
            func.count(Order.id).label('order_count')
        ).join(
            Order, Client.id == Order.client_id
        ).group_by(
            Client.id
        ).order_by(
            func.count(Order.id).desc()
        ).limit(10).all()
        
        return {
            'total_clients': total_clients,
            'new_clients_today': new_clients_today,
            'top_clients': [
                {'name': name, 'phone': phone, 'orders': count}
                for name, phone, count in top_clients
            ],
        }


class AnalyticsService(BaseService):
    """
    Сервис аналитики.
    
    Использует отдельный пул потоков для тяжёлых вычислений.
    Работает только через db_access.
    """
    
    def __init__(self, max_workers: int = 4):
        super().__init__()
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self._cache: Dict[str, tuple] = {}  # key -> (data, timestamp)
        self._cache_ttl = timedelta(minutes=5)
        self.logger.info("AnalyticsService initialized")
    
    def get_dashboard_metrics(
        self, 
        filters: Optional[Dict[str, Any]] = None
    ) -> DashboardMetrics:
        """Получает метрики для дашборда."""
        cache_key = f"dashboard:{filters}"
        
        # Проверяем кэш
        if self._is_cache_valid(cache_key):
            self.logger.debug("Using cached dashboard metrics")
            return self._cache[cache_key][0]
        
        try:
            # Выполняем аналитический запрос через db_access
            query = OrdersAnalyticsQuery(filters)
            result = db_execute_query(query)
            
            if not result.success:
                self.logger.error(f"Failed to get orders analytics: {result.error}")
                return DashboardMetrics()
            
            orders_data = result.data
            
            # Получаем данные по клиентам
            clients_query = ClientsAnalyticsQuery(filters)
            clients_result = db_execute_query(clients_query)
            
            clients_data = clients_result.data if clients_result.success else {}
            
            metrics = DashboardMetrics(
                total_orders=orders_data.get('total_orders', 0),
                active_orders=orders_data.get('active_orders', 0),
                completed_orders=orders_data.get('completed_orders', 0),
                cancelled_orders=orders_data.get('cancelled_orders', 0),
                total_revenue=orders_data.get('total_revenue', 0.0),
                pending_revenue=orders_data.get('pending_revenue', 0.0),
                avg_order_value=orders_data.get('avg_order_value', 0.0),
                total_clients=clients_data.get('total_clients', 0),
                new_clients_today=clients_data.get('new_clients_today', 0),
            )
            
            # Сохраняем в кэш
            self._cache[cache_key] = (metrics, datetime.now())
            
            return metrics
            
        except Exception as e:
            self.logger.error(f"Error getting dashboard metrics: {e}")
            return DashboardMetrics()
    
    def generate_report(
        self,
        report_type: str,
        filters: Optional[Dict[str, Any]] = None,
        period_start: Optional[datetime] = None,
        period_end: Optional[datetime] = None,
    ) -> Future[AnalyticsReport]:
        """
        Генерирует отчёт в отдельном потоке.
        
        Возвращает Future для получения результата.
        """
        def _generate() -> AnalyticsReport:
            self.logger.info(f"Generating report: {report_type}")
            
            # Собираем данные в зависимости от типа отчёта
            data = self._collect_report_data(report_type, filters, period_start, period_end)
            
            report = AnalyticsReport(
                report_type=report_type,
                data=data,
                filters=filters or {},
                period_start=period_start,
                period_end=period_end,
            )
            
            # Публикуем событие о готовности отчёта
            event_bus = get_event_bus()
            event_bus.publish(Event(
                event_type="analytics.report_generated",
                source="analytics_service",
                data={
                    'report_type': report_type,
                    'generated_at': report.generated_at.isoformat(),
                },
            ))
            
            return report
        
        return self.executor.submit(_generate)
    
    def _collect_report_data(
        self,
        report_type: str,
        filters: Optional[Dict[str, Any]],
        period_start: Optional[datetime],
        period_end: Optional[datetime],
    ) -> Dict[str, Any]:
        """Собирает данные для отчёта."""
        try:
            if report_type == 'orders_summary':
                return self._get_orders_summary(filters, period_start, period_end)
            elif report_type == 'clients_activity':
                return self._get_clients_activity(filters, period_start, period_end)
            elif report_type == 'revenue':
                return self._get_revenue_report(filters, period_start, period_end)
            else:
                self.logger.warning(f"Unknown report type: {report_type}")
                return {}
                
        except Exception as e:
            self.logger.error(f"Error collecting report data: {e}")
            return {}
    
    def _get_orders_summary(
        self,
        filters: Optional[Dict[str, Any]],
        period_start: Optional[datetime],
        period_end: Optional[datetime],
    ) -> Dict[str, Any]:
        """Получает сводку по заказам."""
        query_filters = filters or {}
        if period_start:
            query_filters['date_from'] = period_start
        if period_end:
            query_filters['date_to'] = period_end
        
        query = OrdersAnalyticsQuery(query_filters)
        result = db_execute_query(query)
        
        if result.success:
            return result.data
        return {}
    
    def _get_clients_activity(
        self,
        filters: Optional[Dict[str, Any]],
        period_start: Optional[datetime],
        period_end: Optional[datetime],
    ) -> Dict[str, Any]:
        """Получает активность клиентов."""
        query_filters = filters or {}
        if period_start:
            query_filters['date_from'] = period_start
        if period_end:
            query_filters['date_to'] = period_end
        
        query = ClientsAnalyticsQuery(query_filters)
        result = db_execute_query(query)
        
        if result.success:
            return result.data
        return {}
    
    def _get_revenue_report(
        self,
        filters: Optional[Dict[str, Any]],
        period_start: Optional[datetime],
        period_end: Optional[datetime],
    ) -> Dict[str, Any]:
        """Получает отчёт по выручке."""
        query_filters = filters or {}
        if period_start:
            query_filters['date_from'] = period_start
        if period_end:
            query_filters['date_to'] = period_end
        
        # Используем orders analytics
        orders_query = OrdersAnalyticsQuery(query_filters)
        result = db_execute_query(orders_query)
        
        if result.success:
            data = result.data
            return {
                'total_revenue': data.get('total_revenue', 0.0),
                'pending_revenue': data.get('pending_revenue', 0.0),
                'avg_order_value': data.get('avg_order_value', 0.0),
                'completed_orders': data.get('completed_orders', 0),
                'period': {
                    'start': period_start.isoformat() if period_start else None,
                    'end': period_end.isoformat() if period_end else None,
                },
            }
        return {}
    
    def _is_cache_valid(self, cache_key: str) -> bool:
        """Проверяет валидность кэша."""
        if cache_key not in self._cache:
            return False
        
        data, timestamp = self._cache[cache_key]
        return datetime.now() - timestamp < self._cache_ttl
    
    def clear_cache(self) -> None:
        """Очищает кэш."""
        self._cache.clear()
        self.logger.info("Analytics cache cleared")
    
    def shutdown(self) -> None:
        """Останавливает сервис."""
        self.executor.shutdown(wait=True)
        self.logger.info("AnalyticsService shut down")


# Глобальный экземпляр сервиса
_analytics_service: Optional[AnalyticsService] = None


def get_analytics_service() -> AnalyticsService:
    """Получает глобальный экземпляр сервиса аналитики."""
    global _analytics_service
    if _analytics_service is None:
        _analytics_service = AnalyticsService()
    return _analytics_service


def reset_analytics_service() -> None:
    """Сбрасывает сервис (для тестов)."""
    global _analytics_service
    if _analytics_service:
        _analytics_service.shutdown()
    _analytics_service = None

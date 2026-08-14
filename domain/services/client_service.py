"""
Client domain service - бизнес-сервис для работы с клиентами.

Содержит бизнес-логику управления клиентами:
- Создание и обновление клиентов
- Расчет статистики клиента
- Поиск и фильтрация
"""

from __future__ import annotations
import logging
from typing import List, Optional, Tuple, Protocol
from datetime import datetime, timedelta

from ..entities import Client

logger = logging.getLogger(__name__)


class ClientRepositoryProtocol(Protocol):
    """Протокол репозитория клиентов."""
    
    def get(self, client_id: int) -> Optional[Client]: ...
    def get_by_phone(self, phone: str) -> Optional[Client]: ...
    def get_all(self) -> List[Client]: ...
    def save(self, client: Client) -> Client: ...
    def delete(self, client_id: int) -> bool: ...
    def search(self, query: str) -> List[Client]: ...


class ClientService:
    """
    Сервис для управления клиентами.
    
    Отвечает за:
    - Создание и обновление клиентов
    - Поиск клиентов
    - Расчет статистики
    - Валидацию данных
    """
    
    def __init__(self, repository: ClientRepositoryProtocol):
        self._repository = repository
    
    def create_or_update_client(
        self,
        name: str,
        phone: str,
        status: str = "Новый",
    ) -> Tuple[bool, Optional[Client], str]:
        """
        Создание нового клиента или обновление существующего.
        
        Клиент идентифицируется по телефону (уникальный ключ).
        
        Returns:
            Кортеж (успех, клиент или None, сообщение)
        """
        try:
            # Нормализация телефона
            normalized_phone = self._normalize_phone(phone)
            
            if not normalized_phone:
                return False, None, "Некорректный номер телефона"
            
            if not name.strip():
                return False, None, "Не указано имя клиента"
            
            # Проверка существования клиента
            existing_client = self._repository.get_by_phone(normalized_phone)
            
            if existing_client:
                # Обновление существующего
                existing_client.name = name.strip()
                if status != "Новый":
                    existing_client.status = status
                existing_client.last_order_date = datetime.now()
                
                saved_client = self._repository.save(existing_client)
                logger.info(f"Обновлен клиент {name} ({normalized_phone})")
                return True, saved_client, f"Клиент обновлен"
            
            else:
                # Создание нового
                new_client = Client(
                    name=name.strip(),
                    phone=normalized_phone,
                    status=status,
                    first_order_date=datetime.now(),
                    last_order_date=datetime.now(),
                )
                
                saved_client = self._repository.save(new_client)
                logger.info(f"Создан новый клиент {name} ({normalized_phone})")
                return True, saved_client, f"Клиент создан"
                
        except Exception as e:
            logger.error(f"Ошибка создания/обновления клиента: {e}", exc_info=True)
            return False, None, f"Ошибка: {e}"
    
    def update_client_stats(
        self,
        client_id: int,
        order_total: float,
        is_completed: bool = False,
    ) -> bool:
        """
        Обновление статистики клиента после заказа.
        
        Args:
            client_id: ID клиента
            order_total: Стоимость заказа
            is_completed: Заказ завершен (влияет на completed_orders)
        """
        try:
            client = self._repository.get(client_id)
            if not client:
                return False
            
            client.total_orders += 1
            client.total_spent += order_total
            
            if is_completed:
                client.completed_orders += 1
            
            client.last_order_date = datetime.now()
            
            # Определение любимого устройства (упрощенно)
            # В реальной реализации нужно анализировать историю заказов
            
            self._repository.save(client)
            return True
            
        except Exception as e:
            logger.error(f"Ошибка обновления статистики клиента: {e}", exc_info=True)
            return False
    
    def get_client_by_phone(self, phone: str) -> Optional[Client]:
        """Поиск клиента по телефону."""
        normalized_phone = self._normalize_phone(phone)
        return self._repository.get_by_phone(normalized_phone)
    
    def search_clients(self, query: str) -> List[Client]:
        """
        Поиск клиентов по имени или телефону.
        
        Args:
            query: Поисковый запрос
        """
        return self._repository.search(query)
    
    def get_vip_clients(self, min_spent: float = 10000.0) -> List[Client]:
        """
        Получение VIP-клиентов (потративших больше определенной суммы).
        
        Args:
            min_spent: Минимальная сумма расходов
        """
        all_clients = self._repository.get_all()
        return [c for c in all_clients if c.total_spent >= min_spent]
    
    def get_inactive_clients(self, days: int = 90) -> List[Client]:
        """
        Получение неактивных клиентов (не заказывавших N дней).
        
        Args:
            days: Количество дней неактивности
        """
        all_clients = self._repository.get_all()
        cutoff_date = datetime.now() - timedelta(days=days)
        
        return [
            c for c in all_clients 
            if c.last_order_date and c.last_order_date < cutoff_date
        ]
    
    def get_statistics(self) -> dict:
        """Получение общей статистики по клиентам."""
        clients = self._repository.get_all()
        
        total_clients = len(clients)
        new_clients = sum(1 for c in clients if c.status == "Новый")
        vip_clients = len(self.get_vip_clients())
        
        avg_order_value = 0
        total_spent = sum(c.total_spent for c in clients)
        total_orders = sum(c.total_orders for c in clients)
        
        if total_orders > 0:
            avg_order_value = total_spent / total_orders
        
        return {
            'total_clients': total_clients,
            'new_clients': new_clients,
            'vip_clients': vip_clients,
            'total_spent': total_spent,
            'total_orders': total_orders,
            'avg_order_value': avg_order_value,
        }
    
    def _normalize_phone(self, phone: str) -> str:
        """
        Нормализация номера телефона.
        
        Удаляет все нецифровые символы, кроме +.
        """
        if not phone:
            return ""
        
        # Простая нормализация - оставляем только цифры
        # В production можно использовать библиотеку phonenumbers
        normalized = ''.join(c for c in phone if c.isdigit())
        
        # Добавляем +7 для российских номеров без кода
        if len(normalized) == 10 and normalized.startswith('8'):
            normalized = '7' + normalized[1:]
        elif len(normalized) == 10:
            normalized = '7' + normalized
        
        return '+' + normalized if not normalized.startswith('+') else normalized
    
    def validate_phone(self, phone: str) -> Tuple[bool, str]:
        """
        Валидация номера телефона.
        
        Returns:
            Кортеж (валиден, сообщение)
        """
        normalized = self._normalize_phone(phone)
        
        if not normalized:
            return False, "Телефон не может быть пустым"
        
        # Проверка длины (минимум 10 цифр для RU, максимум 15 для международных)
        digits_only = normalized.replace('+', '')
        if len(digits_only) < 10:
            return False, "Слишком короткий номер"
        if len(digits_only) > 15:
            return False, "Слишком длинный номер"
        
        return True, "OK"

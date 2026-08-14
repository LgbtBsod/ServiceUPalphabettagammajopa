"""
Core Contracts (Ports)
Определение интерфейсов и DTO для Clean Architecture.
Здесь нет зависимостей от SQLAlchemy, UI или внешних библиотек.
Только стандартная библиотека и typing.

Принципы:
- DIP: Зависимости от абстракций (Protocol), а не реализаций
- SRP: Каждый протокол отвечает за одну сущность
- SSOT: DTO определены один раз здесь
"""
from __future__ import annotations
from typing import Protocol, Any, Optional
from abc import abstractmethod
from datetime import datetime
from dataclasses import dataclass, field


# === Базовые DTO (Data Transfer Objects) ===
@dataclass
class BaseDTO:
    """Базовый класс для всех объектов передачи данных."""
    id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class OrderDTO(BaseDTO):
    """DTO для заказа."""
    order_number: str = ""
    client_id: Optional[int] = None
    status: str = "new"
    priority: str = "normal"
    total_amount: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ClientDTO(BaseDTO):
    """DTO для клиента."""
    name: str = ""
    contact_info: str = ""
    status: str = "active"


# === Контракты Репозиториев (Ports) ===
class IOrderRepository(Protocol):
    """
    Контракт для работы с заказами.
    Реализуется в infrastructure слое (SQLAlchemy).
    """
    
    @abstractmethod
    def get_by_id(self, order_id: int) -> Optional[OrderDTO]:
        """Получить заказ по ID."""
        pass

    @abstractmethod
    def get_all(self, filters: Optional[dict[str, Any]] = None) -> list[OrderDTO]:
        """Получить все заказы с фильтрацией."""
        pass

    @abstractmethod
    def save(self, dto: OrderDTO) -> OrderDTO:
        """Сохранить заказ (создать или обновить)."""
        pass

    @abstractmethod
    def delete(self, order_id: int) -> bool:
        """Удалить заказ по ID."""
        pass


class IClientRepository(Protocol):
    """
    Контракт для работы с клиентами.
    Реализуется в infrastructure слое (SQLAlchemy).
    """
    
    @abstractmethod
    def get_by_id(self, client_id: int) -> Optional[ClientDTO]:
        """Получить клиента по ID."""
        pass

    @abstractmethod
    def get_all(self, filters: Optional[dict[str, Any]] = None) -> list[ClientDTO]:
        """Получить всех клиентов с фильтрацией."""
        pass

    @abstractmethod
    def save(self, dto: ClientDTO) -> ClientDTO:
        """Сохранить клиента."""
        pass

    @abstractmethod
    def delete(self, client_id: int) -> bool:
        """Удалить клиента."""
        pass


# === Сервис Локатор (Упрощенный DI Container) ===
class CoreContainer:
    """
    Единая точка входа для получения реализаций репозиториев.
    Реализует Dependency Injection через регистрацию зависимостей.
    
    Пример использования:
        kernel = CoreContainer()
        kernel.register_order_repository(SqlAlchemyOrderRepository(session))
        
        # Получение доступа к данным через ядро
        orders = kernel.orders.get_all(filters={'status': 'new'})
    """
    _instance: Optional["CoreContainer"] = None
    _order_repo: Optional[IOrderRepository] = None
    _client_repo: Optional[IClientRepository] = None

    def __new__(cls) -> "CoreContainer":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def register_order_repository(self, repo: IOrderRepository) -> None:
        """Зарегистрировать реализацию репозитория заказов."""
        self._order_repo = repo

    def register_client_repository(self, repo: IClientRepository) -> None:
        """Зарегистрировать реализацию репозитория клиентов."""
        self._client_repo = repo

    @property
    def orders(self) -> IOrderRepository:
        """Получить репозиторий заказов."""
        if self._order_repo is None:
            raise RuntimeError(
                "OrderRepository not registered in CoreContainer. "
                "Call register_order_repository() first."
            )
        return self._order_repo

    @property
    def clients(self) -> IClientRepository:
        """Получить репозиторий клиентов."""
        if self._client_repo is None:
            raise RuntimeError(
                "ClientRepository not registered in CoreContainer. "
                "Call register_client_repository() first."
            )
        return self._client_repo

    def reset(self) -> None:
        """Сбросить все регистрации (для тестов)."""
        self._order_repo = None
        self._client_repo = None


# Глобальный экземпляр ядра (Singleton)
kernel = CoreContainer()

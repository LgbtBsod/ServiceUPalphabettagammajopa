#!/usr/bin/env python3

"""Нативная машина состояний заказа на стандартных возможностях Python 3.14

Принципы:
- State Pattern без сторонних библиотек
- Type hints Python 3.14
- Immutable transitions (frozen dataclass)
- Protocol для расширяемости
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Protocol

logger = logging.getLogger(__name__)


class OrderStatus(Enum):
    """Статусы заказа (SSOT)."""

    DRAFT = auto()  # Черновик
    NEW = auto()  # Новый заказ
    DIAGNOSTICS = auto()  # Диагностика
    WAITING_PARTS = auto()  # Ожидание запчастей
    REPAIRING = auto()  # В ремонте
    TESTING = auto()  # Тестирование
    READY = auto()  # Готов к выдаче
    ISSUED = auto()  # Выдан клиенту
    CANCELLED = auto()  # Отменен
    REFUSED = auto()  # Отказ от ремонта


@dataclass(frozen=True)
class StateTransition:
    """Неизменяемый переход состояния."""

    from_status: OrderStatus
    to_status: OrderStatus
    allowed: bool
    description: str


@dataclass
class TransitionHistory:
    """История переходов состояния."""

    from_status: OrderStatus
    to_status: OrderStatus
    timestamp: datetime
    user: str | None = None
    comment: str = ""


class StateValidator(Protocol):
    """Протокол валидатора переходов."""

    def can_transition(self, from_status: OrderStatus, to_status: OrderStatus) -> bool:
        """Проверка возможности перехода."""
        ...

    def get_allowed_transitions(self, current_status: OrderStatus) -> list[OrderStatus]:
        """Получение списка допустимых следующих статусов."""
        ...


@dataclass
class NativeStateMachine:
    """Нативная машина состояний на стандартном Python.

    Реализует:
    - Валидацию переходов
    - Историю изменений
    - Callback'и при смене состояния
    """

    # Таблица допустимых переходов (SSOT)
    ALLOWED_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = field(
        default_factory=lambda: {
            OrderStatus.DRAFT: {OrderStatus.NEW, OrderStatus.CANCELLED},
            OrderStatus.NEW: {OrderStatus.DIAGNOSTICS, OrderStatus.CANCELLED},
            OrderStatus.DIAGNOSTICS: {
                OrderStatus.WAITING_PARTS,
                OrderStatus.REPAIRING,
                OrderStatus.REFUSED,
            },
            OrderStatus.WAITING_PARTS: {OrderStatus.REPAIRING, OrderStatus.CANCELLED},
            OrderStatus.REPAIRING: {OrderStatus.TESTING, OrderStatus.REFUSED},
            OrderStatus.TESTING: {OrderStatus.READY, OrderStatus.REPAIRING},
            OrderStatus.READY: {OrderStatus.ISSUED, OrderStatus.CANCELLED},
            OrderStatus.ISSUED: set(),  # Конечное состояние
            OrderStatus.CANCELLED: set(),  # Конечное состояние
            OrderStatus.REFUSED: set(),  # Конечное состояние
        }
    )

    current_status: OrderStatus = OrderStatus.DRAFT
    history: list[TransitionHistory] = field(default_factory=list)
    callbacks: list[callable] = field(default_factory=list)

    def can_transition(self, to_status: OrderStatus) -> bool:
        """Проверка возможности перехода."""
        allowed = self.ALLOWED_TRANSITIONS.get(self.current_status, set())
        return to_status in allowed

    def get_allowed_transitions(self) -> list[OrderStatus]:
        """Получение списка допустимых следующих статусов."""
        return list(self.ALLOWED_TRANSITIONS.get(self.current_status, set()))

    def transition_to(
        self, to_status: OrderStatus, user: str | None = None, comment: str = ""
    ) -> bool:
        """Выполнение перехода состояния.

        Returns:
            True если переход успешен, False иначе
        """
        if not self.can_transition(to_status):
            logger.warning(
                f"Недопустимый переход: {self.current_status.name} → {to_status.name}"
            )
            return False

        # Создаем запись истории
        history_entry = TransitionHistory(
            from_status=self.current_status,
            to_status=to_status,
            timestamp=datetime.now(),
            user=user,
            comment=comment,
        )

        # Сохраняем предыдущее состояние
        old_status = self.current_status

        # Обновляем состояние
        self.current_status = to_status

        # Добавляем в историю
        self.history.append(history_entry)

        # Вызываем callback'и
        for callback in self.callbacks:
            try:
                callback(old_status, to_status, history_entry)
            except Exception as e:
                logger.exception(f"Ошибка callback при переходе состояния: {e}")

        logger.info(f"Переход состояния: {old_status.name} → {to_status.name}")
        return True

    def add_callback(self, callback: callable) -> None:
        """Добавление callback'а при смене состояния."""
        self.callbacks.append(callback)

    def get_current_status_name(self) -> str:
        """Получение читаемого имени текущего статуса."""
        status_names = {
            OrderStatus.DRAFT: "Черновик",
            OrderStatus.NEW: "Новый",
            OrderStatus.DIAGNOSTICS: "Диагностика",
            OrderStatus.WAITING_PARTS: "Ожидание запчастей",
            OrderStatus.REPAIRING: "В ремонте",
            OrderStatus.TESTING: "Тестирование",
            OrderStatus.READY: "Готов к выдаче",
            OrderStatus.ISSUED: "Выдан",
            OrderStatus.CANCELLED: "Отменен",
            OrderStatus.REFUSED: "Отказ",
        }
        return status_names.get(self.current_status, self.current_status.name)

    def is_final_state(self) -> bool:
        """Проверка на конечное состояние."""
        final_states = {OrderStatus.ISSUED, OrderStatus.CANCELLED, OrderStatus.REFUSED}
        return self.current_status in final_states


# Глобальный экземпляр для использования как Singleton
_order_state_machine: NativeStateMachine | None = None


def get_order_state_machine(
    initial_status: OrderStatus = OrderStatus.DRAFT,
) -> NativeStateMachine:
    """Получение экземпляра машины состояний (Singleton)."""
    global _order_state_machine
    if _order_state_machine is None:
        _order_state_machine = NativeStateMachine(current_status=initial_status)
    return _order_state_machine


def reset_state_machine() -> None:
    """Сброс машины состояний (для тестов)."""
    global _order_state_machine
    _order_state_machine = None

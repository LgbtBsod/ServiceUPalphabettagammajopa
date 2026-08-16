#!/usr/bin/env python3

"""Доменные события — публикуются через core.kernel.get_core().publish(),
подписчики регистрируются в bootstrap.py::initialize_kernel() через
core.subscribe(EventClass, handler).

Слабая связь между слоями: издатель (например, Database.update_device())
не знает и не должен знать, кто слушает — IntegrationManager сегодня,
что-то ещё завтра решают сами, реагировать ли. Первый и пока единственный
реальный кейс EventBus в этом приложении (см. AUDIT_REPORT_v25.md — до
этого core/events/event_bus.py был полностью построен, зарегистрирован в
DI, но ни один код нигде его не вызывал)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.events import DomainEvent


@dataclass
class DeviceStatusChangedEvent(DomainEvent):
    """Публикуется при РЕАЛЬНОМ (не BOBF no-op) изменении статуса
    устройства — Database.update_device()/update_device_status(), т.е. на
    обоих путях смены статуса (полная форма и быстрая кнопка/PWA),
    закрывая разрыв, где раньше уведомление о готовности можно было
    вызвать только из одного конкретного места в GUI."""

    device_id: int = 0
    old_status: str = ""
    new_status: str = ""
    device_data: dict[str, Any] = field(default_factory=dict)

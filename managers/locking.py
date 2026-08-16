#!/usr/bin/env python3

"""Пессимистичные блокировки редактируемых записей (по аналогии с SAP
enqueue-объектами, SM12) — необязательный GUI-уровня UX-слой поверх ВСЕГДА
включённой оптимистичной блокировки (Device.version_id, см.
Database.update_device()). Управляется настройкой
"pessimistic_locking_enabled" (по умолчанию выключена).

Не владеет своей БД-сессией — как managers/analytics.py, идёт через ядро
(core.call_module_method('db_access', ...)); сырой CRUD над таблицей
record_locks живёт в database/sqlalchemy_database.py (acquire_lock/
refresh_lock/release_lock/get_lock), здесь — только бизнес-правила:
кто "держит" блокировку и какой у неё TTL.

Кто держит блокировку — текущий выбранный сотрудник (plugins/employees),
либо, раз в приложении нет обязательной авторизации, одноразовый GUID
процесса — так что даже без выбора сотрудника два одновременно открытых
экземпляра приложения не затирают правки друг друга молча."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime

from core.base import BaseService
from utils.messages import Msg

logger = logging.getLogger(__name__)

_DEFAULT_TTL_SECONDS = 300


@dataclass
class LockResult:
    """Результат попытки захвата/статуса блокировки."""

    ok: bool
    holder_key: str | None = None
    holder_label: str | None = None
    started_at: datetime | None = None


class LockManager(BaseService):
    """Пессимистичные блокировки — единственная точка бизнес-логики поверх
    сырого record_locks CRUD в Database."""

    def __init__(self, core):
        self._core = core
        # Один на процесс/сессию приложения — стабилен, пока приложение не
        # перезапущено; используется, только если сотрудник не выбран.
        self._session_guid = uuid.uuid4().hex[:12]

    def _holder_identity(self) -> tuple[str, str]:
        """(holder_key, holder_label) — текущий сотрудник, если выбран,
        иначе GUID процесса (без выбора сотрудника приложение всё ещё
        различает "кто" держит блокировку между разными запусками)."""
        try:
            employees_api = self._core.get_module_api("employees")
        except Exception:
            employees_api = None
        if employees_api:
            try:
                employee = employees_api.get_current_employee()
            except Exception:
                employee = None
            if employee:
                return f"emp:{employee.id}", employee.full_name
        return f"session:{self._session_guid}", "Сотрудник не выбран"

    def _ttl_seconds(self) -> int:
        try:
            settings_api = self._core.get_module_api("settings")
            return int(settings_api.get("lock_ttl_seconds", _DEFAULT_TTL_SECONDS))
        except Exception:
            return _DEFAULT_TTL_SECONDS

    def is_enabled(self) -> bool:
        """Читает "pessimistic_locking_enabled" из настроек — вызывающий
        GUI-код должен проверить это ПЕРЕД тем, как звать try_acquire и
        показывать баннер/heartbeat; при выключенной настройке диалог
        редактирования ведёт себя как раньше, без единого обращения к
        record_locks."""
        try:
            settings_api = self._core.get_module_api("settings")
            return bool(settings_api.get("pessimistic_locking_enabled", False))
        except Exception:
            return False

    def try_acquire(self, object_type: str, object_id: int) -> LockResult:
        """Пытается захватить блокировку. Короткое замыкание на is_enabled()
        живёт ЗДЕСЬ (не в вызывающем GUI-коде) — единственная ответственность
        за глобальный выключатель фичи должна быть в одном месте (SSOT),
        независимо от того, сколько вызывающих появится в будущем."""
        if not self.is_enabled():
            return LockResult(ok=True)
        holder_key, holder_label = self._holder_identity()
        try:
            raw = self._core.call_module_method(
                "db_access",
                "acquire_lock",
                object_type,
                object_id,
                holder_key,
                holder_label,
                self._ttl_seconds(),
            )
        except Exception as e:
            # Fail-CLOSED, не открыто: если мы не можем проверить блокировку,
            # вызывающий код не должен думать, что она успешно получена
            # (иначе GUI покажет форму как "эксклюзивно моя", хотя в
            # record_locks ничего не записалось) — единственный метод класса,
            # у которого раньше было наоборот (see AUDIT_REPORT_v25.md).
            self.logger.exception(f"acquire_lock не выполнен: {e}")
            return LockResult(ok=False, holder_label=Msg.LOCK_CHECK_FAILED)

        started_at = raw.get("started_at")
        if isinstance(started_at, str):
            try:
                started_at = datetime.fromisoformat(started_at)
            except ValueError:
                started_at = None
        return LockResult(
            ok=raw.get("ok", False),
            holder_key=raw.get("holder_key"),
            holder_label=raw.get("holder_label"),
            started_at=started_at,
        )

    def refresh(self, object_type: str, object_id: int) -> bool:
        if not self.is_enabled():
            return True
        holder_key, _ = self._holder_identity()
        return bool(
            self.safe_execute(
                self._core.call_module_method,
                "db_access",
                "refresh_lock",
                object_type,
                object_id,
                holder_key,
                default=False,
            )
        )

    def release(self, object_type: str, object_id: int) -> None:
        holder_key, _ = self._holder_identity()
        try:
            self._core.call_module_method(
                "db_access", "release_lock", object_type, object_id, holder_key
            )
        except Exception as e:
            # Обычный try/except, а не safe_execute(default=None) — тот
            # трактует default=None как "дефолт не задан" и пробрасывает
            # исключение дальше (см. core/base.py), что для release() (нечего
            # возвращать вызывающему в любом случае) не то поведение, какое
            # подразумевал вызывающий код.
            self.logger.warning(f"release_lock не выполнен: {e}")

    def get_lock_info(self, object_type: str, object_id: int) -> dict | None:
        try:
            return self._core.call_module_method(
                "db_access", "get_lock", object_type, object_id
            )
        except Exception as e:
            self.logger.warning(f"get_lock не выполнен: {e}")
            return None

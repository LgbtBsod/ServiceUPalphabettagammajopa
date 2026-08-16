#!/usr/bin/env python3
"""LocksMixin — raw CRUD над record_locks (пессимистичные блокировки,
опционально). Бизнес-правила (TTL, идентичность держателя) живут в
managers/locking.py::LockManager, который зовёт эти методы через
core.call_module_method('db_access', ...), а не держит свою сессию (см.
AUDIT_REPORT_v21.md про единственный путь к БД). См. AUDIT_REPORT_v25.md,
Task T."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from database.facade.shared import as_utc
from database.sqlalchemy_models import RecordLock

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class LocksMixin:
    """Требует self._session() от финального класса Database."""

    def acquire_lock(
        self,
        object_type: str,
        object_id: int,
        holder_key: str,
        holder_label: str,
        ttl_seconds: int,
    ) -> dict[str, Any]:
        """Пытается захватить блокировку (object_type, object_id) для
        holder_key. {"ok": True, ...} — вызывающий код теперь держит её
        (была свободна / уже была его / забрана как протухшая). {"ok":
        False, "holder_key"/"holder_label"/"started_at": ...} — занята
        другим, ttl ещё не истёк."""
        now = datetime.now(timezone.utc)
        with self._session() as s:
            row = s.execute(
                select(RecordLock).where(
                    RecordLock.object_type == object_type,
                    RecordLock.object_id == object_id,
                )
            ).scalar_one_or_none()

            if row is None:
                try:
                    s.add(
                        RecordLock(
                            object_type=object_type,
                            object_id=object_id,
                            holder_key=holder_key,
                            holder_label=holder_label,
                            started_at=now,
                            last_heartbeat_at=now,
                        )
                    )
                    s.commit()
                except IntegrityError:
                    # Кто-то захватил в промежутке между SELECT и INSERT
                    # (UniqueConstraint на object_type+object_id решает гонку
                    # на уровне БД, а не в питоновском коде) — не наша.
                    s.rollback()
                    return self._lock_row_to_conflict(s, object_type, object_id)
                return {
                    "ok": True,
                    "holder_key": holder_key,
                    "holder_label": holder_label,
                    "started_at": now.isoformat(),
                }

            if row.holder_key == holder_key:
                row.last_heartbeat_at = now
                s.commit()
                return {
                    "ok": True,
                    "holder_key": holder_key,
                    "holder_label": holder_label,
                    "started_at": row.started_at.isoformat(),
                }

            stale = (now - as_utc(row.last_heartbeat_at)).total_seconds() > ttl_seconds
            if stale:
                row.holder_key = holder_key
                row.holder_label = holder_label
                row.started_at = now
                row.last_heartbeat_at = now
                s.commit()
                return {
                    "ok": True,
                    "holder_key": holder_key,
                    "holder_label": holder_label,
                    "started_at": now.isoformat(),
                }

            return {
                "ok": False,
                "holder_key": row.holder_key,
                "holder_label": row.holder_label,
                "started_at": row.started_at.isoformat(),
            }

    @staticmethod
    def _lock_row_to_conflict(s: Session, object_type: str, object_id: int) -> dict[str, Any]:
        loser_row = s.execute(
            select(RecordLock).where(
                RecordLock.object_type == object_type,
                RecordLock.object_id == object_id,
            )
        ).scalar_one_or_none()
        if loser_row is None:
            # Крайне маловероятно: строка исчезла между конфликтом и
            # повторным SELECT (например, победитель уже вышел) — просим
            # попробовать снова, не подвешиваем вызывающий код.
            return {"ok": False, "holder_key": None, "holder_label": None, "started_at": None}
        return {
            "ok": False,
            "holder_key": loser_row.holder_key,
            "holder_label": loser_row.holder_label,
            "started_at": loser_row.started_at.isoformat(),
        }

    def refresh_lock(self, object_type: str, object_id: int, holder_key: str) -> bool:
        """Heartbeat — не даёт TTL истечь, пока диалог открыт. Не трогает
        чужую блокировку (если её успели забрать как протухшую)."""
        with self._session() as s:
            row = s.execute(
                select(RecordLock).where(
                    RecordLock.object_type == object_type,
                    RecordLock.object_id == object_id,
                    RecordLock.holder_key == holder_key,
                )
            ).scalar_one_or_none()
            if row is None:
                return False
            row.last_heartbeat_at = datetime.now(timezone.utc)
            s.commit()
            return True

    def release_lock(self, object_type: str, object_id: int, holder_key: str) -> None:
        """Снимает СВОЮ блокировку (holder_key должен совпасть) — закрытие
        диалога, чья блокировка уже была забрана кем-то другим по TTL, не
        должно снести чужую актуальную блокировку."""
        with self._session() as s:
            row = s.execute(
                select(RecordLock).where(
                    RecordLock.object_type == object_type,
                    RecordLock.object_id == object_id,
                    RecordLock.holder_key == holder_key,
                )
            ).scalar_one_or_none()
            if row is not None:
                s.delete(row)
                s.commit()

    def get_lock(self, object_type: str, object_id: int) -> dict[str, Any] | None:
        """Только чтение статуса — без попытки захвата."""
        with self._session() as s:
            row = s.execute(
                select(RecordLock).where(
                    RecordLock.object_type == object_type,
                    RecordLock.object_id == object_id,
                )
            ).scalar_one_or_none()
            if row is None:
                return None
            return {
                "holder_key": row.holder_key,
                "holder_label": row.holder_label,
                "started_at": row.started_at.isoformat(),
                "last_heartbeat_at": row.last_heartbeat_at.isoformat(),
            }

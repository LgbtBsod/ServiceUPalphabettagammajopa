#!/usr/bin/env python3
"""BasisCockpitMixin — вкладка "🔧 Базис" главного окна: технические/
административные настройки, отделённые от повседневных пользовательских
(подключение к БД + миграция, полномочия/RBAC — задел, переключатель
пессимистичной блокировки заказов). По аналогии с SAP Basis/BC — область
для администратора, а не для рядового сотрудника.

Раньше подключение к БД и переключатель блокировок жили в обычном диалоге
настроек вперемешку с пользовательскими настройками (тема, уведомления,
бэкапы) — см. AUDIT_REPORT_v25.md, Task U."""

from __future__ import annotations

import logging
from tkinter import messagebox

import customtkinter as ctk

from gui.widgets import ModernCard
from utils.messages import Msg

logger = logging.getLogger(__name__)


class BasisCockpitMixin:
    """Требует от финального класса ServiceCenterApp: self.root, self.colors,
    self.settings."""

    def create_basis_tab(self, parent):
        """Строит содержимое вкладки "🔧 Базис"."""
        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=10, pady=10)

        self._create_db_connection_section(scroll)
        self._create_query_cache_section(scroll)
        self._create_permissions_section(scroll)
        self._create_locking_section(scroll)

    def _basis_section(self, parent, title: str):
        """Секция с заголовком — тот же визуальный паттерн, что и
        SettingsWindow.create_section(), но у главного окна нет доступа к
        тому классу напрямую, поэтому небольшой дубль здесь (2 виджета,
        ниже порога DRY-рефакторинга этой сессии)."""
        card = ModernCard(parent, self.colors)
        card.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(
            card,
            text=title,
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=self.colors["accent"],
        ).pack(anchor="w", padx=15, pady=(12, 8))
        content = ctk.CTkFrame(card, fg_color="transparent")
        content.pack(fill="x", padx=15, pady=(0, 15))
        return content

    def _create_db_connection_section(self, parent):
        content = self._basis_section(parent, "🗄️ Подключение к БД")

        try:
            from database.db_config import get_db_config

            cfg = get_db_config()
            if cfg.db_type.value == "sqlite":
                conn_info = f"SQLite: {cfg.database}"
            else:
                conn_info = f"{cfg.db_type.value}: {cfg.host}:{cfg.port}/{cfg.database}"
        except Exception:
            conn_info = "Не удалось определить текущую БД"

        ctk.CTkLabel(
            content,
            text=conn_info,
            font=ctk.CTkFont(size=12),
            text_color=self.colors["text_secondary"],
            wraplength=500,
            justify="left",
        ).pack(anchor="w", pady=(0, 8))

        ctk.CTkButton(
            content,
            text="🔄 Мигрировать в новую БД...",
            command=self._open_database_migration,
            fg_color=self.colors["bg_tertiary"],
            text_color=self.colors["text_primary"],
            height=32,
        ).pack(anchor="w")

    def _open_database_migration(self):
        from gui.dialogs.database_migration import DatabaseMigrationDialog

        DatabaseMigrationDialog(self.root, self.colors)

    def _create_query_cache_section(self, parent):
        """Кэш запросов к БД (справочники) — DatabaseCore.query_cache, TTL
        ~1 час, см. database/db_core.py, AUDIT_REPORT_v25.md Task W. Общий
        на процесс (не per-пользователь) — обычное окно и мобильная версия
        (PWA) работают с одним и тем же self.db в одном процессе."""
        content = self._basis_section(parent, "🗃️ " + Msg.BASIS_QUERY_CACHE_LABEL)

        ctk.CTkLabel(
            content,
            text=Msg.BASIS_QUERY_CACHE_HINT,
            font=ctk.CTkFont(size=12),
            text_color=self.colors["text_secondary"],
            wraplength=500,
            justify="left",
        ).pack(anchor="w", pady=(0, 8))

        ctk.CTkButton(
            content,
            text=Msg.BASIS_REFRESH_CACHE_BUTTON,
            command=self._refresh_query_cache,
            fg_color=self.colors["bg_tertiary"],
            text_color=self.colors["text_primary"],
            height=32,
        ).pack(anchor="w")

    def _refresh_query_cache(self):
        try:
            count = self.db.refresh_query_cache()
        except Exception as e:
            logger.error(f"Не удалось обновить кэш запросов: {e}", exc_info=True)
            messagebox.showerror("Ошибка", str(e))
            return
        messagebox.showinfo("Базис", Msg.BASIS_CACHE_REFRESHED.format(count=count))

    def _create_permissions_section(self, parent):
        """Полномочия/RBAC — пока только задел (PermissionObject/
        core.base.PermissionAwareMixin уже объявлены на сервисах, реальной
        ролевой модели ещё нет). Не строим фиктивные контролы поверх
        несуществующей модели — см. TODO_RBAC_ROADMAP.md."""
        content = self._basis_section(parent, "🔐 Полномочия")
        ctk.CTkLabel(
            content,
            text=(
                "Ролевая модель ещё не реализована — сейчас любой сотрудник "
                "проходит любую проверку (см. TODO_RBAC_ROADMAP.md). Объекты "
                "полномочий уже объявлены на сервисах (CLIENTS, EMPLOYEES, "
                "ANALYTICS) и готовы к подключению реального enforcement."
            ),
            font=ctk.CTkFont(size=12),
            text_color=self.colors["text_secondary"],
            wraplength=500,
            justify="left",
        ).pack(anchor="w")

    def _create_locking_section(self, parent):
        content = self._basis_section(parent, "⚙️ Блокировка заказов")

        ctk.CTkLabel(
            content,
            text=(
                "Оптимистичная блокировка (версия записи) работает всегда и "
                "переключателя не имеет — это единственная защита от "
                "конкурентных правок. Ниже — дополнительный GUI-уровня "
                "UX-слой поверх неё."
            ),
            font=ctk.CTkFont(size=11),
            text_color=self.colors["text_tertiary"],
            wraplength=500,
            justify="left",
        ).pack(anchor="w", pady=(0, 8))

        self.basis_pessimistic_lock_var = ctk.BooleanVar(
            value=self.settings.get("pessimistic_locking_enabled", False)
        )
        ctk.CTkCheckBox(
            content,
            text=Msg.SETTINGS_PESSIMISTIC_LOCK_LABEL,
            variable=self.basis_pessimistic_lock_var,
            fg_color=self.colors["accent"],
        ).pack(anchor="w", pady=3)

        ttl_row = ctk.CTkFrame(content, fg_color="transparent")
        ttl_row.pack(fill="x", pady=5)
        ctk.CTkLabel(ttl_row, text=Msg.SETTINGS_LOCK_TTL_LABEL).pack(side="left")
        self.basis_lock_ttl_entry = ctk.CTkEntry(ttl_row, width=60)
        self.basis_lock_ttl_entry.insert(
            0, str(self.settings.get("lock_ttl_seconds", 300))
        )
        self.basis_lock_ttl_entry.pack(side="right")

        ctk.CTkButton(
            content,
            text="💾 Сохранить",
            command=self._save_basis_locking_settings,
            fg_color=self.colors["accent"],
            text_color="white",
            hover_color=self.colors["accent_hover"],
            height=32,
        ).pack(anchor="w", pady=(10, 0))

    def _save_basis_locking_settings(self):
        """Сохраняет переключатель блокировок сразу (не откладывая до
        закрытия приложения, в отличие от обычных настроек через
        SettingsWindow) — административная настройка заслуживает
        немедленного подтверждения, что применилась."""
        try:
            ttl = int(self.basis_lock_ttl_entry.get())
        except ValueError:
            ttl = 300
        # lo=120 — не 10: heartbeat, держащий блокировку живой, тикает раз в
        # 60с (device_form_parts/locking_mixin.py::LOCK_HEARTBEAT_MS). При
        # TTL ниже интервала heartbeat блокировка могла "протухнуть" в
        # глазах другого пользователя раньше первого же heartbeat держателя
        # — данные это не портит (version_id всё равно ловит конфликт при
        # сохранении), но ломает UX-индикатор "занято другим", см.
        # AUDIT_REPORT_v25.md.
        ttl = max(120, min(ttl, 3600))
        self.settings.set(
            "pessimistic_locking_enabled", self.basis_pessimistic_lock_var.get()
        )
        self.settings.set("lock_ttl_seconds", ttl)
        self.settings.save_settings()
        messagebox.showinfo("Базис", "Настройки блокировок сохранены")

#!/usr/bin/env python3

"""Диалог миграции на новую БД (SQLite-файл или PostgreSQL) — кнопка
"Мигрировать в новую БД" в Настройки → База данных.

Поток: выбор целевой БД -> резервная копия текущей (для SQLite) -> перенос
данных (database.db_migration_tool.migrate_data) -> сверка количества строк
по каждой таблице -> ТОЛЬКО при полном совпадении предлагает записать новую
конфигурацию в .env (требует перезапуска приложения — горячая подмена
боевого движка на лету не делается, см. Database's guard от повторного
подключения в database/sqlalchemy_database.py).
"""

import contextlib
import logging
import os
import shutil
from datetime import datetime
from tkinter import filedialog, messagebox

import customtkinter as ctk

logger = logging.getLogger(__name__)


def _write_env_db_config(**db_env: str) -> None:
    """Обновляет DB_*-ключи в .env (в корне проекта), сохраняя остальные
    строки файла как есть. Создаёт файл, если его ещё нет."""
    from config import BASE_DIR

    env_path = os.path.join(BASE_DIR, ".env")
    lines: list[str] = []
    seen_keys: set[str] = set()

    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if "=" in stripped and not stripped.startswith("#"):
                    key = stripped.split("=", 1)[0].strip()
                    if key in db_env:
                        lines.append(f"{key}={db_env[key]}\n")
                        seen_keys.add(key)
                        continue
                lines.append(line if line.endswith("\n") else line + "\n")

    for key, value in db_env.items():
        if key not in seen_keys:
            lines.append(f"{key}={value}\n")

    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(lines)


class DatabaseMigrationDialog(ctk.CTkToplevel):
    """Диалог выбора целевой БД и запуска миграции данных."""

    def __init__(self, parent, colors: dict[str, str]):
        super().__init__(parent)
        self.colors = colors
        self.title("Миграция на новую БД")
        self.geometry("520x480")
        self.minsize(480, 420)
        self.transient(parent)
        self.grab_set()

        self.db_type_var = ctk.StringVar(value="sqlite")
        self._build_widgets()

    def _build_widgets(self):
        container = ctk.CTkScrollableFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=15, pady=15)

        ctk.CTkLabel(
            container,
            text="⚠️ Перед миграцией автоматически создаётся резервная копия "
            "текущей БД (если это SQLite-файл). После миграции нужно перезапустить "
            "приложение, чтобы оно начало использовать новую БД.",
            font=ctk.CTkFont(size=12),
            text_color=self.colors["text_secondary"],
            wraplength=460,
            justify="left",
        ).pack(anchor="w", pady=(0, 15))

        ctk.CTkLabel(
            container, text="Тип целевой БД:", font=ctk.CTkFont(size=13, weight="bold")
        ).pack(anchor="w", pady=(0, 5))

        type_row = ctk.CTkFrame(container, fg_color="transparent")
        type_row.pack(fill="x", pady=(0, 15))
        ctk.CTkRadioButton(
            type_row, text="SQLite (файл)", variable=self.db_type_var, value="sqlite",
            command=self._on_type_changed,
        ).pack(side="left", padx=(0, 15))
        ctk.CTkRadioButton(
            type_row, text="PostgreSQL", variable=self.db_type_var, value="postgresql",
            command=self._on_type_changed,
        ).pack(side="left")

        self.fields_frame = ctk.CTkFrame(container, fg_color="transparent")
        self.fields_frame.pack(fill="x", pady=(0, 15))
        self._build_sqlite_fields()

        self.status_label = ctk.CTkLabel(
            container, text="", font=ctk.CTkFont(size=12), wraplength=460, justify="left"
        )
        self.status_label.pack(anchor="w", pady=(0, 10), fill="x")

        btn_row = ctk.CTkFrame(container, fg_color="transparent")
        btn_row.pack(fill="x", pady=(5, 0))
        ctk.CTkButton(
            btn_row, text="🔄 Мигрировать", command=self._on_migrate,
            fg_color=self.colors["accent"], height=36,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            btn_row, text="Отмена", command=self.destroy,
            fg_color=self.colors["bg_tertiary"], text_color=self.colors["text_primary"],
            height=36,
        ).pack(side="left")

    def _on_type_changed(self):
        for child in self.fields_frame.winfo_children():
            child.destroy()
        if self.db_type_var.get() == "sqlite":
            self._build_sqlite_fields()
        else:
            self._build_postgres_fields()

    def _build_sqlite_fields(self):
        ctk.CTkLabel(self.fields_frame, text="Путь к новому файлу БД:").pack(anchor="w")
        row = ctk.CTkFrame(self.fields_frame, fg_color="transparent")
        row.pack(fill="x", pady=(2, 0))
        self.sqlite_path_entry = ctk.CTkEntry(row)
        self.sqlite_path_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        ctk.CTkButton(
            row, text="📂", width=40, command=self._choose_sqlite_path,
            fg_color=self.colors["bg_tertiary"], text_color=self.colors["text_primary"],
        ).pack(side="left")

    def _build_postgres_fields(self):
        self.pg_entries: dict[str, ctk.CTkEntry] = {}
        for label, key, default in (
            ("Хост:", "host", "localhost"),
            ("Порт:", "port", "5432"),
            ("Имя БД:", "database", "serviceup"),
            ("Пользователь:", "user", "postgres"),
            ("Пароль:", "password", ""),
        ):
            ctk.CTkLabel(self.fields_frame, text=label).pack(anchor="w", pady=(6, 0))
            entry = ctk.CTkEntry(self.fields_frame, show="•" if key == "password" else None)
            entry.insert(0, default)
            entry.pack(fill="x")
            self.pg_entries[key] = entry

    def _choose_sqlite_path(self):
        path = filedialog.asksaveasfilename(
            title="Новый файл БД",
            defaultextension=".db",
            filetypes=[("SQLite DB", "*.db")],
        )
        if path:
            self.sqlite_path_entry.delete(0, "end")
            self.sqlite_path_entry.insert(0, path)

    def _build_target_config(self):
        from database.db_config import DatabaseConfig, DatabaseType

        if self.db_type_var.get() == "sqlite":
            path = self.sqlite_path_entry.get().strip()
            if not path:
                raise ValueError("Укажите путь к новому файлу БД")
            return DatabaseConfig(db_type=DatabaseType.SQLITE, database=path)

        port_str = self.pg_entries["port"].get().strip()
        return DatabaseConfig(
            db_type=DatabaseType.POSTGRESQL,
            database=self.pg_entries["database"].get().strip(),
            host=self.pg_entries["host"].get().strip() or None,
            port=int(port_str) if port_str else None,
            user=self.pg_entries["user"].get().strip() or None,
            password=self.pg_entries["password"].get() or None,
        )

    def _on_migrate(self):
        if not messagebox.askyesno(
            "Подтверждение",
            "Перенести все данные в новую БД? Текущая БД не изменится "
            "(будет создана резервная копия перед началом).",
        ):
            return

        try:
            target_config = self._build_target_config()
        except ValueError as e:
            messagebox.showerror("Ошибка", str(e))
            return

        self.status_label.configure(text="⏳ Выполняется миграция...")
        self.update_idletasks()

        try:
            from database.db_config import get_db_config
            from database.db_migration_tool import migrate_data, verify_migration
            from database.engines import create_engine_for

            source_config = get_db_config()

            # Бэкап текущей БД (только для SQLite — файл можно просто скопировать)
            if source_config.db_type.value == "sqlite" and os.path.exists(
                source_config.database
            ):
                from config import BACKUP_DIR

                os.makedirs(BACKUP_DIR, exist_ok=True)
                backup_name = f"pre_migration_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
                shutil.copy2(source_config.database, os.path.join(BACKUP_DIR, backup_name))

            source_engine = create_engine_for(source_config)
            target_engine = create_engine_for(target_config)
            target_engine.create_tables()

            report = migrate_data(source_engine, target_engine)
            mismatches = verify_migration(report)

            report_lines = [
                f"{table}: {counts['source']} → {counts['target']}"
                + (" ⚠️" if table in mismatches else " ✅")
                for table, counts in sorted(report.items())
            ]
            self.status_label.configure(text="\n".join(report_lines))

            if mismatches:
                messagebox.showerror(
                    "Расхождение при миграции",
                    f"Количество строк не совпало в таблицах: {', '.join(mismatches)}. "
                    "Боевая БД НЕ переключена — проверьте отчёт выше.",
                )
                return

            if messagebox.askyesno(
                "Миграция завершена",
                "Все таблицы перенесены полностью и совпадают. Переключить "
                "приложение на новую БД? Потребуется перезапуск.",
            ):
                env_kwargs = {"DB_TYPE": target_config.db_type.value}
                if target_config.db_type.value == "sqlite":
                    env_kwargs["DB_NAME"] = target_config.database
                else:
                    env_kwargs.update(
                        DB_NAME=target_config.database,
                        DB_HOST=target_config.host or "",
                        DB_PORT=str(target_config.port or ""),
                        DB_USER=target_config.user or "",
                        DB_PASSWORD=target_config.password or "",
                    )
                _write_env_db_config(**env_kwargs)
                messagebox.showinfo(
                    "Готово",
                    "Конфигурация обновлена. Перезапустите приложение, чтобы "
                    "начать использовать новую БД.",
                )
                self.destroy()
        except Exception as e:
            logger.error(f"Ошибка миграции БД: {e}", exc_info=True)
            self.status_label.configure(text=f"❌ Ошибка: {e}")
            messagebox.showerror("Ошибка миграции", str(e))
        finally:
            with contextlib.suppress(Exception):
                source_engine.dispose()
            with contextlib.suppress(Exception):
                target_engine.dispose()

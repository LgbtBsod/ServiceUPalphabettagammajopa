#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Утилиты печати актов: автосохранение во временный файл + печать/просмотр.

Вместо диалога «Сохранить как...» акты сохраняются в exports/ с автоматическим
именем, открываются в просмотрщике или отправляются на принтер, а затем
временные файлы удаляются (чтобы не занимать место).
"""

import logging

logger = logging.getLogger(__name__)

import os
import sys
import subprocess
import tempfile
import time
import threading
from datetime import datetime
from typing import Optional


def get_exports_dir() -> str:
    """Возвращает путь к папке exports/."""
    from config import EXPORT_DIR
    os.makedirs(EXPORT_DIR, exist_ok=True)
    return EXPORT_DIR


def generate_act_filename(act_type: str, order_number: str) -> str:
    """Генерирует имя файла для акта: акт_приёма_00042_15072026_143022.pdf"""
    timestamp = datetime.now().strftime('%d%m%Y_%H%M%S')
    prefix = 'акт_приёма' if act_type == 'receipt' else 'акт_работ'
    order = str(order_number).replace(' ', '_').replace('/', '-')
    return f"{prefix}_{order}_{timestamp}.pdf"


def print_act_pdf(pdf_path: str, delete_after: bool = True, delay_sec: int = 60) -> None:
    """Отправляет PDF на печать / открывает в просмотрщике.

    На Windows — открывает с командой 'print', что вызывает диалог печати
    системного просмотрщика. После задержки (delay_sec) файл удаляется,
    чтобы не занимать место.

    Параметры:
        pdf_path — путь к PDF файлу.
        delete_after — удалить файл после печати.
        delay_sec — через сколько секунд удалить (даёт время на печать).
    """
    try:
        if sys.platform == 'win32':
            # 'print' открывает системский диалог печати
            os.startfile(pdf_path, 'print')
        elif sys.platform == 'darwin':
            subprocess.run(['lpr', pdf_path], check=False)
        else:
            subprocess.run(['lp', pdf_path], check=False)
    except Exception as e:
        logger.warning(f"Печать не удалась, открываю просмотрщик: {e}")
        try:
            if sys.platform == 'win32':
                os.startfile(pdf_path)
        except Exception:
            pass

    # Автоудаление через delay_sec в фоновом потоке
    if delete_after:
        def _cleanup():
            time.sleep(delay_sec)
            try:
                if os.path.exists(pdf_path):
                    os.remove(pdf_path)
                    logger.debug(f"Временный акт удалён: {pdf_path}")
            except OSError:
                pass

        t = threading.Thread(target=_cleanup, daemon=True)
        t.start()


def open_act_pdf(pdf_path: str, delete_after: bool = True, delay_sec: int = 120) -> None:
    """Открывает PDF в системном просмотрщике.

    После задержки файл удаляется.
    """
    try:
        if sys.platform == 'win32':
            os.startfile(pdf_path)
        elif sys.platform == 'darwin':
            subprocess.run(['open', pdf_path], check=False)
        else:
            subprocess.run(['xdg-open', pdf_path], check=False)
    except Exception as e:
        logger.error(f"Не удалось открыть PDF: {e}")

    if delete_after:
        def _cleanup():
            time.sleep(delay_sec)
            try:
                if os.path.exists(pdf_path):
                    os.remove(pdf_path)
            except OSError:
                pass

        t = threading.Thread(target=_cleanup, daemon=True)
        t.start()


def save_act_to_exports(pdf_path: str, act_type: str, order_number: str) -> str:
    """Копирует PDF в exports/ с понятным именем (для ручного сохранения).

    Возвращает путь к сохранённому файлу.
    """
    import shutil
    exports_dir = get_exports_dir()
    filename = generate_act_filename(act_type, order_number)
    dest = os.path.join(exports_dir, filename)
    shutil.copy2(pdf_path, dest)
    return dest


def create_temp_act_pdf(act_type: str, order_number: str) -> str:
    """Создаёт временный путь для PDF акта в exports/."""
    exports_dir = get_exports_dir()
    filename = generate_act_filename(act_type, order_number)
    return os.path.join(exports_dir, filename)

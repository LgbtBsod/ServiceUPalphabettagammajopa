#!/usr/bin/env python3

"""Утилиты печати актов: автосохранение во временный файл + печать/просмотр.

Вместо диалога «Сохранить как...» акты сохраняются в exports/ с автоматическим
именем, открываются в просмотрщике или отправляются на принтер, а затем
временные файлы удаляются (чтобы не занимать место).
"""

import logging
import os
import subprocess
import sys
import time
import uuid
from collections.abc import Callable
from datetime import datetime

logger = logging.getLogger(__name__)


def _start_cleanup_thread(cleanup: Callable[[], None]) -> None:
    """Запускает отложенное удаление временного файла через Kernel ThreadManager
    вместо прямого threading.Thread (см. AUDIT_REPORT_v20.md) — общий хелпер
    для print_act_pdf()/open_act_pdf(), раньше дублировавших этот код.
    """
    from core.kernel import get_core

    core = get_core()
    name = f"act-cleanup-{uuid.uuid4().hex[:8]}"
    core.create_thread(name=name, target=cleanup, daemon=True)
    core.start_thread(name)


def _wait_for_unlock_or_timeout(
    path: str, timeout_sec: float, poll_interval: float = 2.0
) -> None:
    """Лучшее, что можно сделать БЕЗ платформенных API печати
    (win32print/CUPS): os.startfile(path, "print")/lpr/lp — все
    fire-and-forget, ни один не даёт сигнала "печать/спулинг завершены".

    Проба — os.rename(path, path) (переименование файла в самого себя), а
    НЕ open(path, "r+b"): на Windows обычный open() по умолчанию открывает
    файл в разделяемом режиме (_SH_DENYNO) — второй open() того же файла
    (даже из того же процесса) СПОКОЙНО открывается параллельно, пока файл
    занят просмотрщиком/спулером, поэтому такая проверка ничего бы не
    ловила. Переименование же требует эксклюзивного доступа и надёжно
    падает WinError 32 (sharing violation), пока у файла есть любой другой
    открытый хендл — проверено эмпирически на этом же repo.

    Ждём исчезновения блокировки, но не дольше timeout_sec — если
    просмотрщик остался открытым пользователем надолго, не течём файлами
    вечно, удаляем по истечении таймаута как раньше."""
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        try:
            os.rename(path, path)
            return
        except OSError:
            time.sleep(poll_interval)


def get_exports_dir() -> str:
    """Возвращает путь к папке exports/."""
    from config import EXPORT_DIR

    os.makedirs(EXPORT_DIR, exist_ok=True)
    return EXPORT_DIR


def generate_act_filename(act_type: str, order_number: str) -> str:
    """Генерирует имя файла для акта: акт_приёма_00042_15072026_143022.pdf"""
    timestamp = datetime.now().strftime("%d%m%Y_%H%M%S")
    prefix = "акт_приёма" if act_type == "receipt" else "акт_работ"
    order = str(order_number).replace(" ", "_").replace("/", "-")
    return f"{prefix}_{order}_{timestamp}.pdf"


def print_act_pdf(
    pdf_path: str, delete_after: bool = True, delay_sec: int = 180
) -> None:
    """Отправляет PDF на печать / открывает в просмотрщике.

    На Windows — открывает с командой 'print', что вызывает диалог печати
    системного просмотрщика. После задержки (delay_sec) файл удаляется,
    чтобы не занимать место — на Windows не раньше, чем файл перестанет
    быть занят просмотрщиком/спулером (см. _wait_for_unlock_or_timeout);
    на POSIX unlink() безопасен даже пока другой процесс ещё держит файл
    открытым (inode живёт, пока не закроется последний дескриптор), поэтому
    там фиксированная задержка не риск потери данных для печати, только
    "не удалять слишком рано, пока печать точно не запущена".

    Параметры:
        pdf_path — путь к PDF файлу.
        delete_after — удалить файл после печати.
        delay_sec — сколько ждать перед удалением (на Windows — верхняя
            граница ожидания разблокировки, не гарантированная задержка).
    """
    try:
        if sys.platform == "win32":
            # 'print' открывает системский диалог печати
            os.startfile(pdf_path, "print")
        elif sys.platform == "darwin":
            subprocess.run(["lpr", pdf_path], check=False)
        else:
            subprocess.run(["lp", pdf_path], check=False)
    except Exception as e:
        logger.warning(f"Печать не удалась, открываю просмотрщик: {e}")
        try:
            if sys.platform == "win32":
                os.startfile(pdf_path)
        except Exception:
            pass

    # Автоудаление в фоновом потоке — раньше это была БЕЗУСЛОВНАЯ задержка
    # без проверки, действительно ли печать/просмотр завершены (см.
    # workflow-найденный баг: медленная сетевая печать/большой акт могли
    # не уложиться в фиксированные 60с, и файл удалялся прямо во время
    # чтения просмотрщиком/спулером).
    if delete_after:

        def _cleanup():
            if sys.platform == "win32":
                _wait_for_unlock_or_timeout(pdf_path, timeout_sec=delay_sec)
            else:
                time.sleep(delay_sec)
            try:
                if os.path.exists(pdf_path):
                    os.remove(pdf_path)
                    logger.debug(f"Временный акт удалён: {pdf_path}")
            except OSError:
                pass

        _start_cleanup_thread(_cleanup)


def open_act_pdf(
    pdf_path: str, delete_after: bool = True, delay_sec: int = 120
) -> None:
    """Открывает PDF в системном просмотрщике.

    После задержки файл удаляется.
    """
    try:
        if sys.platform == "win32":
            os.startfile(pdf_path)
        elif sys.platform == "darwin":
            subprocess.run(["open", pdf_path], check=False)
        else:
            subprocess.run(["xdg-open", pdf_path], check=False)
    except Exception as e:
        logger.exception(f"Не удалось открыть PDF: {e}")

    if delete_after:

        def _cleanup():
            if sys.platform == "win32":
                _wait_for_unlock_or_timeout(pdf_path, timeout_sec=delay_sec)
            else:
                time.sleep(delay_sec)
            try:
                if os.path.exists(pdf_path):
                    os.remove(pdf_path)
            except OSError:
                pass

        _start_cleanup_thread(_cleanup)


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

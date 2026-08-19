"""Update Manager Module

Модуль проверки и установки обновлений приложения.
Проверяет версию на сервере релизов и сравнивает с локальной версией.
Поддерживает тихое скачивание и автоматическую установку.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Callable


# Конфигурация GitHub
GITHUB_USER = "LgbtBsod"
GITHUB_REPO = "ServiceUPalphabettagammajopa"
API_URL = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/releases/latest"


def get_current_version() -> str:
    """Считывает текущую версию из version.txt"""
    try:
        with open("version.txt", "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return "0.0"


def parse_version(version_str: str) -> tuple[int, ...]:
    """Преобразует строку версии в кортеж чисел для сравнения"""
    clean = version_str.replace('v', '').replace('V', '')
    try:
        return tuple(map(int, clean.split('.')))
    except ValueError:
        return (0, 0)


def check_for_updates(timeout: int = 10) -> dict[str, Any] | None:
    """
    Проверяет наличие новой версии.
    Возвращает dict с данными или None если обновлений нет.
    """
    try:
        headers = {"User-Agent": "ServiceUP-UpdateChecker"}
        req = urllib.request.Request(API_URL, headers=headers)
        
        with urllib.request.urlopen(req, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
            
        latest_version = data.get('tag_name', '0.0').lstrip('vV')
        current_ver = parse_version(get_current_version())
        latest_ver = parse_version(latest_version)
        
        if latest_ver > current_ver:
            # Ищем архив с исходниками (zipball)
            zip_url = data.get('zipball_url')
            if not zip_url:
                # Если нет zipball, пробуем найти ассет
                assets = data.get('assets', [])
                for asset in assets:
                    if asset['name'].endswith('.zip'):
                        zip_url = asset['browser_download_url']
                        break
            
            if zip_url:
                return {
                    "version": latest_version,
                    "url": zip_url,
                    "notes": data.get('body', 'Нет описания изменений')
                }
        return None
    except Exception as e:
        print(f"[Update] Ошибка проверки: {e}")
        return None


def download_and_prepare_update(update_data: dict, progress_callback: Callable[[str, int], None] = None) -> str | None:
    """
    Скачивает архив и распаковывает во временную папку.
    Возвращает путь к папке с новыми файлами или None при ошибке.
    """
    try:
        url = update_data['url']
        temp_dir = tempfile.mkdtemp(prefix="serviceup_update_")
        zip_path = os.path.join(temp_dir, "update.zip")
        extract_path = os.path.join(temp_dir, "new_files")
        
        if progress_callback:
            progress_callback("Начало загрузки...", 0)

        # Скачивание с прогрессом
        headers = {"User-Agent": "ServiceUP-UpdateDownloader"}
        req = urllib.request.Request(url, headers=headers)
        
        with urllib.request.urlopen(req, timeout=300) as response:
            total_length = int(response.headers.get('content-length', 0))
            downloaded = 0
            
            with open(zip_path, 'wb') as f:
                while True:
                    chunk = response.read(8192)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback and total_length:
                        percent = int(100 * downloaded / total_length)
                        progress_callback(f"Загрузка: {percent}%", percent)

        if progress_callback:
            progress_callback("Распаковка...", 60)

        # Распаковка
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_path)
            
        # Находим реальную папку с файлами (GitHub добавляет корневую папку)
        subdirs = [d for d in os.listdir(extract_path) if os.path.isdir(os.path.join(extract_path, d))]
        if subdirs:
            final_source = os.path.join(extract_path, subdirs[0])
        else:
            final_source = extract_path

        if progress_callback:
            progress_callback("Готово к установке", 100)
            
        return final_source
        
    except Exception as e:
        print(f"[Update] Ошибка загрузки/распаковки: {e}")
        return None


def start_update_process(source_path: str):
    """
    Запускает внешний скрипт для замены файлов и рестарта.
    Текущий процесс должен завершиться сразу после вызова этой функции.
    """
    # Путь к скрипту-обновлятору
    updater_script = os.path.join(os.path.dirname(__file__), "apply_update.py")
    python_exe = sys.executable
    
    cmd = [python_exe, updater_script, source_path, os.getcwd(), sys.argv[0]]
    
    # Запускаем в фоне и немедленно выходим
    subprocess.Popen(cmd, creationflags=subprocess.DETACHED_PROCESS if os.name == 'nt' else 0)
    print("[Update] Процесс обновления запущен. Приложение будет перезапущено.")


class UpdateManager:
    """Менеджер обновлений приложения (класс для обратной совместимости)"""
    
    def __init__(self):
        self.version_file = Path(__file__).parent.parent / "version.txt"
        self.current_version = self._read_local_version()
        
    def _read_local_version(self) -> str:
        if not self.version_file.exists():
            from config.settings import get_version
            version = get_version()
            self._write_version(version)
            return version
        try:
            version = self.version_file.read_text(encoding="utf-8").strip()
            return version if version else "0.0"
        except Exception as e:
            print(f"⚠️ Ошибка чтения version.txt: {e}")
            return "0.0"
    
    def _write_version(self, version: str) -> None:
        try:
            self.version_file.write_text(version, encoding="utf-8")
        except Exception as e:
            print(f"⚠️ Ошибка записи version.txt: {e}")
    
    def check_for_updates(self, timeout: int = 10) -> dict[str, Any]:
        """Проверка обновлений (возвращает расширенный результат для GUI)"""
        result = {
            "has_update": False,
            "current_version": self.current_version,
            "latest_version": self.current_version,
            "release_notes": "",
            "download_url": "",
            "error": None
        }
        
        update_data = check_for_updates(timeout)
        if update_data:
            result["has_update"] = True
            result["latest_version"] = update_data["version"]
            result["release_notes"] = update_data["notes"]
            result["download_url"] = update_data["url"]
        
        return result


def check_updates_at_startup(show_dialog: bool = True) -> dict[str, Any]:
    """Функция для проверки обновлений при старте приложения"""
    print("\n🔄 Проверка обновлений...")
    
    manager = UpdateManager()
    result = manager.check_for_updates()
    
    if result.get("error"):
        print(f"⚠️ {result['error']}")
        return result
    
    if result["has_update"]:
        print(f"✨ Доступна новая версия: {result['latest_version']}")
        print(f"   Текущая версия: {result['current_version']}")
        
        if result.get("release_notes"):
            print(f"\n📋 Заметки о релизе:\n{result['release_notes'][:200]}...")
        
        if show_dialog:
            print("\n💡 Будет показан диалог обновления.")
    else:
        print("✅ Установлена последняя версия.")
    
    return result


# Export public API
__all__ = [
    "UpdateManager",
    "check_updates_at_startup",
    "check_for_updates",
    "download_and_prepare_update",
    "start_update_process",
]

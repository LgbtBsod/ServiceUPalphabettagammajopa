#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Менеджер лицензий: триал 14 дней + активация ключом по HWID.

Логика:
1. При первом запуске — начинается триал на TRIAL_DAYS дней.
2. Дата старта сохраняется в реестре Windows + файл .license (двойная защита).
3. При каждом запуске проверяется целостность дат (откат → блокировка).
4. Пользователь активирует ключом, сгенерированным под его HWID.
5. После активации программа работает бессрочно (на этом железе).

Файл лицензии (.license) содержит JSON с HMAC-SHA256 подписью —
нельзя подделать без секретного ключа.
"""

import os
import json
import hmac
import hashlib
from datetime import datetime, timedelta
from typing import Optional

from config import BASE_DIR
from utils.hardware import get_hwid, get_hwid_short

# Секретный ключ для HMAC (одинаковый в keygen.py!)
# ВАЖНО: не меняйте после первой активации клиентов!
SECRET_KEY = b'ServiceUP_2024_License_Secret_Key_v1!'

TRIAL_DAYS = 14
REG_KEY_PATH = r'SOFTWARE\ServiceUP'
LICENSE_FILE = os.path.join(BASE_DIR, '.license')


def _generate_license_key(hwid: str) -> str:
    """Генерирует ключ активации из HWID (HMAC-SHA256).

    Это тот же алгоритм, что в keygen.py — ключ проверяется локально.
    """
    msg = hwid.replace('-', '').upper().encode('utf-8')
    digest = hmac.new(SECRET_KEY, msg, hashlib.sha256).hexdigest()
    # Берём 16 символов, форматируем XXXX-XXXX-XXXX-XXXX
    short = digest[:16].upper()
    return f"{short[0:4]}-{short[4:8]}-{short[8:12]}-{short[12:16]}"


def _compute_checksum(data: str) -> str:
    """Контрольная сумма для проверки целостности данных."""
    return hmac.new(SECRET_KEY, data.encode('utf-8'), hashlib.md5).hexdigest()


class LicenseManager:
    """Управление лицензией и пробным периодом."""

    def __init__(self):
        self.hwid = get_hwid()

    # ------------------------------------------------------------------
    # Реестр Windows (двойное хранение даты старта триала)
    # ------------------------------------------------------------------

    def _reg_read(self, name: str) -> Optional[str]:
        """Читает значение из реестра Windows."""
        import sys
        if sys.platform != 'win32':
            return None
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, REG_KEY_PATH) as key:
                val, _ = winreg.QueryValueEx(key, name)
                return str(val)
        except (FileNotFoundError, OSError, PermissionError):
            try:
                # Пробуем HKCU (без прав админа)
                import winreg
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY_PATH) as key:
                    val, _ = winreg.QueryValueEx(key, name)
                    return str(val)
            except (FileNotFoundError, OSError):
                return None
        except Exception:
            return None

    def _reg_write(self, name: str, value: str) -> bool:
        """Записывает значение в реестр Windows."""
        if sys.platform != 'win32':
            return False
        try:
            import winreg
        except ImportError:
            return False
        # Пробуем HKLM (нужны права), затем HKCU (всегда работает)
        for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                with winreg.CreateKeyEx(root, REG_KEY_PATH, 0, winreg.KEY_WRITE) as key:
                    winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
                return True
            except (PermissionError, OSError):
                continue
            except Exception:
                continue
        return False

    # ------------------------------------------------------------------
    # Файл лицензии
    # ------------------------------------------------------------------

    def _read_license_file(self) -> Optional[dict]:
        """Читает файл .license с проверкой HMAC."""
        try:
            if not os.path.exists(LICENSE_FILE):
                return None
            with open(LICENSE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            # Проверяем подпись
            signature = data.pop('signature', '')
            payload = json.dumps(data, sort_keys=True)
            expected = _compute_checksum(payload)
            if not hmac.compare_digest(signature, expected):
                print("Лицензия: подпись недействительна")
                return None
            return data
        except Exception as e:
            print(f"Ошибка чтения лицензии: {e}")
            return None

    def _write_license_file(self, data: dict) -> bool:
        """Записывает файл .license с HMAC-подписью."""
        try:
            payload = json.dumps(data, sort_keys=True)
            data_with_sig = dict(data)
            data_with_sig['signature'] = _compute_checksum(payload)
            with open(LICENSE_FILE, 'w', encoding='utf-8') as f:
                json.dump(data_with_sig, f, indent=2)
            # Скрываем файл на Windows
            if sys.platform == 'win32':
                try:
                    import ctypes
                    ctypes.windll.kernel32.SetFileAttributesW(LICENSE_FILE, 0x2)  # FILE_ATTRIBUTE_HIDDEN
                except Exception:
                    pass
            return True
        except Exception as e:
            print(f"Ошибка записи лицензии: {e}")
            return False

    # ------------------------------------------------------------------
    # Публичные методы
    # ------------------------------------------------------------------

    def check_license(self) -> str:
        """Проверяет статус лицензии.

        Возвращает:
            'activated' — программа активирована, работает бессрочно
            'trial_active' — пробный период активен, осталось N дней
            'trial_expired' — пробный период истёк, нужна активация
            'corrupted' — обнаружено нарушение целостности (откат даты)
        """
        # 1. Проверяем активацию
        lic = self._read_license_file()
        if lic and lic.get('activated') and lic.get('hwid') == self.hwid:
            # Проверяем ключ
            stored_key = lic.get('key', '')
            if stored_key and stored_key == _generate_license_key(self.hwid):
                return 'activated'

        # 2. Проверяем триал
        trial_start = self._get_trial_start()

        if trial_start is None:
            # Первый запуск — начинаем триал
            now = datetime.now()
            self._set_trial_start(now)
            return 'trial_active'

        # Вычисляем оставшиеся дни
        now = datetime.now()
        days_passed = (now - trial_start).days

        # Защита от отката даты
        last_seen = self._get_last_seen_date()
        if last_seen and now < last_seen:
            return 'corrupted'

        self._set_last_seen_date(now)

        if days_passed < TRIAL_DAYS:
            return 'trial_active'
        else:
            return 'trial_expired'

    def get_trial_days_left(self) -> int:
        """Возвращает количество оставшихся дней триала (0 если истёк)."""
        trial_start = self._get_trial_start()
        if trial_start is None:
            return TRIAL_DAYS
        now = datetime.now()
        days_passed = (now - trial_start).days
        return max(0, TRIAL_DAYS - days_passed)

    def activate(self, key: str) -> bool:
        """Активирует лицензию по ключу.

        Проверяет ключ через HMAC (ключ должен соответствовать HWID).
        При успехе — сохраняет в .license.
        """
        key = key.strip().upper()
        expected_key = _generate_license_key(self.hwid)
        if hmac.compare_digest(key, expected_key):
            data = {
                'activated': True,
                'hwid': self.hwid,
                'key': expected_key,
                'activated_at': datetime.now().isoformat(),
            }
            self._write_license_file(data)
            # Записываем в реестр тоже
            self._reg_write('license_key', expected_key)
            self._reg_write('hwid', self.hwid)
            return True
        return False

    def get_hwid(self) -> str:
        """Возвращает HWID для отображения пользователю."""
        return self.hwid

    def is_activated(self) -> bool:
        """Быстрая проверка — активирована ли лицензия."""
        return self.check_license() == 'activated'

    def deactivate(self) -> bool:
        """Деактивирует лицензию (удаляет файл)."""
        try:
            if os.path.exists(LICENSE_FILE):
                os.remove(LICENSE_FILE)
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Внутренние методы для дат
    # ------------------------------------------------------------------

    def _get_trial_start(self) -> Optional[datetime]:
        """Получает дату старта триала (из файла или реестра)."""
        # Из файла
        lic = self._read_license_file()
        if lic and lic.get('trial_start'):
            try:
                return datetime.fromisoformat(lic['trial_start'])
            except (ValueError, TypeError):
                pass

        # Из реестра
        reg_val = self._reg_read('trial_start')
        if reg_val:
            try:
                return datetime.fromisoformat(reg_val)
            except (ValueError, TypeError):
                pass

        return None

    def _set_trial_start(self, dt: datetime) -> None:
        """Сохраняет дату старта триала."""
        dt_str = dt.isoformat()
        # В реестр
        self._reg_write('trial_start', dt_str)
        # В файл
        lic = self._read_license_file() or {}
        lic['trial_start'] = dt_str
        lic['hwid'] = self.hwid
        self._write_license_file(lic)

    def _get_last_seen_date(self) -> Optional[datetime]:
        """Получает дату последнего запуска (для обнаружения отката)."""
        lic = self._read_license_file()
        if lic and lic.get('last_seen'):
            try:
                return datetime.fromisoformat(lic['last_seen'])
            except (ValueError, TypeError):
                pass
        reg_val = self._reg_read('last_seen')
        if reg_val:
            try:
                return datetime.fromisoformat(reg_val)
            except (ValueError, TypeError):
                pass
        return None

    def _set_last_seen_date(self, dt: datetime) -> None:
        """Сохраняет дату последнего запуска."""
        dt_str = dt.isoformat()
        self._reg_write('last_seen', dt_str)
        lic = self._read_license_file() or {}
        lic['last_seen'] = dt_str
        lic['hwid'] = self.hwid
        self._write_license_file(lic)


# Импорт sys для использования в методах
import sys

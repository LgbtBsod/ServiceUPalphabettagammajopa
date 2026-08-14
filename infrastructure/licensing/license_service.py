"""
License service - инфраструктурный сервис для управления лицензиями.

Использует существующий utils/license_manager с адаптацией под новую архитектуру.
Следует принципу Dependency Inversion.
"""

from __future__ import annotations
import logging
from typing import Optional, Protocol
from datetime import datetime

logger = logging.getLogger(__name__)


class LicenseRepositoryProtocol(Protocol):
    """Протокол хранилища лицензий."""
    
    def read(self) -> Optional[dict]: ...
    def write(self, data: dict) -> bool: ...
    def delete(self) -> bool: ...


class HardwareInfoProtocol(Protocol):
    """Протокол получения HWID."""
    
    def get_hwid(self) -> str: ...


class LicenseService:
    """
    Сервис управления лицензиями.
    
    Адаптирует legacy utils/license_manager под новую архитектуру.
    Реализует паттерн Facade для упрощения работы с лицензированием.
    """
    
    TRIAL_DAYS = 14
    
    def __init__(
        self,
        license_repo: Optional[LicenseRepositoryProtocol] = None,
        hardware_info: Optional[HardwareInfoProtocol] = None,
    ):
        """
        Инициализация сервиса.
        
        Args:
            license_repo: Репозиторий для хранения лицензий (по умолчанию - файл .license)
            hardware_info: Сервис получения HWID (по умолчанию - utils/hardware)
        """
        # Lazy import для избежания циклических зависимостей
        if license_repo is None:
            from infrastructure.licensing.license_repository import FileLicenseRepository
            license_repo = FileLicenseRepository()
        
        if hardware_info is None:
            from infrastructure.licensing.hardware_info import DefaultHardwareInfo
            hardware_info = DefaultHardwareInfo()
        
        self._repo = license_repo
        self._hardware = hardware_info
        self._hwid = self._hardware.get_hwid()
    
    @property
    def hwid(self) -> str:
        """Получение HWID текущего устройства."""
        return self._hwid
    
    def check_license(self) -> str:
        """
        Проверка статуса лицензии.
        
        Returns:
            'activated' — программа активирована
            'trial_active' — пробный период активен
            'trial_expired' — пробный период истёк
            'corrupted' — нарушение целостности (откат даты)
        """
        # Проверка активации
        lic = self._repo.read()
        if lic and lic.get('activated') and lic.get('hwid') == self._hwid:
            stored_key = lic.get('key', '')
            expected_key = self._generate_license_key(self._hwid)
            if stored_key and stored_key == expected_key:
                return 'activated'
        
        # Проверка триала
        trial_start = self._get_trial_start()
        
        if trial_start is None:
            # Первый запуск
            now = datetime.now()
            self._set_trial_start(now)
            return 'trial_active'
        
        now = datetime.now()
        days_passed = (now - trial_start).days
        
        # Защита от отката даты
        last_seen = self._get_last_seen_date()
        if last_seen and now < last_seen:
            return 'corrupted'
        
        self._set_last_seen_date(now)
        
        if days_passed < self.TRIAL_DAYS:
            return 'trial_active'
        else:
            return 'trial_expired'
    
    def get_trial_days_left(self) -> int:
        """Получение оставшихся дней триала."""
        trial_start = self._get_trial_start()
        if trial_start is None:
            return self.TRIAL_DAYS
        
        now = datetime.now()
        days_passed = (now - trial_start).days
        return max(0, self.TRIAL_DAYS - days_passed)
    
    def activate(self, key: str) -> bool:
        """
        Активация лицензии по ключу.
        
        Args:
            key: Ключ активации
            
        Returns:
            True если активация успешна
        """
        key = key.strip().upper()
        expected_key = self._generate_license_key(self._hwid)
        
        import hmac
        if hmac.compare_digest(key, expected_key):
            data = {
                'activated': True,
                'hwid': self._hwid,
                'key': expected_key,
                'activated_at': datetime.now().isoformat(),
            }
            success = self._repo.write(data)
            
            if success:
                logger.info(f"Лицензия активирована для HWID: {self._hwid}")
            
            return success
        
        logger.warning(f"Неверный ключ активации: {key[:4]}...")
        return False
    
    def is_activated(self) -> bool:
        """Быстрая проверка активации."""
        return self.check_license() == 'activated'
    
    def deactivate(self) -> bool:
        """Деактивация лицензии."""
        return self._repo.delete()
    
    def _generate_license_key(self, hwid: str) -> str:
        """Генерация ключа активации из HWID."""
        import hmac
        import hashlib
        from config import LICENSE_SECRET_KEY as SECRET_KEY
        
        msg = hwid.replace('-', '').upper().encode('utf-8')
        digest = hmac.new(SECRET_KEY, msg, hashlib.sha256).hexdigest()
        short = digest[:16].upper()
        return f"{short[0:4]}-{short[4:8]}-{short[8:12]}-{short[12:16]}"
    
    def _get_trial_start(self) -> Optional[datetime]:
        """Получение даты начала триала."""
        lic = self._repo.read()
        if lic and lic.get('trial_start'):
            try:
                return datetime.fromisoformat(lic['trial_start'])
            except (ValueError, TypeError):
                pass
        
        # Fallback к реестру Windows (если на Windows)
        import sys
        if sys.platform == 'win32':
            try:
                import winreg
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\ServiceUP') as key:
                    val, _ = winreg.QueryValueEx(key, 'trial_start')
                    return datetime.fromisoformat(str(val))
            except (FileNotFoundError, OSError, PermissionError):
                pass
        
        return None
    
    def _set_trial_start(self, dt: datetime) -> None:
        """Сохранение даты начала триала."""
        dt_str = dt.isoformat()
        
        # В реестр
        import sys
        if sys.platform == 'win32':
            try:
                import winreg
                with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, r'SOFTWARE\ServiceUP', 0, winreg.KEY_WRITE) as key:
                    winreg.SetValueEx(key, 'trial_start', 0, winreg.REG_SZ, dt_str)
            except (PermissionError, OSError):
                pass
        
        # В файл лицензии
        lic = self._repo.read() or {}
        lic['trial_start'] = dt_str
        lic['hwid'] = self._hwid
        self._repo.write(lic)
    
    def _get_last_seen_date(self) -> Optional[datetime]:
        """Получение даты последнего запуска."""
        lic = self._repo.read()
        if lic and lic.get('last_seen'):
            try:
                return datetime.fromisoformat(lic['last_seen'])
            except (ValueError, TypeError):
                pass
        
        import sys
        if sys.platform == 'win32':
            try:
                import winreg
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\ServiceUP') as key:
                    val, _ = winreg.QueryValueEx(key, 'last_seen')
                    return datetime.fromisoformat(str(val))
            except (FileNotFoundError, OSError, PermissionError):
                pass
        
        return None
    
    def _set_last_seen_date(self, dt: datetime) -> None:
        """Сохранение даты последнего запуска."""
        dt_str = dt.isoformat()
        
        import sys
        if sys.platform == 'win32':
            try:
                import winreg
                with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, r'SOFTWARE\ServiceUP', 0, winreg.KEY_WRITE) as key:
                    winreg.SetValueEx(key, 'last_seen', 0, winreg.REG_SZ, dt_str)
            except (PermissionError, OSError):
                pass
        
        lic = self._repo.read() or {}
        lic['last_seen'] = dt_str
        lic['hwid'] = self._hwid
        self._repo.write(lic)

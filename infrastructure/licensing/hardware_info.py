"""
Hardware info implementations - получение информации об оборудовании.
"""

from __future__ import annotations
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class DefaultHardwareInfo:
    """
    Получение HWID через utils/hardware.
    
    Адаптирует legacy модуль под новый интерфейс.
    """
    
    def __init__(self):
        self._hwid: Optional[str] = None
    
    def get_hwid(self) -> str:
        """Получение HWID текущего устройства."""
        if self._hwid is not None:
            return self._hwid
        
        try:
            from utils.hardware import get_hwid
            self._hwid = get_hwid()
        except ImportError:
            logger.warning("utils.hardware не найден, используем fallback")
            self._hwid = self._get_fallback_hwid()
        
        return self._hwid
    
    def _get_fallback_hwid(self) -> str:
        """Fallback метод получения HWID (кроссплатформенный)."""
        import hashlib
        import platform
        import uuid
        
        # Собираем информацию о системе
        info = [
            platform.node(),  # Имя компьютера
            platform.machine(),  # Архитектура
            str(uuid.getnode()),  # MAC адрес
        ]
        
        # Создаем хеш
        combined = '|'.join(info)
        hwid_hash = hashlib.sha256(combined.encode()).hexdigest()[:16]
        
        # Форматируем как XXXX-XXXX-XXXX-XXXX
        return f"{hwid_hash[0:4]}-{hwid_hash[4:8]}-{hwid_hash[8:12]}-{hwid_hash[12:16]}"


class WindowsHardwareInfo:
    """
    Получение HWID через Windows API (более точное).
    
    Использует WMI для получения информации о железе.
    """
    
    def __init__(self):
        self._hwid: Optional[str] = None
    
    def get_hwid(self) -> str:
        """Получение HWID через WMI."""
        if self._hwid is not None:
            return self._hwid
        
        import sys
        if sys.platform != 'win32':
            return DefaultHardwareInfo().get_hwid()
        
        try:
            import wmi
            c = wmi.WMI()
            
            # Получаем серийный номер BIOS
            bios_serial = ""
            for bios in c.Win32_BIOS():
                bios_serial = bios.SerialNumber or ""
                break
            
            # Получаем ID материнской платы
            motherboard_id = ""
            for base_board in c.Win32_BaseBoard():
                motherboard_id = base_board.SerialNumber or ""
                break
            
            # Получаем ID процессора
            cpu_id = ""
            for processor in c.Win32_Processor():
                cpu_id = processor.ProcessorId or ""
                break
            
            # Комбинируем и хешируем
            import hashlib
            combined = f"{bios_serial}|{motherboard_id}|{cpu_id}"
            hwid_hash = hashlib.sha256(combined.encode()).hexdigest()[:16]
            
            self._hwid = f"{hwid_hash[0:4]}-{hwid_hash[4:8]}-{hwid_hash[8:12]}-{hwid_hash[12:16]}"
            
        except (ImportError, Exception) as e:
            logger.warning(f"WMI не доступен, используем fallback: {e}")
            self._hwid = DefaultHardwareInfo().get_hwid()
        
        return self._hwid

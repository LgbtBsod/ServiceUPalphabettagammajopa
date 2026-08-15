#!/usr/bin/env python3

"""Получение уникального ID железа (HWID) для привязки лицензии.

Использует серийный номер материнской платы и ID процессора (через WMI на
Windows). На других ОС — fallback на uuid.getnode() (MAC-адрес).
Результат кешируется — WMI не вызывается повторно.
"""

import hashlib
import sys
import uuid

_cached_hwid = None
_cached_raw = None


def _get_wmi_value(wmi_query: str) -> str:
    """Выполняет WMI-запрос через PowerShell (wmic устарел в новых Windows).

    Использует bytes + ручную декодировку, т.к. PowerShell на русской Windows
    может вернуть вывод в cp866, что ломает text=True.
    """
    import subprocess as sp

    def _run_and_decode(cmd):
        """Запускает команду, возвращает декодированный stdout."""
        try:
            r = sp.run(
                cmd,
                capture_output=True,
                timeout=10,
                creationflags=0x08000000 if sys.platform == "win32" else 0,
            )
            # Пробуем utf-8, потом cp866 (русская Windows), потом latin-1
            for enc in ("utf-8", "cp866", "cp1251", "latin-1"):
                try:
                    return r.stdout.decode(enc).strip()
                except (UnicodeDecodeError, AttributeError):
                    continue
            return r.stdout.decode("latin-1", errors="replace").strip()
        except Exception:
            return ""

    # PowerShell
    try:
        ps_cmd = f"(Get-WmiObject {wmi_query})"
        out = _run_and_decode(["powershell", "-NoProfile", "-Command", ps_cmd])
        if out and out.lower() not in ("", "default", "none"):
            lines = [l.strip() for l in out.split("\n") if l.strip()]
            return lines[0] if lines else out
    except Exception:
        pass

    # Fallback — wmic (старые системы)
    out = _run_and_decode(["wmic", *wmi_query.split()])
    if out:
        lines = [l.strip() for l in out.split("\n") if l.strip()]
        if len(lines) >= 2:
            return lines[-1]
        elif lines:
            return lines[0]
    return ""


def _get_raw_hardware_data() -> str:
    """Собирает сырые данные о железе."""
    global _cached_raw
    if _cached_raw is not None:
        return _cached_raw

    parts = []

    if sys.platform == "win32":
        # Серийный номер материнской платы
        motherboard = _get_wmi_value("baseboard get serialnumber")
        if motherboard and motherboard.lower() not in ("default", "none", ""):
            parts.append(f"MB:{motherboard}")

        # ID процессора
        cpu_id = _get_wmi_value("cpu get processorid")
        if cpu_id and cpu_id.lower() not in ("default", "none", ""):
            parts.append(f"CPU:{cpu_id}")

    # Fallback — всегда добавляем uuid.getnode() (MAC-based)
    node = uuid.getnode()
    parts.append(f"UUID:{node}")

    # MachineGuid из реестра Windows (уникален для установки ОС)
    if sys.platform == "win32":
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\\Microsoft\\Cryptography"
            ) as key:
                guid, _ = winreg.QueryValueEx(key, "MachineGuid")
                if guid:
                    parts.append(f"GUID:{guid}")
        except Exception:
            pass

    _cached_raw = "|".join(parts)
    return _cached_raw


def get_hwid() -> str:
    """Возвращает уникальный ID железа в формате XXXX-XXXX-XXXX-XXXX.

    Кешируется после первого вызова. Не содержит чувствительных данных —
    это SHA256-хеш от серийников материнской платы и процессора.
    """
    global _cached_hwid
    if _cached_hwid is not None:
        return _cached_hwid

    raw = _get_raw_hardware_data()
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()

    # Берём первые 16 символов, форматируем XXXX-XXXX-XXXX-XXXX
    short = digest[:16].upper()
    formatted = f"{short[0:4]}-{short[4:8]}-{short[8:12]}-{short[12:16]}"

    _cached_hwid = formatted
    return formatted


def get_hwid_short() -> str:
    """Короткий HWID без дефисов (для keygen)."""
    return get_hwid().replace("-", "")


if __name__ == "__main__":
    print(f"HWID: {get_hwid()}")
    print(f"Short: {get_hwid_short()}")
    print(f"Raw: {_get_raw_hardware_data()}")

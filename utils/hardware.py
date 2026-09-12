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


def _run_and_decode(cmd: list[str]) -> str:
    """Запускает команду, возвращает декодированный stdout.

    bytes + ручная декодировка: PowerShell на русской Windows может вернуть
    вывод в cp866, что ломает text=True.
    """
    import subprocess as sp

    try:
        r = sp.run(
            cmd,
            capture_output=True,
            timeout=10,
            creationflags=0x08000000 if sys.platform == "win32" else 0,
        )
        for enc in ("utf-8", "cp866", "cp1251", "latin-1"):
            try:
                return r.stdout.decode(enc).strip()
            except (UnicodeDecodeError, AttributeError):
                continue
        return r.stdout.decode("latin-1", errors="replace").strip()
    except Exception:
        return ""


def _get_wmi_value(cim_class: str, cim_property: str) -> str:
    """Читает одно свойство WMI/CIM-класса.

    Раньше вызывалось как ``_get_wmi_value("baseboard get serialnumber")`` и
    подставлялось в ``(Get-WmiObject baseboard get serialnumber)`` — это
    синтаксис *wmic*, а не PowerShell: команда падала, функция возвращала "" —
    и HWID собирался только из ``uuid.getnode()``, который на машине без
    доступного MAC отдаёт СЛУЧАЙНОЕ число при каждом запуске. Итог: HWID
    (и привязанная к нему лицензия) менялся между запусками. Теперь —
    ``Get-CimInstance`` (``Get-WmiObject`` тоже помечен устаревшим), затем
    ``wmic`` как fallback для старых систем.
    """
    if sys.platform != "win32":
        return ""

    out = _run_and_decode([
        "powershell", "-NoProfile", "-NonInteractive", "-Command",
        f"(Get-CimInstance -ClassName {cim_class} -ErrorAction SilentlyContinue)."
        f"{cim_property}",
    ])
    for line in (l.strip() for l in out.splitlines() if l.strip()):
        if line.lower() not in ("default", "none", "to be filled by o.e.m.", "o.e.m."):
            return line

    # Fallback — wmic (Windows 10 и старее; в 11 24H2+ удалён)
    wmic_map = {"serialnumber": "get serialnumber", "processorid": "get processorid"}
    out = _run_and_decode(["wmic", cim_class_to_wmic(cim_class), wmic_map.get(cim_property.lower(), f"get {cim_property.lower()}")])
    lines = [l.strip() for l in out.splitlines() if l.strip()]
    if len(lines) >= 2:
        return lines[-1]
    return lines[0] if lines else ""


def cim_class_to_wmic(cim_class: str) -> str:
    return {"win32_baseboard": "baseboard", "win32_processor": "cpu"}.get(
        cim_class.lower(), cim_class
    )


def _get_raw_hardware_data() -> str:
    """Собирает сырые данные о железе."""
    global _cached_raw
    if _cached_raw is not None:
        return _cached_raw

    parts = []

    # MachineGuid из реестра Windows — уникален для установки ОС, стабилен,
    # есть всегда. Ставим ПЕРВЫМ (самый надёжный идентификатор), а не в конце.
    # Раньше путь был r"SOFTWARE\\Microsoft\\Cryptography" — raw-строка, т.е.
    # ДВЕ обратных косых подряд: winreg такой ключ не открывал, GUID терялся.
    if sys.platform == "win32":
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Cryptography",
                0,
                winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
            ) as key:
                guid, _ = winreg.QueryValueEx(key, "MachineGuid")
                if guid:
                    parts.append(f"GUID:{guid}")
        except OSError:
            pass

        motherboard = _get_wmi_value("Win32_BaseBoard", "SerialNumber")
        if motherboard:
            parts.append(f"MB:{motherboard}")

        cpu_id = _get_wmi_value("Win32_Processor", "ProcessorId")
        if cpu_id:
            parts.append(f"CPU:{cpu_id}")

    # uuid.getnode() — ТОЛЬКО если ничего стабильного не нашли. На машине без
    # читаемого MAC он возвращает случайное 48-битное число (multicast-бит
    # выставлен) на каждый вызов — такой HWID меняется между запусками, поэтому
    # random-fallback явно отбраковываем.
    if not parts:
        node = uuid.getnode()
        is_random = bool(node >> 40 & 0x01)  # multicast bit -> не настоящий MAC
        if not is_random:
            parts.append(f"UUID:{node}")

    if not parts:
        # Совсем ничего стабильного — привязываемся к имени машины + пользователю.
        import getpass
        import platform

        parts.append(f"HOST:{platform.node()}:{getpass.getuser()}")

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

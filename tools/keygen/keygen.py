#!/usr/bin/env python3

"""Генератор ключей активации для ServiceUP.

Запускайте ТОЛЬКО у себя — НЕ включайте в дистрибутив для клиентов!

Использование:
    python keygen.py
    Введите HWID клиента: B67D-8FC0-8872-4F73
    Ключ активации: XXXX-XXXX-XXXX-XXXX
"""

import hashlib
import hmac

# Секретный ключ — ДОЛЖЕН БЫТЬ одинаковым с utils/license_manager.py!
# Вынесен в config.py для централизованного управления
from config import LICENSE_SECRET_KEY as SECRET_KEY


def generate_key(hwid: str) -> str:
    """Генерирует ключ активации из HWID."""
    msg = hwid.replace("-", "").upper().encode("utf-8")
    digest = hmac.new(SECRET_KEY, msg, hashlib.sha256).hexdigest()
    short = digest[:16].upper()
    return f"{short[0:4]}-{short[4:8]}-{short[8:12]}-{short[12:16]}"


def main():
    print("=" * 50)
    print("  ServiceUP — Генератор ключей активации")
    print("=" * 50)
    print()

    while True:
        hwid = (
            input("Введите HWID клиента (или 'выход' для закрытия): ").strip().upper()
        )
        if hwid.lower() in ("выход", "exit", "quit", "q", ""):
            break

        # Нормализуем — убираем дефисы и добавляем обратно
        hwid_clean = hwid.replace("-", "").replace(" ", "")
        if len(hwid_clean) != 16:
            print(f"  ⚠️ HWID должен содержать 16 символов (получено {len(hwid_clean)})")
            print("  Формат: XXXX-XXXX-XXXX-XXXX")
            print()
            continue

        # Форматируем красиво
        hwid_formatted = f"{hwid_clean[0:4]}-{hwid_clean[4:8]}-{hwid_clean[8:12]}-{hwid_clean[12:16]}"

        key = generate_key(hwid_formatted)
        print()
        print(f"  ✅ HWID:  {hwid_formatted}")
        print(f"  🔑 Ключ:  {key}")
        print()
        print("  Отправьте ключ клиенту для активации программы.")
        print("-" * 50)
        print()


if __name__ == "__main__":
    main()

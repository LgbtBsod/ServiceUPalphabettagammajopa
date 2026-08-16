"""Генератор логина по ФИО в стиле SAP: транслитерация в латиницу,
фамилия + инициалы имени/отчества, до 12 символов. При коллизии —
сокращение фамилии, затем цифровой суффикс.
"""

from __future__ import annotations

from collections.abc import Callable

MAX_LOGIN_LENGTH = 12

_TRANSLIT_MAP = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def _transliterate(text: str) -> str:
    """Транслитерирует кириллицу в латиницу (нижний регистр); не-буквенные
    символы отбрасываются, латиница/цифры остаются как есть."""
    result = []
    for ch in text.lower():
        if ch in _TRANSLIT_MAP:
            result.append(_TRANSLIT_MAP[ch])
        elif ch.isalnum():
            result.append(ch)
    return "".join(result)


def generate_login_candidates(
    full_name: str, max_length: int = MAX_LOGIN_LENGTH
) -> list[str]:
    """Формирует упорядоченный список кандидатов логина по ФИО.

    Ожидаемый порядок слов — "Фамилия Имя Отчество" (может быть неполным).
    Каждый следующий кандидат короче/проще предыдущего — используется как
    fallback-цепочка при коллизии логина.
    """
    parts = [p for p in full_name.split() if p]
    if not parts:
        return ["user"]

    surname = _transliterate(parts[0])
    initials = "".join(_transliterate(p)[:1] for p in parts[1:3])

    candidates = []
    if surname:
        candidates.append((surname + initials)[:max_length])
        # Прогрессивно укорачиваем фамилию (оставляя место под инициалы)
        min_surname_len = 3
        for cut in range(len(surname) - 1, min_surname_len - 1, -1):
            candidates.append((surname[:cut] + initials)[:max_length])
        # Только фамилия + первая буква имени (без отчества)
        if len(parts) > 1:
            first_initial = _transliterate(parts[1])[:1]
            candidates.append((surname + first_initial)[:max_length])
        # Только фамилия
        candidates.append(surname[:max_length])

    # Убираем пустые/дублирующиеся варианты, сохраняя порядок
    seen: set[str] = set()
    unique = []
    for c in candidates:
        if c and c not in seen:
            seen.add(c)
            unique.append(c)
    return unique or ["user"]


def generate_unique_login(
    full_name: str,
    is_taken: Callable[[str], bool],
    max_length: int = MAX_LOGIN_LENGTH,
) -> str:
    """Подбирает свободный логин по ФИО.

    is_taken(login) -> bool — проверка занятости (обычно поход в репозиторий).
    Если все "естественные" варианты (fallback-цепочка сокращений) заняты,
    к первому (самому полному) кандидату добавляется числовой суффикс.
    """
    candidates = generate_login_candidates(full_name, max_length)
    for candidate in candidates:
        if not is_taken(candidate):
            return candidate

    base = candidates[0][: max_length - 2] or "user"
    n = 1
    while True:
        candidate = f"{base}{n}"
        if not is_taken(candidate):
            return candidate
        n += 1

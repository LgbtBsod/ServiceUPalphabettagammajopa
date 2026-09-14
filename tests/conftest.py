"""Global pytest fixtures and configuration."""

# Import project modules
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for each test session."""
    import asyncio

    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_logger() -> MagicMock:
    """Создает мок логгера для тестов."""
    logger = MagicMock()
    logger.debug = MagicMock()
    logger.info = MagicMock()
    logger.warning = MagicMock()
    logger.error = MagicMock()
    logger.exception = MagicMock()
    return logger


@pytest.fixture
def mock_database() -> MagicMock:
    """Создает мок базы данных для тестов."""
    db = MagicMock()
    db.connect = MagicMock(return_value=True)
    db.disconnect = MagicMock()
    db.execute = MagicMock()
    db.fetch_one = MagicMock(return_value=None)
    db.fetch_all = MagicMock(return_value=[])
    return db


@pytest.fixture
def temp_dir(tmp_path: Path) -> Path:
    """Создает временную директорию для тестов."""
    return tmp_path


def _create_tk_root():
    """Создаёт tk.Tk() с несколькими попытками.

    В полном прогоне (`pytest -q` по всему tests/), а НЕ при запуске
    тестового файла изолированно, tk.Tk() изредка (замечено ~1 раз на 4
    прогона) кидает TclError — похоже на кратковременную нехватку
    GDI/USER-хендлов Windows при частом создании/уничтожении top-level окон
    соседними тестами. Настоящей нехватки X-дисплея (CI ubuntu-latest)
    ретраем не лечим — там TclError будет на каждой попытке одинаково, и
    через 3 попытки тест корректно пропустится через tk_root, а не зависнет.
    """
    import time
    import tkinter as tk

    last_err = None
    for _attempt in range(3):
        try:
            return tk.Tk()
        except tk.TclError as e:
            last_err = e
            time.sleep(0.2)
    raise last_err


@pytest.fixture
def tk_root():
    """Скрытый (withdraw()) реальный Tk root для тестов classic-GUI виджетов
    (customtkinter/tkinter.Canvas) — не стаб, настоящий Tk. Пропускается,
    если поднять Tk вообще не удалось (например, CI-раннер без X-дисплея)."""
    import tkinter as tk

    try:
        root = _create_tk_root()
    except tk.TclError:
        pytest.skip("Нет доступного X-дисплея для Tk (например, CI ubuntu-latest)")
    root.withdraw()
    yield root
    root.destroy()


@pytest.fixture
def sample_device_data() -> dict:
    """Пример данных устройства для тестов."""
    return {
        "type": "smartphone",
        "model": "iPhone 13 Pro",
        "serial_number": "SN123456789",
        "color": "graphite",
        "problem": "Не включается после падения",
        "price": 15000.0,
    }


@pytest.fixture
def sample_work_item_data() -> dict:
    """Пример данных работы для тестов."""
    return {
        "title": "Замена экрана",
        "description": "Замена разбитого стекла экрана",
        "price": 5000.0,
        "time_estimate": 120,  # минут
    }

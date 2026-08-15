"""Test Module Architecture
========================

Модульная система тестирования проекта ServiceUp.

Структура:
- unit/ - Модульные тесты для отдельных классов и функций
- integration/ - Интеграционные тесты для взаимодействия модулей
- e2e/ - End-to-End тесты полного цикла
- fixtures/ - Общие фикстуры и моки
- conftest.py - Глобальные конфигурации pytest

Принципы:
1. Каждый плагин имеет свои тесты в tests/plugins/{plugin_name}/
2. Инфраструктурные тесты в tests/infrastructure/{component}/
3. Тесты ядра в tests/core/{component}/
4. Использование параметризации для покрытия граничных случаев
5. Mock внешних зависимостей (БД, API, файловая система)
"""

from pathlib import Path

import pytest

# Базовый путь к проекту
PROJECT_ROOT = Path(__file__).parent.parent


def pytest_configure(config):
    """Конфигурация pytest меток."""
    config.addinivalue_line(
        "markers",
        "unit: mark test as a unit test (fast, isolated)",
    )
    config.addinivalue_line(
        "markers",
        "integration: mark test as an integration test (requires DB/network)",
    )
    config.addinivalue_line(
        "markers",
        "e2e: mark test as an end-to-end test (full cycle)",
    )
    config.addinivalue_line(
        "markers",
        "slow: mark test as slow running",
    )
    config.addinivalue_line(
        "markers",
        "plugin(name): mark test for specific plugin",
    )


@pytest.fixture(scope="session")
def project_root() -> Path:
    """Возвращает корневой путь проекта."""
    return PROJECT_ROOT


@pytest.fixture(scope="session")
def tests_dir() -> Path:
    """Возвращает путь к директории тестов."""
    return PROJECT_ROOT / "tests"


@pytest.fixture
def sample_order_data() -> dict:
    """Пример данных заказа для тестов."""
    return {
        "order_number": "A-000001",
        "client_id": 1,
        "device_type": "smartphone",
        "device_model": "iPhone 13",
        "problem_description": "Не включается",
        "status": "new",
        "priority": "normal",
        "price": 5000.0,
    }


@pytest.fixture
def sample_client_data() -> dict:
    """Пример данных клиента для тестов."""
    return {
        "name": "Иван Иванов",
        "phone": "+79991234567",
        "email": "ivan@example.com",
        "address": "г. Москва, ул. Пушкина, д. 10",
    }

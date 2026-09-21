#!/usr/bin/env python3

"""Тесты для plugins/clients — единственного по-настоящему рабочего плагина,
и для сквозного пути discover() -> load() -> register_module(), который
раньше не вызывался автоматически (плагины существовали только на бумаге,
см. AUDIT_REPORT_v20.md/v21.md).
"""

import os
import tempfile

import pytest

from core.kernel import get_core, reset_core
from database.db_config import DatabaseConfig
from database.engines.sqlite_engine import SQLiteEngine
from database.sqlalchemy_models import Base
from plugins.clients import (
    ClientService,
    CreateClientCommand,
    DeleteClientCommand,
    GetClientByIdQuery,
    GetClientByPhoneQuery,
    IClientRepository,
    UpdateClientCommand,
)
from plugins.clients.repository import SqlAlchemyClientRepository


@pytest.fixture
def engine():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    eng = SQLiteEngine(DatabaseConfig(database=path))
    Base.metadata.create_all(eng.get_engine())
    yield eng
    eng.dispose()
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture
def repository(engine) -> SqlAlchemyClientRepository:
    return SqlAlchemyClientRepository(engine)


@pytest.fixture
def service(repository) -> ClientService:
    return ClientService(repository)


class TestSqlAlchemyClientRepository:
    """SqlAlchemyClientRepository поверх database.sqlalchemy_models.Client —
    та же таблица/движок, что использует остальное приложение (не отдельная
    БД для плагина)."""

    def test_save_and_get_by_id(self, repository):
        from plugins.clients import ClientEntity

        client = ClientEntity(id=0, full_name="Иван Иванов", phone="+79991234567")
        assert repository.save(client) is True
        assert client.id != 0

        fetched = repository.get_by_id(client.id)
        assert fetched is not None
        assert fetched.full_name == "Иван Иванов"

    def test_get_by_phone(self, repository):
        from plugins.clients import ClientEntity

        # ClientEntity.__post_init__ normalizes the phone (e.g. "+79997654321"
        # -> "+7 (999) 765-43-21") — query by the entity's actual stored
        # value, not the raw input.
        client = ClientEntity(id=0, full_name="Пётр Петров", phone="+79997654321")
        repository.save(client)

        found = repository.get_by_phone(client.phone)
        assert found is not None
        assert found.full_name == "Пётр Петров"

    def test_save_returns_false_on_duplicate_phone_unique_constraint(self, repository):
        """Client.phone — unique=True (database/sqlalchemy_models.py). save()
        оборачивает IntegrityError в try/except и возвращает False — но
        единственный существующий тест дублей (test_create_client_
        deduplicates_by_phone) проверяет service-уровневый пред-чек
        (get_by_phone до save), не сам constraint-путь репозитория.
        Пред-чек — не атомарная защита (TOCTOU: два почти одновременных
        create_client с одним новым номером оба проходят пред-чек до того,
        как первый закоммитится) — на практике от гонки спасает именно
        то, что второй save() падает на constraint и возвращает False,
        а не бросает наружу."""
        from plugins.clients import ClientEntity

        first = ClientEntity(id=0, full_name="Первый", phone="+79995554433")
        assert repository.save(first) is True

        # ClientEntity.__post_init__ normalizes the phone (see test_get_by_phone
        # above) — save(second) must collide on the SAME normalized value.
        second = ClientEntity(id=0, full_name="Второй", phone="+79995554433")
        assert second.phone == first.phone
        assert repository.save(second) is False

        # Оригинальная запись не пострадала.
        original = repository.get_by_phone(first.phone)
        assert original is not None
        assert original.full_name == "Первый"

    def test_hard_delete_removes_the_client(self, repository):
        from plugins.clients import ClientEntity

        client = ClientEntity(id=0, full_name="Удаляемый", phone="+79990000000")
        repository.save(client)
        assert repository.delete(client.id, hard=True) is True
        assert repository.get_by_id(client.id) is None

    def test_soft_delete_refuses_instead_of_silently_hard_deleting(self, repository):
        """Workflow-найденный баг: delete(hard=False) — предположительно
        безопасный путь по умолчанию (DeleteClientCommand.hard_delete
        default) — раньше тихо выполнял ПОЛНОЕ удаление (схема не
        поддерживает soft-delete), каскадно стирая всю историю ремонтов
        клиента. Теперь явно отказывает вместо того, чтобы сделать
        противоположное запрошенному."""
        from core.logging.exceptions import BusinessRuleViolation
        from plugins.clients import ClientEntity

        client = ClientEntity(id=0, full_name="Не должен удалиться", phone="+79990000001")
        repository.save(client)

        with pytest.raises(BusinessRuleViolation):
            repository.delete(client.id, hard=False)

        assert repository.get_by_id(client.id) is not None

    def test_delete_default_argument_also_refuses(self, repository):
        """hard по умолчанию False — вызов без аргумента не должен молча
        удалять клиента."""
        from core.logging.exceptions import BusinessRuleViolation
        from plugins.clients import ClientEntity

        client = ClientEntity(id=0, full_name="Дефолтный вызов", phone="+79990000002")
        repository.save(client)

        with pytest.raises(BusinessRuleViolation):
            repository.delete(client.id)

        assert repository.get_by_id(client.id) is not None

    def test_search(self, repository):
        from plugins.clients import ClientEntity

        repository.save(ClientEntity(id=0, full_name="Сидор Сидоров", phone="+79991112233"))
        results = repository.search("Сидоров")
        assert any(c.full_name == "Сидор Сидоров" for c in results)


class TestClientService:
    """Бизнес-логика (валидация/нормализация телефона и email) — использует
    utils.formatters/utils.validators, единственный живой SSOT, см.
    AUDIT_REPORT_v21.md о консолидации validators/formatters."""

    def test_create_client_normalizes_phone(self, service):
        client = service.create_client(
            CreateClientCommand(full_name="Иван Иванов", phone="89991234567")
        )
        assert client is not None
        assert client.phone.startswith("+7")

    def test_create_client_rejects_invalid_phone(self, service):
        client = service.create_client(
            CreateClientCommand(full_name="Плохой Телефон", phone="123")
        )
        assert client is None

    def test_create_client_deduplicates_by_phone(self, service):
        first = service.create_client(
            CreateClientCommand(full_name="Иван Иванов", phone="+79991234567")
        )
        second = service.create_client(
            CreateClientCommand(full_name="Иван Иванов (другое имя)", phone="+79991234567")
        )
        assert first.id == second.id

    def test_find_by_phone(self, service):
        created = service.create_client(
            CreateClientCommand(full_name="Найдёныш", phone="+79995556677")
        )
        found = service.find_by_phone(GetClientByPhoneQuery(phone="+79995556677"))
        assert found is not None
        assert found.id == created.id

    def test_update_client_rejects_invalid_email(self, service):
        created = service.create_client(
            CreateClientCommand(full_name="Тест Email", phone="+79998887766")
        )
        ok = service.update_client(
            UpdateClientCommand(client_id=created.id, email="not-an-email")
        )
        assert ok is False

    def test_update_client_is_active_is_a_logged_no_op_not_a_crash(self, service, caplog):
        """Client не имеет колонки is_active в схеме (в отличие от
        Employee) — раньше UpdateClientCommand.is_active тихо менял только
        in-memory ClientEntity и терялся на save() без единого следа.
        Теперь как минимум логируется явное предупреждение, а сам update
        остальных полей продолжает работать."""
        created = service.create_client(
            CreateClientCommand(full_name="Тест is_active", phone="+79998887799")
        )
        ok = service.update_client(
            UpdateClientCommand(client_id=created.id, notes="реальное поле", is_active=False)
        )
        assert ok is True
        assert "is_active" in caplog.text

    def test_delete_client_refuses_by_default_and_preserves_the_client(self, service):
        """Workflow-найденный баг: DeleteClientCommand.hard_delete=False
        (умолчание, задокументированное как 'safe/soft') раньше приводило к
        ПОЛНОМУ каскадному удалению. Сервисный уровень должен вернуть False
        и оставить клиента на месте, а не молча всё стереть."""
        created = service.create_client(
            CreateClientCommand(full_name="Не должен удалиться", phone="+79998887711")
        )
        ok = service.delete_client(DeleteClientCommand(client_id=created.id))
        assert ok is False
        assert service.get_client(GetClientByIdQuery(client_id=created.id)) is not None

    def test_delete_client_with_explicit_hard_true_actually_deletes(self, service):
        created = service.create_client(
            CreateClientCommand(full_name="Осознанное удаление", phone="+79998887722")
        )
        ok = service.delete_client(
            DeleteClientCommand(client_id=created.id, hard_delete=True)
        )
        assert ok is True
        assert service.get_client(GetClientByIdQuery(client_id=created.id)) is None


class TestPluginDiscoveryIntegration:
    """Сквозной путь: core.initialize() -> discover('plugins', context=core) ->
    register_plugin() -> load() -> on_initialize() -> register_module('clients', ...).
    Это ровно то, что делает bootstrap.py при старте приложения."""

    def test_discover_loads_clients_plugin_and_registers_module(self, engine):
        reset_core()
        core = get_core()
        core.initialize()
        try:
            core.register_service(IClientRepository, SqlAlchemyClientRepository(engine))

            loaded = core.services.plugin_manager.discover("plugins", context=core)

            assert "clients" in loaded
            api = core.get_module_api("clients")
            assert isinstance(api, ClientService)

            # API реально работает через ядро — модуль не просто зарегистрирован,
            # а функционален.
            client = core.call_module_method(
                "clients",
                "create_client",
                CreateClientCommand(full_name="Через Ядро", phone="+79991112200"),
            )
            assert client is not None
            assert client.full_name == "Через Ядро"
        finally:
            reset_core()

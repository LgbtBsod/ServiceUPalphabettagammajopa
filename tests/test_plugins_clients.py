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

    def test_delete(self, repository):
        from plugins.clients import ClientEntity

        client = ClientEntity(id=0, full_name="Удаляемый", phone="+79990000000")
        repository.save(client)
        assert repository.delete(client.id) is True
        assert repository.get_by_id(client.id) is None

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

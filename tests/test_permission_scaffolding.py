#!/usr/bin/env python3

"""Тесты для core.base.PermissionObject/PermissionAwareMixin — декларативный
каркас для будущей ролевой модели (см. TODO_RBAC_ROADMAP.md). Проверяет
только сам каркас (декларация видна на BaseService, дефолт None), НЕ
enforcement — его пока нет намеренно.

BaseRepository намеренно БЕЗ PermissionAwareMixin (пост-фичный аудит: ни один
репозиторий полномочия не объявляет, а дорожная карта нацелена только на
Service-слой) — репозиторий отвечает за персистентность, а не за доступ."""

import pytest

from core.base import (
    BaseRepository,
    BaseService,
    LoggableMixin,
    PermissionAwareMixin,
    PermissionObject,
)
from core.logging.exceptions import PermissionError as PermissionDeniedError
from plugins.clients import ClientService
from plugins.employees import EmployeeService


class TestPermissionObject:
    def test_stores_declared_fields(self):
        po = PermissionObject(name="DEVICES", operations=("create", "read"), table="devices")
        assert po.name == "DEVICES"
        assert po.operations == ("create", "read")
        assert po.table == "devices"

    def test_table_defaults_to_none(self):
        po = PermissionObject(name="X", operations=("read",))
        assert po.table is None


class TestPermissionAwareMixinDefault:
    def test_default_is_none_unrestricted(self):
        class PlainService(PermissionAwareMixin):
            pass

        assert PlainService().permission_object is None

    def test_base_service_has_permission_object_attribute(self):
        assert hasattr(BaseService, "permission_object")

    def test_base_repository_has_no_permission_object_attribute(self):
        assert not hasattr(BaseRepository, "permission_object")


class TestRealServiceDeclarations:
    """ClientService/EmployeeService — уже объявленные примеры каркаса."""

    def test_client_service_declares_permission_object(self):
        po = ClientService.permission_object
        assert po is not None
        assert po.name == "CLIENTS"
        assert po.table == "clients"

    def test_employee_service_declares_permission_object(self):
        po = EmployeeService.permission_object
        assert po is not None
        assert po.name == "EMPLOYEES"
        assert "manage_roles" in po.operations


class TestCheckPermission:
    """check_permission()/require_permission() — точка интеграции для
    будущего enforcement (см. core/base.py), безопасно default-allow, пока
    вызывающий код явно не передаст checker."""

    def test_true_when_no_permission_object_declared(self):
        class PlainService(PermissionAwareMixin):
            pass

        assert PlainService().check_permission("delete") is True

    def test_true_when_no_checker_supplied(self):
        class GuardedService(PermissionAwareMixin):
            permission_object = PermissionObject(name="X", operations=("read", "delete"))

        assert GuardedService().check_permission("delete") is True

    def test_delegates_to_checker_when_supplied(self):
        class GuardedService(PermissionAwareMixin):
            permission_object = PermissionObject(name="X", operations=("read", "delete"))

        svc = GuardedService()
        assert svc.check_permission("delete", checker=lambda op: False) is False
        assert svc.check_permission("delete", checker=lambda op: True) is True

    def test_unknown_operation_raises_value_error(self):
        class GuardedService(PermissionAwareMixin):
            permission_object = PermissionObject(name="X", operations=("read",))

        with pytest.raises(ValueError):
            GuardedService().check_permission("delete")

    def test_require_permission_raises_permission_denied_error(self):
        class GuardedService(PermissionAwareMixin):
            permission_object = PermissionObject(name="X", operations=("delete",))

        svc = GuardedService()
        with pytest.raises(PermissionDeniedError):
            svc.require_permission("delete", checker=lambda op: False)

    def test_require_permission_passes_silently_when_allowed(self):
        class GuardedService(PermissionAwareMixin):
            permission_object = PermissionObject(name="X", operations=("delete",))

        GuardedService().require_permission("delete", checker=lambda op: True)  # не бросает


class TestMsgHelper:
    """LoggableMixin.msg() — форматирует code-based сообщение (utils.messages.Msg.*)
    и логирует одним вызовом."""

    def test_formats_and_returns_text(self):
        class Loggable(LoggableMixin):
            pass

        text = Loggable().msg("Логин занят: {login}", level="warning", login="ivanov")
        assert text == "Логин занят: ivanov"

    def test_works_without_placeholders(self):
        class Loggable(LoggableMixin):
            pass

        assert Loggable().msg("Просто текст") == "Просто текст"

    def test_falls_back_to_info_on_unknown_level(self):
        class Loggable(LoggableMixin):
            pass

        # Не должно бросить — getattr(self.logger, "not_a_level", None) or self.logger.info
        assert Loggable().msg("x", level="not_a_level") == "x"

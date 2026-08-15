#!/usr/bin/env python3

"""Менеджер настроек приложения"""

import copy
import json
import logging
import os
from typing import Any

from config import CONFIG_PATH
from utils.constants import DEFAULT_SETTINGS

logger = logging.getLogger(__name__)


class SettingsManager:
    """Класс для управления настройками приложения"""

    def __init__(self, config_file: str | None = None):
        self.config_file = config_file or CONFIG_PATH
        self.settings = self.load_settings()

    def load_settings(self) -> dict:
        """Загрузка настроек из файла"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, encoding="utf-8") as f:
                    loaded = json.load(f)
                    return self.merge_settings(copy.deepcopy(DEFAULT_SETTINGS), loaded)
        except Exception as e:
            logger.error(f"Ошибка загрузки настроек: {e}", exc_info=True)

        return copy.deepcopy(DEFAULT_SETTINGS)

    def merge_settings(self, default: dict, loaded: dict) -> dict:
        """Рекурсивное объединение настроек"""
        for key, value in loaded.items():
            if key in default:
                if isinstance(value, dict) and isinstance(default[key], dict):
                    default[key] = self.merge_settings(default[key], value)
                else:
                    default[key] = value
        return default

    def save_settings(self) -> None:
        """Сохранение настроек в файл"""
        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Ошибка сохранения настроек: {e}", exc_info=True)

    def get(self, key: str, default: Any = None) -> Any:
        """Получение значения настройки"""
        keys = key.split(".")
        value = self.settings
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k, default)
            else:
                return default
        return value

    def set(self, key: str, value: Any) -> None:
        """Установка значения настройки"""
        keys = key.split(".")
        target = self.settings
        for k in keys[:-1]:
            if k not in target:
                target[k] = {}
            target = target[k]
        target[keys[-1]] = value
        self.save_settings()

    def reset_to_defaults(self) -> None:
        """Сброс к настройкам по умолчанию"""
        self.settings = copy.deepcopy(DEFAULT_SETTINGS)
        self.save_settings()

#!/usr/bin/env python3

"""PWA-пакет: мобильная версия приложения (Flask-сервер + фронтенд)."""

from pwa.server import PWAServerManager, get_local_ip

__all__ = ["PWAServerManager", "get_local_ip"]

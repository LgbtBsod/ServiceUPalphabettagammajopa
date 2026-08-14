"""
Точка входа для модуля дашбордов (Composition Root).
Собирает все зависимости вместе согласно принципам DI.
Здесь определяется, какая реализация будет использоваться.

Принципы:
- SSOT: Все зависимости собираются в одном месте.
- DIP: Высокоуровневые модули не зависят от низкоуровневых.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Infrastructure
from infrastructure.dashboard_repository import SQLAlchemyDashboardRepository

# Application
from application.dashboard_adapter import DashboardAdapter
from application.dashboard_service import DashboardService

# Presentation
from presentation.dashboard_controller import DashboardController
from presentation.web_controller import run_web_server


def create_dashboard_service(db_url: str = "sqlite:///./dashboard.db"):
    """
    Фабрика сервиса дашбордов. Настраивает все зависимости (DI Container).
    Это единственное место, где знают о конкретных реализациях классов.
    """
    # 1. Инфраструктура: БД сессионная фабрика
    engine = create_engine(db_url, echo=False)
    session_factory = sessionmaker(bind=engine)
    
    # 2. Репозиторий (Инфраструктура -> Application)
    repository = SQLAlchemyDashboardRepository(session_factory)
    
    # 3. Адаптер (Application) - трансформирует данные из репозитория в DTO
    adapter = DashboardAdapter(repository)
    
    # 4. Сервис (Application) - бизнес-логика и оркестрация
    service = DashboardService(adapter)
    
    return service


def run_gui_app():
    """Запуск Desktop GUI версии приложения."""
    service = create_dashboard_service()
    controller = DashboardController(service)
    controller.run()


def run_web_app(port: int = 8000):
    """Запуск Web API версии приложения (REST JSON)."""
    service = create_dashboard_service()
    run_web_server(service, port=port)


if __name__ == "__main__":
    import sys
    
    print("=" * 60)
    print("Dashboard Module - Выбор режима запуска")
    print("=" * 60)
    print("1. GUI (Tkinter) - по умолчанию")
    print("2. Web API (JSON) - запуск с флагом 'web'")
    print("=" * 60)
    
    if len(sys.argv) > 1 and sys.argv[1] == "web":
        print("\n[INFO] Запуск в режиме Web API...")
        print(f"[INFO] Откройте браузер: http://localhost:8000/api/dashboard")
        run_web_app()
    else:
        print("\n[INFO] Запуск в режиме Desktop GUI...")
        run_gui_app()

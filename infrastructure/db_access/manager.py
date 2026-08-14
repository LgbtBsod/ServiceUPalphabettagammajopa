"""
Модуль доступа к данным (Data Access Layer)

ЕДИНСТВЕННЫЙ способ работы с БД в приложении.
Реализует паттерны: Repository, Unit of Work, CQRS Query Handler.
Все SQL-запросы инкапсулированы внутри этого модуля.
"""

from typing import Optional, TypeVar, Generic, List, Any, Dict, Union
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
import threading
from contextlib import contextmanager
import logging

from sqlalchemy import create_engine, text, event
from sqlalchemy.orm import sessionmaker, Session, scoped_session, declarative_base
from sqlalchemy.pool import StaticPool, QueuePool
from sqlalchemy.exc import SQLAlchemyError

from core.base import LoggableMixin, ExceptionHandlingMixin
from config.settings import get_settings

logger = logging.getLogger(__name__)

T = TypeVar('T')
Base = declarative_base()


@dataclass
class DatabaseConfig:
    """Конфигурация подключения к БД."""
    db_type: str  # sqlite, postgresql, mysql
    db_path: Optional[str] = None  # Для SQLite
    host: Optional[str] = None  # Для PostgreSQL/MySQL
    port: Optional[int] = None
    database: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    pool_size: int = 5
    max_overflow: int = 10
    echo: bool = False
    
    @classmethod
    def from_settings(cls) -> 'DatabaseConfig':
        """Создаёт конфигурацию из настроек приложения."""
        settings = get_settings()
        
        # Парсим DATABASE_URL из настроек
        db_url = settings.database_url
        
        if db_url.startswith('sqlite'):
            return cls(
                db_type='sqlite',
                db_path=db_url.replace('sqlite:///', ''),
                echo=settings.debug,
            )
        elif db_url.startswith('postgresql'):
            # postgresql://user:pass@host:port/dbname
            parts = db_url.replace('postgresql://', '').split('@')
            creds = parts[0].split(':')
            host_parts = parts[1].split(':')
            
            return cls(
                db_type='postgresql',
                host=host_parts[0],
                port=int(host_parts[1]) if len(host_parts) > 1 else 5432,
                database=host_parts[2] if len(host_parts) > 2 else '',
                username=creds[0],
                password=creds[1] if len(creds) > 1 else '',
                pool_size=settings.db_pool_size,
                max_overflow=settings.db_max_overflow,
                echo=settings.debug,
            )
        elif db_url.startswith('mysql'):
            # mysql://user:pass@host:port/dbname
            parts = db_url.replace('mysql://', '').split('@')
            creds = parts[0].split(':')
            host_parts = parts[1].split(':')
            
            return cls(
                db_type='mysql',
                host=host_parts[0],
                port=int(host_parts[1]) if len(host_parts) > 1 else 3306,
                database=host_parts[2] if len(host_parts) > 2 else '',
                username=creds[0],
                password=creds[1] if len(creds) > 1 else '',
                pool_size=settings.db_pool_size,
                max_overflow=settings.db_max_overflow,
                echo=settings.debug,
            )
        else:
            raise ValueError(f"Unsupported database type: {db_url}")
    
    def get_connection_string(self) -> str:
        """Возвращает строку подключения."""
        if self.db_type == 'sqlite':
            return f"sqlite:///{self.db_path}"
        elif self.db_type == 'postgresql':
            return f"postgresql://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"
        elif self.db_type == 'mysql':
            return f"mysql+pymysql://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"
        else:
            raise ValueError(f"Unsupported database type: {self.db_type}")


class Command(ABC):
    """Базовый класс для команд (изменение данных)."""
    
    @abstractmethod
    def execute(self, session: Session) -> Any:
        """Выполняет команду."""
        pass


class Query(ABC, Generic[T]):
    """Базовый класс для запросов (чтение данных)."""
    
    @abstractmethod
    def execute(self, session: Session) -> T:
        """Выполняет запрос."""
        pass


@dataclass
class QueryResult(Generic[T]):
    """Результат выполнения запроса."""
    data: Optional[T] = None
    error: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    success: bool = True
    
    @classmethod
    def ok(cls, data: T) -> 'QueryResult[T]':
        return cls(data=data, success=True)
    
    @classmethod
    def fail(cls, error: str) -> 'QueryResult[T]':
        return cls(error=error, success=False)


class DataAccessManager(LoggableMixin, ExceptionHandlingMixin):
    """
    Единый интерфейс для доступа к базе данных.
    
    Реализует:
    - Singleton паттерн для управления соединениями
    - CQRS разделение (Command/Query)
    - Unit of Work через контекстные менеджеры
    - Пул соединений
    - Автоматическую миграцию схем
    """
    
    _instance: Optional['DataAccessManager'] = None
    _lock = threading.Lock()
    
    def __new__(cls) -> 'DataAccessManager':
        """Singleton instantiation."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        super().__init__()
        self.config = DatabaseConfig.from_settings()
        self.engine = None
        self.SessionLocal: Optional[sessionmaker] = None
        self._scoped_session: Optional[scoped_session] = None
        self._initialized = True
        
        self.logger.info(f"DataAccessManager initialized with {self.config.db_type} database")
    
    def initialize(self) -> None:
        """Инициализирует подключение к БД."""
        try:
            connection_string = self.config.get_connection_string()
            
            # Настраиваем пул соединений в зависимости от типа БД
            if self.config.db_type == 'sqlite':
                # SQLite использует StaticPool для потокобезопасности
                self.engine = create_engine(
                    connection_string,
                    connect_args={"check_same_thread": False},
                    poolclass=StaticPool,
                    echo=self.config.echo,
                    future=True,
                )
                
                # Включаем WAL mode для лучшей производительности
                @event.listens_for(self.engine, "connect")
                def set_sqlite_pragma(dbapi_connection, connection_record):
                    cursor = dbapi_connection.cursor()
                    cursor.execute("PRAGMA journal_mode=WAL")
                    cursor.execute("PRAGMA foreign_keys=ON")
                    cursor.close()
            else:
                # PostgreSQL/MySQL используют QueuePool
                self.engine = create_engine(
                    connection_string,
                    pool_size=self.config.pool_size,
                    max_overflow=self.config.max_overflow,
                    echo=self.config.echo,
                    future=True,
                )
            
            self.SessionLocal = sessionmaker(
                bind=self.engine,
                autocommit=False,
                autoflush=False,
                expire_on_commit=False,
            )
            
            self._scoped_session = scoped_session(self.SessionLocal)
            
            self.logger.info("Database connection established successfully")
            
        except SQLAlchemyError as e:
            self.logger.error(f"Failed to initialize database: {e}")
            raise
    
    def get_session(self) -> Session:
        """Получает сессию БД."""
        if not self._scoped_session:
            raise RuntimeError("DataAccessManager not initialized. Call initialize() first.")
        return self._scoped_session()
    
    @contextmanager
    def unit_of_work(self):
        """
        Контекстный менеджер Unit of Work.
        
        Пример использования:
            with db_access.unit_of_work() as uow:
                repo = ClientRepository(uow.session)
                client = repo.save(data)
                # commit вызывается автоматически при выходе из контекста
        """
        session = self.get_session()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            self.logger.error(f"Unit of Work failed: {e}")
            raise
        finally:
            session.close()
    
    def execute_command(self, command: Command) -> Any:
        """Выполняет команду (изменение данных)."""
        with self.unit_of_work() as session:
            return command.execute(session)
    
    def execute_query(self, query: Query[T]) -> QueryResult[T]:
        """Выполняет запрос (чтение данных)."""
        try:
            session = self.get_session()
            result = query.execute(session)
            return QueryResult.ok(result)
        except Exception as e:
            self.logger.error(f"Query execution failed: {e}")
            return QueryResult.fail(str(e))
        finally:
            session.close()
    
    def execute_raw_sql(self, sql: str, params: Optional[Dict] = None) -> List[Dict]:
        """
        Выполняет raw SQL запрос (только для чтения!).
        
        Внимание: Используйте только для сложных аналитических запросов,
        которые невозможно реализовать через SQLAlchemy ORM.
        """
        try:
            session = self.get_session()
            result = session.execute(text(sql), params or {})
            columns = result.keys()
            rows = [dict(zip(columns, row)) for row in result.fetchall()]
            return rows
        except SQLAlchemyError as e:
            self.logger.error(f"Raw SQL execution failed: {e}")
            raise
        finally:
            session.close()
    
    def create_tables(self, base: Any = Base) -> None:
        """Создаёт все таблицы в БД."""
        if not self.engine:
            raise RuntimeError("Database engine not initialized")
        
        base.metadata.create_all(bind=self.engine)
        self.logger.info("Database tables created successfully")
    
    def drop_tables(self, base: Any = Base) -> None:
        """Удаляет все таблицы из БД."""
        if not self.engine:
            raise RuntimeError("Database engine not initialized")
        
        base.metadata.drop_all(bind=self.engine)
        self.logger.info("Database tables dropped successfully")
    
    def health_check(self) -> bool:
        """Проверяет здоровье подключения к БД."""
        try:
            session = self.get_session()
            session.execute(text("SELECT 1"))
            return True
        except Exception as e:
            self.logger.error(f"Database health check failed: {e}")
            return False
        finally:
            session.close()
    
    def close(self) -> None:
        """Закрывает подключение к БД."""
        if self._scoped_session:
            self._scoped_session.remove()
        if self.engine:
            self.engine.dispose()
        self.logger.info("Database connection closed")


# Глобальный экземпляр (Singleton)
_db_access: Optional[DataAccessManager] = None


def get_db_access() -> DataAccessManager:
    """Получает глобальный экземпляр DBAccess."""
    global _db_access
    if _db_access is None:
        _db_access = DataAccessManager()
        _db_access.initialize()
    return _db_access


def initialize_db_access() -> DataAccessManager:
    """Инициализирует и возвращает глобальный экземпляр DBAccess."""
    db_access = get_db_access()
    if not db_access.engine:
        db_access.initialize()
    return db_access


def reset_db_access() -> None:
    """Сбрасывает глобальный экземпляр (для тестов)."""
    global _db_access
    if _db_access:
        _db_access.close()
    _db_access = None


# Удобные функции для быстрого доступа
def db_session() -> Session:
    """Получает сессию БД."""
    return get_db_access().get_session()


@contextmanager
def db_unit_of_work():
    """Контекстный менеджер Unit of Work."""
    with get_db_access().unit_of_work() as session:
        yield session


def db_execute_command(command: Command) -> Any:
    """Выполняет команду."""
    return get_db_access().execute_command(command)


def db_execute_query(query: Query[T]) -> QueryResult[T]:
    """Выполняет запрос."""
    return get_db_access().execute_query(query)


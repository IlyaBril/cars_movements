from fastapi import Depends
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.pool import StaticPool
from app.config import DB_FILE, POSTGRES_DATABASE_URL
from sqlalchemy.orm import Session, sessionmaker
from typing import Annotated
from .models import Base, ZonesConfig


SQLITE_DATABASE_URL = f"sqlite:///{DB_FILE}"

sqlite_engine = create_engine(
    SQLITE_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)

postgres_engine = create_engine(
    POSTGRES_DATABASE_URL,
    echo=False  # Установите True для отладки
)

# Создаем сессии
SQLiteSession = scoped_session(sessionmaker(bind=sqlite_engine))
PostgresSession = scoped_session(sessionmaker(bind=postgres_engine))


def init_sqlite_database():
    """Инициализация SQLite базы данных"""
    Base.metadata.create_all(bind=sqlite_engine)
    
    # Добавляем начальные данные, если таблица пуста
    session = SQLiteSession()
    try:
        if session.query(ZonesConfig).count() == 0:
            from app.config import DEFAULT_ZONES, DEFAULT_ZONES_REP
            import json
            
            config = ZonesConfig(
                zones=json.dumps(DEFAULT_ZONES, ensure_ascii=False),
                zones_rep=json.dumps(DEFAULT_ZONES_REP, ensure_ascii=False)
            )
            session.add(config)
            session.commit()
    finally:
        session.close()


def init_postgres_database():
    """Инициализация PostgreSQL базы данных (создание таблиц)"""
    Base.metadata.create_all(bind=postgres_engine)


def get_sqlite_session():
    """Создает сессию БД и гарантирует её закрытие после использования."""
    session = SQLiteSession()
    try:
        yield session
    finally:
        session.close()
			
			
def get_psql_session():
    """Создает сессию БД и гарантирует её закрытие после использования."""
    with PostgresSession() as session:
        try:
            yield session
        finally:
            pass


def close_db_connections():
    """Закрывает все соединения в пуле при остановке приложения."""
    sqlite_engine.dispose()
    postgres_engine.dispose()

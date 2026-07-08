from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.pool import StaticPool
from app.config import DB_FILE
from app.models import Base


# SQLite база данных (для групп и конфигурации)
SQLITE_DATABASE_URL = f"sqlite:///{DB_FILE}"

# PostgreSQL база данных (для movements, только чтение)
# Замените на свои параметры подключения
POSTGRES_DATABASE_URL = "postgresql://user:password@localhost/dbname"

# Создаем движки
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

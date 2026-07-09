from fastapi import FastAPI, Depends
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager

from .db.database import init_sqlite_database, init_postgres_database
from .db.repository import MovementRepository, GroupRepository
from .db.models import Base
from .config import STATIC_DIR
from .routes import analysis, admin, admin_groups


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Инициализация баз данных при старте
    init_sqlite_database()
    init_postgres_database()
    yield
    # Очистка при завершении
    pass

app = FastAPI(lifespan=lifespan, title="movements")
# Инициализация базы данных


# Монтирование статических файлов
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Подключение маршрутов
app.include_router(analysis.router)
app.include_router(admin.router)
app.include_router(admin_groups.router)

@app.get("/health")
async def health_check():
    return {"status": "ok"}

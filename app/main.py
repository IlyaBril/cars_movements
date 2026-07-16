from fastapi import FastAPI, Depends
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager

from .db.database import init_sqlite_database, init_postgres_database, close_db_connections
from .db.repository import MovementRepository, GroupRepository
from .db.models import Base
from .config import STATIC_DIR
from .routes import analysis, admin, admin_groups
from .routes import analysis, admin, admin_groups, sankey


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Инициализация баз данных при старте
    init_sqlite_database()
    #init_postgres_database()
    yield
    # Очистка при завершении
    close_db_connections()

app = FastAPI(lifespan=lifespan, title="movements")

# Монтирование статических файлов
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Подключение маршрутов
app.include_router(analysis.router)
app.include_router(admin.router)
app.include_router(admin_groups.router)
app.include_router(sankey.router) 

@app.get("/health")
async def health_check():
    return {"status": "ok"}

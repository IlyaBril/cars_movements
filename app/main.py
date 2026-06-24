from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from .config import STATIC_DIR
from .database import init_database
from .routes import analysis, admin

# Инициализация базы данных
init_database()

app = FastAPI(title="Анализ движения автомобилей")

# Монтирование статических файлов
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Подключение маршрутов
app.include_router(analysis.router)
app.include_router(admin.router)

@app.get("/health")
async def health_check():
    return {"status": "ok"}
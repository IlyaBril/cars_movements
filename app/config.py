from pathlib import Path
from typing import List
import json

# Пути
BASE_DIR = Path(__file__).parent.parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

# Настройки PostgreSQL
POSTGRES_HOST = "localhost"
POSTGRES_PORT = 5432
POSTGRES_DB = "database"
POSTGRES_USER = "user"
POSTGRES_PASSWORD = "password"

# Настройки подключения
POSTGRES_DATABASE_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"

# Настройки подключения sqlite
DB_FILE = BASE_DIR / "zones.db"

# Значения по умолчанию
REQUIRED_COLUMNS = ['Дата', 'Заказ', 'Точка регистрации']

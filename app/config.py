from pathlib import Path
from typing import List
import json

# Пути
BASE_DIR = Path(__file__).parent.parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

# Настройки PostgreSQL (замените на свои)
POSTGRES_HOST = "localhost"
POSTGRES_PORT = 5432
POSTGRES_DB = "your_database"
POSTGRES_USER = "your_user"
POSTGRES_PASSWORD = "your_password"

# Настройки подключения
POSTGRES_DATABASE_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
DB_FILE = BASE_DIR / "zones.db"

# Значения по умолчанию
DEFAULT_ZONES = [
    'M440. GRT',
    'ТиД',
    'M444. Валидация ретуши',
    'M471. Отказ по качеству',
    'M445. Зона выборочного котроля',
    'M450. Контроль электрики',
    'M470. Передача на СГП (BLAN)',
]

DEFAULT_ZONES_REP = [
    'M401. Ретушь электрики',
    'M403. Ретушь Сварки',
    'M404. Ретушь сборки',
    'M405. Ретушь окраски',
    'M414. Тяжелая ретушь Сборки',
    'M407. Ретушь замена деталей',
]

REQUIRED_COLUMNS = ['Дата', 'Заказ', 'Точка регистрации']

MAIN_ZONE_GROUPS = {
    "ТиД": [
        'M401. Ретушь электрики',
        'M402. Ретушь Механика',
        'M403. Ретушь Сварки',
        'M404. Ретушь сборки',
        'M405. Ретушь окраски',
        'M406. Ретушь герметичности',
        'M407. Ретушь замена деталей',
        'M414. Тяжелая ретушь Сборки',
        'M415. Тяжелая ретушь электрики',
        'M416. Тяжелая ретушь сварки',
        'M417. Ретушь Шум',
        'M418. Тяжелая ретушь Окраски',

        ],

}

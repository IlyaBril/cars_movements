from pathlib import Path
from typing import List
import json

# Пути
BASE_DIR = Path(__file__).parent.parent
DB_FILE = BASE_DIR / "zones.db"
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

# Значения по умолчанию
DEFAULT_ZONES = [
    'M446. AVAL',
    'M444. Валидация ретуши',
    'M471. Отказ по качеству',
    'M445. Зона выборочного ко',
    'M450. Контроль электрики',
    'M470. Передача на СГП (BL',
    'M500. Приемка на СГП (MAD',
]

DEFAULT_ZONES_REP = [
    'M401. Ретушь электрики',
    'M403. Ретушь Сварки',
    'M404. Ретушь сборки',
    'M405. Ретушь окраски',
    'M414. Тяжелая ретушь Сбор',
    'M407. Ретушь замена детал',
]

REQUIRED_COLUMNS = ['Дата', 'Заказ', 'Точка регистрации']

MAIN_ZONE_GROUPS = {
    "ТиД": [
        'M401. Ретушь электрики',
        'M403. Ретушь Сварки',
        'M404. Ретушь сборки',
        'M405. Ретушь окраски',
        'M414. Тяжелая ретушь Сбор',
        'M407. Ретушь замена детал',
        ],

}
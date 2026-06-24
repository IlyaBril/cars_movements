import sqlite3
import json
from pathlib import Path
from typing import List, Tuple

# Путь к файлу базы данных
DB_FILE = "zones.db"

CONFIG_FILE = "zones_config.json"

def load_zones_config():
    if Path(CONFIG_FILE).exists():
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
            return config["zones"], config["zones_rep"]
    else:
        # Значения по умолчанию
        return [], []


def init_database() -> None:
    """
    Инициализация базы данных: создание таблицы и добавление начальных данных,
    если таблица пуста.
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Создание таблицы, если не существует
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS zones_config (
            id INTEGER PRIMARY KEY,
            zones TEXT NOT NULL,
            zones_rep TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Добавление начальных данных, если таблица пуста
    cursor.execute("SELECT COUNT(*) FROM zones_config")
    if cursor.fetchone()[0] == 0:

        # Значения по умолчанию из файла zones_config.json
        default_zones, default_zones_rep = load_zones_config()
        
        cursor.execute('''
            INSERT INTO zones_config (zones, zones_rep)
            VALUES (?, ?)
        ''', (
            json.dumps(default_zones, ensure_ascii=False),
            json.dumps(default_zones_rep, ensure_ascii=False)
        ))

    conn.commit()
    conn.close()


def load_zones_from_db() -> Tuple[List[str], List[str]]:
    """
    Загрузка зон из базы данных.

    Возвращает:
        tuple: (список основных зон, список зон ретуши)
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT zones, zones_rep
        FROM zones_config
        ORDER BY id DESC
        LIMIT 1
    """)
    row = cursor.fetchone()
    conn.close()
	print('ow ', row)

    if row:
        return json.loads(row[0]), json.loads(row[1])

    

def save_zones_to_db(zones_list: List[str], zones_rep_list: List[str]) -> None:
    """
    Сохранение зон в базу данных.

    Args:
        zones_list: список основных зон
        zones_rep_list: список зон ретуши
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE zones_config
        SET zones = ?, zones_rep = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = (SELECT MAX(id) FROM zones_config)
    """, (
        json.dumps(zones_list, ensure_ascii=False),
        json.dumps(zones_rep_list, ensure_ascii=False)
    ))

    conn.commit()
    conn.close()

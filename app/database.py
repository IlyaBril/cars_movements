import sqlite3
import json
from typing import List, Tuple
from pathlib import Path
from app.config import DB_FILE, DEFAULT_ZONES, DEFAULT_ZONES_REP

def init_database() -> None:
    """Инициализация базы данных"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS zones_config (
            id INTEGER PRIMARY KEY,
            zones TEXT NOT NULL,
            zones_rep TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Добавляем начальные данные, если таблица пуста
    cursor.execute("SELECT COUNT(*) FROM zones_config")
    if cursor.fetchone()[0] == 0:
        cursor.execute('''
            INSERT INTO zones_config (zones, zones_rep)
            VALUES (?, ?)
        ''', (
            json.dumps(DEFAULT_ZONES, ensure_ascii=False),
            json.dumps(DEFAULT_ZONES_REP, ensure_ascii=False)
        ))
    
    conn.commit()
    conn.close()

def load_zones_from_db() -> Tuple[List[str], List[str]]:
    """Загрузка зон из базы данных"""
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
    
    if row:
        return json.loads(row[0]), json.loads(row[1])
    return DEFAULT_ZONES.copy(), DEFAULT_ZONES_REP.copy()

def save_zones_to_db(zones_list: List[str], zones_rep_list: List[str]) -> None:
    """Сохранение зон в базу данных"""
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
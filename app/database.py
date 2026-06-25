import sqlite3
import pandas as pd
import json
from datetime import datetime
from typing import List, Tuple
from pathlib import Path
from app.config import DB_FILE, DEFAULT_ZONES, DEFAULT_ZONES_REP

def init_database() -> None:
    """Инициализация базы данных"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
	
	# Создаем таблицу для данных
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS movements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            Дата DATETIME,
            Заказ TEXT,
            "Точка регистрации" TEXT
        )
    ''')
	
	# Индексы для скорости
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_date ON movements(Дата)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_zone ON movements("Точка регистрации")')
	
	 # Таблица для отслеживания обновлений
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    
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
	
def load_excel_to_db(excel_path: str = "Движение.xlsx"):
    """Загрузка данных из Excel в SQLite"""
    try:
        print(f"📂 Загрузка данных из {excel_path}...")
        
        # Читаем Excel
        df = pd.read_excel(
            excel_path,
            sheet_name="Лист_1",
            usecols=['Дата', 'Заказ', 'Точка регистрации']
        )
        
        # Преобразуем дату
        df['Дата'] = pd.to_datetime(df['Дата'], format='%d.%m.%Y %H:%M:%S')
        
        # Подключаемся к БД
        conn = sqlite3.connect(DB_FILE)
        
        # Очищаем старые данные
        cursor = conn.cursor()
        cursor.execute('DELETE FROM movements')
        
        # Загружаем новые данные (batch insert для скорости)
        df.to_sql('movements', conn, if_exists='append', index=False, chunksize=10000)
        
        # Сохраняем информацию об обновлении
        cursor.execute('''
            INSERT OR REPLACE INTO metadata (key, value) 
            VALUES (?, ?)
        ''', ('last_update', datetime.now().isoformat()))
        
        cursor.execute('''
            INSERT OR REPLACE INTO metadata (key, value) 
            VALUES (?, ?)
        ''', ('rows_count', str(len(df))))
        
        conn.commit()
        conn.close()
        
        print(f"✅ Загружено {len(df)} записей в базу данных")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка загрузки: {e}")
        return False

def get_db_connection():
    """Получить соединение с БД"""
    return sqlite3.connect(DB_FILE)

def get_last_update():
    """Получить время последнего обновления"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT value FROM metadata WHERE key = ?', ('last_update',))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

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
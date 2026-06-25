"""Скрипт для загрузки данных из Excel в SQLite"""
from app.database import init_database, load_excel_to_db

if __name__ == "__main__":
    print("🚀 Инициализация базы данных...")
    init_database()
    
    print("📂 Загрузка данных из Excel...")
    success = load_excel_to_db()
    
    if success:
        print("✅ Данные успешно загружены!")
    else:
        print("❌ Ошибка при загрузке данных")
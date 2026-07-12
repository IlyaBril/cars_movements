"""Скрипт для загрузки данных из Excel в SQLite"""
from app.db.database import init_sqlite_database
from app.services.data_service import DataService

data_service = DataService()

if __name__ == "__main__":
    print("🚀 Инициализация базы данных...")
    init_sqlite_database()
    
    print("📂 Загрузка данных из Excel...")
    success = data_service.load_excel_to_db()
    
    if success:
        print("✅ Данные успешно загружены!")
    else:
        print("❌ Ошибка при загрузке данных")
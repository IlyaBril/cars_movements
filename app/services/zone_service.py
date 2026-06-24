from typing import List, Tuple
from app.database import load_zones_from_db, save_zones_to_db

class ZoneService:
    @staticmethod
    def get_zones() -> Tuple[List[str], List[str]]:
        """Получение списков зон"""
        return load_zones_from_db()
    
    @staticmethod
    def update_zones(zones: List[str], zones_rep: List[str]) -> None:
        """Обновление списков зон"""
        save_zones_to_db(zones, zones_rep)
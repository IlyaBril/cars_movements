from typing import List, Tuple
from app.database import load_zones_from_db, load_groups_from_db

class ZoneService:
    _zones: List[str] = []
    _zones_rep: List[str] = []
    
    @classmethod
    def get_zones(cls) -> Tuple[List[str], List[str]]:
        """Получить зоны из БД"""
        zones, zones_rep = load_zones_from_db()
        return zones, zones_rep
    
    @classmethod
    def update_zones(cls, zones: List[str], zones_rep: List[str]) -> None:
        """Обновить зоны в БД"""
        from app.database import save_zones_to_db
        save_zones_to_db(zones, zones_rep)
    
    @classmethod
    def get_groups(cls) -> dict:
        """Получить группы из БД"""
        return load_groups_from_db()
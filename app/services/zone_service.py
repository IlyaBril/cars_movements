from typing import List, Tuple
from app.db.repository import MovementRepository, GroupRepository

class ZoneService:
    def __init__(self, group_repository: GroupRepository):
        self._group_repo = group_repository
    
    @classmethod
    def get_zones(cls) -> Tuple[List[str], List[str]]:
        """Получить зоны из БД"""
        zones, zones_rep = self._group_repo.load_zones_from_db()
        return zones, zones_rep
    
    @classmethod
    def update_zones(cls, zones: List[str], zones_rep: List[str]) -> None:
        """Обновить зоны в БД"""
        self._group_repo.save_zones_to_db(zones, zones_rep)
    
    @classmethod
    def get_groups(cls) -> dict:
        """Получить группы из БД"""
        return self._group_repo.load_groups_from_db()

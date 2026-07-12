from typing import List, Tuple
from app.db.repository import MovementRepository, GroupRepository
from app.db.database import SQLiteSession, PostgresSession

class ZoneService:
    def __init__(self):
        self._sqlite_sesion = SQLiteSession
        self._psql_session = PostgresSession
        self._group_repo = GroupRepository(self._sqlite_sesion)
        self._movement_repo = MovementRepository(self._sqlite_sesion)
		
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self._sqlite_sesion.close()
        self._psql_session.close()
    
    def get_zones(self) -> Tuple[List[str], List[str]]:
        """Получить зоны из БД"""
        zones, zones_rep = self._group_repo.load_zones_from_db()
        return zones, zones_rep
    
    def update_zones(self, zones: List[str], zones_rep: List[str]) -> None:
        """Обновить зоны в БД"""
        self._group_repo.save_zones_to_db(zones, zones_rep)
    
    def get_groups(self) -> dict:
        """Получить группы из БД"""
        return self._group_repo.load_groups_from_db()
		
    def get_all_zones(self) -> dict:
        """Получить все зоны из БД movement"""
        return self._movement_repo.get_all_zones_from_db()

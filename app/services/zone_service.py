import json
from typing import List, Tuple, Optional, Dict
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
        print('Zone Srvice zones, zones_rep ', zones, zones_rep)
        return zones, zones_rep
    
    def update_zones(self, zones: List[str], zones_rep: List[str]) -> None:
        """Обновить зоны в БД"""
        self._group_repo.save_zones_to_db(zones, zones_rep)
    
    def get_groups(self,
        zone_names: Optional[List[str]] = None,
        ) -> Dict[str, List[str]]:
        """Получить группы из БД"""
        query = self._group_repo.load_groups_from_db(zone_names)
        groups = {}
        for group in query:
            groups[group.group_name] = json.loads(group.zones)
        return groups
		
    def get_all_zones(self)-> list:
        """Получить все зоны из БД movement"""
        all_zones = self._movement_repo.get_all_zones_from_db()
        return [zone[0] for zone in all_zones]

    def get_available_zones(self, editing_group: str = None) -> list:
        """Получение зон, которые еще не входят ни в одну группу"""
        all_zones = self.get_all_zones()
        groups = self.get_groups()
    
        # Собираем все занятые зоны
        used_zones = set()
        for zones in groups.values():
            used_zones.update(zones)
    
        # Определяем доступные зоны
        available_zones = [zone for zone in all_zones if zone not in used_zones]
    
        # Если редактируем группу - добавляем её зоны обратно в доступные
        if editing_group and editing_group in groups:
            editing_zones = groups[editing_group]
            # Объединяем доступные зоны с зонами редактируемой группы
            available_zones = sorted(set(available_zones) | set(editing_zones))
        else:
            available_zones = sorted(available_zones)
        return available_zones

    def save_group_to_db(self, group_name: str, zones: List[str]) -> bool:
        result = self._group_repo.save_group_to_db(
            group_name, zones
            )
        return result

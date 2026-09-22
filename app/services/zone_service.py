import json
import logging
from typing import List, Tuple, Optional, Dict
from app.db.repository import MovementRepository
from app.db.database import SQLiteSession

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class BaseZoneService:
    def __init__(self):
        self._sqlite_session = SQLiteSession
        self._movement_repo = MovementRepository(self._sqlite_session)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._sqlite_session.close()

    def get_all_zones(self) -> list:
        all_zones = self._movement_repo.get_all_zones_from_db()
        return [zone[0] for zone in all_zones]


class ZoneService(BaseZoneService):

    #Отчеты
    def get_dash_zones(self) -> Dict[str, List[str]]:
        """Словарь отчетов (groups) со списком (zones) для каждого отчета """
        query = self._movement_repo.get_dash_zones_repo()
        reports = {}
        for report in query:
            reports[report.name] = [
                zone.name for zone in report.report_zones
            ]
        logger.info(f'{__name__} dash zones {reports}')
        return reports

    def save_zone_report(self, group_name: str, zones_names: List[str]) -> bool:
        """Сохранение группы отчета"""
        
        #zones_names = [s.split("<br>")[0].strip() for s in zones]
        logger.info(f'\n group_name {group_name} '
                    f'zones names {zones_names}')
        
        result = self._movement_repo.save_zone_report_to_db(
            group_name, zones_names
            )
        return result  

    def delete_dash_group(self, group_name: str) -> bool:
        return self._movement_repo.delete_dash_group_from_db(group_name)

    #Группировка зон
    def get_groups(self,
        zone_names: Optional[List[str]] = None,
        ) -> Dict[str, List[str]]:
        """Получение групп зон."""
        query = self._movement_repo.load_groups_from_db(zone_names)
        groups = {}
        for group in query:
            groups[group.name] = [
                zone.name for zone in group.children]
        logger.info(f'get groups {groups}')
        return groups

    def get_available_zones(self, editing_group: str = None) -> list:
        """Получение зон, которые еще не входят ни в одну группу"""
        all_zones = self.get_all_zones()
        groups = self.get_groups()
    
        # Собираем все занятые зоны
        used_zones = set()
        for zones in groups.values():
            used_zones.update(zones)
    
        # Определяем доступные зоны
        available_zones = [
            zone for zone in all_zones if zone not in used_zones]
    
        # Если редактируем группу - добавляем её зоны обратно в доступные
        if editing_group and editing_group in groups:
            editing_zones = groups[editing_group]
            # Объединяем доступные зоны с зонами редактируемой группы
            available_zones = sorted(set(available_zones) | set(editing_zones))
        else:
            available_zones = sorted(available_zones)
        return available_zones

    def save_zones_group(self, group_name: str, zones: List[str]) -> bool:
        """Сохранение группы модели ZoneWithGroup"""
        
        result = self._movement_repo.save_zones_group_to_db(
            group_name, zones
            )
        return result

    def delete_group(self, group_name: str) -> bool:
        return self._movement_repo.delete_group_from_db(group_name)
    


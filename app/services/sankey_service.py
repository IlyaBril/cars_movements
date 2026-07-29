import pandas as pd
import json
from typing import List, Dict, Optional, Tuple
from collections import defaultdict
from datetime import datetime
from app.db.repository import MovementRepository, GroupRepository
from app.db.database import SQLiteSession, PostgresSession


class SankeyService:
    """Сервис для подготовки данных Sankey диаграммы"""
    
    def __init__(self):
        self._sqlite_sesion = SQLiteSession()
        self._psql_session = PostgresSession()
        self._group_repo = GroupRepository(self._sqlite_sesion)
        self._movement_repo = MovementRepository(self._sqlite_sesion)
		
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self._sqlite_sesion.close()
        self._psql_session.close()
    
    def prepare_sankey_data(
        self,
        df: pd.DataFrame,
        date: str,
        zones_config: List[str],
        zones_rep: List[str],
        groups_dict: Dict[str, List[str]],
        group_name: Optional[str] = None,
        zone_type: str = "main"
    ) -> Dict:
        """
        Подготовка данных для Sankey диаграммы
        
        Args:
            df: DataFrame с движениями
            date: Дата анализа
            zones_config: Список зон
            zones_rep: Список зон ретуши
            groups_dict: Словарь групп
            group_name: Имя группы (опционально)
            zone_type: Тип зон (main/rep)
        
        Returns:
            Dict с данными для Sankey диаграммы
        """
        # Фильтруем по дате
        df['Дата'] = pd.to_datetime(df['Дата']).dt.date
        target_date = pd.to_datetime(date).date()
        df_day = df[df['Дата'] == target_date].copy()
        
        if df_day.empty:
            return {
                "nodes": [],
                "links": [],
                "total_entries": 0,
                "total_exits": 0
            }
        
        # Выбираем зоны в зависимости от типа
        if zone_type == "main":
            all_zones = zones_config
        else:
            all_zones = zones_rep
        
        # Если указана группа, фильтруем зоны
        if group_name and group_name in groups_dict:
            group_zones = groups_dict[group_name]
            all_zones = [z for z in all_zones if z in group_zones]
        
        # Группируем по заказам
        order_zones = df_day.groupby('Заказ')['Точка_регистрации'].agg(list).reset_index()
        
        # Анализируем переходы между зонами
        transitions = defaultdict(int)
        zone_counts = defaultdict(int)
        
        for _, row in order_zones.iterrows():
            zones = [z for z in row['Точка_регистрации'] if z in all_zones]
            
            if len(zones) > 1:
                # Создаем переходы между последовательными зонами
                for i in range(len(zones) - 1):
                    from_zone = zones[i]
                    to_zone = zones[i + 1]
                    if from_zone != to_zone:  # Игнорируем переходы в ту же зону
                        transition_key = f"{from_zone}|{to_zone}"
                        transitions[transition_key] += 1
            
            # Считаем вхождения в зоны
            for zone in zones:
                zone_counts[zone] += 1
        
        # Создаем узлы (уникальные зоны)
        unique_zones = list(set(all_zones))
        nodes = [{"name": zone} for zone in unique_zones]
        
        # Создаем связи
        links = []
        for transition_key, value in transitions.items():
            from_zone, to_zone = transition_key.split('|')
            if from_zone in unique_zones and to_zone in unique_zones:
                links.append({
                    "source": from_zone,
                    "target": to_zone,
                    "value": value
                })
        
        # Сортируем связи по значению
        links.sort(key=lambda x: x['value'], reverse=True)
        
        # Рассчитываем общее количество входов и выходов
        total_entries = sum(1 for _, row in df_day.iterrows() 
                           if row['Точка_регистрации'] in all_zones)
        total_exits = sum(1 for _, row in df_day.iterrows() 
                         if row['Точка_регистрации'] in all_zones)
        
        return {
            "nodes": nodes,
            "links": links,
            "zone_counts": dict(zone_counts),
            "total_entries": total_entries,
            "total_exits": total_exits,
            "total_transitions": sum(transitions.values())
        }

    def get_allowed_zones(self, zone_type: str) -> list:
        """Получает список разрешенных зон в зависимости от типа"""
        zones, zones_rep = self._group_repo.load_zones_from_db()
        
    
        if zone_type == "rep":
            all_entities = zones_rep.copy()
        else:
            all_entities = zones.copy()
        return all_entities

    
    def get_zone_statistics(
        self,
        df: pd.DataFrame,
        date: str,
        zones: List[str]
    ) -> Dict[str, Dict]:
        """
        Получение статистики по зонам
        
        Returns:
            Словарь с количеством входов/выходов для каждой зоны
        """
        df['Дата'] = pd.to_datetime(df['Дата']).dt.date
        target_date = pd.to_datetime(date).date()
        df_day = df[df['Дата'] == target_date].copy()
        
        stats = {}
        for zone in zones:
            zone_data = df_day[df_day['Точка_регистрации'] == zone]
            stats[zone] = {
                "entries": len(zone_data),
                "exits": len(zone_data),
                "orders": zone_data['Заказ'].nunique()
            }
        
        return stats

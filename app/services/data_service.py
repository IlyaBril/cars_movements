import json
import pandas as pd
import logging
from fastapi import Depends
from datetime import datetime, date
from typing import List, Tuple, Dict, Annotated
from app.db.models import ZoneStats
from app.db.repository import MovementRepository, GroupRepository
from app.db.database import SQLiteSession, PostgresSession
from app.db.schemas import MovementSchema
from app.services.zone_service import ZoneService
from sqlalchemy.orm import Session


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

logger.debug("start")

class DataService:
    """ Вся логика вычислений и работы с БД"""
	
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
    
    def get_data(self, date_filter=None) -> pd.DataFrame:
        """Загрузка данных из SQLite"""
        try:
            target_date = pd.Timestamp(date_filter).date()
            movements = self._movement_repo.get_data_from_db(target_date)
            schema = MovementSchema(many=True)
            df = pd.DataFrame(schema.dump(movements, many=True))
            print(df)
            if df.empty:
                raise ValueError("База данных пуста. Сначала загрузите данные через /load-data")
            df['Дата'] = pd.to_datetime(df['Дата'], format='%Y-%m-%d %H:%M:%S')                
            return df
            
        except Exception as e:
            raise ValueError(f"Ошибка при чтении данных: {str(e)}")

    def _prepare_zones_and_mapping(self, zone_type: str, df: pd.DataFrame) -> Tuple[List[str], List[str], Dict[str, str], List[str]]:
        """Подготовка списков зон и маппинга"""
        zones, zones_rep = self._group_repo.load_zones_from_db()
        print(f"{__name__} - zones, zones_rep {zones} - {zones_rep}")        
        if zone_type == "rep":
            all_entities = zones_rep.copy()           
        else:           
            all_entities = zones.copy()

        query = self._group_repo.load_groups_from_db(all_entities)
        print(f"{__name__} - load_groups_from_db {query}")
        groups = {}
        for group in query:
            print(f"{__name__} - group_name {group.group_name} zones {group.zones}")
            groups[group.group_name] = json.loads(group.zones)
        print(f"{__name__} - groups {groups}")

        all_available_zones = df['Точка регистрации'].unique()
        zone_to_group = {}           
        
        for group_name, group_zones in groups.items():
            existing_zones = [zone for zone in group_zones if zone in all_available_zones]
            missing_zones = [zone for zone in group_zones if zone not in all_available_zones]

            if existing_zones:  # Если есть хотя бы одна существующая зона
                for zone in existing_zones:
                    zone_to_group[zone] = group_name
        
                if missing_zones:
                    print(f"⚠️ Группа '{group_name}' добавлена частично. Пропущены зоны: {missing_zones}")
                else:
                    print(f"✅ Добавлена группа: {group_name}")
            else:
                print(f"❌ Группа '{group_name}' пропущена. Нет доступных зон")
                all_entities.remove(group_name)
    
            print(f"Группы для замены: {zone_to_group}")
        
        return zones, zones_rep, zone_to_group, all_entities

    def _transform_dataframe(self, df: pd.DataFrame, zone_to_group: Dict[str, str]) -> pd.DataFrame:
        """Трансформация DataFrame: замена зон на группы и обработка дубликатов"""
        df_transformed = df.copy()

        
        # Заменяем зоны на группы
        logger.info(f'zones to group {zone_to_group}')
        if zone_to_group:
            df_transformed['Точка регистрации'] = df_transformed['Точка регистрации'].map(
                lambda x: zone_to_group.get(x, x)
            )
        
        # Сортировка и обработка дубликатов
        df_transformed = df_transformed.sort_values(['Заказ', 'Дата'])
        df_transformed['next_zone'] = df_transformed.groupby('Заказ')['Точка регистрации'].shift(-1)
        df_transformed['exit_time'] = df_transformed.groupby('Заказ')['Дата'].shift(-1)
        
        # Удаление дубликатов (последовательных одинаковых зон)
        mask = df_transformed['Точка регистрации'] == df_transformed['next_zone']
        df_transformed.loc[mask.shift(1).fillna(False), 'Дата'] = df_transformed.loc[mask, 'Дата'].values
        df_transformed = df_transformed[~mask]
        
        # Добавляем часы
        df_transformed['hour'] = df_transformed['Дата'].dt.hour
        df_transformed['next_hour'] = df_transformed['exit_time'].dt.hour
        
        return df_transformed

    def _calculate_hourly_stats(self, df: pd.DataFrame, target_date: date, all_entities: List[str]) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """Расчет почасовой статистики въездов и выездов"""
        # Въезды
        print('df - transformeed ', df[['Точка регистрации', 'Заказ', 'Дата', 'hour']])
        enter_df = df[df['Дата'].dt.date == target_date]
        print('enter_df ', enter_df[['Точка регистрации', 'Заказ', 'Дата', 'hour']])
        entries_pivot = pd.crosstab(
            enter_df['Точка регистрации'],
            enter_df['hour'],
            dropna=False
        ).reindex(columns=range(6, 24), fill_value=0)

        logger.info(f"entries_pivot {entries_pivot}")
        
        
        # Выезды
        exit_df = df[df['exit_time'].dt.date == target_date]
        exits_pivot = pd.crosstab(
            exit_df['Точка регистрации'],
            exit_df['next_hour'],
            dropna=False
        ).reindex(columns=range(6, 24), fill_value=0)
        logger.info(f"exits_pivot {exits_pivot}")
        
        return entries_pivot, exits_pivot

    def _build_result(self, entries_pivot: pd.DataFrame, exits_pivot: pd.DataFrame, 
                     all_entities: List[str], zone_type: str) -> Tuple[List[ZoneStats], str]:
        """Формирование результата и балансовых сообщений"""
        result = []
        balance_messages = []
        
        for entity in all_entities:
            # Получаем данные по часам
            entries_hours = {}
            exits_hours = {}
            
            for hour in range(6, 24):
                entries_hours[hour] = int(entries_pivot.loc[entity, hour]) if entity in entries_pivot.index else 0
                exits_hours[hour] = int(exits_pivot.loc[entity, hour]) if entity in exits_pivot.index else 0
            
            total_entries = sum(entries_hours.values())
            total_exits = sum(exits_hours.values())
            balance = total_entries - total_exits
            
            balance_messages.append(f"{entity}: въехало={total_entries}, выехало={total_exits}, разница={balance}")

            result.append(ZoneStats(
                zone_name=entity,
                entries=entries_hours,
                exits=exits_hours
            ))
        logger.info(f"zone_name {entity} \n entries {entries_hours}  \n exits {exits_hours}")

        
        return result, "\n".join(balance_messages)

    def calculate_statistics(self, df: pd.DataFrame, date_filter: str, zone_type: str = "main") -> Tuple[List[ZoneStats], str]:
        """Основной метод - оркестрирует все шаги"""
        # 1. Подготовка зон и маппинга
        
        _, _, zone_to_group, all_entities = self._prepare_zones_and_mapping(zone_type, df)
                
        logger.debug(f"zone to group, {datetime.now()} {zone_to_group}")
        logger.debug(f" all_entities, { all_entities}")
        
        # 2. Трансформация DataFrame
        target_date = pd.Timestamp(date_filter).date()
        df_transformed = self._transform_dataframe(df, zone_to_group)
        logger.info(f"{datetime.now()} zone to group, {zone_to_group}")
        
        # 3. Расчет почасовой статистики
        entries_pivot, exits_pivot = self._calculate_hourly_stats(
            df_transformed, target_date, all_entities
        )
        logger.debug(f"entries_pivot ________ {entries_pivot}")
        logger.debug(f"exits_pivot ___________ {exits_pivot}")
        logger.debug(f"all_entities {all_entities}")
        
        # 4. Формирование результата
        return self._build_result(entries_pivot, exits_pivot, all_entities, zone_type)
				
    def load_excel_to_db(self):
        return self._movement_repo.load_excel_to_db()
		

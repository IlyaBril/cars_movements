import json
import pandas as pd
import logging
from datetime import datetime, date
from fastapi import Depends
from io import BytesIO
from typing import List, Tuple, Dict, Annotated, Optional
from app.db.models import ZoneStats
from app.db.repository import MovementRepository, GroupRepository
from app.db.database import SQLiteSession, PostgresSession
from app.db.schemas import MovementSchema
from app.services.zone_service import ZoneService
from sqlalchemy.orm import Session
from marshmallow import ValidationError 


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
        """
           Загрузка данных из SQLite
           Возвращает таблицу со всеми движениями VIN в таблице
           на которые есть любое движение этого VIN в указанный день date_filter
           Преобразует формат столбца Дата в %Y-%m-%d %H:%M:%S

        """
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


    def export_to_excel(self) -> Optional[bytes]:
        """Экспортировать данные в Excel"""
        try:
            movements = self._movement_repo.get_data_from_db()
            schema = MovementSchema(many=True)           
            validated_data = schema.dump(movements)

            df = pd.DataFrame(validated_data)
            logger.info(f'{__name__} validated data done')
            if df.empty:
                return None
            
            # Создаем Excel файл в памяти
            output = BytesIO()
            logger.info(f'{__name__} output')
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='Данные', index=False)
            logger.info(f'{__name__} to excel')
            return output.getvalue()
            
        except Exception as e:
            print(f"Ошибка экспорта: {e}")
            return None                
 

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
        """Трансформация DataFrame: замена зон на группы и удаление дубликатов
        Args:
        df_transformed (pd.DataFrame): Датафрейм с колонками 'Точка регистрации' и 'Заказ'.
                                       Датафрейм должен быть отсортирован по времени.
        Returns:
        pd.DataFrame: Отфильтрованный датафрейм с перезаписанными индексами.
                      Содержит только строки, где изменилась точка или заказ.
        """
		
        df_transformed = df.copy()
        
        # Заменяем зоны на группы
        if zone_to_group:
            df_transformed['Точка регистрации'] = df_transformed['Точка регистрации'].map(
                lambda x: zone_to_group.get(x, x)
            )

        # Сортировка и обработка дубликатов
        df_transformed = df_transformed.sort_values(['Заказ', 'Дата'])
        mask = (df_transformed['Точка регистрации'] != df_transformed['Точка регистрации'].shift()) | \
           (df_transformed['Заказ'] != df_transformed['Заказ'].shift())
        df_transformed = df_transformed[mask].reset_index(drop=True)
    
        # Создание next_zone и exit time
        grouped_clean = df_transformed.groupby('Заказ')
        df_transformed['next_zone'] = grouped_clean['Точка регистрации'].shift(-1).fillna('')
        df_transformed['exit_time'] = grouped_clean['Дата'].shift(-1)
                
        # Добавление часов
        df_transformed['hour'] = df_transformed['Дата'].dt.hour
        df_transformed['next_hour'] = df_transformed['exit_time'].dt.hour
        
        return df_transformed

    def _calculate_hourly_stats(self, df: pd.DataFrame, target_date: date, all_entities: List[str]) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """Расчет почасовой статистики въездов и выездов"""

        # Въезды       
        enter_df = df[df['Дата'].dt.date == target_date]
        entries_pivot = pd.crosstab(
            enter_df['Точка регистрации'],
            enter_df['hour'],
            dropna=False
        ).reindex(columns=range(6, 24), fill_value=0)
        
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
                
        # 2. Трансформация DataFrame
        target_date = pd.Timestamp(date_filter).date()
        df_transformed = self._transform_dataframe(df, zone_to_group)
        
        # 3. Расчет почасовой статистики
        entries_pivot, exits_pivot = self._calculate_hourly_stats(
            df_transformed, target_date, all_entities
        )
        logger.debug(f"entries_pivot ________ {entries_pivot}")
        logger.debug(f"exits_pivot ___________ {exits_pivot}")
        
        # 4. Формирование результата
        return self._build_result(entries_pivot, exits_pivot, all_entities, zone_type)
				
    def load_excel_to_db(self):
        return self._movement_repo.load_excel_to_db()

    def load_from_excel(self, file_content: bytes) -> Tuple[bool, str, int]:
        try:
            df = pd.read_excel(
                BytesIO(file_content),
                sheet_name=0,
                usecols=['Номер', 'Дата', 'Заказ', 'Точка регистрации']
                )
            df['Дата'] = pd.to_datetime(df['Дата'], format='%d.%m.%Y %H:%M:%S')

            print(df)
            schema = MovementSchema(many=True)
            logger.info(f'{__name__} pd.read_excel done')
            
            validated_data = schema.load(df.to_dict('records'))

        
            logger.info(f'{__name__} data validation pass ok')
        
            try:
                result, msg, added = self._movement_repo.load_from_excel_to_db(validated_data)
                logger.info(f'{__name__} _movement_repo.load_from_excel_to_db ok {result} , {msg} , {added}')
                return result, msg, added
            except Exception as e:
                # Логируем полную ошибку с traceback
                logger.error(f'{__name__} Error in load_from_excel_to_db: {str(e)}', exc_info=True)
                return False, f"Ошибка при сохранении в БД: {str(e)}", 0
            
        except Exception as e:
            logger.error(f'{__name__} Unexpected error: {str(e)}', exc_info=True)
            return False, f"Ошибка: {str(e)}", 0
            

    def clear_database(self) -> Tuple[bool, str]:
        """Очистить базу данных"""
        try:
            count = self._movement_repo.clear_all()

            return True, f"Очищено {count} записей"
        except Exception as e:
            self.session.rollback()
            return False, f"Ошибка очистки: {str(e)}"

import pandas as pd
from datetime import datetime, date
from typing import List, Tuple, Dict
from app.models import ZoneStats
from app.services.zone_service import ZoneService
from app.database import load_groups_from_db, get_db_connection

class DataService:
    @staticmethod
    def get_data() -> pd.DataFrame:
        """Загрузка данных из SQLite"""
        try:
            conn = get_db_connection()
            df = pd.read_sql_query('SELECT * FROM movements', conn)
            conn.close()
            
            if df.empty:
                raise ValueError("База данных пуста. Сначала загрузите данные через /load-data")
            df['Дата'] = pd.to_datetime(df['Дата'], format='%Y-%m-%d %H:%M:%S')                
            return df
            
        except Exception as e:
            raise ValueError(f"Ошибка при чтении данных: {str(e)}")

    @staticmethod
    def _prepare_zones_and_mapping(zone_type: str) -> Tuple[List[str], List[str], Dict[str, str], List[str]]:
        """Подготовка списков зон и маппинга"""
        zones, zones_rep = ZoneService.get_zones()
        groups = load_groups_from_db()
        
        if zone_type == "rep":
            all_entities = zones_rep.copy()
            zone_to_group = {}
        else:
            all_available_zones = zones + zones_rep
            all_entities = zones.copy()
            
            zone_to_group = {}
            for group_name, group_zones in groups.items():
                # Проверяем, все ли зоны группы существуют
                if all(zone in all_available_zones for zone in group_zones):
                    all_entities.append(group_name)
                    for zone in group_zones:
                        zone_to_group[zone] = group_name
                    print(f"✅ Добавлена группа: {group_name}")
                else:
                    missing = [z for z in group_zones if z not in all_available_zones]
                    print(f"⚠️ Группа '{group_name}' пропущена. Отсутствуют зоны: {missing}")
            
            print(f"Группы для замены: {zone_to_group}")
        
        return zones, zones_rep, zone_to_group, all_entities

    @staticmethod
    def _transform_dataframe(df: pd.DataFrame, zone_to_group: Dict[str, str]) -> pd.DataFrame:
        """Трансформация DataFrame: замена зон на группы и обработка дубликатов"""
        df_transformed = df.copy()
        
        # Заменяем зоны на группы
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

    @staticmethod
    def _calculate_hourly_stats(df: pd.DataFrame, target_date: date, all_entities: List[str]) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """Расчет почасовой статистики въездов и выездов"""
        # Въезды
        enter_df = df[df['Дата'].dt.date == target_date]
        entries_pivot = pd.crosstab(
            enter_df['Точка регистрации'],
            enter_df['hour'],
            dropna=False
        ).reindex(columns=range(6, 24), fill_value=0)
        
        # Добавляем все сущности, даже если их нет в данных
        for entity in all_entities:
            if entity not in entries_pivot.index:
                entries_pivot.loc[entity] = [0] * 18
        
        entries_pivot = entries_pivot.reindex(all_entities)
        
        # Выезды
        exit_df = df[df['exit_time'].dt.date == target_date]
        exits_pivot = pd.crosstab(
            exit_df['Точка регистрации'],
            exit_df['next_hour'],
            dropna=False
        ).reindex(columns=range(6, 24), fill_value=0)
        
        for entity in all_entities:
            if entity not in exits_pivot.index:
                exits_pivot.loc[entity] = [0] * 18
        
        exits_pivot = exits_pivot.reindex(all_entities)
        
        return entries_pivot, exits_pivot

    @staticmethod
    def _build_result(entries_pivot: pd.DataFrame, exits_pivot: pd.DataFrame, 
                     all_entities: List[str], zone_type: str) -> Tuple[List[ZoneStats], str]:
        """Формирование результата и балансовых сообщений"""
        result = []
        balance_messages = []
        
        groups = load_groups_from_db()
        
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
            
            # Определяем тип сущности
            if zone_type == "rep":
                prefix = "📍 Зона (ремонт)"
            elif entity in groups:
                prefix = "📊 Группа"
            else:
                prefix = "📍 Зона"
            
            balance_messages.append(f"{prefix} {entity}: въехало={total_entries}, выехало={total_exits}, разница={balance}")
            
            result.append(ZoneStats(
                zone_name=entity,
                entries=entries_hours,
                exits=exits_hours
            ))
        
        return result, "\n".join(balance_messages)

    @staticmethod
    def calculate_statistics(df: pd.DataFrame, date_filter: str, zone_type: str = "main") -> Tuple[List[ZoneStats], str]:
        """Основной метод - оркестрирует все шаги"""
        # 1. Подготовка зон и маппинга
        _, _, zone_to_group, all_entities = DataService._prepare_zones_and_mapping(zone_type)
        
        # 2. Трансформация DataFrame
        target_date = pd.Timestamp(date_filter).date()
        df_transformed = DataService._transform_dataframe(df, zone_to_group)
        
        # 3. Расчет почасовой статистики
        entries_pivot, exits_pivot = DataService._calculate_hourly_stats(
            df_transformed, target_date, all_entities
        )
        
        # 4. Формирование результата
        return DataService._build_result(entries_pivot, exits_pivot, all_entities, zone_type)
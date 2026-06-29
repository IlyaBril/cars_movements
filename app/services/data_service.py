
import pandas as pd
from datetime import datetime
from typing import List, Tuple
from app.models import ZoneStats
from app.services.zone_service import ZoneService
from app.config import MAIN_ZONE_GROUPS
from app.database import get_db_connection

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
    def calculate_statistics(df: pd.DataFrame, date_filter: str, zone_type: str = "main") -> Tuple[List[ZoneStats], str]:
        """Расчет статистики по зонам и группам"""
        # Получаем актуальные списки зон
        zones, zones_rep = ZoneService.get_zones()
        
        if zone_type == "rep":
            # Для ремонтных зон - только зоны, без групп
            current_zones = zones_rep
            all_entities = current_zones.copy()
            zone_to_group = {} # Пустой маппинг для rep
            
            # Создаем копию DataFrame без замены на группы
            df_transformed = df.copy()
            
        else:
            # Для main используем зоны + группы
            current_zones = zones
            all_entities = current_zones.copy()
            
            # Добавляем группы для main отчета
            for group_name, group_zones in MAIN_ZONE_GROUPS.items():
                all_available_zones = zones + zones_rep
                missing_zones = [zone for zone in group_zones if zone not in all_available_zones]
                
                if not missing_zones:
                    all_entities.append(group_name)
                    print(f"✅ Добавлена группа: {group_name} ({len(group_zones)} зон)")
                else:
                    print(f"⚠️ Группа '{group_name}' пропущена. Отсутствуют зоны: {missing_zones}")
            
            # Создаем маппинг зона -> группа
            zone_to_group = {}
            for group_name, group_zones in MAIN_ZONE_GROUPS.items():
                for zone in group_zones:
                    if zone in all_available_zones:
                        zone_to_group[zone] = group_name
                    
            print('zone to group ', zone_to_group)
            
            # Создаем копию DataFrame для трансформации
            df_transformed = df.copy()
            
            # Заменяем зоны на группы
            df_transformed['Точка регистрации'] = df_transformed['Точка регистрации'].map(
                lambda x: zone_to_group.get(x, x))
            
        
        # Перемещаем "ТиД" в начало если есть
        if "ТиД" in all_entities:
            all_entities.remove("ТиД")
            all_entities.insert(1, "ТиД")
        
        # Фильтруем данные по дате и сортируем
        target_date = pd.Timestamp(date_filter).date()
        df_transformed = df_transformed.sort_values(['Заказ', 'Дата'])
        
        # Сдвиг для получения следующей зоны
        df_transformed['next_zone'] = df_transformed.groupby('Заказ')['Точка регистрации'].shift(-1)
        df_transformed['exit_time'] = df_transformed.groupby('Заказ')['Дата'].shift(-1)
        
        # Удаляем дублирующиеся записи с одинаковой зоной подряд
        df_transformed = df_transformed[
            df_transformed['Точка регистрации'] != df_transformed['next_zone']
        ]
        
        # Добавляем часы
        df_transformed['hour'] = df_transformed['Дата'].dt.hour
        df_transformed['next_hour'] = df_transformed['exit_time'].dt.hour
        
        # Для расчета используем ТОЛЬКО те сущности, которые есть в данных
        # и которые соответствуют текущему типу зон
        entities_in_data = df_transformed['Точка регистрации'].unique().tolist()
        
        # --- Въезды ---
        enter_df = df_transformed[df_transformed['Дата'].dt.date == target_date]
        entries_pivot = pd.crosstab(
            enter_df['Точка регистрации'],
            enter_df['hour'],
            dropna=False
        ).reindex(columns=range(6, 24), fill_value=0, index=all_entities)
        print(entries_pivot)
        
        # --- Выезды ---
        exit_df = df_transformed[df_transformed['exit_time'].dt.date == target_date]
        exits_pivot = pd.crosstab(
            exit_df['Точка регистрации'],
            exit_df['next_hour'],
            dropna=False
        ).reindex(columns=range(6, 24), fill_value=0, index=all_entities)
        
        # --- Формирование результата ---
        result = []
        balance_messages = []
        
        for entity in all_entities:
            # Получаем данные по въездам/выездам
            if entity in entries_pivot.index:
                entries_hours = {hour: int(entries_pivot.loc[entity, hour]) for hour in range(6, 24)}
            else:
                entries_hours = {hour: 0 for hour in range(6, 24)}
            
            if entity in exits_pivot.index:
                exits_hours = {hour: int(exits_pivot.loc[entity, hour]) for hour in range(6, 24)}
            else:
                exits_hours = {hour: 0 for hour in range(6, 24)}
            
            total_entries = sum(entries_hours.values())
            total_exits = sum(exits_hours.values())
            balance = total_entries - total_exits
            
            # Определяем тип сущности
            if zone_type == "rep":
                prefix = "📍 Зона (ремонт)"
                is_group = False
            else:
                is_group = entity in MAIN_ZONE_GROUPS
                prefix = "📊 Группа" if is_group else "📍 Зона"
            
            balance_messages.append(f"{prefix} {entity}: въехало={total_entries}, выехало={total_exits}, разница={balance}")
            
            result.append(ZoneStats(
                zone_name=entity,
                entries=entries_hours,
                exits=exits_hours
            ))
        
        return result, "\n".join(balance_messages)



# app/services/data_service.py
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
            current_zones = zones_rep
            # Для rep зон группы не используем (пока)
            all_entities = current_zones.copy()
            # Если появятся группы для rep, добавим их здесь
        else:
            # Для main используем zones как основные
            current_zones = zones
            all_entities = current_zones.copy()
            
            # Добавляем группы для main отчета
            # Группы могут состоять из любых зон (и main, и rep)
            for group_name, group_zones in MAIN_ZONE_GROUPS.items():
                # Проверяем существование зон в группе
                # Проверяем по всем доступным зонам (zones + zones_rep)
                all_available_zones = zones + zones_rep
                missing_zones = [zone for zone in group_zones if zone not in all_available_zones]
                
                if not missing_zones:
                    all_entities.append(group_name)
                    print(f"✅ Добавлена группа: {group_name} ({len(group_zones)} зон)")
                else:
                    print(f"⚠️ Группа '{group_name}' пропущена. Отсутствуют зоны: {missing_zones}")
        if "ТиД" in all_entities:
            all_entities.remove("ТиД")  # Удаляем из текущей позиции
            # Вставляем на нужное место (индекс 1 = после первого элемента)
            all_entities.insert(0, "ТиД")
        
        target_date = pd.Timestamp(date_filter).date()
        df = df.sort_values(['Заказ', 'Дата'])
        # Сдвиг для получения следующей зоны
        df['next_zone'] = df.groupby('Заказ')['Точка регистрации'].shift(-1)
        df['exit_time'] = df.groupby('Заказ')['Дата'].shift(-1)
        df['hour'] = df['Дата'].dt.hour
        df['next_hour'] = df['exit_time'].dt.hour
		
        # Удаление дублирующих зон
        double_df = df[(df['Точка регистрации'] == df['next_zone'])]
        df = df[(df['Точка регистрации'] != df['next_zone'])]
        
        # Для расчета въезда/выезда используем все зоны (и main, и rep)
        all_zones_for_calc = zones + zones_rep
        
        # Въезд
        enter_df = df[
            (df['Точка регистрации'].isin(all_zones_for_calc)) & 
            (df['Дата'].dt.date == target_date)
        ]

        entries_pivot = pd.crosstab(
            enter_df['Точка регистрации'],
            enter_df['hour'],
            dropna=False
        ).reindex(columns=range(6, 24), fill_value=0, index=all_zones_for_calc)
        
        # Выезд
        exit_df = df[
            (df['Точка регистрации'].isin(all_zones_for_calc)) &
            (df['exit_time'].dt.date == target_date)
        ]
        
        exits_pivot = pd.crosstab(
            exit_df['Точка регистрации'],
            exit_df['next_hour'],
            dropna=False
        ).reindex(columns=range(6, 24), fill_value=0, index=all_zones_for_calc)
        
        # Формирование результата
        result = []
        balance_messages = []
        
        for entity in all_entities:
            # Определяем, зона это или группа
            if entity in zones or entity in zones_rep:
                # Это обычная зона
                zone_set = {entity}
                is_group = False
                entity_name = entity
            else:
                # Это группа
                zone_set = set(MAIN_ZONE_GROUPS[entity])
                is_group = True
                entity_name = f"{entity} (группа)"
            
            # Расчет для зоны или группы
            entries_hours = {}
            exits_hours = {}
            # Суммируем по всем зонам в группе
            for zone in zone_set:
                if zone in entries_pivot.index:
                    for hour in range(6, 24):
                        entries_hours[hour] = entries_hours.get(hour, 0) + int(entries_pivot.loc[zone, hour])
                if zone in exits_pivot.index:
                    for hour in range(6, 24):
                        exits_hours[hour] = exits_hours.get(hour, 0) + int(exits_pivot.loc[zone, hour])
            
            total_entries = sum(entries_hours.values())
            total_exits = sum(exits_hours.values())
            balance = total_entries - total_exits
            
            prefix = "📊 Группа" if is_group else "📍 Зона"
            balance_messages.append(f"{prefix} {entity}: въехало={total_entries}, выехало={total_exits}, разница={balance}")
            
            result.append(ZoneStats(
                zone_name=entity_name,
                entries=entries_hours,
                exits=exits_hours
            ))
        return result, "\n".join(balance_messages)
import pandas as pd
from datetime import datetime
from typing import List, Tuple
from app.models import ZoneStats
from app.services.zone_service import ZoneService

class DataService:
    @staticmethod
    def get_data() -> pd.DataFrame:
        """Загрузка данных из Excel"""
        try:
            df = pd.read_excel(
                'Движение.xlsx',
                sheet_name="Лист_1",
                nrows=20000,
                usecols=['Дата', 'Заказ', 'Точка регистрации'],
            )
            
            # Проверка колонок
            required_columns = ['Дата', 'Заказ', 'Точка регистрации']
            if not all(col in df.columns for col in required_columns):
                raise ValueError(f"Файл должен содержать колонки: {required_columns}")
            
            df['Дата'] = pd.to_datetime(df['Дата'], format='%d.%m.%Y %H:%M:%S')
            return df
        except Exception as e:
            raise ValueError(f"Ошибка при чтении файла: {str(e)}")
    
    @staticmethod
    def calculate_statistics(df: pd.DataFrame, date_filter: str, zone_type: str = "main") -> Tuple[List[ZoneStats], str]:
        """Расчет статистики по зонам"""
        # Получаем актуальные списки зон
        zones, zones_rep = ZoneService.get_zones()
        
        if zone_type == "rep":
            current_zones = zones_rep
        else:
            current_zones = zones
        
        target_date = pd.Timestamp(date_filter).date()
        df = df.sort_values(['Заказ', 'Дата'])
        
        # Сдвиг для получения следующей зоны
        df['next_zone'] = df.groupby('Заказ')['Точка регистрации'].shift(-1)
        df['exit_time'] = df.groupby('Заказ')['Дата'].shift(-1)
        df['hour'] = df['Дата'].dt.hour
        df['next_hour'] = df['exit_time'].dt.hour
        print('current_zones ', current_zones, 'target_date', target_date)
        # Въезд
        enter_df = df[
            (df['Точка регистрации'].isin(current_zones)) & 
            (df['Дата'].dt.date == target_date)
        ]
        print('e ', enter_df)
        entries_pivot = pd.crosstab(
            enter_df['Точка регистрации'],
            enter_df['hour'],
            dropna=False
        ).reindex(columns=range(6, 24), fill_value=0, index=current_zones)
        
        # Выезд
        exit_df = df[
            (df['Точка регистрации'].isin(current_zones)) &
            (df['exit_time'].dt.date == target_date)
        ]
        
        exits_pivot = pd.crosstab(
            exit_df['Точка регистрации'],
            exit_df['next_hour'],
            dropna=False
        ).reindex(columns=range(6, 24), fill_value=0, index=current_zones)
        
        # Баланс
        balance_messages = []
        for zone in current_zones:
            total_entries = entries_pivot.loc[zone].sum() if zone in entries_pivot.index else 0
            total_exits = exits_pivot.loc[zone].sum() if zone in exits_pivot.index else 0
            balance = total_entries - total_exits
            balance_messages.append(f"⚠️ {zone}: въехало={total_entries}, выехало={total_exits}, разница={balance}")
        balance_text = "\n".join(balance_messages)
        
        # Формирование результата
        result = []
        for zone in current_zones:
            entries_hours = {}
            exits_hours = {}
            
            for hour in range(6, 24):
                entries_hours[hour] = int(entries_pivot.loc[zone, hour]) if zone in entries_pivot.index else 0
                exits_hours[hour] = int(exits_pivot.loc[zone, hour]) if zone in exits_pivot.index else 0
            
            result.append(ZoneStats(
                zone_name=str(zone),
                entries=entries_hours,
                exits=exits_hours
            ))
        
        return result, balance_text
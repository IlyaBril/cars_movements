from datetime import datetime
from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi import Request
from pydantic import BaseModel
from typing import List, Dict, Optional
import pandas as pd
from datetime import datetime, timedelta
import io
from pathlib import Path
import uvicorn
import time

# Импортируем функции работы с БД из database.py
from database import init_database, load_zones_from_db, save_zones_to_db


app = FastAPI(title="Анализ движения автомобилей")
app.mount("/static", StaticFiles(directory="static"), name="static")

# Настройка шаблонов и статики
templates = Jinja2Templates(directory="templates")

#Группы зон
zones = ['M446. AVAL',
         'M444. Валидация ретуши',
         'M471. Отказ по качеству',
         'M445. Зона выборочного ко',
         'M450. Контроль электрики',
         'M470. Передача на СГП (BL',         
         'M500. Приемка на СГП (MAD',
         ]


zones_rep = ['M401. Ретушь электрики',
             'M403. Ретушь Сварки',
             'M404. Ретушь сборки',
             'M405. Ретушь окраски',
             'M414. Тяжелая ретушь Сбор',
             'M407. Ретушь замена детал',
             ]

required_columns = ['Дата', 'Заказ', 'Точка регистрации']


class ZoneStats(BaseModel):
    zone_name: str
    entries: Dict[int, int] # час -> количество входов
    exits: Dict[int, int] # час -> количество выходов


class AnalysisResponse(BaseModel):
    success: bool
    message: str
    data: Optional[List[ZoneStats]] = None


def default_date():
    return datetime.today().strftime("%Y-%m-%d")


def get_data(zone_type: str = "main") -> pd.DataFrame:
    """Парсинг Excel файла с данными c фильтрацией"""

    df = pd.read_excel(
        'C:/Users/mv3120/Documents/Движение/Движение.xlsx',
        sheet_name="Лист_1", nrows=200000,
        usecols=['Дата', 'Заказ', 'Точка регистрации'],
        )
    
    try:
        # Проверка необходимых колонок
        required_columns = ['Дата', 'Заказ', 'Точка регистрации']
        if not all(col in df.columns for col in required_columns):
            raise ValueError(f"Файл должен содержать колонки: {required_columns}")
              
        # Преобразование времени
        df['Дата'] = pd.to_datetime(df['Дата'], format='%d.%m.%Y %H:%M:%S')
        
        
        return df
    
    except Exception as e:
        raise ValueError(f"Ошибка при чтении файла")


def calculate_zone_statistics(df: pd.DataFrame, date_filter: str, zone_type: str = "main") -> List[ZoneStats]:
    # Выбор списка зон для индексации
    if zone_type == "rep":
        current_zones = zones_rep
    else:
        current_zones = zones

    target_date = pd.Timestamp(date_filter).date()
    df = df.sort_values(['Заказ', 'Дата'])
	
    # Сдвиг для каждой группы, чтобы получить следующую зону
    df['next_zone'] = df.groupby('Заказ')['Точка регистрации'].shift(-1)    
    df['exit_time'] = df.groupby('Заказ')['Дата'].shift(-1)
    df['hour'] = df['Дата'].dt.hour
    df['next_hour'] = df['exit_time'].dt.hour

    #Въезд авто в зоны 
    enter_df = df[
        (df['Точка регистрации'].isin(current_zones)) & 
        (df['Дата'].dt.date == target_date)
    ]
	
    entries_pivot = pd.crosstab(
        enter_df['Точка регистрации'],
        enter_df['hour'],
        dropna=False
    ).reindex(columns=range(6, 24), fill_value=0, index=current_zones)
    
    #Выезд авто из зоны
    exit_df = df[
        (df['Точка регистрации'].isin(current_zones)) &
        (df['exit_time'].dt.date == target_date)  # время ВЫЕЗДА = текущее время записи
    ]
    
    exits_pivot = pd.crosstab(
        exit_df['Точка регистрации'],
        exit_df['next_hour'],
        dropna=False
    ).reindex(columns=range(6, 24), fill_value=0, index=current_zones)

    print('exits_pivot', exits_pivot)
	
   # Сообщение о балансе
    balance_messages = []
    for zone in current_zones:
        total_entries = entries_pivot.loc[zone].sum() if zone in entries_pivot.index else 0
        total_exits = exits_pivot.loc[zone].sum() if zone in exits_pivot.index else 0
        balance = total_entries - total_exits
        balance_messages.append(f"⚠️ {zone}: въехало={total_entries}, выехало={total_exits}, разница={balance}")
    balance_text = "\n".join(balance_messages)

   # Преобразование в формат ZoneStats
    result = []
    
    for zone in current_zones:
        entries_hours = {}
        exits_hours = {}
        
        # Заполнение данных по часам
        for hour in range(6, 24):
            if zone in entries_pivot.index:
                entries_hours[hour] = int(entries_pivot.loc[zone, hour])
            else:
                entries_hours[hour] = 0
                
            if zone in exits_pivot.index:
                exits_hours[hour] = int(exits_pivot.loc[zone, hour])
            else:
                exits_hours[hour] = 0
        
        result.append(ZoneStats(
            zone_name=str(zone),
            entries=entries_hours,
            exits=exits_hours
        ))
        
    return result, balance_text


@app.get("/analyze/")
def analyze_zones(date: str = Query(default="2026-06-09"), zone_type: str = Query(default="main")):
    df = get_data(zone_type)
    stats, balance = calculate_zone_statistics(df, date, zone_type)


    # Табличные данные для отображения
    result = []
    for zone_stat in stats:
        result.append({
            "zone": zone_stat.zone_name,
            "entries": [zone_stat.entries.get(h, 0) for h in range(6, 24)],
            "exits": [zone_stat.exits.get(h, 0) for h in range(6, 24)]
            })

    return {
        "success": True,
        "data": result,
        "hours": list(range(6, 24)),
        "zone_type": zone_type,
        "balance": balance,
        }


@app.get("/")
def root(request: Request):
    """Главная страница с интерфейсом"""
    
    date = default_date()
    
    return templates.TemplateResponse(
        request=request, name="index(bootstrap).html",
        context={"default_date": date},
        )


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

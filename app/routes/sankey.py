from fastapi import APIRouter, Request, Query, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from app.services.data_service import DataService
from app.services.zone_service import ZoneService
from app.services.sankey_service import SankeyService
from datetime import datetime, timedelta
import plotly.graph_objects as go
import json
import pandas as pd
import logging
import random

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

router = APIRouter(tags=["sankey"])
templates = Jinja2Templates(directory="templates")

sankey_service = SankeyService()

def default_date():
    return datetime.today().strftime("%Y-%m-%d")

@router.get("/sankey")
async def sankey_page(request: Request):
    """Страница с Sankey диаграммой"""
    return templates.TemplateResponse(
        request=request,
        name="sankey.html",
        context={
            "default_date": default_date()
        }
    )

@router.get("/api/sankey-data")
async def get_sankey_data(
    date: str = Query(default=default_date()),
    zone_type: str = Query(default="main")
):
    """
    API для получения данных Sankey диаграммы
    """
    print(f'{__name__}  zone_type {zone_type}') 
    try:
        data_service = DataService()
        with data_service:
            # Получаем данные
            df = data_service.get_data(date)
            if df.empty:
                return JSONResponse(
                    status_code=404,
                    content={"error": "Нет данных за выбранную дату"}
                )
            
            # Подготавливаем данные для Sankey
            stats, balance = data_service.calculate_statistics(df, date, zone_type)
            
            # Получаем список зон для фильтрации
            
            allowed_zones = sankey_service.get_allowed_zones(zone_type)
            
            # Преобразуем статистику в формат для Sankey с фильтрацией
            sankey_data = prepare_sankey_data(stats, df, date, allowed_zones)
            
            return {
                "success": True,
                "data": sankey_data,
                "balance": balance,
                "zone_type": zone_type,
                "date": date
            }
            
    except Exception as e:
        logger.error(f"Ошибка в Sankey API: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )

@router.get("/sankey-chart")
async def get_sankey_chart(
    date: str = Query(default=default_date()),
    zone_type: str = Query(default="main")
):
    """
    Создает Sankey диаграмму с помощью plotly
    """
    try:
        data_service = DataService()
        with data_service:
            df = data_service.get_data(date)
            if df.empty:
                return HTMLResponse(content="<h3>Нет данных за выбранную дату</h3>")
            
            stats, balance = data_service.calculate_statistics(df, date, zone_type)
            
            # Получаем список зон для фильтрации
            allowed_zones = sankey_service.get_allowed_zones(zone_type)
            print('allowed zones ', allowed_zones)
            
            # Создаем Sankey диаграмму с фильтрацией
            fig = create_sankey_chart(stats, df, date, allowed_zones, zone_type)
            
            return HTMLResponse(content=fig.to_html(full_html=False))
            
    except Exception as e:
        logger.error(f"Ошибка создания Sankey диаграммы: {e}")
        return HTMLResponse(content=f"<h3>Ошибка: {str(e)}</h3>")


def prepare_sankey_data(stats, df: pd.DataFrame, date: str, allowed_zones: list) -> dict:
    """
    Подготовка данных для Sankey диаграммы с фильтрацией зон
    """
    target_date = pd.Timestamp(date).date()
    
    # Фильтруем данные за выбранную дату и только разрешенные зоны
    df_day = df[df['Дата'].dt.date == target_date].copy()
    
    # Применяем фильтр по разрешенным зонам
    df_filtered = df_day[df_day['Точка регистрации'].isin(allowed_zones)]
    
    # Логируем для отладки
    logger.info(f"Разрешенные зоны allowed zones: {allowed_zones}")
    logger.info(f"Всего записей за день: {len(df_day)}")
    logger.info(f"Записей после фильтрации: {len(df_filtered)}")
    logger.info(f"Разрешенные зоны: {allowed_zones}")
    logger.info(f"Уникальные зоны в данных: {df_filtered['Точка регистрации'].unique().tolist()}")
    
    if df_filtered.empty:
        return {
            'nodes': [],
            'links': [],
            'message': f'Нет данных по зонам типа {"ретуши" if zone_type == "rep" else "основным"} за выбранную дату'
        }
    
    # Собираем переходы между зонами
    nodes = []
    links = {}
    
    # Сортируем по заказу и времени
    df_filtered = df_filtered.sort_values(['Заказ', 'Дата'])
    
    # Для каждого заказа собираем последовательность зон
    for order in df_filtered['Заказ'].unique():
        order_data = df_filtered[df_filtered['Заказ'] == order]
        zones = order_data['Точка регистрации'].tolist()
        
        # Создаем переходы между соседними зонами
        for i in range(len(zones) - 1):
            from_zone = zones[i]
            to_zone = zones[i + 1]
            
            # Добавляем узлы
            if from_zone not in nodes:
                nodes.append(from_zone)
            if to_zone not in nodes:
                nodes.append(to_zone)
            
            # Создаем связь
            link_key = f"{from_zone}->{to_zone}"
            if link_key not in links:
                links[link_key] = {
                    'source': nodes.index(from_zone),
                    'target': nodes.index(to_zone),
                    'value': 0,
                    'from_zone': from_zone,
                    'to_zone': to_zone
                }
            links[link_key]['value'] += 1
    
    # Добавляем виртуальные узлы для въезда и выезда
    entry_node = "Въезд"
    exit_node = "Выезд"
    
    # Проверяем, есть ли зоны для отображения
    if not nodes:
        return {
            'nodes': [],
            'links': [],
            'message': 'Нет переходов между зонами'
        }
    
    if entry_node not in nodes:
        nodes.append(entry_node)
    if exit_node not in nodes:
        nodes.append(exit_node)
    
    # Подсчитываем въезды для каждой зоны (первое появление)
    first_entries = df_filtered.groupby('Заказ').first()['Точка регистрации']
    entries = first_entries.value_counts()
    
    # Добавляем связи с въездом
    for zone, count in entries.items():
        if zone in nodes:
            link_key = f"{entry_node}->{zone}"
            if link_key not in links:
                links[link_key] = {
                    'source': nodes.index(entry_node),
                    'target': nodes.index(zone),
                    'value': 0,
                    'from_zone': entry_node,
                    'to_zone': zone
                }
            links[link_key]['value'] += count
    
    # Подсчитываем выезды (последняя зона в каждом заказе)
    last_zones = df_filtered.groupby('Заказ').last()['Точка регистрации']
    exits = last_zones.value_counts()
    
    for zone, count in exits.items():
        if zone in nodes:
            link_key = f"{zone}->{exit_node}"
            if link_key not in links:
                links[link_key] = {
                    'source': nodes.index(zone),
                    'target': nodes.index(exit_node),
                    'value': 0,
                    'from_zone': zone,
                    'to_zone': exit_node
                }
            links[link_key]['value'] += count
    
    # Фильтруем связи: удаляем нулевые значения и связи с несуществующими узлами
    valid_nodes = set(nodes)
    links = {k: v for k, v in links.items() 
             if v['value'] > 0 and v['source'] < len(nodes) and v['target'] < len(nodes)}
    
    # Формируем результат
    result_links = []
    for link in links.values():
        result_links.append({
            'source': link['source'],
            'target': link['target'],
            'value': link['value'],
            'from_zone': link['from_zone'],
            'to_zone': link['to_zone']
        })
    
    # Сортируем узлы: сначала въезд, потом основные зоны, потом выезд
    sorted_nodes = [entry_node] + [n for n in nodes if n not in [entry_node, exit_node]] + [exit_node]
    
    return {
        'nodes': sorted_nodes,
        'links': result_links,
        'message': None
    }



def create_sankey_chart(stats, df: pd.DataFrame, date: str, allowed_zones: list, zone_type: str) -> go.Figure:
    """
    Создает интерактивную Sankey диаграмму с использованием plotly
    """
    sankey_data = prepare_sankey_data(stats, df, date, allowed_zones)

    print(f'{__name__} sankey data {sankey_data})')

    
    
    # Проверяем, есть ли данные
    if not sankey_data['nodes'] or not sankey_data['links']:
        fig = go.Figure()
        message = sankey_data.get('message', 'Нет данных для отображения')
        fig.update_layout(
            title={
                'text': f'{message} за {date}',
                'y': 0.5,
                'x': 0.5,
                'xanchor': 'center',
                'yanchor': 'middle'
            },
            height=400,
            annotations=[
                dict(
                    text="Попробуйте выбрать другой тип зон или дату",
                    x=0.5,
                    y=0.4,
                    xref="paper",
                    yref="paper",
                    showarrow=False,
                    font=dict(size=14, color="#6c757d")
                )
            ]
        )
        return fig
    
    # Подготовка данных для plotly
    node_labels = sankey_data['nodes']
    sources = []
    targets = []
    values = []
    
    for link in sankey_data['links']:
        sources.append(link['source'])
        targets.append(link['target'])
        values.append(link['value'])
    
    # Создаем цветовую схему для узлов
    import random
    colors = []
    for i, label in enumerate(node_labels):
        if label == "Въезд":
            colors.append('rgba(46, 204, 113, 0.9)')  # Зеленый
        elif label == "Выезд":
            colors.append('rgba(231, 76, 60, 0.9)')  # Красный
        else:
            # Генерируем случайный цвет для основных зон
            r = random.randint(100, 200)
            g = random.randint(100, 200)
            b = random.randint(100, 200)
            colors.append(f'rgba({r}, {g}, {b}, 0.8)')
    
    # Название диаграммы в зависимости от типа зон
    title_text = f"Sankey диаграмма потоков за {date}"
    if zone_type == "rep":
        title_text += " (Зоны ретуши)"
    else:
        title_text += " (Основные зоны)"
    
    # Создаем Sankey диаграмму
    fig = go.Figure(data=[go.Sankey(
        node=dict(
            pad=15,
            thickness=20,
            line=dict(color="black", width=0.5),
            label=node_labels,
            color=colors,
        ),
        link=dict(
            source=sources,
            target=targets,
            value=values,
            color='rgba(100, 100, 255, 0.2)'  # Полупрозрачные линии
        )
    )])
    
    fig.update_layout(
        title={
            'text': title_text,
            'y': 0.95,
            'x': 0.5,
            'xanchor': 'center',
            'yanchor': 'top',
            'font': dict(size=16)
        },
        font=dict(
            size=12,
            family='Arial, sans-serif'
        ),
        height=700,
        margin=dict(
            l=50,
            r=50,
            t=80,
            b=50
        ),
        hoverlabel=dict(
            font_size=12,
            font_family="Arial"
        )
    )
    
    return fig

from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from app.services.data_service import DataService
from app.services.sankey_service import SankeyService
from datetime import datetime
import plotly.graph_objects as go
import pandas as pd
import logging
import random

logger = logging.getLogger(__name__)
router = APIRouter(tags=["sankey"])
templates = Jinja2Templates(directory="templates")


ZONE_POSITIONS = {
    # Основные зоны
    'Приемка': {'x': 0.05, 'y': 0.2, 'color': '#FF6B6B'},
    'Склад': {'x': 0.05, 'y': 0.5, 'color': '#4ECDC4'},
    'Сборка': {'x': 0.5, 'y': 0.2, 'color': '#45B7D1'},
    'Упаковка': {'x': 0.5, 'y': 0.5, 'color': '#96CEB4'},
    'Отгрузка': {'x': 0.95, 'y': 0.5, 'color': '#FFEAA7'},
    'Брак': {'x': 0.95, 'y': 0.8, 'color': '#DDA0DD'},
    
    # Зоны ретуши
    'Ретушь 1': {'x': 0.2, 'y': 0.3, 'color': '#FF9FF3'},
    'Ретушь 2': {'x': 0.2, 'y': 0.6, 'color': '#F368E0'},
    'Ретушь 3': {'x': 0.5, 'y': 0.3, 'color': '#FF9F43'},
    'Ретушь 4': {'x': 0.5, 'y': 0.6, 'color': '#FECA57'},
    'Контроль': {'x': 0.8, 'y': 0.3, 'color': '#54A0FF'},
    'Доработка': {'x': 0.8, 'y': 0.6, 'color': '#5F27CD'},
}


def default_date():
    return datetime.today().strftime("%Y-%m-%d")

@router.get("/sankey")
async def sankey_page(request: Request):
    return templates.TemplateResponse(request=request, name="sankey.html", context={"default_date": default_date()})


@router.get("/sankey-chart")
async def get_sankey_chart(date: str = Query(default=default_date()), zone_type: str = Query(default="main")):
    try:
        data_service = DataService()
        with data_service:
            df = data_service.get_data(date)
            _, _, zone_to_group, allowed_zones = data_service._prepare_zones_and_mapping(zone_type, df)
            df = data_service._transform_dataframe(df, zone_to_group)
            if df.empty:
                return HTMLResponse(content="<h3>Нет данных за выбранную дату</h3>")

        fig = create_sankey_chart(df, date, allowed_zones, zone_type)
        return HTMLResponse(content=fig.to_html(full_html=False))
    except Exception as e:
        logger.error(f"Ошибка создания Sankey диаграммы: {e}")
        return HTMLResponse(content=f"<h3>Ошибка: {str(e)}</h3>")


def prepare_sankey_data(df: pd.DataFrame, date: str, allowed_zones: list) -> dict:
    target_date = pd.Timestamp(date).date()
    df_day = df[df['exit_time'].dt.date == target_date].copy()
    df_filtered = df_day[df_day['next_zone'].isin(allowed_zones)]
    
    if df_filtered.empty:
        return {'nodes': [], 'links': [], 'message': 'Нет данных'}

    # Собираем все зоны и связи
    all_zones = set()
    links = {}
    df_filtered = df_filtered.sort_values(['Заказ', 'exit_time'])

    for order in df_filtered['Заказ'].unique():
        zones = df_filtered[df_filtered['Заказ'] == order]['next_zone'].tolist()
        for i in range(len(zones) - 1):
            from_zone, to_zone = zones[i], zones[i+1]
            all_zones.add(from_zone)
            all_zones.add(to_zone)
            link_key = f"{from_zone}->{to_zone}"
            if link_key not in links:
                links[link_key] = {'source': from_zone, 'target': to_zone, 'value': 0}
            links[link_key]['value'] += 1

    # Подсчет статистики входов и выходов
    zone_stats = {zone: {'in': 0, 'out': 0} for zone in all_zones}
    
    for link in links.values():
        zone_stats[link['source']]['out'] += link['value']
        zone_stats[link['target']]['in'] += link['value']

    # Создаем узлы с обогащенными названиями
    nodes = []
    node_to_index = {}
    
    for i, zone in enumerate(all_zones):
        stats = zone_stats[zone]
        # Формат с переносом строки
        label = f"{zone}<br>(вх: {stats['in']}, вых: {stats['out']})"
        # Альтернативный компактный формат:
        # label = f"{zone} [{stats['in']}→{stats['out']}]"
        nodes.append(label)
        node_to_index[zone] = i

    # Обновляем связи
    updated_links = []
    for link in links.values():
        updated_links.append({
            'source': node_to_index[link['source']],
            'target': node_to_index[link['target']],
            'value': link['value']
        })

    logger.info(f"{__name__} nodes: \n {nodes} \n links {updated_links}")
    
    return {'nodes': nodes, 'links': updated_links}


def create_sankey_chart(
    df: pd.DataFrame,
    date: str,
    allowed_zones: list,
    zone_type: str,
    ) -> go.Figure:

    sankey_data = prepare_sankey_data(df, date, allowed_zones)
    
    if not sankey_data['nodes'] or not sankey_data['links']:
        fig = go.Figure()
        fig.update_layout(
            title={
                'text': f'Нет данных для отображения за {date}',
                'y': 0.5,
                'x': 0.5
                },
            height=400
            )
        return fig

    node_labels = sankey_data['nodes']
    sources, targets, values = [], [], []
    
    for link in sankey_data['links']:
        sources.append(link['source'])
        targets.append(link['target'])
        values.append(link['value'])

    colors = [f'rgba({random.randint(100,200)}, {random.randint(100,200)}, {random.randint(100,200)}, 0.8)' for _ in node_labels]

    fig = go.Figure(data=[go.Sankey(
        node=dict(
            pad=15,
            thickness=20,
            line=dict(color="black", width=0.5), label=node_labels, color=colors),
        link=dict(
            source=sources,
            target=targets,
            value=values,
            color='rgba(100, 100, 255, 0.2)'
            )
    )])

    fig.update_layout(
        title={'text': f'Sankey диаграмма потоков за {date} {"(Зоны ретуши)" if zone_type == "rep" else "(Основные зоны)"}', 
               'y': 0.95, 'x': 0.5, 'xanchor': 'center', 'yanchor': 'top'},
        height=700, margin=dict(l=50, r=50, t=80, b=50)
    )
    return fig

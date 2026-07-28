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
    'M440. GRT': {'x': 0.05, 'y': 0.5, 'color': '#FF6B6B'},
    'М444_М446 Валидация': {'x': 0.3, 'y': 0.2, 'color': '#45B7D1'},
    'M450. Контроль электрики': {'x': 0.6, 'y': 0.2, 'color': '#DDA0DD'},
    'M470. Передача на СГП (BLAN)': {'x': 0.8, 'y': 0.2, 'color': '#DDA0DD'}, 
    'ТиД': {'x': 0.2, 'y': 0.6, 'color': '#4ECDC4'},
    'M471. Отказ по качеству': {'x': 0.4, 'y': 0.6, 'color': '#96CEB4'},
    'M445. Зона выборочного контроля': {'x': 0.55, 'y': 0.5, 'color': '#FFEAA7'},
    'M422. Некомплекты': {'x': 0.95, 'y': 0.7, 'color': '#FFEAA7'},
    'M500. Приемка на СГП (MADU)': {'x': 0.95, 'y': 0.3, 'color': '#FFEAA7'},
    'M483. Чистые автомобили': {'x': 0.95, 'y': 0.4, 'color': '#FFEAA7'},
}

ADDITINAL_ZONES = ['M422. Некомплекты', 'M500. Приемка на СГП (MADU)', 'M483. Чистые автомобили']

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
        content = fig.to_html(
            full_html=False,
            include_plotlyjs=True,
            config={
                'responsive': True,
                'autosizable': True,
                'displayModeBar': True,
                },
            default_width='100%',
            default_height='700px',
            )

        return HTMLResponse(content=content)
    except Exception as e:
        logger.error(f"Ошибка создания Sankey диаграммы: {e}")
        return HTMLResponse(content=f"<h3>Ошибка: {str(e)}</h3>")


def prepare_sankey_data(df: pd.DataFrame, date: str, allowed_zones: list) -> dict:
    """

    """
    allowed_zones = allowed_zones + ADDITINAL_ZONES
    logger.info(f'{__name__} allowed extended {allowed_zones}')
	
    # Фильтрация по дате отчета
    target_date = pd.Timestamp(date).date()	
    df_day = df[df['exit_time'].dt.date == target_date].copy()
    
	# Фильтрация, отчетная зона существует или в Точки Регистрации, или next_zone
    df_filtered = df_day[
        df_day['next_zone'].isin(allowed_zones) |
        df_day['Точка регистрации'].isin(allowed_zones)
        ]

    if df_filtered.empty:
        return {'nodes': [], 'links': [], 'message': 'Нет данных'}
    
    # Сортировка
    df_transitions = df_filtered.sort_values(['Заказ', 'exit_time'])
    
    # Группировка и подсчет переходов
    transition_counts = (df_transitions
                        .groupby(['Точка регистрации', 'next_zone'])
                        .size()
                        .reset_index(name='count'))
    
    # Получаем все уникальные зоны в виде: 
    # Точка регистрации next_zone  count
    # Москва             Питер       2
    # Москва             Казань      1
    # Питер              Москва      1
    
    all_zones = pd.concat([
        transition_counts['Точка регистрации'], 
        transition_counts['next_zone']
    ]).unique()
	
    logger.info(f'{__name__} transition_counts {transition_counts}')
    logger.info(f'{__name__} all zones {all_zones}')
    
    # Считаем входы и выходы с помощью groupby
	# Получаем словарь типа {'Москва': 2, 'Питер': 2, 'Казань': 1}
    out_stats = (transition_counts
                .groupby('Точка регистрации')['count']
                .sum()
                .to_dict())
    
    in_stats = (transition_counts
               .groupby('next_zone')['count']
               .sum()
               .to_dict())
    
    logger.info(f'{__name__} in_stats {in_stats} \n out_stats {out_stats}')
    
	# 8. Создаем узлы
    nodes = []
    node_to_index = {}
    
    for i, zone in enumerate(sorted(allowed_zones)):
        stats_in = in_stats.get(zone, 0)
        stats_out = out_stats.get(zone, 0)
        label = f"{zone}<br> (вх:{stats_in}, вых:{stats_out})"
        nodes.append(label)
        node_to_index[zone] = i
    
    logger.info(f'{__name__}  \n  >>> nodes {nodes} \n >>> node_to_index {node_to_index}')
    
	# 9. Создаем связи
    links = []
    for _, row in transition_counts.iterrows():
        source = row['Точка регистрации']
        target = row['next_zone']
        if (source in allowed_zones and target in allowed_zones and source in node_to_index and target in node_to_index):
            links.append({
            'source': node_to_index[source],
            'target': node_to_index[target],
            'value': row['count']
        })
    logger.info(f'{__name__} links {links}')
    return {'nodes': nodes, 'links': links, 'message': None}


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

    zone_names = []

    for label in node_labels:
        # Извлекаем имя зоны из метки (до <br>)
        zone_name = label.split('<br>')[0]
        zone_names.append(zone_name)

    # Определяем позиции и цвета для каждой зоны
    node_positions = []
    node_colors = []
    
    for zone_name in zone_names:
        if zone_name in ZONE_POSITIONS:
            pos = ZONE_POSITIONS[zone_name]
            node_positions.append([pos['x'], pos['y']])
            node_colors.append(pos['color'])
            logger.info(f"Зона '{zone_name}' positions x {pos['x']} y {pos['y']}")
        else:
            # Если зона не найдена в словаре, используем случайные координаты и цвет
            logger.warning(f"Зона '{zone_name}' не найдена в ZONE_POSITIONS, используются случайные координаты")
            node_positions.append([random.uniform(0.1, 0.9), random.uniform(0.1, 0.9)])
            node_colors.append(f'rgba({random.randint(100,200)}, {random.randint(100,200)}, {random.randint(100,200)}, 0.8)')

    fig = go.Figure(data=[go.Sankey(
        node=dict(
            pad=15,
            thickness=20,
            line=dict(color="black", width=0.5),
            label=node_labels,
            color=node_colors,
            x=[pos[0] for pos in node_positions],
            y=[pos[1] for pos in node_positions]
        ),
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
        autosize=True, width=None, height=700, margin=dict(l=50, r=50, t=80, b=50)
    )
    return fig

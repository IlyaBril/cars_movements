import pandas as pd
import logging
import plotly.graph_objects as go
import json
import random
from typing import List, Dict, Optional, Tuple
from collections import defaultdict
from datetime import datetime
from app.db.repository import MovementRepository, GroupRepository
from app.db.database import SQLiteSession, PostgresSession
from app.services.data_service import DataService

logger = logging.getLogger(__name__)

ENABLE_CALIBRATION = True

ZONES_POSITIONS = {
    'M150. Выход с линии DKD Off': {'x': 0.01, 'y': 0.3, 'color': '#FFEAA7'},
    'M151. Выход с линии DKD+': {'x': 0.01, 'y': 0.8, 'color': '#FFEAA7'},
    'БелЗона_FORI': {'x': 0.1, 'y': 0.7, 'color': '#FFEAA7'},
    'Качество': {'x': 0.15, 'y': 0.2, 'color': '#FFEAA7'},   
    'M440. GRT': {'x': 0.2, 'y': 0.5, 'color': '#FF6B6B'},
    'М444_М446 Валидация': {'x': 0.3, 'y': 0.5, 'color': '#45B7D1'},
    'M450. Контроль электрики': {'x': 0.6, 'y': 0.2, 'color': '#DDA0DD'},
    'M470. Передача на СГП (BLAN)': {'x': 0.8, 'y': 0.2, 'color': '#DDA0DD'}, 
    'ТиД': {'x': 0.8, 'y': 0.7, 'color': '#4ECDC4'},
    'M471. Отказ по качеству': {'x': 0.6, 'y': 0.6, 'color': '#96CEB4'},
    'M445. Зона выборочного контроля': {'x': 0.45, 'y': 0.6, 'color': '#FFEAA7'},
    'M422. Некомплекты': {'x': 0.89, 'y': 0.87, 'color': '#FFEAA7'},
    'M500. Приемка на СГП (MADU)': {'x': 0.95, 'y': 0.3, 'color': '#FFEAA7'},
    'M483. Чистые автомобили': {'x': 0.95, 'y': 0.5, 'color': '#FFEAA7'},
    'M412. Ретрофит Телематика': {'x': 0.9, 'y': 0.1, 'color': '#FFEAA7'},
    'calibration': {'x': -0.1, 'y': 0.5, 'color': '#FFFFF0'}, 
}


class SankeyService:
    """Сервис для подготовки данных Sankey диаграммы"""
    
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

    def get_zone_attributes(self, group_name):
        zone_attributes = self._movement_repo.get_zone_attributes(group_name)       
        return zone_attributes


    def save_colors_positions(self, zone_type, positions):
        positions = {
            label.split('<br>', 1)[0].strip(): item
            for label, item in positions.items()
            }
     
        sucsess, saved = self._movement_repo.save_color_positions_db(zone_type, positions)
        return sucsess, saved
     
    

def prepare_sankey_data(df: pd.DataFrame, date: str, allowed_zones: list) -> dict:
    """
    df - таблица, фильтрованная по условию: если есть движение VIN в этот день,
    выгружаем все движения по этому VIN за все дни.
    allowed_zones - Точки регистрации, для которых нужно построить sankey диаграмму
    """
    # Фильтрация по дате отчета
    target_date = pd.Timestamp(date).date()

    # Подготовка DataFrame для подсчета входа и выхода.
    # Вход в Точку регистрации происходит во время регистрации этой точки,
    # выход — во время регистрации следующей точки.
    df_enter = df[df['Дата'].dt.date == target_date]
    df_exit = df[df['exit_time'].dt.date == target_date]

    # Подсчет количества переходов между точками за день.
    # Фильтрация происходит по df_exit, т.к. выход из текущей точки в следующую
    # происходит во время входа в следующую точку.
    # Точка регистрации  next_zone   count
    # Москва             Питер       2
    # Москва             Казань      1
    # Питер              Москва      1

    transition_counts = (df_exit
                         .sort_values(['Заказ', 'exit_time'])
                         .groupby(['Точка регистрации', 'next_zone'])
                         .size()
                         .reset_index(name='count'))

    # Считаем входы и выходы: {'Москва': 2, 'Питер': 2, 'Казань': 1}
    out_stats = df_exit['Точка регистрации'].value_counts().to_dict()
    in_stats = df_enter['Точка регистрации'].value_counts().to_dict()
    logger.info(f'{__name__} in_stats {in_stats} \n out_stats {out_stats}')

    # Получаем все уникальные зоны
    all_zones = set(transition_counts['Точка регистрации']) | set(transition_counts['next_zone'])
    zone_names = sorted(set(allowed_zones) & all_zones)


    # Чистые имена зон (для позиций/цветов) + индексы
    node_to_index = {zone: i for i, zone in enumerate(zone_names)}

    # Метки с статистикой — то, что идёт в node.label
    node_labels = [
        f"{zone}<br> (вх:{in_stats.get(zone, 0)}, вых:{out_stats.get(zone, 0)})"
        for zone in zone_names
    ]

    # Сразу собираем плоские списки для go.Sankey.link
    sources, targets, values = [], [], []
    for _, row in transition_counts.iterrows():
        src, dst = row['Точка регистрации'], row['next_zone']
        if src in node_to_index and dst in node_to_index:
            sources.append(node_to_index[src])
            targets.append(node_to_index[dst])
            values.append(row['count'])

    logger.info(f'{__name__} sources {sources} targets {targets} values {values}')

    sankey_data = {
        'zone_names':  zone_names,
        'node_labels': node_labels,
        'sources':     sources,
        'targets':     targets,
        'values':      values,
        'message':     None,
    }
    # ============ КАЛИБРОВКА ============
    if ENABLE_CALIBRATION:
        sankey_data = add_calibration_node(sankey_data, calibration_value=500)
    # ====================================

    return sankey_data

def get_positions_colors(zone_names):
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

    return node_positions, node_colors


def get_positions_colors_from_obj(zone_names, zone_type):
    service = SankeyService()
    node_positions = []
    node_colors = []

    with service:
        report = service.get_zone_attributes(zone_type)
        zones_by_name = {z.name: z for z in report.report_zones}
        logger.info(f'{__name__} zones_by_name {zones_by_name} \n zone_names {zone_names}')
        for zone_name in zone_names:
            zone = zones_by_name.get(zone_name)

            if zone is not None and zone.x is not None and zone.y is not None:
                node_positions.append([zone.x, zone.y])
                node_colors.append(zone.color)
                logger.info(f"Зона '{zone_name}' positions x {zone.x} y {zone.y}")
            else:
                logger.warning(
                    f"Зона '{zone_name}' не найдена в отчёте или без координат, "
                    f"используются случайные координаты"
                )
                node_positions.append([
                    random.uniform(0.1, 0.9),
                    random.uniform(0.1, 0.9),
                ])
                node_colors.append(
                    f'rgba({random.randint(100, 200)}, '
                    f'{random.randint(100, 200)}, '
                    f'{random.randint(100, 200)}, 0.8)'
                )

    return node_positions, node_colors


def get_link_colors(sources: list, node_colors: list, opacity: float = 0.4) -> list:
    """
    Определяет цвета для связей на основе цвета узлов-источников
    
    Args:
        sources: список индексов узлов-источников для каждой связи
        node_colors: список цветов всех узлов
        opacity: прозрачность (0.0 - 1.0), по умолчанию 0.4
    
    Returns:
        list: список цветов для каждой связи
    """
    link_colors = []
    
    for src_idx in sources:
        # Проверяем, что индекс существует в списке цветов узлов
        if src_idx < len(node_colors):
            node_color = node_colors[src_idx]
            
            # Если цвет в формате rgba, меняем прозрачность
            if isinstance(node_color, str) and node_color.startswith('rgba'):
                # Разбиваем строку rgba(r,g,b,a) и заменяем alpha
                parts = node_color.replace('rgba(', '').replace(')', '').split(',')
                if len(parts) == 4:
                    r, g, b, _ = parts
                    link_colors.append(f'rgba({r.strip()}, {g.strip()}, {b.strip()}, {opacity})')
                else:
                    link_colors.append(node_color)
            # Если цвет в формате HEX, используем его как есть
            elif isinstance(node_color, str) and node_color.startswith('#'):
                link_colors.append(node_color)
            else:
                # Для других форматов - стандартный синий
                link_colors.append(f'rgba(100, 100, 255, {opacity})')
        else:
            # Если индекс не найден - стандартный синий
            link_colors.append(f'rgba(100, 100, 255, {opacity})')
    
    return link_colors


# ============ НОВАЯ ФУНКЦИЯ ДЛЯ ДОБАВЛЕНИЯ КАЛИБРОВКИ ============
def add_calibration_node(sankey_data: dict, calibration_value: int = 400) -> dict:
    """
    Добавляет калибровочный узел и связь для фиксации масштаба диаграммы.
    
    """
    if not sankey_data['values']:
        return sankey_data

    logger.info(f'{__name__} before calibration: {sankey_data}')

    result = {
        'zone_names':  ['calibration'] + sankey_data['zone_names'],
        'node_labels': ['calibration'] + sankey_data['node_labels'],
        # все существующие индексы сдвигаются на +1
        'sources': [s + 1 for s in sankey_data['sources']],
        'targets': [t + 1 for t in sankey_data['targets']],
        'values':  list(sankey_data['values']),
        'message': sankey_data.get('message'),
    }

    # калибровочная связь: узел 0 -> узел 1 (первый реальный узел)
    if len(result['zone_names']) > 1:
        result['sources'].append(0)
        result['targets'].append(1)
        result['values'].append(calibration_value)

    logger.info(f'{__name__} after calibration: {result}')
    return result
# ================================================================


def create_sankey_chart(
    df: pd.DataFrame,
    date: str,
    allowed_zones: list,
    zone_type: str,
    ) -> go.Figure:

    sankey_data = prepare_sankey_data(df, date, allowed_zones)
    logger.info(f'{__name__} sankey_data {sankey_data}')
    #{
    #   'zone_names': zone_names,      # для get_positions_colors_from_obj
    #   'node_labels': node_labels,    # для node.label
    #   'sources': sources,            # для link.source
    #   'targets': targets,            # для link.target
    #   'values': values,              # для link.value
    #   'message': None,
    #}
    
    # Пустая диаграмма, если нет связей
    if not sankey_data['values']:
        fig = go.Figure()
        fig.update_layout(
            title={'text': f'Нет данных для отображения за {date}', 'y': 0.5, 'x': 0.5},
            height=400,
        )
        return fig

    zone_names  = sankey_data['zone_names']
    node_labels = sankey_data['node_labels']
    sources     = sankey_data['sources']
    targets     = sankey_data['targets']
    values      = sankey_data['values']

    # Определяем позиции и цвета для каждой зоны
    node_positions, node_colors = get_positions_colors_from_obj(zone_names, zone_type)

    # Цвета для связей
    link_colors = get_link_colors(sources, node_colors, opacity=0.4)

    fig = go.Figure(data=[go.Sankey(
        node=dict(
            pad=15,
            thickness=10,
            line=dict(color="black", width=0.5),
            label=node_labels,
            color=node_colors,
            x=[pos[0] for pos in node_positions],
            y=[pos[1] for pos in node_positions],
        ),
        link=dict(
            source=sources,
            target=targets,
            value=values,
            color=link_colors,
        ),
    )])

    fig.update_layout(
        autosize=True, width=None, height=400, margin=dict(l=20, r=20, t=60, b=20)
    )
    return fig

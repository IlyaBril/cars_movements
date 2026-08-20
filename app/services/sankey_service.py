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

ENABLE_CALIBRATION = True  # Глобальная переменная в начале файла

ZONE_POSITIONS = {
    # Основные зоны
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
    'M422. Некомплекты': {'x': 0.95, 'y': 0.7, 'color': '#FFEAA7'},
    'M500. Приемка на СГП (MADU)': {'x': 0.95, 'y': 0.3, 'color': '#FFEAA7'},
    'M483. Чистые автомобили': {'x': 0.95, 'y': 0.5, 'color': '#FFEAA7'},
    'calibration': {'x': -0.1, 'y': 0.5, 'color': 'rgba(0,0,0,0)'}, 
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


def prepare_sankey_data(df: pd.DataFrame, date: str, allowed_zones: list) -> dict:
    """

    """
    
	
    # Фильтрация по дате отчета
    target_date = pd.Timestamp(date).date()	
    
    
	# Фильтрация, отчетная зона существует или в Точки Регистрации, или next_zone
    df_filtered = df[
        df['next_zone'].isin(allowed_zones) |
        df['Точка регистрации'].isin(allowed_zones)
        ]

    if df_filtered.empty:
        return {'nodes': [], 'links': [], 'message': 'Нет данных'}
    
    # Подготовка DataFrame для подсчета входа и выхода
    # Вход в Точку регистрации происходит во время регистрации этой точки
    # Выход из Точки регистрации происходит во время регистрации следующей точки

    df_enter = df[df['Дата'].dt.date == target_date].copy()
    df_exit = df[df['exit_time'].dt.date == target_date].copy()
      
    # Подсчет количесива переходов между точками за день
    # Фильтрация происходит по df_exit, т.к. выход из текущей точки в следующую
    # происходит во время входа в следующую точку
 
    df_transitions = df_exit.sort_values(['Заказ', 'exit_time'])
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

    out_stats = (df_exit['Точка регистрации']
                .value_counts()
                .to_dict())
    
    in_stats = (df_enter['Точка регистрации']
               .value_counts()
               .to_dict())
    
    logger.info(f'{__name__} in_stats {in_stats} \n out_stats {out_stats}')
    allowed_zones = list(set(allowed_zones) & set(all_zones))
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



# ============ ФУНКЦИЯ ДЛЯ ОПРЕДЕЛЕНИЯ ЦВЕТОВ СВЯЗЕЙ ============
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
# ================================================================



# ============ НОВАЯ ФУНКЦИЯ ДЛЯ ДОБАВЛЕНИЯ КАЛИБРОВКИ ============
def add_calibration_node(sankey_data: dict, calibration_value: int = 400) -> dict:
    """
    Добавляет калибровочный узел и связь для фиксации масштаба диаграммы
    
    Args:
        sankey_data: словарь с данными {'nodes': [...], 'links': [...]}
        calibration_value: фиксированное значение для калибровки (по умолчанию 300)
    
    Returns:
        dict: обновленный словарь с добавленным калибровочным узлом и связью
    """
    if not sankey_data['nodes'] or not sankey_data['links']:
        return sankey_data

    logger.info(f'{__name__} sankey data {sankey_data}')
    
    # Создаем копию данных
    result = {
        'nodes': sankey_data['nodes'].copy(),
        'links': sankey_data['links'].copy(),
        'message': sankey_data.get('message')
    }
    
    # Добавляем калибровочный узел как СТРОКУ (не словарь!)
    result['nodes'].insert(0, "calibration")
    
    
    # Обновляем индексы в связях (+1)
    updated_links = []
    for link in result['links']:
        updated_links.append({
            'source': link['source'] + 1,
            'target': link['target'] + 1,
            'value': link['value']
        })
    result['links'] = updated_links
    
    # Добавляем калибровочную связь
    if len(result['nodes']) > 1:
        calibration_link = {
            'source': 0,
            'target': 1,
            'value': calibration_value,
        }
        result['links'].append(calibration_link)
    logger.info(f'{__name__} result  {result}')
    
    return result
# ================================================================


def create_sankey_chart(
    df: pd.DataFrame,
    date: str,
    allowed_zones: list,
    zone_type: str,
    ) -> go.Figure:

    sankey_data = prepare_sankey_data(df, date, allowed_zones)


# ============ ВЫЗОВ ФУНКЦИИ КАЛИБРОВКИ ============
# Для ОТКЛЮЧЕНИЯ калибровки просто закомментируйте следующую строку
# или замените на: sankey_data = sankey_data
    if ENABLE_CALIBRATION:
        sankey_data = add_calibration_node(sankey_data, calibration_value=500)
# ===================================================
    
    
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


# ============ ПОЛУЧАЕМ ЦВЕТА ДЛЯ СВЯЗЕЙ ============
    link_colors = get_link_colors(sources, node_colors, opacity=0.4)
# ====================================================



    fig = go.Figure(data=[go.Sankey(
        node=dict(
            pad=15,
            thickness=10,
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
            color=link_colors,
            )
    )])

    fig.update_layout(
        autosize=True, width=None, height=400, margin=dict(l=20, r=20, t=60, b=20)
    )
    return fig

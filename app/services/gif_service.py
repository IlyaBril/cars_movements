import os
import tempfile
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import imageio.v2 as imageio
from PIL import Image
import numpy as np
from app.services.data_service import DataService
from app.services.sankey_service import create_sankey_chart, prepare_sankey_data, add_calibration_node, get_link_colors
from app.services.sankey_service import ZONE_POSITIONS, ENABLE_CALIBRATION
import random

logger = logging.getLogger(__name__)

class GifService:
    """Сервис для создания GIF-отчетов динамики движения (оптимизированный)"""
    
    def __init__(self):
        self.data_service = DataService()
        self._cached_data = None
        self._cached_zones = None
        self._cached_mapping = None
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.data_service.__exit__(exc_type, exc_val, exc_tb)
    
    def _load_and_prepare_data(self, date: str, zone_type: str) -> tuple:
        """
        Однократная загрузка и подготовка данных
        """
        if self._cached_data is None:
            with self.data_service:
                df = self.data_service.get_data(date)
                zone_to_group, allowed_zones = self.data_service._prepare_zones_and_mapping(zone_type, df)
                df_transformed = self.data_service._transform_dataframe(df, zone_to_group)
                
                self._cached_data = df_transformed
                self._cached_zones = allowed_zones
                self._cached_mapping = zone_to_group
        
        return self._cached_data, self._cached_zones, self._cached_mapping
    
    def prepare_sankey_data_for_time(
        self, 
        df: pd.DataFrame,
        current_time: datetime,
        allowed_zones: list,
        target_date: date
    ) -> dict:
        """
        Подготовка данных Sankey для конкретного момента времени
        (оптимизированная версия)
        """
        # Фильтруем данные до текущего времени
        df_snapshot = df[df['Дата'] <= current_time].copy()
        
        if df_snapshot.empty:
            return {'nodes': [], 'links': [], 'message': 'Нет данных'}
        
        # Фильтруем по разрешенным зонам
        df_filtered = df_snapshot[
            df_snapshot['next_zone'].isin(allowed_zones) |
            df_snapshot['Точка регистрации'].isin(allowed_zones)
        ]
        
        if df_filtered.empty:
            return {'nodes': [], 'links': [], 'message': 'Нет данных'}
        
        # Входы и выходы за весь период до current_time
        df_enter = df_filtered[df_filtered['Дата'].dt.date == target_date].copy()
        df_exit = df_filtered[df_filtered['exit_time'].dt.date == target_date].copy()
        
        # Подсчет переходов
        df_transitions = df_exit.sort_values(['Заказ', 'exit_time'])
        transition_counts = (df_transitions
                            .groupby(['Точка регистрации', 'next_zone'])
                            .size()
                            .reset_index(name='count'))
        
        # Все уникальные зоны
        all_zones = pd.concat([
            transition_counts['Точка регистрации'], 
            transition_counts['next_zone']
        ]).unique()
        
        # Статистика входов/выходов
        out_stats = (df_exit['Точка регистрации']
                    .value_counts()
                    .to_dict())
        
        in_stats = (df_enter['Точка регистрации']
                   .value_counts()
                   .to_dict())
        
        # Создаем узлы
        nodes = []
        node_to_index = {}
        allowed_zones = list(set(allowed_zones) & set(all_zones))
        for i, zone in enumerate(sorted(allowed_zones)):
            stats_in = in_stats.get(zone, 0)
            stats_out = out_stats.get(zone, 0)
            label = f"{zone}<br> (вх:{stats_in}, вых:{stats_out})"
            nodes.append(label)
            node_to_index[zone] = i
        
        # Создаем связи
        links = []
        for _, row in transition_counts.iterrows():
            source = row['Точка регистрации']
            target = row['next_zone']
            if (source in allowed_zones and target in allowed_zones and 
                source in node_to_index and target in node_to_index):
                links.append({
                    'source': node_to_index[source],
                    'target': node_to_index[target],
                    'value': row['count']
                })
        
        return {'nodes': nodes, 'links': links, 'message': None}
    
    def get_hourly_snapshots_optimized(
        self, 
        date: str, 
        zone_type: str = "main",
        interval_minutes: int = 30
    ) -> tuple:
        """
        Оптимизированное получение снимков - данные загружаются один раз
        """
        target_date = pd.Timestamp(date).date()
        
        # Однократная загрузка и подготовка данных
        df_transformed, allowed_zones, _ = self._load_and_prepare_data(date, zone_type)
        
        # Создаем временные метки для снимков (с 6:00 до 23:59)
        start_time = datetime.combine(target_date, datetime.min.time().replace(hour=6))
        end_time = datetime.combine(target_date, datetime.min.time().replace(hour=23, minute=59))
        
        snapshots = []
        current_time = start_time
        
        # Предварительная фильтрация данных по дате (для ускорения)
        df_day = df_transformed[
            (df_transformed['Дата'].dt.date == target_date) |
            (df_transformed['exit_time'].dt.date == target_date)
        ].copy()
        
        while current_time <= end_time:
            # Подготавливаем данные для текущего момента
            sankey_data = self.prepare_sankey_data_for_time(
                df_day,
                current_time,
                allowed_zones,
                target_date
            )
            
            # Подсчет общего количества переходов
            total_flow = sum(link['value'] for link in sankey_data.get('links', []))
            
            snapshots.append({
                'time': current_time.strftime("%H:%M"),
                'sankey_data': sankey_data,
                'total_flow': total_flow,
                'nodes_count': len(sankey_data.get('nodes', []))
            })
            
            current_time += timedelta(minutes=interval_minutes)
        
        return snapshots, allowed_zones
    
    def create_gif_report(
        self,
        date: str,
        zone_type: str = "main",
        interval_minutes: int = 30,
        output_path: Optional[str] = None,
        duration: float = 1.0,
        max_frames: int = 24
    ) -> Optional[str]:
        """
        Создает GIF-отчет динамики движения (оптимизированный)
        """
        # Получаем снимки (данные загружаются один раз)
        snapshots, allowed_zones = self.get_hourly_snapshots_optimized(
            date, zone_type, interval_minutes
        )
        
        if not snapshots:
            logger.warning("Нет данных для создания GIF")
            return None
        
        # Фильтруем только снимки с данными
        valid_snapshots = [s for s in snapshots if s['sankey_data'].get('nodes')]
        
        if not valid_snapshots:
            logger.warning("Нет снимков с данными для создания GIF")
            return None
        
        # Ограничиваем количество кадров
        if len(valid_snapshots) > max_frames:
            step = max(1, len(valid_snapshots) // max_frames)
            valid_snapshots = valid_snapshots[::step]
        
        # Создаем временную папку для кадров
        with tempfile.TemporaryDirectory() as temp_dir:
            frame_paths = []
            
            for i, snapshot in enumerate(valid_snapshots):
                # Создаем диаграмму для текущего снимка
                fig = self._create_snapshot_figure(
                    snapshot, 
                    date, 
                    zone_type,
                    allowed_zones,
                    i,
                    len(valid_snapshots)
                )
                
                # Сохраняем кадр как изображение
                frame_path = os.path.join(temp_dir, f"frame_{i:03d}.png")
                fig.write_image(frame_path, width=1200, height=800, scale=1.2)
                frame_paths.append(frame_path)
            
            # Создаем GIF
            if output_path is None:
                output_path = os.path.join(
                    tempfile.gettempdir(),
                    f"sankey_dynamics_{date}_{zone_type}.gif"
                )
            
            # Читаем изображения и создаем GIF
            images = []
            for frame_path in frame_paths:
                img = Image.open(frame_path)
                if img.mode == 'RGBA':
                    img = img.convert('RGB')
                images.append(img)
            
            # Сохраняем GIF
            if images:
                images[0].save(
                    output_path,
                    save_all=True,
                    append_images=images[1:],
                    duration=duration * 1000,
                    loop=0,
                    optimize=True,
                    quality=85
                )
                
                logger.info(f"GIF создан: {output_path}, кадров: {len(images)}")
                return output_path
        
        return None
    
    def _create_snapshot_figure(
        self, 
        snapshot: dict, 
        date: str, 
        zone_type: str,
        allowed_zones: list,
        frame_index: int,
        total_frames: int
    ) -> go.Figure:
        """Создает фигуру Plotly для отдельного снимка"""
        from app.services.sankey_service import ZONE_POSITIONS, ENABLE_CALIBRATION, add_calibration_node, get_link_colors
        import random
        
        sankey_data = snapshot['sankey_data']
        time_label = snapshot['time']
        total_flow = snapshot.get('total_flow', 0)
        
        # Если нет данных, создаем пустую фигуру с сообщением
        if not sankey_data.get('nodes') or not sankey_data.get('links'):
            fig = go.Figure()
            fig.update_layout(
                title={
                    'text': f'Динамика движения<br>{date} {time_label}<br>Нет данных',
                    'y': 0.5,
                    'x': 0.5
                },
                height=500,
                annotations=[
                    dict(
                        text=f'Прогресс: {frame_index + 1}/{total_frames}',
                        x=0.5,
                        y=0.02,
                        xref='paper',
                        yref='paper',
                        showarrow=False,
                        font=dict(size=12, color='gray')
                    )
                ]
            )
            return fig
        
        # Если калибровка включена, добавляем ее
        if ENABLE_CALIBRATION:
            sankey_data = add_calibration_node(sankey_data, calibration_value=500)
        
        node_labels = sankey_data['nodes']
        sources, targets, values = [], [], []
        
        for link in sankey_data['links']:
            sources.append(link['source'])
            targets.append(link['target'])
            values.append(link['value'])
        
        # Определяем позиции и цвета для каждой зоны
        node_positions = []
        node_colors = []
        
        for label in node_labels:
            zone_name = label.split('<br>')[0]
            if zone_name in ZONE_POSITIONS:
                pos = ZONE_POSITIONS[zone_name]
                node_positions.append([pos['x'], pos['y']])
                node_colors.append(pos['color'])
            else:
                node_positions.append([random.uniform(0.1, 0.9), random.uniform(0.1, 0.9)])
                node_colors.append(f'rgba({random.randint(100,200)}, {random.randint(100,200)}, {random.randint(100,200)}, 0.8)')
        
        link_colors = get_link_colors(sources, node_colors, opacity=0.4)
        
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
        
        # Информация о времени и прогрессе
        fig.update_layout(
            title={
                'text': f'Динамика движения<br>{date} {time_label}',
                'y': 0.95,
                'x': 0.5,
                'xanchor': 'center',
                'yanchor': 'top',
                'font': dict(size=16)
            },
            annotations=[
                dict(
                    text=f'Всего переходов: {total_flow}  |  Кадр {frame_index + 1}/{total_frames}',
                    x=0.5,
                    y=0.02,
                    xref='paper',
                    yref='paper',
                    showarrow=False,
                    font=dict(size=14, color='#333')
                )
            ],
            autosize=True,
            width=None,
            height=500,
            margin=dict(l=20, r=20, t=80, b=40),
            plot_bgcolor='white',
            paper_bgcolor='white'
        )
        
        return fig

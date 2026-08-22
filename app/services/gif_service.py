import os
import tempfile
import logging
from datetime import datetime, timedelta
from typing import List, Optional
import pandas as pd
import plotly.graph_objects as go
from PIL import Image
from app.services.data_service import DataService
from app.services.sankey_service import ZONE_POSITIONS, ENABLE_CALIBRATION, add_calibration_node, get_link_colors

logger = logging.getLogger(__name__)

class GifService:
    """Сервис для создания GIF-отчетов динамики движения"""
    
    def __init__(self):
        self.data_service = DataService()


    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.data_service.__exit__(exc_type, exc_val, exc_tb)
    
    def prepare_sankey_data_for_time(
        self, 
        df: pd.DataFrame,
        current_time: datetime,
        allowed_zones: list,
        target_date: date
    ) -> dict:
        """Подготовка данных Sankey для конкретного момента времени"""
        df_enter = df[df['Дата'] <= current_time].copy()
        df_exit = df[df['exit_time'] <= current_time].copy()
        
        df_enter = df_enter[df_enter['Дата'].dt.date == target_date].copy()
        df_exit = df_exit[df_exit['exit_time'].dt.date == target_date].copy()
        
        df_transitions = df_exit.sort_values(['Заказ', 'exit_time'])
        transition_counts = (df_transitions
                            .groupby(['Точка регистрации', 'next_zone'])
                            .size()
                            .reset_index(name='count'))
        
        all_zones = pd.concat([
            transition_counts['Точка регистрации'], 
            transition_counts['next_zone']
        ]).unique()
        
        out_stats = (df_exit['Точка регистрации']
                    .value_counts()
                    .to_dict())
        
        in_stats = (df_enter['Точка регистрации']
                   .value_counts()
                   .to_dict())
        
        nodes = []
        node_to_index = {}
        allowed_zones = list(set(allowed_zones) & set(all_zones))
        for i, zone in enumerate(sorted(allowed_zones)):
            stats_in = in_stats.get(zone, 0)
            stats_out = out_stats.get(zone, 0)
            label = f"{zone}<br> (вх:{stats_in}, вых:{stats_out})"
            nodes.append(label)
            node_to_index[zone] = i
        
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
        """Получение снимков с однократной загрузкой данных"""
        target_date = pd.Timestamp(date).date()
        
        # Загрузка данных
        with self.data_service:
            df = self.data_service.get_data(date)
            zone_to_group, allowed_zones = self.data_service._prepare_zones_and_mapping(zone_type, df)
            df_transformed = self.data_service._transform_dataframe(df, zone_to_group)
        
        start_time = datetime.combine(target_date, datetime.min.time().replace(hour=6))
        end_time = datetime.combine(target_date, datetime.min.time().replace(hour=23, minute=59))
        
        snapshots = []
        current_time = start_time
        
        while current_time <= end_time:
            sankey_data = self.prepare_sankey_data_for_time(
                df_transformed,
                current_time,
                allowed_zones,
                target_date
            )
            
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
        """Создает GIF-отчет динамики движения"""
        snapshots, allowed_zones = self.get_hourly_snapshots_optimized(
            date, zone_type, interval_minutes
        )
        
        if not snapshots:
            logger.warning("Нет данных для создания GIF")
            return None
        
        valid_snapshots = [s for s in snapshots if s['sankey_data'].get('nodes')]
        
        if not valid_snapshots:
            logger.warning("Нет снимков с данными для создания GIF")
            return None
        
        if len(valid_snapshots) > max_frames:
            step = max(1, len(valid_snapshots) // max_frames)
            valid_snapshots = valid_snapshots[::step]
        
        with tempfile.TemporaryDirectory() as temp_dir:
            frame_paths = []
            
            for i, snapshot in enumerate(valid_snapshots):
                fig = self._create_snapshot_figure(
                    snapshot, 
                    date, 
                    zone_type,
                    allowed_zones,
                    i,
                    len(valid_snapshots)
                )
                
                frame_path = os.path.join(temp_dir, f"frame_{i:03d}.png")
                fig.write_image(frame_path, width=1200, height=800, scale=1.2)
                frame_paths.append(frame_path)
            
            if output_path is None:
                output_path = os.path.join(
                    tempfile.gettempdir(),
                    f"sankey_dynamics_{date}_{zone_type}.gif"
                )
            
            images = []
            for frame_path in frame_paths:
                img = Image.open(frame_path)
                if img.mode == 'RGBA':
                    img = img.convert('RGB')
                images.append(img)
            
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
        import random
        
        sankey_data = snapshot['sankey_data']
        time_label = snapshot['time']
        total_flow = snapshot.get('total_flow', 0)
        
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
        
        if ENABLE_CALIBRATION:
            sankey_data = add_calibration_node(sankey_data, calibration_value=500)
        
        node_labels = sankey_data['nodes']
        sources, targets, values = [], [], []
        
        for link in sankey_data['links']:
            sources.append(link['source'])
            targets.append(link['target'])
            values.append(link['value'])
        
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

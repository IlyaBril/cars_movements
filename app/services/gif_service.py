import os
import tempfile
import imageio_ffmpeg
import logging
import pandas as pd
import plotly.graph_objects as go
import subprocess

from datetime import datetime, timedelta, date
from typing import List, Optional
from PIL import Image

from app.services.data_service import DataService
from app.services.sankey_service import get_link_colors, prepare_sankey_data, SankeyService


logger = logging.getLogger(__name__)

class GifService:
    """Сервис для создания GIF-отчетов динамики движения"""
    
    def __init__(self):
        self.data_service = DataService()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.data_service.__exit__(exc_type, exc_val, exc_tb)
    
    def get_hourly_snapshots_optimized(
        self, 
        date: str, 
        zone_type: str = "main",
        interval_minutes: int = 30,
        filters: dict | None = None,
    ) -> tuple:
        """Получение снимков с однократной загрузкой данных"""

        target_date = pd.Timestamp(date).date()
        
        # Загрузка данных
        with self.data_service:
            df = self.data_service.get_data(date, filters=filters)
            zone_to_group, allowed_zones = self.data_service._prepare_zones_and_mapping(zone_type, df)
            df_transformed = self.data_service._transform_dataframe(df, zone_to_group)
        
        start_time = datetime.combine(
            target_date, datetime.min.time().replace(hour=6))
        end_time = datetime.combine(
            target_date, datetime.min.time().replace(hour=23, minute=59))
        
        snapshots = []
        current_time = start_time
        
        while current_time <= end_time:
            sankey_data = prepare_sankey_data(
                df_transformed,
                target_date,
                allowed_zones,
                current_time,
            )
            
            total_flow = sum(
                link['value'] for link in sankey_data.get('links', [])
                )
            
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
        max_frames: int = 24,
        convert_to_mp4: bool = True,          # <-- новый флаг
        crf: int = 23,                        # качество H.264
        filters: dict | None = None,
    ) -> Optional[str]:
        """
        Создаёт отчёт динамики движения.

        Если convert_to_mp4=True — сначала собирает GIF, затем конвертирует
        его в MP4 и возвращает путь к MP4. Иначе — путь к GIF.
        """

        snapshots, allowed_zones = self.get_hourly_snapshots_optimized(
            date, zone_type, interval_minutes, filters=filters
        )

        if not snapshots:
            logger.warning("Нет данных для создания отчёта")
            return None

        valid_snapshots = [
            s for s in snapshots if s['sankey_data'].get('node_labels')
        ]
        if not valid_snapshots:
            logger.warning("Нет снимков с данными")
            return None

        if len(valid_snapshots) > max_frames:
            step = max(1, len(valid_snapshots) // max_frames)
            valid_snapshots = valid_snapshots[::step]

        with tempfile.TemporaryDirectory() as temp_dir:
            frame_paths = []

            for i, snapshot in enumerate(valid_snapshots):
                fig = self._create_snapshot_figure(
                    snapshot, date, zone_type, allowed_zones,
                    i, len(valid_snapshots),
                )
                frame_path = os.path.join(temp_dir, f"frame_{i:03d}.png")
                fig.write_image(frame_path, width=1200, height=800, scale=1.2)
                frame_paths.append(frame_path)

            if not frame_paths:
                return None

            # ---- 1. Собираем GIF во временный файл ----
            gif_path = os.path.join(temp_dir, "report.gif")

            images = []
            for frame_path in frame_paths:
                img = Image.open(frame_path)
                if img.mode == 'RGBA':
                    img = img.convert('RGB')
                images.append(img)

            images[0].save(
                gif_path,
                save_all=True,
                append_images=images[1:],
                duration=duration * 1000,
                loop=0,
                optimize=True,
                quality=85,
            )
            logger.info(f"GIF собран: {gif_path}, кадров: {len(images)}")

            # ---- 2. Если нужен MP4 — конвертируем ----
            if not convert_to_mp4:
                final_path = output_path or os.path.join(
                    tempfile.gettempdir(),
                    f"sankey_dynamics_{date}_{zone_type}.gif",
                )
                # копируем из temp_dir, т.к. он сейчас удалится
                import shutil
                shutil.copy2(gif_path, final_path)
                return final_path

            if output_path is None:
                output_path = os.path.join(
                    tempfile.gettempdir(),
                    f"sankey_dynamics_{date}_{zone_type}.mp4",
                )

            self._convert_gif_to_mp4(gif_path, output_path, crf=crf)
            logger.info(f"MP4 создан: {output_path}")
            return output_path

    
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

        logger.info(f' node_labels {sankey_data['node_labels']}')
        
        if not sankey_data.get('node_labels'):# or not sankey_data.get('links'):
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
            
        node_labels = sankey_data['node_labels']
        zone_names  = sankey_data['zone_names']
        sources     = sankey_data['sources']
        targets     = sankey_data['targets']
        values      = sankey_data['values']

        # Определяем позиции и цвета для каждой зоны
        service = SankeyService()
        with service:
            node_position_x, node_position_y, node_colors = service.get_positions_colors_from_obj(
                zone_names, zone_type)

        logger.info(f'\n call get_positions_colors'
                    f'\n node_position_x {node_position_x}'
                    f'\n node_position_y {node_position_y}'
                    f'\n node_colors {node_colors}')
            
        link_colors = get_link_colors(sources, node_colors, opacity=0.4)
        
        fig = go.Figure(data=[go.Sankey(
            node=dict(
                pad=15,
                thickness=10,
                line=dict(color="black", width=0.5),
                label=node_labels,
                color=node_colors,
                x=node_position_x,
                y=node_position_y,
            ),
            link=dict(
                source=sources,
                target=targets,
                value=values,
                color=link_colors,
            ),
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

    def _convert_gif_to_mp4(
        self,
        gif_path: str,
        mp4_path: str,
        crf: int = 23,
    ) -> None:
        """
        Конвертирует GIF в H.264 MP4.

        - pixel format yuv420p       — совместимость с браузерами/QuickTime
        - scale=trunc(iw/2)*2:...    — H.264 требует чётные размеры
        - +faststart                 — быстрый старт воспроизведения в вебе
        - fps из GIF                 — берётся автоматически из файла
        """
        if not os.path.exists(gif_path):
            raise FileNotFoundError(f"GIF не найден: {gif_path}")

        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()

        cmd = [
            ffmpeg_exe,
            "-y",                          # перезаписать файл
            "-i", gif_path,
            "-movflags", "+faststart",
            "-pix_fmt", "yuv420p",
            "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
            "-c:v", "libx264",
            "-crf", str(crf),
            "-preset", "medium",
            mp4_path,
        ]

        logger.debug(f"FFmpeg cmd: {' '.join(cmd)}")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            logger.error(f"FFmpeg stderr:\n{result.stderr}")
            raise RuntimeError(
                f"FFmpeg завершился с кодом {result.returncode}"
            )

        if not os.path.exists(mp4_path):
            raise RuntimeError("FFmpeg не создал MP4-файл")


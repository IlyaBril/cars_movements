import logging
import os
import random
import plotly.graph_objects as go
import pandas as pd

from datetime import datetime
from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.responses import FileResponse
from app.services.gif_service import GifService
from app.services.data_service import DataService
from app.services.sankey_service import SankeyService, ZONE_POSITIONS, prepare_sankey_data, get_link_colors, add_calibration_node, create_sankey_chart

logger = logging.getLogger(__name__)

router = APIRouter(tags=["sankey"])
templates = Jinja2Templates(directory="templates")

ENABLE_CALIBRATION = True  # Глобальная переменная в начале файла


def default_date():
    return datetime.today().strftime("%Y-%m-%d")


@router.get("/sankey")
async def sankey_page(request: Request):
    data_service = DataService()
    with data_service:
        reports = data_service.get_zones_types()
        
    return templates.TemplateResponse(
        request=request,
        name="sankey.html",
        context={
            "default_date": default_date(),
            "zone_types": reports,
        })


@router.get("/sankey-chart")
async def get_sankey_chart(
    date: str = Query(default=default_date()), 
    zone_type: str = Query(default="main")
):
    try:
        data_service = DataService()
        logger.info(f'{__name__} get sankey chart, data service done')
        with data_service:
            df = data_service.get_data(date)
            logger.info(f'{__name__} get sankey chart, data service get data df {zone_type}')
            zone_to_group, allowed_zones = data_service._prepare_zones_and_mapping(zone_type, df)
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


@router.get("/sankey-gif")
async def get_sankey_gif(
    date: str = Query(default=default_date()),
    zone_type: str = Query(default="main"),
    interval_minutes: int = Query(default=30, ge=10, le=120),
    duration: float = Query(default=1.0, ge=0.3, le=3.0),
    max_frames: int = Query(default=24, ge=5, le=50)
):
    """
    Создает GIF-отчет динамики движения за день
    
    - **date**: дата в формате YYYY-MM-DD
    - **zone_type**: тип зоны (main, etc.)
    - **interval_minutes**: интервал между кадрами (10-120 минут)
    - **duration**: длительность каждого кадра в секундах (0.3-3.0)
    - **max_frames**: максимальное количество кадров (5-50)
    """
    try:
        gif_service = GifService()
        
        with gif_service:
            start_time = datetime.now()
            
            gif_path = gif_service.create_gif_report(
                date=date,
                zone_type=zone_type,
                interval_minutes=interval_minutes,
                duration=duration,
                max_frames=max_frames
            )
            
            elapsed = (datetime.now() - start_time).total_seconds()
            logger.info(f"GIF создан за {elapsed:.2f} секунд")
            
            if gif_path and os.path.exists(gif_path):
                return FileResponse(
                    gif_path,
                    media_type="image/gif",
                    filename=f"sankey_dynamics_{date}_{zone_type}.gif"
                )
            else:
                return JSONResponse(
                    status_code=404,
                    content={"error": "Не удалось создать GIF-отчет"}
                )
    
    except Exception as e:
        logger.error(f"Ошибка создания GIF: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error": f"Ошибка: {str(e)}"}
        )


import logging
import os
import random
import plotly.graph_objects as go
import pandas as pd

from datetime import datetime
from fastapi import APIRouter, Request, Query, Body, Cookie
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.responses import FileResponse
from app.services.gif_service import GifService
from app.services.data_service import DataService
from app.services.sankey_service import SankeyService, create_snapshot_figure, prepare_sankey_data, get_link_colors, add_calibration_node, create_sankey_chart
from app.db.schemas import NodeLayoutItem, SavePositionsResponse
from app.services.filter_parser import parse_filter, FilterParseError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["sankey"])
templates = Jinja2Templates(directory="templates")

ENABLE_CALIBRATION = True  # Глобальная переменная в начале файла

COOKIE_NAME = "sankey_filters"
COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 дней


def default_date():
    return datetime.today().strftime("%Y-%m-%d")


def _read_filters_cookie(raw: str | None) -> dict:
    """Читает JSON из cookie и валидирует структуру."""
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            return {}
    except (ValueError, TypeError):
        return {}
    result = {}
    if isinstance(data.get("filters"), dict):
        result["filters"] = data["filters"]
    if isinstance(data.get("date"), str):
        result["date"] = data["date"]
    if isinstance(data.get("zone_type"), str):
        result["zone_type"] = data["zone_type"]
    return result


@router.post("/sankey-filters")
async def save_sankey_filters(
    response: Response,
    payload: dict = Body(...),
    sankey_filters: str | None = Cookie(default=None, alias=COOKIE_NAME),
):
    """
    Сохраняет настройки фильтров в cookie.
    Тело: { "filters": {...}, "date": "YYYY-MM-DD", "zone_type": "main" }
    Мержит с уже сохранённым значением, чтобы не потерять поля.
    """
    existing = _read_filters_cookie(sankey_filters)
    merged = {
        "filters": payload.get("filters", existing.get("filters", {})),
        "date": payload.get("date", existing.get("date", default_date())),
        "zone_type": payload.get("zone_type", existing.get("zone_type", "main")),
    }
    response.set_cookie(
        key=COOKIE_NAME,
        value=json.dumps(merged, ensure_ascii=False),
        max_age=COOKIE_MAX_AGE,
        httponly=False,  # фронту не обязательно читать, но не мешает
        samesite="lax",
        path="/",
    )
    return {"success": True}


@router.get("/sankey")
async def sankey_page(
    request: Request,
    sankey_filters: str | None = Cookie(default=None, alias=COOKIE_NAME),
):
    data_service = DataService()
    with data_service:
        reports = data_service.get_zones_types()
        vehicle_models = data_service.get_filter_values("VehicleModel")
        all_zones = data_service.get_filter_values("Точка_регистрации")
        # для новых фильтров добавите здесь свои get_filter_values(...)

    saved = _read_filters_cookie(sankey_filters)

    # filters — произвольный dict: {"VehicleModel": [...], "Точка_регистрации": [...], ...}
    saved_filters = saved.get("filters", {}) or {}

    default_zone = saved.get("zone_type")
    if not default_zone or default_zone not in reports:
        default_zone = reports[0] if reports else "main"

    default_date_value = saved.get("date") or default_date()

    return templates.TemplateResponse(
        request=request,
        name="sankey.html",
        context={
            "default_date": default_date_value,
            "zone_types": reports,
            "vehicle_models": vehicle_models,
            "all_zones": all_zones,
            "initial_zone_type": default_zone,
            "initial_filters": saved_filters,
        },
    )


@router.get("/sankey-chart")
async def get_sankey_chart(
    date: str = Query(default=default_date()), 
    zone_type: str = Query(default="main"),
    row_filters: str | None = Query(default=None, alias="filter")
):
    try:
        filters = parse_filter(row_filters)
    except FilterParseError as e:
        return HTMLResponse(content=f"<h3>Некорректный фильтр: {e}</h3>", status_code=400)

    
    try:
        
        data_service = DataService()
        logger.info(f'get sankey chart, data service done')
        with data_service:
            df = data_service.get_data(date, filters=filters)       
            zone_to_group, allowed_zones = data_service._prepare_zones_and_mapping(zone_type, df)
            logger.info(f'get sankey chart, \n'
                        f'zone_to_group {zone_to_group} \n'
                        f'allowed_zones {allowed_zones}')
            df = data_service._transform_dataframe(df, zone_to_group)
            if df.empty:
                return HTMLResponse(content="<h3>Нет данных за выбранную дату</h3>")

        sankey_data = prepare_sankey_data(df, date, allowed_zones)

        target_date = pd.Timestamp(date).date()
        current_time = datetime.combine(
            target_date, datetime.min.time().replace(hour=23, minute=59))



        snapshot = {
                'time': current_time.strftime("%H:%M"),
                'sankey_data': sankey_data,
                'total_flow': 1,
                'nodes_count': 1,
            }
        #fig = create_sankey_chart(df, date, allowed_zones, zone_type)
        fig = create_snapshot_figure(
            snapshot,
            date,
            zone_type,
            allowed_zones,
            1,
            1,
            )
      
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


@router.post("/sankey-save-positions", response_model=SavePositionsResponse)
async def sankey_save_positions(
    payload: dict[str, NodeLayoutItem] = Body(...),
    zone_type: str = Query(...)):
    """
    Сохраняет координаты и цвета узлов Sankey для указанной zone_type.
    Тело запроса: { "Узел A": {x, y, color}, ... }
    """
    if not payload:
        raise HTTPException(status_code=400, detail="Пустой payload")
    sankey_service = SankeyService()
    with sankey_service:
        logger.info("sankey service requested success and saved")
        success, saved = sankey_service.save_colors_positions(zone_type, payload)
        
    return SavePositionsResponse(success=success, saved=saved)
        


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


import json
import logging

from datetime import datetime
from fastapi import APIRouter, Request, Query, Body, Cookie, Response, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.services.data_service import DataService
from app.services.filter_parser import parse_filter, FilterParseError


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(tags=["analysis"])
templates = Jinja2Templates(directory="templates")

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


@router.post("/analysis-filters")
async def save_analysis_filters(
    response: Response,
    payload: dict = Body(...),
    sankey_filters: str | None = Cookie(default=None, alias=COOKIE_NAME),
):
    """Сохраняет фильтры/дату/зону в общий cookie (мержит с существующим)."""
    existing = _read_filters_cookie(sankey_filters)
    merged = {
        "filters": payload.get("filters", existing.get("filters", {})),
        "date": payload.get("date", existing.get("date", default_date())),
        "zone_type": payload.get("zone_type", existing.get("zone_type", "main")),
    }
    logger.info(f'cookie  {merged}')
    response.set_cookie(
        key=COOKIE_NAME,
        value=json.dumps(merged, ensure_ascii=True),
        max_age=COOKIE_MAX_AGE,
        httponly=False,
        samesite="lax",
        path="/",
    )
    return {"success": True}


@router.get("/")
def root(
    request: Request,
    sankey_filters: str | None = Cookie(default=None, alias=COOKIE_NAME),
):
    """Главная страница с интерфейсом"""
    data_service = DataService()
    with data_service:
        zone_types = data_service.get_zones_types()
        vehicle_models = data_service.get_filter_values("VehicleModel")
        all_zones = data_service.get_filter_values("Точка_регистрации")
    logger.info(f'zone_types {zone_types}')

    saved = _read_filters_cookie(sankey_filters)
    saved_filters = saved.get("filters", {}) or {}

    default_zone = saved.get("zone_type")
    if not default_zone or default_zone not in zone_types:
        default_zone = zone_types[0] if zone_types else "main"

    default_date_value = saved.get("date") or default_date()

    return templates.TemplateResponse(
        request=request,
        name="hourly_table.html",
        context={
            "default_date": default_date_value,
            "zone_types": zone_types,
            "vehicle_models": vehicle_models,
            "all_zones": all_zones,
            "initial_zone_type": default_zone,
            "initial_filters": saved_filters,
        },
    )


@router.get("/analyze/")
def analyze_zones(
    date: str = Query(default="2026-06-09"),
    zone_type: str = Query(default="main"),
    row_filters: str | None = Query(default=None, alias="filter"),
):
    """API для анализа зон"""
    try:
        filters = parse_filter(row_filters)
    except FilterParseError as e:
        return {"success": False, "message": f"Некорректный фильтр: {e}"}

    data_service = DataService()
    try:
        with data_service:
            df = data_service.get_data(date, filters=filters)
            logger.info(f'dfff {df}')
            stats, balance = data_service.calculate_statistics(df, date, zone_type)
            logger.info(f' stats {stats}')
        result = []
        for zone_stat in stats:
            result.append({
                "zone": zone_stat.zone_name,
                "entries": [zone_stat.entries.get(h, 0) for h in range(6, 24)],
                "exits": [zone_stat.exits.get(h, 0) for h in range(6, 24)],
            })
        return {
            "success": True,
            "data": result,
            "hours": list(range(6, 24)),
            "zone_type": zone_type,
            "balance": balance,
        }
    except Exception as e:
        return {"success": False, "message": str(e)}

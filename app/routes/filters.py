import json

from datetime import datetime

from fastapi import APIRouter, Request, Query, Body, Cookie, Response, HTTPException
from app.utils.read_filter import _read_filters_cookie


router = APIRouter(tags=["filters"])


COOKIE_NAME = "sankey_filters"
COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 дней


def default_date():
    return datetime.today().strftime("%Y-%m-%d")


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
        "auto_refresh": payload.get("auto_refresh", existing.get("auto_refresh", True)),
    }
    response.set_cookie(
        key=COOKIE_NAME,
        value=json.dumps(merged, ensure_ascii=True),
        max_age=COOKIE_MAX_AGE,
        httponly=False,
        samesite="lax",
        path="/",
    )
    return {"success": True}

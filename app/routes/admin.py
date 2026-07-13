from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from app.db.models import ZoneUpdateRequest
from app.services.zone_service import ZoneService
from app.db.repository import GroupRepository

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory="templates")
	
zone_service = ZoneService()

@router.get("/", response_class=HTMLResponse)
async def admin_page(request: Request):				 
    """Страница администрирования"""
    zones, zones_rep = zone_service.get_zones()
    return templates.TemplateResponse(
        request=request, name="admin.html",
        context={
            "request": request,
            "zones": zones,
            "zones_rep": zones_rep
        }
    )

@router.post("/update_zones")
async def update_zones(request: ZoneUpdateRequest):
    """Обновление списков зон"""
    try:
        zone_service.update_zones(request.zones, request.zones_rep)
        return {"status": "success", "message": "Зоны успешно обновлены"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

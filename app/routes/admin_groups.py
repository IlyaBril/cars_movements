import json
import logging
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import List
from app.services.zone_service import ZoneService
from app.services.data_service import DataService

from app.db.repository import MovementRepository, GroupRepository

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/groups", tags=["admin"])
templates = Jinja2Templates(directory="templates")

zone_service = ZoneService()
data_service = DataService()

class GroupCreateRequest(BaseModel):
    group_name: str
    zones: List[str]


@router.get("/", response_class=HTMLResponse)
async def groups_page(request: Request):
    """Получить все группы"""

    groups = zone_service.get_groups()
    print(f"{__name__} Существующие группы: {groups}")
    available_zones = zone_service.get_available_zones()
        
    # Получаем все зоны для отображения (включая занятые)
    print(f"{__name__} available zones: {available_zones}")
    
    return templates.TemplateResponse(
        request=request, 
        name="admin_groups.html",
        context={
            "request": request,
            "available_zones": available_zones,  # Передаем все зоны
            "groups": groups,
            "groups_json": json.dumps(groups)
            }
        )


@router.get("/edit/{group_name}")
async def get_edit_data(group_name: str):
    """Данные для редактирования группы"""
    groups = zone_service.get_groups()
    if group_name not in groups:
        raise HTTPException(status_code=404, detail="Группа не найдена")
    
    # Получаем доступные зоны (включая зоны редактируемой группы)
    available_zones = zone_service.get_available_zones(editing_group=group_name)
    print('get_edit_data available_zones', available_zones)
    print('get_edit_data current_zones', groups[group_name])
    return {
        "available_zones": available_zones,
        "current_zones": groups[group_name]
    }


@router.post("/create")
async def create_group(request: GroupCreateRequest):
    """Создание или обновление группы"""
    try:
        if not request.group_name or not request.group_name.strip():
            raise HTTPException(status_code=400, detail="Название группы не может быть пустым")
        
        if not request.zones:
            raise HTTPException(status_code=400, detail="Выберите хотя бы одну зону")
        
        # Проверяем, что зоны не используются в других группах
        existing_groups = zone_service.get_groups()
        print('admin groups existing_groups ', existing_groups)
        for group_name, zones in existing_groups.items():
            if group_name != request.group_name:
                for zone in request.zones:
                    if zone in zones:
                        raise HTTPException(
                            status_code=400, 
                            detail=f"Зона '{zone}' уже используется в группе '{group_name}'"
                        )
        
        success = zone_service.save_group_to_db(request.group_name.strip(), request.zones)
        if success:
            return {"status": "success", "message": f"Группа '{request.group_name}' успешно сохранена"}
        else:
            raise HTTPException(status_code=500, detail="Ошибка при сохранении группы")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{group_name}")
async def delete_dash_group(group_name: str):
    """Удаление группы"""
    try:
        success = zone_service.delete_group(group_name)
        if success:
            return {"status": "success", "message": f"Группа '{group_name}' удалена"}
        else:
            raise HTTPException(status_code=404, detail="Группа не найдена")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# MOVE TO SEPARATE FILE admin_zones.py

@router.get("/zones", response_class=HTMLResponse)
async def zones_page(request: Request):
    """Получить все группы"""

    dash_boards = zone_service.get_dash_zones()

    groups = list(zone_service.get_groups().keys())
    zones = zone_service.get_all_zones()
    all_zones = groups + zones
    print(f"{__name__} all_zoness: {groups}")
    
    return templates.TemplateResponse(
        request=request, 
        name="admin_zones.html",
        context={
            "request": request,
            "all_zones": all_zones,  # Передаем все зоны
            "groups": dash_boards,
            "groups_json": json.dumps(groups)
            }
        )


@router.get("/edit/zones/{group_name}")
async def get_edit_zones_data(group_name: str):
    """Данные для редактирования группы"""

    dash_zones = zone_service.get_dash_zones()
    if group_name not in dash_zones:
        raise HTTPException(status_code=404, detail="Группа не найдена")
    
    # Получаем доступные зоны (включая зоны редактируемой группы)
    groups_names = list(zone_service.get_groups().keys())
    zones = zone_service.get_all_zones()
    all_zones = groups_names + zones
    print('get_edit_data all', all_zones)
    print('get_edit_data groups', dash_zones[group_name])
    
    return {
        "available_zones": all_zones,
        "current_zones": dash_zones[group_name],
    }



@router.post("/zones/create")
async def create_group(request: GroupCreateRequest):
    """Создание или обновление группы"""
    
    try:
        if not request.group_name or not request.group_name.strip():
            raise HTTPException(status_code=400, detail="Название группы не может быть пустым")
        
        if not request.zones:            
            raise HTTPException(status_code=400, detail="Выберите хотя бы одну зону")
                
        success = zone_service.save_dash_group(request.group_name.strip(), request.zones)
        if success:
            return {"status": "success", "message": f"Группа '{request.group_name}' успешно сохранена"}
        else:
            raise HTTPException(status_code=500, detail="Ошибка при сохранении группы")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/zones/{group_name}")
async def delete_dash_group(group_name: str):
    """Удаление группы"""
    try:
        success = zone_service.delete_dash_group(group_name)
        if success:
            return {"status": "success", "message": f"Группа '{group_name}' удалена"}
        else:
            raise HTTPException(status_code=404, detail="Группа не найдена")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

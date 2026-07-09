from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import List
import json
from app.database import (
    get_available_zones_for_groups,
    load_groups_from_db, 
    save_group_to_db,
    delete_group_from_db,
    get_all_zones_from_db,
)

from app.db.repository import MovementRepository, GroupRepository

router = APIRouter(prefix="/admin/groups", tags=["admin"])
templates = Jinja2Templates(directory="templates")

class GroupCreateRequest(BaseModel):
    group_name: str
    zones: List[str]

@router.get("/", response_class=HTMLResponse)
async def groups_page(request: Request):
    """Получить все группы"""
    repo = MovementRepository()
    try:
        groups = repo.load_groups()
        all_zones = repo.get_all_zones()
        
    # Получаем все зоны для отображения (включая занятые)
    #all_zones = available_zones = get_available_zones_for_groups()
    #groups = load_groups_from_db()
    
    # Для отладки
        print(f"Все зоны: {all_zones}")
        print(f"Существующие группы: {groups}")
    
        return templates.TemplateResponse(
            request=request, 
            name="admin_groups.html",
            context={
                "request": request,
                "available_zones": all_zones,  # Передаем все зоны
                "groups": groups,
                "groups_json": json.dumps(groups)
                }
            )
    finally:
        repo.close()


@router.get("/edit/{group_name}")
async def get_edit_data(group_name: str):
    """Данные для редактирования группы"""
    groups = load_groups_from_db()
    if group_name not in groups:
        raise HTTPException(status_code=404, detail="Группа не найдена")
    
    # Получаем доступные зоны (включая зоны редактируемой группы)
    available_zones = get_available_zones_for_groups(editing_group=group_name)
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
        existing_groups = load_groups_from_db()
        for group_name, zones in existing_groups.items():
            if group_name != request.group_name:
                for zone in request.zones:
                    if zone in zones:
                        raise HTTPException(
                            status_code=400, 
                            detail=f"Зона '{zone}' уже используется в группе '{group_name}'"
                        )
        
        success = save_group_to_db(request.group_name.strip(), request.zones)
        if success:
            return {"status": "success", "message": f"Группа '{request.group_name}' успешно сохранена"}
        else:
            raise HTTPException(status_code=500, detail="Ошибка при сохранении группы")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{group_name}")
async def delete_group(group_name: str):
    """Удаление группы"""
    try:
        success = delete_group_from_db(group_name)
        if success:
            return {"status": "success", "message": f"Группа '{group_name}' удалена"}
        else:
            raise HTTPException(status_code=404, detail="Группа не найдена")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

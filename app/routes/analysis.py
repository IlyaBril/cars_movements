from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from app.services.data_service import DataService
from app.services.zone_service import ZoneService
from datetime import datetime


router = APIRouter(tags=["analysis"])
templates = Jinja2Templates(directory="templates")

data_service = DataService()

def default_date():
    return datetime.today().strftime("%Y-%m-%d")

@router.get("/")
def root(request: Request):
    """Главная страница с интерфейсом"""
    
    date = default_date()
    print('root')
    return templates.TemplateResponse(  
        request=request, name="index(bootstrap).html",
        context={"default_date": date},
        )


@router.get("/analyze/")
def analyze_zones(
    date: str = Query(default="2026-06-09"),
    zone_type: str = Query(default="main"),

):
    """API для анализа зон"""
    try:
        df = data_service.get_data(date)
        #print(f'{__name__} df ',df)
        stats, balance = data_service.calculate_statistics(df, date, zone_type)
        print(f'{__name__} stats, balance ',stats, balance)
        result = []
        for zone_stat in stats:
            result.append({
                "zone": zone_stat.zone_name,
                "entries": [zone_stat.entries.get(h, 0) for h in range(6, 24)],
                "exits": [zone_stat.exits.get(h, 0) for h in range(6, 24)]
            })
        
        return {
            "success": True,
            "data": result,
            "hours": list(range(6, 24)),
            "zone_type": zone_type,
            "balance": balance,
        }
    except Exception as e:
        return {
            "success": False,
            "message": str(e)
        }

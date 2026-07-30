import base64
import logging
from fastapi import APIRouter, UploadFile, File, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse, Response
from fastapi.templating import Jinja2Templates
from io import BytesIO
from app.services.data_service import DataService

router = APIRouter(prefix="/upload", tags=["upload"])
templates = Jinja2Templates(directory="templates")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@router.get('/', response_class=HTMLResponse)
def upload_page(request: Request):
    """Страница загрузки"""
    return templates.TemplateResponse(
        request=request,
        name="upload.html",
        context={
            "request": request,
        }
    )


@router.post('/')
async def upload_excel(file: UploadFile = File(...)):
    """Загрузка Excel файла"""
    try:
        # Проверяем расширение
        if not file.filename:
            raise HTTPException(status_code=400, detail="Файл не выбран")
        
        if not file.filename.endswith(('.xlsx', '.xls')):
            raise HTTPException(
                status_code=400, 
                detail="Поддерживаются только .xlsx и .xls файлы"
            )

        logger.info(f'{__name__} before async with file')
        
        file_content = await file.read()
        service = DataService()
		
        logger.info(f'{__name__} file uploaded. ')

        # Загружаем данные
        success, message, added_count = service.load_from_excel(file_content)

        if not success:
            # Если ошибка валидации - возвращаем 400
            if "валидации" in message.lower():
                raise HTTPException(status_code=400, detail=message)
            raise HTTPException(status_code=500, detail=message)
        
        return JSONResponse({
            'success': success,
            'message': message,
            'added_count': added_count
        })
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Ошибка: {str(e)}')

  
@router.post("/clear")
async def clear_database():
    """Очистка базы данных"""
    try:
        service = DataService()
        with service:
            success, message = service.clear_database()
        
        return JSONResponse({
            'success': success,
            'message': message
        })
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Ошибка: {str(e)}')


@router.get("/export/")
async def export_excel():
    try:
        service = DataService()
        with service:
            excel_data = service.export_to_excel()
        
        if excel_data is None:
            raise HTTPException(status_code=404, detail='Нет данных для экспорта')
        
        # ✅ Просто возвращаем Response с байтами
        return Response(
            content=excel_data,
            media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            headers={'Content-Disposition': 'attachment; filename="export_database.xlsx"'}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f'{__name__} export error: {e}')
        raise HTTPException(status_code=500, detail=f'Ошибка экспорта: {str(e)}')
        

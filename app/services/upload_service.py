import json
import pandas as pd
import logging
from datetime import datetime, date
from fastapi import Depends
from io import BytesIO
from typing import List, Tuple, Dict, Annotated, Optional
from app.db.models import ZoneStats
from app.db.repository import MovementRepository, GroupRepository
from app.db.database import SQLiteSession, PostgresSession
from app.db.schemas import MovementSchema
from app.services.zone_service import ZoneService
from sqlalchemy.orm import Session


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DataService:
    """ Вся логика вычислений и работы с БД"""
	
    def __init__(self):
        self._sqlite_sesion = SQLiteSession()
        self._psql_session = PostgresSession()
        self._group_repo = GroupRepository(self._sqlite_sesion)
        self._movement_repo = MovementRepository(self._sqlite_sesion)
		
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self._sqlite_sesion.close()
        self._psql_session.close()

    def clear_database(self) -> Tuple[bool, str]:
        """Очистить базу данных"""
        try:
            count = self.repository.clear_all()
            return True, f"Очищено {count} записей"
        except Exception as e:
            self.session.rollback()
            return False, f"Ошибка очистки: {str(e)}"
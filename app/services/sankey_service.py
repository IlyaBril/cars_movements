import pandas as pd
import json
from typing import List, Dict, Optional, Tuple
from collections import defaultdict
from datetime import datetime
from app.db.repository import MovementRepository, GroupRepository
from app.db.database import SQLiteSession, PostgresSession


class SankeyService:
    """Сервис для подготовки данных Sankey диаграммы"""
    
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

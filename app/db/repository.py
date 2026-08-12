import json
import pandas as pd
import logging
from datetime import datetime
from fastapi import Depends
from typing import List, Tuple, Dict, Optional, Annotated
from sqlalchemy.orm import Session
from sqlalchemy import text, distinct
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import func

from .database import SQLiteSession, PostgresSession, get_sqlite_session
from .models import Movement, Metadata, ZonesConfig, ZoneGroup, ZonesList


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MovementRepository:
    """Репозиторий для работы с движениями (PostgreSQL, только чтение)"""
    
    def __init__(self, session: Session = None):
        self.session = session

    def get_data_from_db (self, date=None):
        """Получение всей таблицы из движений"""
        try:
            
            if date:
                orders_query = self.session.query(Movement.Заказ).filter(
                    func.date(Movement.Дата) == date
                    ).distinct()

                orders = orders_query.all()
                 
                # Извлекаем номера заказов
                order_numbers = [order[0] for order in orders]
                
                if not order_numbers:
                    return []  # Если заказов нет, возвращаем пустой список
        
                # Шаг 2: Получаем все движения, где номера заказов есть в списке
                movements = self.session.query(Movement).filter(
                    Movement.Заказ.in_(order_numbers)
                    ).all()
                
                return movements
            else:
                return self.session.query(Movement).all()
            
        except SQLAlchemyError as e:
            #Нужно добавить логирование ошибки
            raise SQLAlchemyError(f"Ошибка при получении данных из таблицы Movement: {e}")
    
    def get_all_zones_from_db(self)-> list[tuple[str]]: 
        """Получение всех зон из движений"""
        all_zones = self.session.query(
            distinct(Movement.Точка_регистрации)
            ).order_by(
                Movement.Точка_регистрации
            ).all()
        
        return all_zones
		
    def get_zones_from_db(self, zones_list_name: str):
        zones_list = self.session.query(ZonesList).filter_by(name=zones_list_name).first()
        logger.info(f'{__name__} zones_list {zones_list.zones}')
        return zones_list.zones

    def load_from_excel_to_db(self, validated_data: list) -> Tuple[bool, str, int]:
        """Быстрая загрузка больших объемов данных"""
        
        if not validated_data:
            return False, "Нет данных", 0

        try:
            batch_size = 1000  # Подберите под свой объем
            inserted = 0
            
            with self.session.begin():
                for i in range(0, len(validated_data), batch_size):
                    batch = validated_data[i:i + batch_size]
                    numbers = [r['Номер'] for r in batch]
                    
                    # Быстрая проверка существования
                    existing = set(
                        row[0] for row in self.session.query(Movement.Номер)
                        .filter(Movement.Номер.in_(numbers)).all()
                    )
                    
                    new_batch = [r for r in batch if r['Номер'] not in existing]
                    
                    if new_batch:
                        self.session.bulk_insert_mappings(Movement, new_batch)
                        inserted += len(new_batch)
            
            return True, f"Добавлено {inserted} записей", inserted

        except SQLAlchemyError as e:
            return False, f"Ошибка: {str(e)}", 0

        
    def load_excel_to_db(self, excel_path: str = "Движение.xlsx") -> bool:
        """Загрузка данных из Excel в PostgreSQL"""
        try:
            print(f"📂 Загрузка данных из {excel_path}...")
            
            df = pd.read_excel(
                excel_path,
                sheet_name=0,
                usecols=['Номер', 'Дата', 'Заказ', 'Точка регистрации']
            )
            
            df['Дата'] = pd.to_datetime(df['Дата'], format='%d.%m.%Y %H:%M:%S')
            
            # Очищаем старые данные
            self.session.query(Movement).delete()
            
            # Загружаем новые данные
            movements = []
            for _, row in df.iterrows():
                movement = Movement(
                    Номер=row['Номер'],
                    Дата=row['Дата'],
                    Заказ=row['Заказ'],
                    Точка_регистрации=row['Точка регистрации']
                )
                movements.append(movement)
            
            # Batch insert
            batch_size = 10000
            for i in range(0, len(movements), batch_size):
                self.session.add_all(movements[i:i+batch_size])
                self.session.flush()
            
            self.session.commit()
            print(f"✅ Загружено {len(df)} записей в базу данных")
            return True
            
        except Exception as e:
            self.session.rollback()
            print(f"❌ Ошибка загрузки: {e}")
            return False
 
    def close(self):
        """Закрыть сессию"""
        self.session.close()


    def clear_all(self) -> int:
        """Очистить всю таблицу"""
        count = self.session.query(Movement).count()
        self.session.query(Movement).delete()
        self.session.commit()
        return count


class GroupRepository:
    """Репозиторий для работы с группами (SQLite)"""
    
    def __init__(self, session: Session = None):
        self.session = session
    
    def load_zones_from_db(self) -> Tuple[List[str], List[str]]:
        """Загрузка конфигурации зон"""
        config = self.session.query(ZonesConfig).order_by(ZonesConfig.id.desc()).first()
        if config:
            return json.loads(config.zones), json.loads(config.zones_rep)
        
        from app.config import DEFAULT_ZONES, DEFAULT_ZONES_REP
        return DEFAULT_ZONES.copy(), DEFAULT_ZONES_REP.copy()
    
    def save_zones_to_db(self, zones_list: List[str], zones_rep_list: List[str]) -> None:
        """Сохранение конфигурации зон"""
        config = self.session.query(ZonesConfig).order_by(ZonesConfig.id.desc()).first()
        if config:
            config.zones = json.dumps(zones_list, ensure_ascii=False)
            config.zones_rep = json.dumps(zones_rep_list, ensure_ascii=False)
        else:
            config = ZonesConfig(
                zones=json.dumps(zones_list, ensure_ascii=False),
                zones_rep=json.dumps(zones_rep_list, ensure_ascii=False)
            )
            self.session.add(config)
        self.session.commit()
    
    def load_groups_from_db(self,
        zone_names: Optional[List[str]] = None,
        ) -> List[ZoneGroup]:
        """Выделение из списка зон главной страницы
           групп для показа"""
        query = self.session.query(ZoneGroup)
        if zone_names:
            query = query.filter(ZoneGroup.group_name.in_(zone_names))
        logger.info(f'{__name__} - load_groups_from_db {query}')
        return query.order_by(ZoneGroup.group_name).all()
    
    def save_group_to_db(self, group_name: str, zones: List[str]) -> bool:
        """Сохранение группы"""
        try:
            group = self.session.query(ZoneGroup).filter_by(group_name=group_name).first()
            if group:
                group.zones = json.dumps(zones, ensure_ascii=False)
            else:
                group = ZoneGroup(
                    group_name=group_name,
                    zones=json.dumps(zones, ensure_ascii=False)
                )
                self.session.add(group)
            self.session.commit()
            return True
        except Exception as e:
            self.session.rollback()
            print(f"Ошибка сохранения группы: {e}")
            return False
    
    def delete_group_from_db(self, group_name: str) -> bool:
        """Удаление группы"""
        try:
            group = self.session.query(ZoneGroup).filter_by(group_name=group_name).first()
            if group:
                self.session.delete(group)
                self.session.commit()
            return True
        except Exception as e:
            self.session.rollback()
            print(f"Ошибка удаления группы: {e}")
            return False

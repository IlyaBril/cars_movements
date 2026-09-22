import json
import pandas as pd
import logging
from datetime import datetime
from fastapi import Depends
from typing import List, Tuple, Dict, Optional, Annotated
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import text, distinct, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import func
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.exc import SQLAlchemyError
from typing import Tuple

from .database import SQLiteSession, PostgresSession, get_sqlite_session
from .models import Movement,  ZoneGroup, ZonesList, ZoneWithGroup, ZoneReport


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MovementRepository:
    """Репозиторий для работы с движениями (PostgreSQL, только чтение)"""
    
    def __init__(self, session: Session = None):
        self.session = session


    #Отчеты
    def get_zones_types_repo(self):
        """Получение списка названий отчетов"""
        zone_types = self.session.scalars(select(ZonesList.name)).all()
        logger.info(f'zone_types {zone_types}')
        return zone_types

    def get_dash_zones_repo(self) -> list[ZonesList]:
        """Получение всех объектов отчетов"""
        return self.session.query(ZonesList).all()
       
    def get_all_zones_from_db(self)-> list[tuple[str]]: 
        """Получение всех существующих зон в базе movement"""
        all_zones = self.session.query(
            distinct(Movement.Точка_регистрации)
            ).order_by(
                Movement.Точка_регистрации
            ).all()
        return all_zones

    def save_dash_group_to_db(self, group_name: str, zones: List[str]) -> bool:
        """Сохранение группы отчета"""
        logger.info(f'{__name__} group_name {group_name} ')
        try:
            group = self.session.query(ZonesList).filter_by(name=group_name).first()
            logger.info(f'{__name__} grpu {group} group_name {group_name} zones {zones}')
            if group:
                group.zones = json.dumps(zones, ensure_ascii=False)
            else:
                logger.info(f'{__name__} grpu else')
                group = ZonesList(
                    name=group_name,
                    zones=json.dumps(zones, ensure_ascii=False)
                )
                self.session.add(group)
            self.session.commit()
            return True
        except Exception as e:
            self.session.rollback()
            print(f"Ошибка сохранения группы: {e}")
            return False


    def save_zone_report_to_db(self, report_name: str, zones_br: List[str]) -> bool:
        """Сохранение группы отчета"""

        zones = [s.split("<br>")[0].strip() for s in zones_br]
        logger.info(f'{__name__} report_name {report_name} ')
        try:
            report = self.session.query(
                ZoneReport).filter_by(name=report_name).first()
            logger.info(f'{__name__} group_name {report} zones {zones}')

            if report is None:
                report = ZoneReport(name=report_name)
                self.session.add(report)
                self.session.flush()  # получаем report.id

            # Собираем существующие зоны отчета в словарь {name: zone}
            existing_zones = {
                zone.name: zone
                for zone in self.session.query(ZoneWithGroup).filter(
                    ZoneWithGroup.report_id == report.id
                ).all()
            }

            # Множество имен зон из переданного списка — для быстрой проверки
            new_zone_names = set(zones)

            # Удаляем зоны, которых нет в новом списке
            for zone_name, zone in existing_zones.items():
                if zone_name not in new_zone_names:
                    self.session.delete(zone)

            # Обрабатываем зоны из переданного списка
            for order_index, zone_name in enumerate(zones):
                if zone_name in existing_zones:
                    # Зона уже существует — обновляем только order
                    existing_zones[zone_name].order = order_index
                else:
                    new_zone = ZoneWithGroup(
                        name=zone_name,
                        order=order_index,
                        report_id=report.id,
                        group_id=None,
                    )
                    self.session.add(new_zone)

            self.session.commit()
            return True

        except Exception as e:
            self.session.rollback()
            print(f"Ошибка сохранения группы: {e}")
            return False
    
    
    def delete_dash_group_from_db(self, group_name: str) -> bool:
        """Удаление группы"""
        try:
            group = self.session.query(ZonesList).filter_by(name=group_name).first()
            if group:
                self.session.delete(group)
                self.session.commit()
            return True
        except Exception as e:
            self.session.rollback()
            print(f"Ошибка удаления группы: {e}")
            return False


    #Data service
    def load_groups_from_db(self,
        zone_names: Optional[List[str]] = None,
        ) -> List[ZoneWithGroup]:
        """Выделение из списка зон главной страницы
           групп для показа"""
        
        query = (
            self.session.query(ZoneWithGroup)
            .filter(ZoneWithGroup.children.any())
            .options(selectinload(ZoneWithGroup.children))
        )
        
        if zone_names:
            query = query.filter(ZoneWithGroup.name.in_(zone_names))

        result = query.all()
        logger.info(f'load_groups_from_db result 2 {result[0].name}')
        return result

    

    def get_data_from_db (self, date=None):
        """Получение всей таблицы из движений"""
        try:
            
            if date:
                orders_query = self.session.query(Movement.Заказ).filter(
                    func.date(Movement.Дата) == date,
                    #Movement.Точка_регистрации == "M151. Выход с линии DKD+"
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
            raise SQLAlchemyError(f"Ошибка при получении данных из таблицы Movement: {e}")
		
    def get_zones_from_db(self, zones_list_name: str):
        zones_list = self.session.query(ZonesList).filter_by(name=zones_list_name).first()
        logger.info(f'zones_list {zones_list.zones}')
        return zones_list.zones

    def load_from_excel_to_db(self, validated_data: list) -> Tuple[bool, str, int]:
        """Быстрая загрузка больших объемов данных"""
        
        if not validated_data:
            return False, "Нет данных", 0

        try:
            batch_size = 1000
            inserted = 0
            
            with self.session.begin():
                for i in range(0, len(validated_data), batch_size):
                    batch = validated_data[i:i + batch_size]
                    
                    # Создаем запрос на вставку
                    stmt = insert(Movement).values(batch)
                    
                    # Настраиваем игнорирование конфликтов по полю 'Номер'
                    stmt = stmt.on_conflict_do_nothing(index_elements=['Номер'])
                    
                    # Выполняем запрос
                    result = self.session.execute(stmt)
                    inserted += result.rowcount  # rowcount вернет количество реально вставленных записей
                
            return True, f"Добавлено {inserted} записей", inserted

        except SQLAlchemyError as e:
            return False, f"Ошибка: {str(e)}", 0

#Upload     
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

#Sankey
    def get_zone_attributes(self, group_name):
        return self.session.query(ZoneReport).filter_by(name=group_name).first()

    def get_existing_nodes(self, zone_type):
        stmt = (
        select(ZoneWithGroup)
        .join(ZoneReport)
        .where(ZoneReport.name == zone_type)
        .order_by(ZoneWithGroup.order)
        )
        response = self.session.execute(stmt).scalars().all()
        logger.info(f'{__name__} response {response}')
        return response

    def save_color_positions_db(self, zone_type, positions):
        try:
            zone_names_with_br = list(positions.keys())
            labels = []
            for label in zone_names_with_br:
                # Извлекаем имя зоны из метки (до <br>)
                zone_name = label.split('<br>')[0]
                labels.append(zone_name)
            logger.info(f"{__name__} /n Sankey positions {positions}")
            existing = self.get_existing_nodes(zone_type)
            logger.info("Sankey layout existing=%s", existing)
            existing_map = {row.name: row for row in existing}
            logger.info("Sankey layout existing map=%s", existing_map)
            saved = 0
            report = self.session.query(ZoneReport).filter_by(name=zone_type).first()
            for label, item in positions.items():
                row = existing_map.get(label)
                if row is None:
                    row = ZoneWithGroup(
                        report=report,
                        name=label,
                        x=item.x,
                        y=item.y,
                        color=item.color,
                        )
                    self.session.add(row)
                else:
                    row.x = item.x
                    row.y = item.y
                    # если color не пришёл — не трогаем сохранённый
                    if item.color is not None:
                        row.color = item.color
                saved += 1

            self.session.commit()
            logger.info("Sankey layout saved: zone=%s nodes=%d", zone_type, saved)
            return True, saved
        
        except Exception as e:
            self.session.rollback()
            logger.exception("Ошибка сохранения Sankey layout: %s", e)
            return False, str(e)
        

class GroupRepository:
    """Репозиторий для работы с группами (SQLite)"""
    
    def __init__(self, session: Session = None):
        self.session = session
    
    
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

    def save_zones_group_to_db(self, group_name: str, zones: List[str]) -> bool:
        """Сохранение группы модели ZoneWithGroup"""
        try:
            group = self.session.query(
                ZoneWithGroup).filter_by(name=group_name).first()

            if group is None:
                group = ZoneWithGroup(name=group_name)
                self.session.add(group)
                self.session.flush()

            for zone in zones:
                zone = ZoneWithGroup(
                    name=zone,
                    group_id=group.id,
                    )
                
                self.session.add(zone)
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


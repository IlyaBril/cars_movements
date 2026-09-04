from sqlalchemy import Column, Integer, String, DateTime, Text, TIMESTAMP, func, Float, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
from pydantic import BaseModel
from typing import Dict, List, Optional


Base = declarative_base()


class ZoneStats(BaseModel):
    zone_name: str
    entries: Dict[int, int]
    exits: Dict[int, int]


class AnalysisResponse(BaseModel):
    success: bool
    message: str
    data: Optional[List[ZoneStats]] = None
    

class Movement(Base):
    __tablename__ = 'movements'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    Номер = Column(String, unique=True, nullable=False)
    Дата = Column(DateTime)
    Заказ = Column(String)
    Точка_регистрации = Column(String, name="Точка регистрации")


class ZoneReport(Base):
    """Отчеты"""    
    __tablename__ = 'report_zones'
    
    id = Column(Integer, primary_key=True)
    name = Column(Text, nullable=False)
    report_zones = relationship("ZoneWithGroup", back_populates="report", cascade="all, delete-orphan")


class ZoneWithGroup(Base):
    """Зона с координатами и цветом для конкретной группы"""
    __tablename__ = 'zone_with_group'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    x = Column(Float, nullable=False)
    y = Column(Float, nullable=False)
    color = Column(String, nullable=True)
    order = Column(Integer, default=0)
    report_id = Column(Integer, ForeignKey("report_zones.id", ondelete='CASCADE', name="fk_zone_report_id"), nullable=False)
    report = relationship("ZoneReport", back_populates="report_zones")
    
    # Ссылка на родительскую зону (может быть NULL)
    group_id = Column(Integer, ForeignKey('zone_with_group.id', ondelete='SET NULL', name="fk_zone_group_id"), nullable=True,)
    
    # Связи для иерархии
    group = relationship("ZoneWithGroup", remote_side=[id], back_populates="children")
    children = relationship("ZoneWithGroup", back_populates="group")

    __table_args__ = (
        UniqueConstraint("name", "group_id", name="uq_zone_name_per_group"),
    )


#Старые модели
class ZonesList(Base):
    """Отчеты"""
    
    __tablename__ = 'zones'
    
    id = Column(Integer, primary_key=True)
    name = Column(Text, nullable=False)
    zones = Column(Text, nullable=False)


class ZoneGroup(Base):
    __tablename__ = 'zone_groups'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    group_name = Column(String, nullable=False, unique=True)
    zones = Column(Text, nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())
 

# Pydantic модели для API
class ZonePosition(BaseModel):
    name: str
    x: Optional[float] = None
    y: Optional[float] = None
    color: Optional[str] = None
    order: Optional[int] = 0

class ZoneGroupCreate(BaseModel):
    group_name: str
    description: Optional[str] = None
    zones: List[ZonePosition]

class ZoneGroupUpdate(BaseModel):
    zones: List[ZonePosition]


from sqlalchemy import Column, Integer, String, DateTime, Text, TIMESTAMP, func
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
    

class ZoneUpdateRequest(BaseModel):
    zones: List[str]
    zones_rep: List[str]
    

class GroupUpdateRequest(BaseModel):
    groups: Dict[str, List[str]]  # {group_name: [zone1, zone2, ...]}
    

class GroupCreateRequest(BaseModel):
    name: str
    zones: List[str]


class Movement(Base):
    __tablename__ = 'movements'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    Дата = Column(DateTime)
    Заказ = Column(String)
    Точка_регистрации = Column(String, name="Точка регистрации")


class Metadata(Base):
    __tablename__ = 'metadata'
    
    key = Column(String, primary_key=True)
    value = Column(String)


class ZonesConfig(Base):
    __tablename__ = 'zones_config'
    
    id = Column(Integer, primary_key=True)
    zones = Column(Text, nullable=False)
    zones_rep = Column(Text, nullable=False)
    updated_at = Column(TIMESTAMP, server_default=func.current_timestamp())


class ZoneGroup(Base):
    __tablename__ = 'zone_groups'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    group_name = Column(String, nullable=False, unique=True)
    zones = Column(Text, nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.current_timestamp())

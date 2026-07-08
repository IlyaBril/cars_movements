from sqlalchemy import Column, Integer, String, DateTime, Text, TIMESTAMP, func
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime


Base = declarative_base()

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

from marshmallow import Schema, fields, post_load
from datetime import datetime
from typing import Dict, Optional
from pydantic import BaseModel, Field, field_validator
import re

class MovementSchema(Schema):

    class Meta:
        unknown = 'EXCLUDE'  # Игнорировать неизвестные поля
        
    id = fields.Int(dump_only=True)  # dump_only - только для вывода
    Дата = fields.DateTime(format='%Y-%m-%d %H:%M:%S', allow_none=True)
    Заказ = fields.Str(required=False, allow_none=True)
    Точка_регистрации = fields.Str(
        required=False,
        data_key="Точка регистрации",
        attribute="Точка_регистрации",
        )
    Номер = fields.Int(allow_none=True)



class NodeLayoutItem(BaseModel):
    x: float = Field(..., ge=-1.0, le=1.0)
    y: float = Field(..., ge=-1.0, le=1.0)
    color: Optional[str] = None

    @field_validator("color")
    @classmethod
    def validate_color(cls, v):
        if v is None:
            return v
        # допускаем #rgb, #rrggbb, #rrggbbaa
        #if not re.fullmatch(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})", v):
        #    raise ValueError(f"Некорректный цвет: {v}")
        return v.lower()


class SavePositionsResponse(BaseModel):
    success: bool
    saved: int = 0
    error: Optional[str] = None



from marshmallow import Schema, fields, post_load
from datetime import datetime

class MovementSchema(Schema):
    id = fields.Int(dump_only=True)  # dump_only - только для вывода
    Дата = fields.DateTime(format='%Y-%m-%d %H:%M:%S', allow_none=True)
    Заказ = fields.Str(required=False, allow_none=True)
    Точка_регистрации = fields.Str(
        required=True,
        data_key="Точка регистрации",
        attribute="Точка_регистрации",
        )

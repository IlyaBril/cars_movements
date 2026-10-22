import json
import logging
from typing import Any, Dict, List

from app.db.models import Movement

logger = logging.getLogger(__name__)


class FilterParseError(ValueError):
    """Некорректный фильтр."""


def get_allowed_filter_columns() -> set[str]:
    """
    Колонки, по которым разрешено фильтровать — берём напрямую из модели.

    Учитываем:
      - Python-имя атрибута (Movement.VehicleModel, Movement.Точка_регистрации)
      - реальное имя колонки в БД (column.name), на случай если оно отличается

    Автоматически подхватит любую новую колонку, добавленную в модель.
    """
    allowed: set[str] = set()
    for col in Movement.__table__.columns:
        # col.key     -> python-имя (например, 'Точка_регистрации')
        # col.name    -> имя в БД (например, 'Точка регистрации')
        allowed.add(col.key)
        if col.name:
            allowed.add(col.name)
    return allowed


def _resolve_column(name: str):
    """
    Возвращает колонку модели по python-имени ИЛИ по имени в БД.
    None — если такой колонки нет.
    """
    # 1) прямое совпадение по python-атрибуту (самый частый случай)
    attr = getattr(Movement, name, None)
    if attr is not None and hasattr(attr, "in_"):
        return attr

    # 2) поиск по column.name (реальное имя в БД)
    for col in Movement.__table__.columns:
        if col.name == name or col.key == name:
            return getattr(Movement, col.key)

    return None


def parse_filter(raw: str | None) -> Dict[str, List[str]]:
    """
    Превращает строку filter из query в dict {column: [values]}.

    Пример:
        '{"VehicleModel":["M3"],"Точка_регистрации":["Москва"]}'
        -> {"VehicleModel": ["M3"], "Точка_регистрации": ["Москва"]}

    Возвращает пустой dict, если raw пуст/None.
    Бросает FilterParseError на некорректный JSON или неизвестную колонку.
    """
    if not raw:
        return {}

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise FilterParseError(f"filter не является валидным JSON: {e}") from e

    if not isinstance(data, dict):
        raise FilterParseError("filter должен быть JSON-объектом")

    result: Dict[str, List[str]] = {}
    for column, values in data.items():
        if _resolve_column(column) is None:
            raise FilterParseError(f"Недопустимая колонка фильтра: {column}")

        if values is None:
            continue
        if not isinstance(values, list):
            raise FilterParseError(
                f"Значение фильтра '{column}' должно быть списком"
            )

        cleaned = list({str(v).strip() for v in values if str(v).strip()})
        if cleaned:
            result[column] = cleaned

    return result

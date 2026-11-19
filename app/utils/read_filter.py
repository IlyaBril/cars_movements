import json


def _read_filters_cookie(raw: str | None) -> dict:
    """Читает JSON из cookie и валидирует структуру."""
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            return {}
    except (ValueError, TypeError):
        return {}
    result = {}
    if isinstance(data.get("filters"), dict):
        result["filters"] = data["filters"]
    if isinstance(data.get("date"), str):
        result["date"] = data["date"]
    if isinstance(data.get("zone_type"), str):
        result["zone_type"] = data["zone_type"]
    if isinstance(data.get("auto_refresh"), bool):
        result["auto_refresh"] = data["auto_refresh"]
    return result

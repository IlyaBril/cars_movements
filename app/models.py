from pydantic import BaseModel
from typing import List, Dict, Optional

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
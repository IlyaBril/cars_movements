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

class GroupUpdateRequest(BaseModel):
    groups: Dict[str, List[str]]  # {group_name: [zone1, zone2, ...]}

class GroupCreateRequest(BaseModel):
    name: str
    zones: List[str]
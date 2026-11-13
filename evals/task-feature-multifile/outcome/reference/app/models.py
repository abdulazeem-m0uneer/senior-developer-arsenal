from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class User:
    id: int
    name: str
    role: str = "member"
    active: bool = True
    deactivated_at: Optional[datetime] = None

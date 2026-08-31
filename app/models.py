from dataclasses import dataclass, field
from typing import Optional
import time

@dataclass
class Channel:
    service_ref: str
    name: str
    bouquet_ref: str
    multicast: str = ""
    port: int = 0

@dataclass
class Stream:
    service_ref: str
    channel_name: str
    multicast: str
    port: int
    pid: Optional[int] = None
    started_at: float = field(default_factory=time.time)
    clients: int = 0
    stop_task: object = None

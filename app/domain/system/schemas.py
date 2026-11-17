from datetime import datetime

from pydantic import BaseModel, Field


class CpuMetrics(BaseModel):
    usage_percent: float = Field(ge=0, le=100)
    cores: int = Field(ge=1)
    load_1m: float = Field(ge=0)
    load_5m: float = Field(ge=0)
    load_15m: float = Field(ge=0)


class CapacityMetrics(BaseModel):
    total_bytes: int = Field(ge=0)
    used_bytes: int = Field(ge=0)
    available_bytes: int = Field(ge=0)
    usage_percent: float = Field(ge=0, le=100)


class SystemMetrics(BaseModel):
    observed_at: datetime
    uptime_seconds: int = Field(ge=0)
    cpu: CpuMetrics
    memory: CapacityMetrics
    swap: CapacityMetrics
    disk: CapacityMetrics

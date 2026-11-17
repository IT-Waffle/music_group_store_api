import pytest

import app.domain.system.router as system_router_module
from app.domain.system.metrics import _calculate_cpu_usage, _capacity
from app.domain.system.schemas import CapacityMetrics, CpuMetrics, SystemMetrics
from datetime import UTC, datetime


@pytest.mark.asyncio
async def test_health_live(async_client):
    """Smoke-test: application starts"""
    response = await async_client.get("/health/live")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_health_ready(async_client):
    """Smoke-test: DB and Redis are connected and ready for work"""
    response = await async_client.get("/health/ready")
    assert response.status_code == 200


def test_metric_calculations_are_bounded():
    assert _calculate_cpu_usage((100, 60), (200, 100)) == 60.0
    assert _capacity(1000, 250).model_dump() == {
        "total_bytes": 1000,
        "used_bytes": 750,
        "available_bytes": 250,
        "usage_percent": 75.0,
    }
    assert _capacity(0, 0).usage_percent == 0.0


def sample_metrics() -> SystemMetrics:
    return SystemMetrics(
        observed_at=datetime(2026, 9, 4, 8, 0, tzinfo=UTC),
        uptime_seconds=37230,
        cpu=CpuMetrics(
            usage_percent=14.2,
            cores=1,
            load_1m=0.05,
            load_5m=0.1,
            load_15m=0.09,
        ),
        memory=CapacityMetrics(
            total_bytes=1_000_000,
            used_bytes=600_000,
            available_bytes=400_000,
            usage_percent=60.0,
        ),
        swap=CapacityMetrics(
            total_bytes=2_000_000,
            used_bytes=100_000,
            available_bytes=1_900_000,
            usage_percent=5.0,
        ),
        disk=CapacityMetrics(
            total_bytes=24_000_000,
            used_bytes=8_000_000,
            available_bytes=16_000_000,
            usage_percent=33.3,
        ),
    )


@pytest.mark.asyncio
async def test_metrics_require_authentication(async_client):
    response = await async_client.get("/api/v1/system/metrics")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_metrics_require_admin_role(moderator_client):
    response = await moderator_client.get("/api/v1/system/metrics")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_can_read_non_cacheable_metrics(admin_client, monkeypatch):
    async def fake_collect_system_metrics() -> SystemMetrics:
        return sample_metrics()

    monkeypatch.setattr(
        system_router_module,
        "collect_system_metrics",
        fake_collect_system_metrics,
    )

    response = await admin_client.get("/api/v1/system/metrics")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"
    assert response.json()["cpu"]["usage_percent"] == 14.2
    assert response.json()["memory"]["used_bytes"] == 600_000

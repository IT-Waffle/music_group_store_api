from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_standalone_api_port_is_bound_to_loopback():
    compose = (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert '"127.0.0.1:8000:8000"' in compose
    assert '\n      - "8000:8000"' not in compose


def test_uv_builder_image_is_version_pinned():
    dockerfile = (PROJECT_ROOT / "dockerfile").read_text(encoding="utf-8")

    assert "ghcr.io/astral-sh/uv:0.12.9" in dockerfile
    assert "ghcr.io/astral-sh/uv:latest" not in dockerfile

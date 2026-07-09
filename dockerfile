FROM python:3.14.3-slim-bookworm

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./

RUN uv sync --frozen --no-cache

COPY . .

RUN mkdir -p /app/uploads/products
RUN chmod +x /app/seed.py


CMD ["sh", "-c", "uv run alembic upgrade head && uv run python seed.py && uv run fastapi run app/main.py --host 0.0.0.0 --port 8000"]
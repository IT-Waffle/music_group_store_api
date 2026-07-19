# Music Group Store API

FastAPI backend for the Amor Fati music & art storefront.

## Local Docker run

```bash
cp .env.example .env
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

Create the first administrator explicitly after the database is ready:

```bash
docker compose exec api uv run python seed.py
```

The API is available at `http://localhost:8000`, Swagger UI at `/docs`.

## Checks

```bash
uv run pytest -v
uv run alembic upgrade head
uv run python -m compileall app tests
```

The current test suite contains 17 tests. Full API usage documentation is in
[`docs/api-usage.md`](docs/api-usage.md); the focused music frontend guide is in
[`docs/music-api-frontend.md`](docs/music-api-frontend.md). The production
internal-media location example is in
[`deploy/nginx.music.conf.example`](deploy/nginx.music.conf.example).

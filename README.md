# Planogram

Compares Shelf Photos against Approved Planograms (Compliance Check) and builds Draft
Planograms from Shelf Photos (Extraction). See `GLOSSARY.md` for the domain language and
`docs/adr/` for the decisions behind the design.

- `service/`: the standalone FastAPI service (ADR 0002). The HTTP API is documented by its
  generated OpenAPI schema at `/docs` and `/openapi.json`.
- `ui/`: a small React development UI that calls the service directly.

## Service

```sh
cd service
python -m venv --system-site-packages .venv
.venv/Scripts/python -m pip install -e ".[dev]"      # add ",vision" for the real models
PLANOGRAM_API_KEY=dev-key .venv/Scripts/uvicorn planogram.main:app --reload
```

Configuration (environment variables):

| Variable | Default | Meaning |
| --- | --- | --- |
| `PLANOGRAM_API_KEY` | (required) | Service API key the host backend must send as `X-API-Key` |
| `PLANOGRAM_DATA_DIR` | `data` | Base folder for the database and images |
| `PLANOGRAM_DB_PATH` | `$DATA_DIR/planogram.sqlite` | SQLite database |
| `PLANOGRAM_IMAGE_DIR` | `$DATA_DIR/images` | Image store folder |

Every request carries `X-API-Key`, the acting user's opaque `X-User-Id` and their
`X-User-Role` (`Viewer`, `Operator` or `Manager`). The service stores no names or emails.

Tests call the HTTP API in-process against a temporary database and image folder:

```sh
.venv/Scripts/python -m pytest
.venv/Scripts/python -m mypy planogram
```

## Development UI

```sh
cd ui
npm install
npm run dev     # proxies /api to http://localhost:8000 (override with PLANOGRAM_API_URL)
```

Set the API key, user ID and role in the header bar.

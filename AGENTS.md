# AGENTS.md — Dollar Link Dashboard

Single-file FastAPI app that serves a dashboard for Argentine Dollar Link instruments.

## Developer commands

```bash
pip install -r requirements.txt
python3 dollar_link_dashboard.py   # http://localhost:9120
```

- Port and host are hardcoded: `0.0.0.0:9120`.
- There is **no test suite**, **no linter**, and **no typechecker** configured.

## Architecture

- **Entrypoint**: `dollar_link_dashboard.py` (only source file).
- **UI**: The entire dashboard is a single inline HTML/CSS/JS string (`DASHBOARD_HTML`) inside that file. To change the frontend, edit the Python file.
- **Data**: Fetched live from external APIs on every request — no database, no cache.
  - `data912.com` — bond/note panel data
  - `dolarapi.com` — FX rates (official, MEP, CCL, blue)
  - `api.bcra.gob.ar/estadisticas/v4.0` — REM inflation expectations and BADLAR rates
- **CORS**: Enabled for all origins (`allow_origins=["*"]`).

## API surface

- `GET /` — Dashboard HTML
- `GET /api/dollar-link` — Instrument data + FX + REM/BADLAR context
- `GET /api/market-summary` — FX summary only

## Important code locations

- Instrument list and maturity dates: `DL_INSTRUMENTS` and `VENCIMIENTOS` constants.
- Fair-value math (REM/BADLAR): inside `assemble_dollar_link_data()`.
- BCRA variable IDs used: `7` (BADLAR), `27` (REM next month), `29` (REM 12-month).

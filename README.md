# Dollar Link Dashboard 🇦🇷

Dashboard web de instrumentos **Dollar Link** argentinos — títulos públicos del Tesoro Nacional ajustados por tipo de cambio oficial BCRA.

## Instrumentos

| Símbolo | Tipo | Vencimiento |
|---------|------|-------------|
| D30A6 | Letra Dollar Link | 30/04/2026 |
| D30S6 | Letra Dollar Link | 30/09/2026 |
| TZV26 | Bono Dollar Link | 30/06/2026 |
| TZV27 | Bono Dollar Link | 30/06/2027 |
| TZV28 | Bono Dollar Link | 30/06/2028 |
| TZV7D | Bono Dollar Link | — |

## Preview

> Dashboard con dark theme, auto-refresh cada 60s, precio en ARS, equivalente USD, bid/ask, volumen y overview de dólar MEP/CCL/Blue.

## Quick Start

```bash
# 1. Instalar dependencias
pip install -r requirements.txt

# 2. Correr
python3 dollar_link_dashboard.py

# 3. Abrir en browser
open http://localhost:9120
```

## APIs

- `GET /` — Dashboard HTML
- `GET /api/dollar-link` — Datos de instrumentos en JSON
- `GET /api/market-summary` — Resumen MEP/CCL/Blue en JSON

## Datos

Los precios se obtienen de **Data912.com** y **DolarAPI.com** — son datos educativos/referenciales, no tiempo real.

## Tech Stack

- Python 3.13+
- FastAPI
- uvicorn
- requests

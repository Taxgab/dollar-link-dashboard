# Dollar Link Dashboard 🇦🇷

Dashboard web de instrumentos **Dollar Link** argentinos — títulos públicos del Tesoro Nacional ajustados por tipo de cambio oficial BCRA.

## Instrumentos

| Símbolo | Tipo | Vencimiento |
|---------|------|-------------|
| D30A6 | Letra Dollar Link | 30/06/2026 |
| D30S6 | Letra Dollar Link | 30/06/2026 |
| TZV26 | Bono Dollar Link | 31/03/2026 |
| TZV27 | Bono Dollar Link | 31/03/2027 |
| TZV28 | Bono Dollar Link | 31/03/2028 |

## Preview

Dashboard con dark theme, auto-refresh cada 60s, precios en ARS, equivalente USD (Oficial/MEP/CCL), fair values (REM y BADLAR), vencimiento y volumen.

## Quick Start

```bash
pip install -r requirements.txt
python3 dollar_link_dashboard.py
open http://localhost:9120
```

## Columnas

| Columna | Descripción |
|---------|-------------|
| **Último (ARS)** | Precio de cierre en pesos |
| **Var%** | Variación porcentual del día |
| **Bid / Ask** | Órdenes de compra y venta |
| **USD Oficial** | `precio_ARS / tipo_cambio_oficial` |
| **USD MEP** | `precio_ARS / dólar MEP (Bolsa)` |
| **USD CCL** | `precio_ARS / dólar CCL (Contado con Liqui)` |
| **USD Fair (REM)** | Fair value usando expectativa de inflación REM del BCRA (ID 27/29) — proyecta tipo de cambio forward a 12 meses |
| **USD Fair (BADLAR)** | Fair value usando paridad descubierta de tasas: `forward = spot × (1 + BADLAR)^(t) / (1 + tasa_USD)^(t)` — BADLAR 30 días del BCRA (ID 7), tasa USD ~5% |
| **Vto.** | Fecha de vencimiento del instrumento |

### ¿Cómo se interpretan los Fair Values?

Si el precio actual en USD está **por encima** del fair value, el bono está "barato" respecto a la expectativa de mercado. Si está **por debajo**, está "caro".

- **REM**: usa expectativa de inflación a 12 meses del Relevamiento de Expectativas de Mercado del BCRA
- **BADLAR**: usa la tasa de interés de depósitos a 30 días (BADLAR) como proxy de la tasa en pesos, comparada con la tasa en USD

## APIs

- `GET /` — Dashboard HTML
- `GET /api/dollar-link` — Datos de instrumentos en JSON
- `GET /api/market-summary` — Resumen MEP/CCL/Blue en JSON

### Respuesta `/api/dollar-link`

```json
{
  "instruments": [{
    "symbol": "D30S6",
    "last": 142000.0,
    "pct_change": 0.12,
    "bid": 141500.0,
    "ask": 142000.0,
    "volume": 48219321.0,
    "usd_price_oficial": 100.0,
    "usd_price_mep": 80.2,
    "usd_price_ccl": 72.1,
    "usd_fair_value_rem": 80.78,
    "usd_fair_value_badlar": 92.77,
    "maturity": "30/06/2026",
    "tipo": "letra"
  }],
  "dolar_oficial": {"compra": 1400, "venta": 1420},
  "dolar_mep": 1771.0,
  "dolar_ccl": 1970.0,
  "dolar_blue": 2020.0,
  "rem": {
    "inflacion_mes_siguiente": 2.9,
    "inflacion_prox_12_meses": 23.8,
    "fecha": "2026-03-31"
  },
  "badlar": {
    "tasa_ars": 22.0,
    "tasa_usd": 5.0,
    "fecha": "2026-04-23"
  },
  "timestamp": "2026-04-25T..."
}
```

## Fuentes

- **Data912.com** — precios de mercado (referenciales)
- **DolarAPI.com** — tipos de cambio (oficial, MEP, CCL, blue)
- **BCRA API v4.0** — expectativas REM (inflación) y BADLAR (tasas)

> Los datos son educativos y referenciales, no constituyen asesoramiento financiero.

## Tech Stack

- Python 3.13+
- FastAPI
- uvicorn
- requests

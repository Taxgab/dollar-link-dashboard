#!/usr/bin/env python3
"""
Dollar Link Dashboard — FastAPI
Sirve en puerto 9120.
Consulta Data912 + DolarAPI y muestra instrumentos dollar link argentinos.
"""

import sys
import json
import time
import hmac
import hashlib
import base64
from datetime import datetime, timezone
from typing import Optional

import requests
import uvicorn
from fastapi import FastAPI, Response
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.requests import Request

# ── Config ──────────────────────────────────────────────────────────────────
PORT = 9120
HOST = "0.0.0.0"
REFRESH_INTERVAL = 60  # segundos

# ── APIs ───────────────────────────────────────────────────────────────────────
DATA912_BASE = "https://data912.com"
DOLAR_API_BASE = "https://dolarapi.com"
BCRA_API_BASE = "https://api.bcra.gob.ar/estadisticas/v4.0"

# ── US Treasury yield curve (riesgo libre) ─────────────────────────────────────
TREASURY_YIELD_CURVE_URL = (
    "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
    "daily-treasury-rates.csv/2026/all?type=daily_treasury_yield_curve&"
    "field_tdr_date_value=2026&download=true"
)

# ── Instrumentos Dollar Link a trackear ──────────────────────────────────────
DL_INSTRUMENTS = ["D30A6", "D30S6", "TZV26", "TZV27", "TZV28"]

# ── Vencimientos (dd/mm/aaaa) — fuente: Ministerio de Economía Argentina ───────
VENCIMIENTOS = {
    "D30A6": "30/06/2026",
    "D30S6": "30/06/2026",
    "TZV26": "31/03/2026",
    "TZV27": "31/03/2027",
    "TZV28": "31/03/2028",
}

# ── Funciones de fetch ────────────────────────────────────────────────────────

def fetch_json(url: str, timeout=10) -> Optional[dict | list]:
    try:
        r = requests.get(url, timeout=timeout)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


def fetch_bonds_panel() -> list:
    """Trae panel de bonos de Data912."""
    data = fetch_json(f"{DATA912_BASE}/live/arg_bonds")
    if not data:
        return []
    instruments = [i for i in data if i.get("symbol", "") in DL_INSTRUMENTS]
    return instruments


def fetch_notes_panel() -> list:
    """Trae panel de notas de Data912."""
    data = fetch_json(f"{DATA912_BASE}/live/arg_notes")
    if not data:
        return []
    instruments = [i for i in data if i.get("symbol", "") in DL_INSTRUMENTS]
    return instruments


def fetch_dolar_oficial() -> Optional[dict]:
    """Dólar oficial BCRA."""
    return fetch_json(f"{DOLAR_API_BASE}/v1/dolares/oficial")


def fetch_all_dolares() -> list:
    """Todos los tipos de dólar."""
    data = fetch_json(f"{DOLAR_API_BASE}/v1/dolares")
    return data if isinstance(data, list) else []


def get_dolar_types() -> dict:
    """Trae dólar MEP, CCL y Blue."""
    dolares = fetch_all_dolares()
    result = {}
    for d in dolares:
        t = d.get("casa", "").lower()
        if t == "bolsa":
            result["mep"] = d.get("venta") or 0
        elif t == "contadoconliqui":
            result["ccl"] = d.get("venta") or 0
        elif t == "blue":
            result["blue"] = d.get("venta") or 0
    return result


def fetch_bcra_variable(var_id: int, max_entries: int = 5) -> list:
    """Trae entries de una variable BCRA v4.0. Sin query params — filtra client-side."""
    data = fetch_json(f"{BCRA_API_BASE}/monetarias/{var_id}", timeout=15)
    if data and data.get("results"):
        return data["results"][0].get("detalle", [])[:max_entries]
    return []


def fetch_rem_inflacion() -> dict:
    """Expectativas de inflación del REM (BCRA)."""
    result = {"mes_siguiente": None, "prox_12_meses": None, "ultimo_rem": None, "fecha": None}
    try:
        entries = fetch_bcra_variable(29, 3)
        if entries:
            result["prox_12_meses"] = entries[0].get("valor")
            result["fecha"] = entries[0].get("fecha")
    except Exception:
        pass
    try:
        entries = fetch_bcra_variable(27, 2)
        if entries:
            result["mes_siguiente"] = entries[0].get("valor")
    except Exception:
        pass
    return result


def fetch_treasury_yield() -> Optional[dict]:
    """Trae el yield de US Treasury a 6 meses (riesgo libre)."""
    try:
        r = requests.get(TREASURY_YIELD_CURVE_URL, timeout=15)
        if r.status_code != 200:
            return None
        lines = r.text.strip().split("\n")
        if len(lines) < 2:
            return None
        headers = [h.strip().strip('"') for h in lines[0].split(",")]
        # Buscar columna "6 Mo"
        col_6m = None
        for i, h in enumerate(headers):
            if h == "6 Mo":
                col_6m = i
                break
        if col_6m is None:
            return None
        # Última fila = fecha más reciente
        last_line = lines[1].split(",")
        yield_6m = float(last_line[col_6m].strip().strip('"'))
        date_str = last_line[0].strip().strip('"')
        return {"yield_6m": yield_6m, "date": date_str}
    except Exception:
        return None


def fetch_badlar() -> dict:
    """Trae BADLAR (ID 7, BCRA) y US Treasury 6M (riesgo libre)."""
    treasury = fetch_treasury_yield()
    tasa_usd = treasury["yield_6m"] if treasury else 5.0
    treasury_date = treasury["date"] if treasury else None
    entries = fetch_bcra_variable(7, 3)
    if not entries:
        return {"badlar": None, "tasa_usd": tasa_usd, "tasa_usd_source": "fallback", "badlar_fecha": None, "treasury_date": treasury_date}
    return {
        "badlar": entries[0].get("valor"),
        "tasa_usd": tasa_usd,
        "tasa_usd_source": "US Treasury 6M",
        "badlar_fecha": entries[0].get("fecha"),
        "treasury_date": treasury_date,
    }


def assemble_dollar_link_data() -> dict:
    """Consolida datos de instrumentos dollar link."""
    bonds = {b["symbol"]: b for b in fetch_bonds_panel()}
    notes = {n["symbol"]: n for n in fetch_notes_panel()}
    all_data = {**bonds, **notes}

    dolar = fetch_dolar_oficial() or {}
    dolar_oficial_venta = dolar.get("venta", 0) or 0
    dolares = get_dolar_types()
    mep = dolares.get("mep", 0) or 0
    ccl = dolares.get("ccl", 0) or 0

    # REM inflación
    rem = fetch_rem_inflacion()
    prox_12_meses = rem.get("prox_12_meses")  # % inflación esperada 12m

    # BADLAR tasa
    badlar_data = fetch_badlar()
    badlar = badlar_data.get("badlar")  # % anual
    tasa_usd = badlar_data.get("tasa_usd", 5.0)  # % anual USD

    rows = []
    for sym in DL_INSTRUMENTS:
        item = all_data.get(sym, {})
        if not item:
            rows.append({
                "symbol": sym,
                "last": None,
                "pct_change": None,
                "bid": None,
                "ask": None,
                "volume": None,
                "usd_price_oficial": None,
                "usd_price_mep": None,
                "usd_price_ccl": None,
                "usd_fair_value_rem": None,
                "usd_fair_value_badlar": None,
                "maturity": VENCIMIENTOS.get(sym),
                "tipo": "bono" if sym.startswith("TZV") else "letra",
            })
            continue

        last = item.get("c", 0) or 0
        pct = item.get("pct_change", 0) or 0
        bid = item.get("px_bid", 0) or 0
        ask = item.get("px_ask", 0) or 0
        vol = item.get("v", 0) or 0

        usd_oficial = round(last / dolar_oficial_venta, 2) if dolar_oficial_venta else None
        usd_mep = round(last / mep, 2) if mep else None
        usd_ccl = round(last / ccl, 2) if ccl else None

        # Fair value con REM: divide por (1 + inf_12m/100)
        if usd_oficial and prox_12_meses:
            usd_fair_rem = round(usd_oficial / (1 + prox_12_meses / 100), 2)
        else:
            usd_fair_rem = None

        # Fair value con BADLAR: paridad descubierta de tasas
        # forward_rate = oficial * (1 + badlar/100)^(6/12) / (1 + tasa_usd/100)^(6/12)
        if usd_oficial and badlar and tasa_usd:
            forward_factor = ((1 + badlar / 100) ** 0.5) / ((1 + tasa_usd / 100) ** 0.5)
            forward_rate = dolar_oficial_venta * forward_factor
            usd_fair_badlar = round(last / forward_rate, 2) if forward_rate else None
        else:
            usd_fair_badlar = None

        # Valor teórico en pesos ajustado por inflación REM 12m
        if last and prox_12_meses:
            rem_adjusted_ars = round(last * (1 + prox_12_meses / 100), 2)
        else:
            rem_adjusted_ars = None

        rows.append({
            "symbol": sym,
            "last": last,
            "pct_change": pct,
            "bid": bid,
            "ask": ask,
            "volume": vol,
            "usd_price_oficial": usd_oficial,
            "usd_price_mep": usd_mep,
            "usd_price_ccl": usd_ccl,
            "usd_fair_value_rem": usd_fair_rem,
            "usd_fair_value_badlar": usd_fair_badlar,
            "rem_adjusted_ars": rem_adjusted_ars,
            "maturity": VENCIMIENTOS.get(sym),
            "tipo": "bono" if sym.startswith("TZV") else "letra",
        })

    return {
        "instruments": rows,
        "dolar_oficial": {
            "compra": dolar.get("compra"),
            "venta": dolar.get("venta"),
            "fecha": dolar.get("fechaActualizacion"),
        },
        "dolar_mep": mep,
        "dolar_ccl": ccl,
        "dolar_blue": dolares.get("blue", 0),
        "rem_forward_tc": round(dolar_oficial_venta * (1 + prox_12_meses / 100), 2) if (dolar_oficial_venta and prox_12_meses) else None,
        "rem": {
            "inflacion_mes_siguiente": rem.get("mes_siguiente"),
            "inflacion_prox_12_meses": prox_12_meses,
            "fecha": rem.get("fecha"),
        },
        "badlar": {
            "tasa_ars": badlar,
            "tasa_usd": tasa_usd,
            "tasa_usd_source": badlar_data.get("tasa_usd_source"),
            "badlar_fecha": badlar_data.get("badlar_fecha"),
            "treasury_date": badlar_data.get("treasury_date"),
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def get_market_summary() -> dict:
    """Info de mercado: Oficial, MEP, CCL, Blue."""
    dolares = fetch_all_dolares()
    oficial = fetch_dolar_oficial()
    result = {}
    for d in dolares:
        t = d.get("casa", "").lower()
        if t in ("bolsa", "contadoconliqui", "blue"):
            key = "Bolsa" if t == "bolsa" else t
            result[key] = {
                "compra": d.get("compra"),
                "venta": d.get("venta"),
                "fecha": d.get("fechaActualizacion"),
            }
    if oficial:
        result["oficial"] = {
            "compra": oficial.get("compra"),
            "venta": oficial.get("venta"),
            "fecha": oficial.get("fechaActualizacion"),
        }
    return result


# ── FastAPI App ──────────────────────────────────────────────────────────────

app = FastAPI(title="Dollar Link Dashboard", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── HTML Dashboard ────────────────────────────────────────────────────────────

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang='es'>
<head>
<meta charset='UTF-8'>
<meta name='viewport' content='width=device-width, initial-scale=1.0'>
<title>Dollar Link AR — Dashboard</title>
<link rel='preconnect' href='https://fonts.googleapis.com'>
<link rel='preconnect' href='https://fonts.gstatic.com' crossorigin>
<link href='https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;700&family=Outfit:wght@300;400;500;600;700&family=Playfair+Display:ital,wght@0,400;0,600;0,700;1,400&display=swap' rel='stylesheet'>
<script src='https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js'></script>
<style>
  :root {
    --bg-void: #030303;
    --bg-surface: #0a0a0f;
    --bg-elevated: #111118;
    --glass: rgba(255, 255, 255, 0.03);
    --border: rgba(255, 255, 255, 0.08);
    --border-strong: rgba(255, 255, 255, 0.15);
    --text-primary: #e2e8f0;
    --text-secondary: #475569;
    --text-muted: #334155;
    --gold: #d4af37;
    --gold-dim: rgba(212, 175, 55, 0.15);
    --green: #4ade80;
    --green-dim: rgba(74, 222, 128, 0.1);
    --red: #f87171;
    --red-dim: rgba(248, 113, 113, 0.1);
    --blue: #60a5fa;
    --font-display: 'Playfair Display', serif;
    --font-mono: 'JetBrains Mono', monospace;
    --font-ui: 'Outfit', sans-serif;
  }

  * { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    background-color: var(--bg-void);
    color: var(--text-primary);
    font-family: var(--font-ui);
    min-height: 100vh;
    overflow-x: hidden;
    position: relative;
  }

  /* Atmospheric background */
  body::before {
    content: '';
    position: fixed;
    inset: 0;
    background-image:
      radial-gradient(circle at 20% 30%, rgba(212, 175, 55, 0.04) 0%, transparent 50%),
      radial-gradient(circle at 80% 70%, rgba(96, 165, 250, 0.03) 0%, transparent 50%);
    pointer-events: none;
    z-index: 0;
  }

  /* Subtle dot grid */
  body::after {
    content: '';
    position: fixed;
    inset: 0;
    background-image: radial-gradient(rgba(255,255,255,0.03) 1px, transparent 1px);
    background-size: 32px 32px;
    pointer-events: none;
    z-index: 0;
  }

  ::selection { background: var(--gold); color: var(--bg-void); }

  .container {
    position: relative;
    z-index: 1;
    max-width: 1400px;
    margin: 0 auto;
    padding: 40px 24px;
  }

  /* Header */
  header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 48px;
    animation: fadeInDown 0.8s ease-out both;
  }

  .brand {
    display: flex;
    align-items: baseline;
    gap: 16px;
  }

  .brand h1 {
    font-family: var(--font-display);
    font-size: 2.8rem;
    font-weight: 700;
    letter-spacing: -0.02em;
    line-height: 1;
    background: linear-gradient(180deg, #fff 0%, var(--text-secondary) 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
  }

  .brand-tag {
    font-family: var(--font-mono);
    font-size: 0.65rem;
    font-weight: 500;
    color: var(--gold);
    border: 1px solid var(--gold-dim);
    padding: 4px 10px;
    border-radius: 4px;
    letter-spacing: 0.1em;
    text-transform: uppercase;
  }

  .status-group {
    text-align: right;
  }

  .status-live {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    font-family: var(--font-mono);
    font-size: 0.75rem;
    color: var(--green);
    margin-bottom: 8px;
  }

  .status-live::before {
    content: '';
    width: 8px;
    height: 8px;
    background: var(--green);
    border-radius: 50%;
    box-shadow: 0 0 8px var(--green);
    animation: pulse 2s infinite;
  }

  .status-time {
    font-family: var(--font-mono);
    font-size: 0.8rem;
    color: var(--text-secondary);
  }

  /* Section titles */
  .section-label {
    font-family: var(--font-mono);
    font-size: 0.65rem;
    font-weight: 500;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.15em;
    margin-bottom: 16px;
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .section-label::after {
    content: '';
    flex: 1;
    height: 1px;
    background: linear-gradient(90deg, var(--border) 0%, transparent 100%);
  }

  /* FX Cards - asymmetric composition */
  .fx-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 1px;
    background: var(--border);
    border: 1px solid var(--border);
    border-radius: 12px;
    overflow: hidden;
    margin-bottom: 40px;
    animation: fadeInUp 0.8s 0.1s ease-out both;
  }

  .fx-card {
    background: var(--bg-surface);
    padding: 24px;
    position: relative;
    transition: background 0.3s ease;
  }

  .fx-card:hover {
    background: var(--bg-elevated);
  }

  .fx-card:not(:last-child)::after {
    content: '';
    position: absolute;
    right: 0;
    top: 20%;
    bottom: 20%;
    width: 1px;
    background: var(--border);
  }

  .fx-name {
    font-family: var(--font-ui);
    font-size: 0.75rem;
    font-weight: 500;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-bottom: 8px;
  }

  .fx-value {
    font-family: var(--font-mono);
    font-size: 1.6rem;
    font-weight: 700;
    color: var(--text-primary);
    letter-spacing: -0.02em;
  }

  .fx-value.gold { color: var(--gold); }
  .fx-value.blue { color: var(--blue); }
  .fx-value.red { color: var(--red); }
  .fx-value.green { color: var(--green); }

  .fx-sub {
    font-family: var(--font-mono);
    font-size: 0.7rem;
    color: var(--text-muted);
    margin-top: 4px;
  }

  /* Context banners (REM/BADLAR) */
  .context-strip {
    display: flex;
    gap: 16px;
    margin-bottom: 40px;
    animation: fadeInUp 0.8s 0.2s ease-out both;
  }

  .context-card {
    flex: 1;
    background: var(--glass);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 20px 24px;
    backdrop-filter: blur(8px);
    position: relative;
    overflow: hidden;
  }

  .context-card::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    width: 3px;
    height: 100%;
  }

  .context-card.rem::before { background: var(--blue); }
  .context-card.badlar::before { background: var(--gold); }

  .context-title {
    font-family: var(--font-mono);
    font-size: 0.6rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: var(--text-secondary);
    margin-bottom: 10px;
  }

  .context-body {
    font-family: var(--font-mono);
    font-size: 0.85rem;
    color: var(--text-primary);
    display: flex;
    gap: 20px;
    flex-wrap: wrap;
    align-items: center;
  }

  .context-stat {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .context-stat .label {
    font-size: 0.65rem;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .context-stat .value {
    font-size: 1rem;
    font-weight: 600;
    color: var(--text-primary);
  }

  .context-stat .sub {
    font-size: 0.6rem;
    color: var(--text-muted);
    font-style: italic;
  }

  /* Instruments */
  .instruments-section {
    animation: fadeInUp 0.8s 0.3s ease-out both;
  }

  .instruments-table {
    width: 100%;
    border-collapse: separate;
    border-spacing: 0 6px;
  }

  .instruments-table thead th {
    font-family: var(--font-mono);
    font-size: 0.6rem;
    font-weight: 500;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.1em;
    text-align: right;
    padding: 12px 20px;
    border-bottom: 1px solid var(--border);
  }

  .instruments-table thead th:first-child {
    text-align: left;
  }

  .instruments-table tbody tr {
    background: var(--bg-surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    position: relative;
    cursor: default;
  }

  .instruments-table tbody tr:hover {
    background: var(--bg-elevated);
    transform: translateX(6px);
    box-shadow: -4px 0 0 var(--gold-dim), 0 4px 24px rgba(0,0,0,0.4);
    border-color: var(--border-strong);
  }

  .instruments-table tbody td {
    padding: 18px 20px;
    font-family: var(--font-mono);
    font-size: 0.85rem;
    text-align: right;
    border-top: 1px solid var(--border);
    border-bottom: 1px solid var(--border);
    color: var(--text-primary);
  }

  .instruments-table tbody td:first-child {
    text-align: left;
    border-left: 1px solid var(--border);
    border-radius: 8px 0 0 8px;
  }

  .instruments-table tbody td:last-child {
    border-right: 1px solid var(--border);
    border-radius: 0 8px 8px 0;
  }

  .sym-tag {
    font-family: var(--font-mono);
    font-size: 0.8rem;
    font-weight: 700;
    color: var(--gold);
    letter-spacing: 0.05em;
  }

  .tipo-badge {
    font-family: var(--font-ui);
    font-size: 0.6rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    padding: 3px 8px;
    border-radius: 4px;
    background: var(--glass);
    border: 1px solid var(--border);
    color: var(--text-secondary);
  }

  .tipo-badge.letra { color: #d4af37; border-color: rgba(212, 175, 55, 0.2); }
  .tipo-badge.bono { color: #60a5fa; border-color: rgba(96, 165, 250, 0.2); }

  .up { color: var(--green); text-shadow: 0 0 10px var(--green-dim); }
  .down { color: var(--red); text-shadow: 0 0 10px var(--red-dim); }
  .flat { color: var(--text-secondary); }

  .vol {
    font-size: 0.75rem;
    color: var(--text-muted);
    font-weight: 400;
  }

  /* Footer */
  .footer {
    margin-top: 48px;
    padding-top: 24px;
    border-top: 1px solid var(--border);
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-family: var(--font-mono);
    font-size: 0.65rem;
    color: var(--text-muted);
    animation: fadeInUp 0.8s 0.5s ease-out both;
  }

  .refresh-btn {
    background: transparent;
    color: var(--text-secondary);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 8px 16px;
    font-family: var(--font-mono);
    font-size: 0.7rem;
    cursor: pointer;
    transition: all 0.3s ease;
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }

  .refresh-btn:hover {
    border-color: var(--gold);
    color: var(--gold);
    background: var(--gold-dim);
  }

  /* Chart Section */
  .chart-section {
    animation: fadeInUp 0.8s 0.4s ease-out both;
    margin-top: 48px;
  }
  .chart-container {
    position: relative;
    height: 380px;
    background: var(--bg-surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 24px;
  }

  /* Scrollbar */
  ::-webkit-scrollbar { width: 6px; }
  ::-webkit-scrollbar-track { background: var(--bg-void); }
  ::-webkit-scrollbar-thumb { background: var(--border-strong); border-radius: 3px; }
  ::-webkit-scrollbar-thumb:hover { background: var(--text-muted); }

  /* Animations */
  @keyframes fadeInUp {
    from { opacity: 0; transform: translateY(20px); }
    to { opacity: 1; transform: translateY(0); }
  }

  @keyframes fadeInDown {
    from { opacity: 0; transform: translateY(-20px); }
    to { opacity: 1; transform: translateY(0); }
  }

  @keyframes pulse {
    0%, 100% { opacity: 1; transform: scale(1); }
    50% { opacity: 0.5; transform: scale(0.9); }
  }

  @media (max-width: 900px) {
    .fx-grid { grid-template-columns: repeat(2, 1fr); }
    .context-strip { flex-direction: column; }
    .brand h1 { font-size: 2rem; }
    .instruments-table tbody td { padding: 14px 12px; font-size: 0.8rem; }
  }

  @media (max-width: 640px) {
    header { flex-direction: column; gap: 20px; }
    .status-group { text-align: left; }
    .fx-grid { grid-template-columns: 1fr; }
    .fx-card:not(:last-child)::after { display: none; }
    .brand h1 { font-size: 1.6rem; }
    .instruments-table thead { display: none; }
    .instruments-table tbody tr { display: block; margin-bottom: 12px; }
    .instruments-table tbody td {
      display: flex;
      justify-content: space-between;
      align-items: center;
      text-align: right;
      border: none;
      border-bottom: 1px solid var(--border);
      padding: 10px 16px;
    }
    .instruments-table tbody td:first-child,
    .instruments-table tbody td:last-child {
      border-radius: 0;
      border-left: none;
      border-right: none;
    }
    .instruments-table tbody td::before {
      content: attr(data-label);
      font-size: 0.65rem;
      text-transform: uppercase;
      color: var(--text-muted);
      letter-spacing: 0.05em;
    }
  }
</style>
</head>
<body>

<div class='container'>
  <header>
    <div class='brand'>
      <h1>Dollar Link</h1>
      <span class='brand-tag'>ARG · Tesoro Nacional</span>
    </div>
    <div class='status-group'>
      <div class='status-live'>Mercado en vivo</div>
      <div class='status-time' id='ts'>—</div>
    </div>
  </header>

  <div class='section-label'>Tipos de Cambio</div>
  <div class='fx-grid' id='cards-dolar'></div>

  <div class='context-strip'>
    <div class='context-card rem' id='rem-card' style='display:none'>
      <div class='context-title'>Expectativas REM · BCRA</div>
      <div class='context-body'>
        <div class='context-stat'>
          <span class='label'>Próximo Mes</span>
          <span class='value' id='rem-mes'>—</span>
        </div>
        <div class='context-stat'>
          <span class='label'>Próx. 12 Meses</span>
          <span class='value' id='rem-12m'>—</span>
        </div>
        <div class='context-stat'>
          <span class='label'>Fecha</span>
          <span class='value' id='rem-fecha'>—</span>
        </div>
      </div>
    </div>
    <div class='context-card badlar' id='badlar-card' style='display:none'>
      <div class='context-title'>Paridad de Tasas · BADLAR</div>
      <div class='context-body'>
        <div class='context-stat'>
          <span class='label'>BADLAR ARS</span>
          <span class='value' id='badlar-ars'>—</span>
        </div>
        <div class='context-stat'>
          <span class='label'>USD Riesgo Libre</span>
          <span class='value' id='badlar-usd'>—</span>
          <span class='sub' id='badlar-usd-source'>—</span>
        </div>
        <div class='context-stat'>
          <span class='label'>Fecha</span>
          <span class='value' id='badlar-fecha'>—</span>
        </div>
      </div>
    </div>
  </div>

  <div class='instruments-section'>
    <div class='section-label'>Instrumentos</div>
    <table class='instruments-table'>
      <thead>
        <tr>
          <th>Instrumento</th>
          <th>Tipo</th>
          <th>Vto.</th>
          <th>Último</th>
          <th>Var%</th>
          <th>Bid</th>
          <th>Ask</th>
          <th>USD Ofic.</th>
          <th>USD MEP</th>
          <th>USD CCL</th>
          <th>Fair REM</th>
          <th>Fair BADLAR</th>
          <th>Vol.</th>
        </tr>
      </thead>
      <tbody id='tbody'></tbody>
    </table>
  </div>

  <div class='chart-section'>
    <div class='section-label'>Proyección REM 12 Meses</div>
    <div class='chart-container'>
      <canvas id='remChart'></canvas>
    </div>
  </div>

  <div class='footer'>
    <span>Fuentes: Data912 · DolarAPI · BCRA. Datos referenciales.</span>
    <button class='refresh-btn' onclick='loadData()'>↻ Refrescar</button>
  </div>
</div>

<script>
const INSTRUMENTS = ['D30A6','D30S6','TZV26','TZV27','TZV28'];

function fmt(n) {
  if (n == null || isNaN(n)) return '—';
  return n.toLocaleString('es-AR', {minimumFractionDigits: 2, maximumFractionDigits: 2});
}
function fmtVol(n) {
  if (!n) return '—';
  if (n >= 1e9) return (n/1e9).toFixed(1) + 'B';
  if (n >= 1e6) return (n/1e6).toFixed(1) + 'M';
  if (n >= 1e3) return (n/1e3).toFixed(0) + 'K';
  return n;
}
function pctClass(p) {
  if (p == null) return 'flat';
  if (p > 0) return 'up';
  if (p < 0) return 'down';
  return 'flat';
}
function pctSign(p) {
  if (p == null) return '—';
  return (p >= 0 ? '+' : '') + p.toFixed(2) + '%';
}
function tsLocal(iso) {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString('es-AR', {hour:'2-digit',minute:'2-digit',second:'2-digit',day:'2-digit',month:'2-digit'});
  } catch(e) { return iso; }
}

function renderDolarCards(dolares) {
  const tipoLabel = {'oficial':'Dólar Oficial','Bolsa':'Dólar MEP','contadoconliqui':'Dólar CCL','blue':'Dólar Blue'};
  const tipoColorClass = {'oficial':'gold','Bolsa':'blue','contadoconliqui':'red','blue':'green'};
  let html = '';
  for (const [k,v] of Object.entries(dolares)) {
    const lbl = tipoLabel[k] || k;
    const color = tipoColorClass[k] || '';
    html += `<div class='fx-card'>
      <div class='fx-name'>${lbl}</div>
      <div class='fx-value ${color}'>$${fmt(v.venta)}</div>
      <div class='fx-sub'>Compra $${fmt(v.compra)}</div>
    </div>`;
  }
  document.getElementById('cards-dolar').innerHTML = html;
}

function renderInstruments(data) {
  document.getElementById('ts').textContent = tsLocal(data.timestamp);
  let html = '';
  for (const row of data.instruments) {
    const pct = row.pct_change;
    const pClass = pctClass(pct);
    const tipoClass = row.tipo === 'bono' ? 'bono' : 'letra';
    const tipoLabel = row.tipo === 'bono' ? 'Bono' : 'Letra';
    html += `<tr>
      <td data-label='Inst.'><span class='sym-tag'>${row.symbol}</span></td>
      <td data-label='Tipo'><span class='tipo-badge ${tipoClass}'>${tipoLabel}</span></td>
      <td data-label='Vto.' class='vol'>${row.maturity || '—'}</td>
      <td data-label='Último'>$${fmt(row.last)}</td>
      <td data-label='Var%' class='${pClass}'>${pctSign(pct)}</td>
      <td data-label='Bid'>$${fmt(row.bid)}</td>
      <td data-label='Ask'>$${fmt(row.ask)}</td>
      <td data-label='USD Ofic.'>${row.usd_price_oficial != null ? 'USD ' + fmt(row.usd_price_oficial) : '—'}</td>
      <td data-label='USD MEP'>${row.usd_price_mep != null ? 'USD ' + fmt(row.usd_price_mep) : '—'}</td>
      <td data-label='USD CCL'>${row.usd_price_ccl != null ? 'USD ' + fmt(row.usd_price_ccl) : '—'}</td>
      <td data-label='Fair REM' style='color:var(--blue)'>${row.usd_fair_value_rem != null ? 'USD ' + fmt(row.usd_fair_value_rem) : '—'}</td>
      <td data-label='Fair BADLAR' style='color:var(--gold)'>${row.usd_fair_value_badlar != null ? 'USD ' + fmt(row.usd_fair_value_badlar) : '—'}</td>
      <td data-label='Vol.' class='vol'>${fmtVol(row.volume)}</td>
    </tr>`;
  }
  document.getElementById('tbody').innerHTML = html;
}

function renderChart(data) {
  const ctx = document.getElementById('remChart');
  if (!ctx) return;

  const labels = ['Dólar Oficial', ...data.instruments.map(i => i.symbol)];
  const currentValues = [data.dolar_oficial.venta, ...data.instruments.map(i => i.last)];
  const projectedValues = [data.rem_forward_tc, ...data.instruments.map(i => i.rem_adjusted_ars)];

  if (window.remChartInstance) {
    window.remChartInstance.data.labels = labels;
    window.remChartInstance.data.datasets[0].data = currentValues;
    window.remChartInstance.data.datasets[1].data = projectedValues;
    window.remChartInstance.update();
    return;
  }

  window.remChartInstance = new Chart(ctx.getContext('2d'), {
    type: 'line',
    data: {
      labels: labels,
      datasets: [
        {
          label: 'Valor Actual (ARS)',
          data: currentValues,
          borderColor: '#475569',
          backgroundColor: '#475569',
          borderWidth: 2,
          tension: 0.4,
          pointRadius: 4,
          pointHoverRadius: 6,
          pointBackgroundColor: '#0a0a0f'
        },
        {
          label: 'Proyección REM 12m (ARS)',
          data: projectedValues,
          borderColor: '#d4af37',
          backgroundColor: '#d4af37',
          borderWidth: 2,
          borderDash: [6, 4],
          tension: 0.4,
          pointRadius: 4,
          pointHoverRadius: 6,
          pointBackgroundColor: '#0a0a0f'
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: {
          labels: {
            color: '#e2e8f0',
            font: { family: 'JetBrains Mono', size: 12 },
            usePointStyle: true,
            boxWidth: 8
          }
        },
        tooltip: {
          backgroundColor: '#0a0a0f',
          titleColor: '#d4af37',
          bodyColor: '#e2e8f0',
          borderColor: 'rgba(255,255,255,0.1)',
          borderWidth: 1,
          titleFont: { family: 'JetBrains Mono', size: 13 },
          bodyFont: { family: 'JetBrains Mono', size: 12 },
          padding: 12,
          displayColors: true,
          callbacks: {
            label: function(context) {
              let label = context.dataset.label || '';
              if (label) label += ': ';
              if (context.parsed.y != null) {
                label += '$' + context.parsed.y.toLocaleString('es-AR', {minimumFractionDigits: 2, maximumFractionDigits: 2});
              }
              return label;
            }
          }
        }
      },
      scales: {
        x: {
          grid: { color: 'rgba(255,255,255,0.03)' },
          ticks: { color: '#475569', font: { family: 'JetBrains Mono', size: 11 } }
        },
        y: {
          grid: { color: 'rgba(255,255,255,0.03)' },
          ticks: {
            color: '#475569',
            font: { family: 'JetBrains Mono', size: 11 },
            callback: function(value) {
              if (value >= 1e6) return '$' + (value/1e6).toFixed(1) + 'M';
              if (value >= 1e3) return '$' + (value/1e3).toFixed(0) + 'K';
              return '$' + value;
            }
          }
        }
      }
    }
  });
}

async function loadData() {
  try {
    const r = await fetch('/api/dollar-link');
    const data = await r.json();
    renderInstruments(data);
    renderChart(data);
    const resDol = await fetch('/api/market-summary');
    const dol = await resDol.json();
    renderDolarCards(dol);

    const rem = data.rem || {};
    const remEl = document.getElementById('rem-card');
    if (remEl) {
      remEl.style.display = 'block';
      document.getElementById('rem-mes').textContent = rem.inflacion_mes_siguiente != null ? rem.inflacion_mes_siguiente.toFixed(1) + '%' : '—';
      document.getElementById('rem-12m').textContent = rem.inflacion_prox_12_meses != null ? rem.inflacion_prox_12_meses.toFixed(1) + '%' : '—';
      document.getElementById('rem-fecha').textContent = rem.fecha || '—';
    }

    const badlar = data.badlar || {};
    const badlarEl = document.getElementById('badlar-card');
    if (badlarEl) {
      badlarEl.style.display = 'block';
      document.getElementById('badlar-ars').textContent = badlar.tasa_ars != null ? badlar.tasa_ars.toFixed(2) + '%' : '—';
      document.getElementById('badlar-usd').textContent = badlar.tasa_usd != null ? badlar.tasa_usd.toFixed(2) + '%' : '—';
      document.getElementById('badlar-usd-source').textContent = badlar.tasa_usd_source || '—';
      document.getElementById('badlar-fecha').textContent = badlar.badlar_fecha || badlar.treasury_date || '—';
    }
  } catch(e) {
    console.error(e);
    document.getElementById('tbody').innerHTML = `<tr><td colspan='13' style='text-align:center;color:var(--red);padding:40px;border:none;'>Error al cargar datos: ${e.message}</td></tr>`;
  }
}

loadData();
setInterval(loadData, 60 * 1000);
</script>
</body>
</html>"""

# ── Rutas ────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def root():
    return DASHBOARD_HTML


@app.get("/api/dollar-link")
async def api_dollar_link():
    data = assemble_dollar_link_data()
    return JSONResponse(content=data)


@app.get("/api/market-summary")
async def api_market_summary():
    summary = get_market_summary()
    return JSONResponse(content=summary)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"🚀 Dollar Link Dashboard → http://{HOST}:{PORT}")
    print(f"   API: http://{HOST}:{PORT}/api/dollar-link")
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")


if __name__ == "__main__":
    main()

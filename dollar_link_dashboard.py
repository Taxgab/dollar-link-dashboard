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

# ── Proxies para APIs ────────────────────────────────────────────────────────
DATA912_BASE = "https://data912.com"
DOLAR_API_BASE = "https://dolarapi.com"

# ── Instrumentos Dollar Link a trackear ──────────────────────────────────────
DL_INSTRUMENTS = ["D30A6", "D30S6", "TZV26", "TZV27", "TZV28", "TZV7D"]

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


def assemble_dollar_link_data() -> dict:
    """Consolida datos de instrumentos dollar link."""
    bonds = {b["symbol"]: b for b in fetch_bonds_panel()}
    notes = {n["symbol"]: n for n in fetch_notes_panel()}
    all_data = {**bonds, **notes}

    dolar = fetch_dolar_oficial() or {}
    dolar_oficial_venta = dolar.get("venta", 0) or 0

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
                "usd_price": None,
                "tipo": "bono" if sym.startswith("TZV") else "letra",
            })
            continue

        last = item.get("c", 0) or 0
        pct = item.get("pct_change", 0) or 0
        bid = item.get("px_bid", 0) or 0
        ask = item.get("px_ask", 0) or 0
        vol = item.get("v", 0) or 0

        usd_price = round(last / dolar_oficial_venta, 2) if dolar_oficial_venta else None

        rows.append({
            "symbol": sym,
            "last": last,
            "pct_change": pct,
            "bid": bid,
            "ask": ask,
            "volume": vol,
            "usd_price": usd_price,
            "tipo": "bono" if sym.startswith("TZV") else "letra",
        })

    return {
        "instruments": rows,
        "dolar_oficial": {
            "compra": dolar.get("compra"),
            "venta": dolar.get("venta"),
            "fecha": dolar.get("fechaActualizacion"),
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def get_market_summary() -> dict:
    """Info de mercado: MEP, CCL, Blue."""
    dolares = fetch_all_dolares()
    result = {}
    for d in dolares:
        t = d.get("casa", "")
        if t in ("Bolsa", "contadoconliqui", "blue"):
            result[t] = {
                "compra": d.get("compra"),
                "venta": d.get("venta"),
                "fecha": d.get("fechaActualizacion"),
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
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Dollar Link AR — Dashboard</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: #0d1117;
    color: #e6edf3;
    font-family: 'Inter', 'Segoe UI', system-ui, sans-serif;
    min-height: 100vh;
    padding: 24px;
  }
  header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 32px;
    flex-wrap: wrap;
    gap: 12px;
  }
  header h1 {
    font-size: 1.6rem;
    font-weight: 700;
    color: #58a6ff;
  }
  .badge {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 6px 14px;
    font-size: 0.8rem;
    color: #8b949e;
  }
  .badge span { color: #58a6ff; font-weight: 600; }

  /* Cards row */
  .cards-row {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 12px;
    margin-bottom: 28px;
  }
  .card {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 12px;
    padding: 16px 20px;
  }
  .card-label { font-size: 0.72rem; color: #8b949e; text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 4px; }
  .card-value { font-size: 1.5rem; font-weight: 700; color: #f0f6fc; }
  .card-sub { font-size: 0.75rem; color: #58a6ff; margin-top: 2px; }
  .card-value.red { color: #f85149; }
  .card-value.green { color: #3fb950; }

  /* Instruments table */
  .section-title {
    font-size: 1rem;
    font-weight: 600;
    color: #8b949e;
    margin-bottom: 12px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }
  table {
    width: 100%;
    border-collapse: collapse;
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 12px;
    overflow: hidden;
  }
  th {
    background: #1c2128;
    color: #8b949e;
    font-size: 0.72rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    padding: 12px 16px;
    text-align: right;
    border-bottom: 1px solid #30363d;
  }
  th:first-child { text-align: left; }
  td {
    padding: 14px 16px;
    font-size: 0.9rem;
    text-align: right;
    border-bottom: 1px solid #21262d;
    color: #e6edf3;
  }
  td:first-child { text-align: left; font-weight: 600; }
  tr:last-child td { border-bottom: none; }
  tr:hover td { background: #1c2128; }

  .sym-tag {
    display: inline-block;
    background: #21262d;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 3px 8px;
    font-size: 0.8rem;
    font-weight: 700;
    font-family: 'Courier New', monospace;
    color: #79c0ff;
  }
  .tipo-badge {
    display: inline-block;
    font-size: 0.68rem;
    padding: 2px 7px;
    border-radius: 10px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }
  .tipo-bono { background: #1f3a5f; color: #58a6ff; }
  .tipo-letra { background: #3a2f1f; color: #d29922; }

  .up { color: #3fb950; }
  .down { color: #f85149; }
  .flat { color: #8b949e; }
  .mono { font-family: 'Courier New', monospace; font-size: 0.85rem; }
  .vol { color: #8b949e; font-size: 0.8rem; }

  .footer {
    margin-top: 24px;
    font-size: 0.72rem;
    color: #484f58;
    text-align: center;
  }
  .refresh-btn {
    background: #238636;
    color: #fff;
    border: none;
    border-radius: 6px;
    padding: 6px 14px;
    font-size: 0.78rem;
    cursor: pointer;
    font-weight: 600;
  }
  .refresh-btn:hover { background: #2ea043; }

  @media (max-width: 640px) {
    th, td { padding: 10px 8px; font-size: 0.8rem; }
    .card-value { font-size: 1.2rem; }
  }
</style>
</head>
<body>

<header>
  <h1>🇦🇷 Dollar Link AR</h1>
  <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;">
    <div class="badge">Actualizado: <span id="ts">—</span></div>
    <button class="refresh-btn" onclick="loadData()">↻ Refrescar</button>
  </div>
</header>

<!-- Dólar Overview -->
<div class="cards-row" id="cards-dolar"></div>

<!-- Instruments Table -->
<div class="section-title">📈 Instrumentos Dollar Link — Tesoro Nacional</div>
<table id="tbl-instruments">
  <thead>
    <tr>
      <th>Instrumento</th>
      <th>Tipo</th>
      <th>Último (ARS)</th>
      <th>Var%</th>
      <th>Bid</th>
      <th>Ask</th>
      <th>USD equivalente</th>
      <th>Volumen</th>
    </tr>
  </thead>
  <tbody id="tbody"></tbody>
</table>

<div class="footer">
  Fuentes: Data912.com (market data educativo) · DolarAPI.com · No es asesoramiento financiero.
  Los precios son referenciales y pueden variar.
</div>

<script>
const INSTRUMENTS = ["D30A6","D30S6","TZV26","TZV27","TZV28","TZV7D"];

function fmt(n) {
  if (n == null || isNaN(n)) return "—";
  return n.toLocaleString("es-AR", {minimumFractionDigits: 2, maximumFractionDigits: 2});
}
function fmtVol(n) {
  if (!n) return "—";
  if (n >= 1e9) return (n/1e9).toFixed(1) + "B";
  if (n >= 1e6) return (n/1e6).toFixed(1) + "M";
  if (n >= 1e3) return (n/1e3).toFixed(0) + "K";
  return n;
}
function pctClass(p) {
  if (p == null) return "flat";
  if (p > 0) return "up";
  if (p < 0) return "down";
  return "flat";
}
function pctSign(p) {
  if (p == null) return "—";
  return (p >= 0 ? "+" : "") + p.toFixed(2) + "%";
}
function tsLocal(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("es-AR", {hour:"2-digit",minute:"2-digit",second:"2-digit",day:"2-digit",month:"2-digit"});
  } catch(e) { return iso; }
}

function renderDolarCards(dolares) {
  const tipoLabel = {"Bolsa":"Dólar MEP","contadoconliqui":"CCL","blue":"Blue"};
  const tipoColor = {"Bolsa":"#58a6ff","contadoconliqui":"#f85149","blue":"#d29922"};
  let html = "";
  for (const [k,v] of Object.entries(dolares)) {
    const lbl = tipoLabel[k] || k;
    const color = tipoColor[k] || "#8b949e";
    html += `<div class="card">
      <div class="card-label">${lbl}</div>
      <div class="card-value" style="color:${color}">$${fmt(v.venta)}</div>
      <div class="card-sub">Compra: $${fmt(v.compra)}</div>
    </div>`;
  }
  document.getElementById("cards-dolar").innerHTML = html;
}

function renderInstruments(data) {
  const oficial = data.dolar_oficial?.venta;
  document.getElementById("ts").textContent = tsLocal(data.timestamp);

  let html = "";
  for (const row of data.instruments) {
    const pct = row.pct_change;
    const pClass = pctClass(pct);
    const tipoBadge = row.tipo === "bono"
      ? `<span class="tipo-badge tipo-bono">Bono</span>`
      : `<span class="tipo-badge tipo-letra">Letra</span>`;
    html += `<tr>
      <td><span class="sym-tag">${row.symbol}</span></td>
      <td>${tipoBadge}</td>
      <td class="mono">$${fmt(row.last)}</td>
      <td class="${pClass}">${pctSign(pct)}</td>
      <td class="mono">$${fmt(row.bid)}</td>
      <td class="mono">$${fmt(row.ask)}</td>
      <td class="mono">${row.usd_price != null ? "USD " + fmt(row.usd_price) : "—"}</td>
      <td class="vol">${fmtVol(row.volume)}</td>
    </tr>`;
  }
  document.getElementById("tbody").innerHTML = html;
}

async function loadData() {
  try {
    const r = await fetch("/api/dollar-link");
    const data = await r.json();
    renderInstruments(data);
    const resDol = await fetch("/api/market-summary");
    const dol = await resDol.json();
    renderDolarCards(dol);
  } catch(e) {
    console.error(e);
    document.getElementById("tbody").innerHTML = `<tr><td colspan="8" style="text-align:center;color:#f85149;padding:20px;">Error al cargar datos: ${e.message}</td></tr>`;
  }
}

// Auto-refresh
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

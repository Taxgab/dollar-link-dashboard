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
BCRA_API_BASE = "https://api.bcra.gob.ar/estadisticas/v4.0"

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


def fetch_badlar() -> dict:
    """Trae última BADLAR bancos privados (ID 7) y tasa USD implícita (~5%)."""
    BADLAR_USD = 5.0  # Tasa anual USD aprox (Fed Funds ~5%)
    entries = fetch_bcra_variable(7, 3)
    if not entries:
        return {"badlar": None, "tasa_usd": BADLAR_USD, "fecha": None}
    return {
        "badlar": entries[0].get("valor"),
        "tasa_usd": BADLAR_USD,
        "fecha": entries[0].get("fecha"),
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
        "rem": {
            "inflacion_mes_siguiente": rem.get("mes_siguiente"),
            "inflacion_prox_12_meses": prox_12_meses,
            "fecha": rem.get("fecha"),
        },
        "badlar": {
            "tasa_ars": badlar,
            "tasa_usd": tasa_usd,
            "fecha": badlar_data.get("fecha"),
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

<!-- REM Info -->
<div id="rem-info" class="rem-banner" style="display:none; margin-bottom:24px; padding:12px 18px; background:#161b22; border:1px solid #30363d; border-radius:10px; font-size:0.82rem; color:#8b949e;">
  <span style="color:#58a6ff;font-weight:600;">REM Inflación esperada:</span>
  Mes próximo: <span id="rem-mes" style="color:#f0f6fc;font-family:'Courier New',monospace;">—</span>
  &nbsp;|&nbsp;
  Próx. 12 meses: <span id="rem-12m" style="color:#f0f6fc;font-family:'Courier New',monospace;">—</span>
  &nbsp;|&nbsp;
  <span style="font-size:0.72rem;">Fuente: BCRA REM · Actualizado: <span id="rem-fecha">—</span></span>
</div>

<!-- BADLAR Info -->
<div id="badlar-info" style="display:none; margin-bottom:24px; padding:12px 18px; background:#161b22; border:1px solid #30363d; border-radius:10px; font-size:0.82rem; color:#8b949e;">
  <span style="color:#d29922;font-weight:600;">Paridad de tasas (BADLAR):</span>
  BADLAR (ARS): <span id="badlar-ars" style="color:#f0f6fc;font-family:'Courier New',monospace;">—</span>
  &nbsp;|&nbsp;
  Tasa USD: <span id="badlar-usd" style="color:#f0f6fc;font-family:'Courier New',monospace;">—</span>
  &nbsp;|&nbsp;
  <span style="font-size:0.72rem;">Fuente: BCRA · Actualizado: <span id="badlar-fecha">—</span></span>
</div>

<!-- Instruments Table -->
<div class="section-title">📈 Instrumentos Dollar Link — Tesoro Nacional</div>
<table id="tbl-instruments">
  <thead>
    <tr>
      <th>Instrumento</th>
      <th>Tipo</th>
      <th>Vto.</th>
      <th>Último (ARS)</th>
      <th>Var%</th>
      <th>Bid</th>
      <th>Ask</th>
      <th>USD Oficial</th>
      <th>USD MEP</th>
      <th>USD CCL</th>
      <th>USD Fair (REM)</th>
      <th>USD Fair (BADLAR)</th>
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
const INSTRUMENTS = ["D30A6","D30S6","TZV26","TZV27","TZV28"];

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
  const tipoLabel = {"oficial":"Dólar Oficial","Bolsa":"Dólar MEP","contadoconliqui":"CCL","blue":"Blue"};
  const tipoColor = {"oficial":"#3fb950","Bolsa":"#58a6ff","contadoconliqui":"#f85149","blue":"#d29922"};
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
      <td class="mono" style="color:#8b949e;">${row.maturity || "—"}</td>
      <td class="mono">$${fmt(row.last)}</td>
      <td class="${pClass}">${pctSign(pct)}</td>
      <td class="mono">$${fmt(row.bid)}</td>
      <td class="mono">$${fmt(row.ask)}</td>
      <td class="mono">${row.usd_price_oficial != null ? "USD " + fmt(row.usd_price_oficial) : "—"}</td>
      <td class="mono">${row.usd_price_mep != null ? "USD " + fmt(row.usd_price_mep) : "—"}</td>
      <td class="mono">${row.usd_price_ccl != null ? "USD " + fmt(row.usd_price_ccl) : "—"}</td>
      <td class="mono" style="color:#f0883e;">${row.usd_fair_value_rem != null ? "USD " + fmt(row.usd_fair_value_rem) : "—"}</td>
      <td class="mono" style="color:#d29922;">${row.usd_fair_value_badlar != null ? "USD " + fmt(row.usd_fair_value_badlar) : "—"}</td>
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

    // REM banner
    const rem = data.rem || {};
    const remEl = document.getElementById("rem-info");
    if (remEl) {
      remEl.style.display = "block";
      const mesEl = document.getElementById("rem-mes");
      const m12El = document.getElementById("rem-12m");
      const fecEl = document.getElementById("rem-fecha");
      if (mesEl) mesEl.textContent = rem.inflacion_mes_siguiente != null ? rem.inflacion_mes_siguiente.toFixed(1) + "%" : "—";
      if (m12El) m12El.textContent = rem.inflacion_prox_12_meses != null ? rem.inflacion_prox_12_meses.toFixed(1) + "%" : "—";
      if (fecEl) fecEl.textContent = rem.fecha || "—";
    }

    // BADLAR banner
    const badlar = data.badlar || {};
    const badlarEl = document.getElementById("badlar-info");
    if (badlarEl) {
      badlarEl.style.display = "block";
      const arsEl = document.getElementById("badlar-ars");
      const usdEl = document.getElementById("badlar-usd");
      const fecEl = document.getElementById("badlar-fecha");
      if (arsEl) arsEl.textContent = badlar.tasa_ars != null ? badlar.tasa_ars.toFixed(2) + "%" : "—";
      if (usdEl) usdEl.textContent = badlar.tasa_usd != null ? badlar.tasa_usd.toFixed(1) + "%" : "—";
      if (fecEl) fecEl.textContent = badlar.fecha || "—";
    }
  } catch(e) {
    console.error(e);
    document.getElementById("tbody").innerHTML = `<tr><td colspan="12" style="text-align:center;color:#f85149;padding:20px;">Error al cargar datos: ${e.message}</td></tr>`;
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

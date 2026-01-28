import streamlit as st
import pandas as pd
import time
import json
import os
from datetime import datetime, timedelta

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from indicators import ut_bot, macd, stochastic, rsi, sma, cci, adx
from discord import send_discord

# ======================================================
# SECRETS
# ======================================================

API_KEY = st.secrets.get("POLYGON_API_KEY")
WEBHOOK = st.secrets.get("DISCORD_WEBHOOK")

if not API_KEY:
    st.error("❌ POLYGON_API_KEY manquant dans les secrets")
    st.stop()

if not WEBHOOK:
    st.error("❌ DISCORD_WEBHOOK manquant dans les secrets")
    st.stop()

# ======================================================
# PARAMÈTRES GÉNÉRAUX
# ======================================================

FILE_PATH = "russell3000_constituents.xlsx"
LOOKBACK_DAYS = 400

BATCH_SIZE = 300
SLEEP_API = 0.4
PROGRESS_FILE = "scan_progress.json"
RERUN_DELAY = 5  # secondes entre les batchs

# ======================================================
# SESSION HTTP ROBUSTE (ANTI TIMEOUT)
# ======================================================

session = requests.Session()

retries = Retry(
    total=3,
    backoff_factor=1.5,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET"]
)

adapter = HTTPAdapter(max_retries=retries)
session.mount("https://", adapter)

# ======================================================
# POLYGON — DAILY DATA
# ======================================================

def load_polygon_daily(ticker):
    end = datetime.utcnow().date()
    start = end - timedelta(days=LOOKBACK_DAYS)

    url = f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day/{start}/{end}"

    try:
        r = session.get(
            url,
            params={"apiKey": API_KEY, "adjusted": "true"},
            timeout=30
        )

        if r.status_code != 200:
            return None

        data = r.json()
        if "results" not in data:
            return None

        df = pd.DataFrame(data["results"])
        if df.empty or len(df) < 200:
            return None

        df["close"] = df["c"]
        df["high"] = df["h"]
        df["low"] = df["l"]

        return df.reset_index(drop=True)

    except Exception:
        return None

# ======================================================
# INTERFACE
# ======================================================

st.title("🎯 Coach Swing — Daily NEW BUY (Batch automatique)")

df_tickers = pd.read_excel(FILE_PATH, engine="openpyxl")

if "Symbol" not in df_tickers.columns:
    st.error("❌ Colonne 'Symbol' introuvable dans le fichier")
    st.stop()

tickers = (
    df_tickers["Symbol"]
    .dropna()
    .astype(str)
    .str.upper()
    .unique()
    .tolist()
)

st.caption(f"📊 Univers total : {len(tickers)} actions")

# ======================================================
# GESTION DE LA PROGRESSION (BATCH)
# ======================================================

if os.path.exists(PROGRESS_FILE):
    with open(PROGRESS_FILE, "r") as f:
        start_index = json.load(f).get("index", 0)
else:
    start_index = 0

end_index = min(start_index + BATCH_SIZE, len(tickers))
batch_tickers = tickers[start_index:end_index]

st.caption(f"📦 Batch automatique : {start_index + 1} → {end_index}")

# ======================================================
# SCAN AUTOMATIQUE
# ======================================================

st.info("⏳ Scan daily automatique en cours…")

progress = st.progress(0)
new_buys = []

for i, ticker in enumerate(batch_tickers, start=start_index + 1):
    df = load_polygon_daily(ticker)

    if df is None:
        progress.progress((i - start_index) / len(batch_tickers))
        continue

    # ======================
    # INDICATEURS
    # ======================

    ut = ut_bot(df)
    macd_val, macd_sig = macd(df["close"])
    k, d = stochastic(df)
    rsi_val = rsi(df["close"], 12)
    rsi_ma = sma(rsi_val, 5)
    cci_val = cci(df)
    adx_val = adx(df)

    i0 = -1   # aujourd'hui
    i1 = -2   # hier

    # ======================
    # LOGIQUE BUY STRICTE (AUJOURD'HUI SEULEMENT)
    # ======================

    ut_today = (
        df["close"].iloc[i0] > ut.iloc[i0] and
        df["close"].iloc[i1] <= ut.iloc[i1]
    )

    ut_yesterday = (
        df["close"].iloc[i1] > ut.iloc[i1] and
        df["close"].iloc[i1-1] <= ut.iloc[i1-1]
    )

    macd_today = (
        macd_val.iloc[i0] > macd_sig.iloc[i0] and
        macd_val.iloc[i0] < 0
    )

    macd_yesterday = (
        macd_val.iloc[i1] > macd_sig.iloc[i1] and
        macd_val.iloc[i1] < 0
    )

    stoch_today = k.iloc[i0] > d.iloc[i0]
    stoch_yesterday = k.iloc[i1] > d.iloc[i1]

    buy_today = ut_today and macd_today and stoch_today
    buy_yesterday = ut_yesterday and macd_yesterday and stoch_yesterday

    # ======================
    # SCORE
    # ======================

    score_today = (
        (rsi_val.iloc[i0] < 40) +
        (cci_val.iloc[i0] > cci_val.iloc[i0-1]) +
        (adx_val.iloc[i0] > 20) +
        (rsi_val.iloc[i0] > rsi_ma.iloc[i0])
    )

    # ======================
    # NEW BUY UNIQUEMENT
    # ======================

    if buy_today and not buy_yesterday:
        if score_today >= 3:
            label = "🟢 BUY VERT"
        elif score_today >= 1:
            label = "🟡 BUY JAUNE"
        else:
            label = "🔴 BUY ROUGE"

        new_buys.append(f"{label} **{ticker}**")

    progress.progress((i - start_index) / len(batch_tickers))
    time.sleep(SLEEP_API)

progress.empty()

# ======================================================
# SAUVEGARDE + RERUN AUTOMATIQUE
# ======================================================

if end_index >= len(tickers):
    # Scan COMPLET terminé
    with open(PROGRESS_FILE, "w") as f:
        json.dump({"index": 0}, f)

    st.success("✅ Scan Russell 3000 COMPLÉTÉ")
    st.stop()

else:
    # Sauvegarde progression
    with open(PROGRESS_FILE, "w") as f:
        json.dump({"index": end_index}, f)

    st.info("🔄 Batch suivant dans 5 secondes…")
    time.sleep(RERUN_DELAY)
    st.experimental_rerun()

# ======================================================
# DISCORD
# ======================================================

if new_buys:
    message = (
        "🎯 **COACH SWING — NEW BUY DAILY**\n"
        f"Batch {start_index + 1} → {end_index}\n\n"
        + "\n".join(new_buys)
    )
    send_discord(WEBHOOK, message)

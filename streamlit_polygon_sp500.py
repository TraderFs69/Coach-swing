import streamlit as st
import pandas as pd
import requests
import time
from datetime import datetime, timedelta

from indicators import *
from discord import send_discord

API_KEY = st.secrets["POLYGON_API_KEY"]
WEBHOOK = st.secrets["DISCORD_WEBHOOK"]

# ======================
# PARAMÈTRES
# ======================

FILE_PATH = "russell3000_constituents.xlsx"
TIMEFRAME = "day"
LOOKBACK_DAYS = 400   # assez pour indicateurs
SLEEP_API = 0.25      # protection Polygon

# ======================
# POLYGON
# ======================

def load_polygon_daily(ticker):
    end = datetime.utcnow().date()
    start = end - timedelta(days=LOOKBACK_DAYS)

    url = f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day/{start}/{end}"
    r = requests.get(
        url,
        params={"apiKey": API_KEY, "adjusted": "true"},
        timeout=10
    ).json()

    if "results" not in r:
        return None

    df = pd.DataFrame(r["results"])
    if df.empty:
        return None

    df["close"] = df["c"]
    df["high"] = df["h"]
    df["low"] = df["l"]
    return df.reset_index(drop=True)

# ======================
# INTERFACE
# ======================

st.title("🎯 Coach Swing – Daily NEW BUY Scanner")

df_tickers = pd.read_excel(FILE_PATH)

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

st.caption(f"📊 {len(tickers)} tickers chargés")

run = st.button("🚀 Lancer le scan daily")

# ======================
# SCAN
# ======================

if run:
    progress = st.progress(0)
    new_buys = []

    for idx, ticker in enumerate(tickers, start=1):
        df = load_polygon_daily(ticker)

        if df is None or len(df) < 200:
            progress.progress(idx / len(tickers))
            continue

        # === Indicateurs
        ut = ut_bot(df)
        macd_val, macd_sig = macd(df["close"])
        k, d = stochastic(df)
        rsi_val = rsi(df["close"], 12)
        rsi_ma = sma(rsi_val, 5)
        cci_val = cci(df)
        adx_val = adx(df)

        i = -1      # aujourd'hui
        i_prev = -2 # hier

        # === UT récent (aujourd’hui ou 2 jours avant, comme ton Pine)
        ut_today = any(
            df["close"].iloc[i-j] > ut.iloc[i-j] and
            df["close"].iloc[i-j-1] <= ut.iloc[i-j-1]
            for j in range(3)
        )

        ut_yesterday = any(
            df["close"].iloc[i_prev-j] > ut.iloc[i_prev-j] and
            df["close"].iloc[i_prev-j-1] <= ut.iloc[i_prev-j-1]
            for j in range(3)
        )

        # === MACD croisé sous zéro
        macd_today = any(
            macd_val.iloc[i-j] > macd_sig.iloc[i-j] and macd_val.iloc[i-j] < 0
            for j in range(5)
        )

        macd_yesterday = any(
            macd_val.iloc[i_prev-j] > macd_sig.iloc[i_prev-j] and macd_val.iloc[i_prev-j] < 0
            for j in range(5)
        )

        # === Stoch
        stoch_today = any(
            k.iloc[i-j] > d.iloc[i-j]
            for j in range(3)
        )

        stoch_yesterday = any(
            k.iloc[i_prev-j] > d.iloc[i_prev-j]
            for j in range(3)
        )

        # === Score
        score_today = (
            (rsi_val.iloc[i] < 40) +
            (cci_val.iloc[i] > cci_val.iloc[i-1]) +
            (adx_val.iloc[i] > 20) +
            (rsi_val.iloc[i] > rsi_ma.iloc[i])
        )

        score_yesterday = (
            (rsi_val.iloc[i_prev] < 40) +
            (cci_val.iloc[i_prev] > cci_val.iloc[i_prev-1]) +
            (adx_val.iloc[i_prev] > 20) +
            (rsi_val.iloc[i_prev] > rsi_ma.iloc[i_prev])
        )

        # === BUY AUJOURD’HUI / HIER
        buy_today = ut_today and macd_today and stoch_today
        buy_yesterday = ut_yesterday and macd_yesterday and stoch_yesterday

        # === NEW BUY UNIQUEMENT
        if buy_today and not buy_yesterday:
            if score_today >= 3:
                label = "🟢 BUY VERT"
            elif score_today >= 1:
                label = "🟡 BUY JAUNE"
            else:
                label = "🔴 BUY ROUGE"

            new_buys.append(f"{label} **{ticker}**")

        progress.progress(idx / len(tickers))
        time.sleep(SLEEP_API)

    progress.empty()

    # ======================
    # DISCORD
    # ======================

    if new_buys:
        message = "🎯 **COACH SWING – NEW BUY (DAILY)**\n\n" + "\n".join(new_buys)
        send_discord(WEBHOOK, message)
        st.success(f"✅ {len(new_buys)} NEW BUY envoyés sur Discord")
    else:
        st.info("ℹ️ Aucun NEW BUY aujourd’hui")

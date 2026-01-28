import streamlit as st
import pandas as pd
import requests
from indicators import *
from discord import send_discord

API_KEY = st.secrets["POLYGON_API_KEY"]
WEBHOOK = st.secrets["DISCORD_WEBHOOK"]

TICKERS = ["AAPL", "MSFT", "NVDA"]  # à remplacer par ton univers
TIMEFRAME = "day"  # ou "5/minute"

def load_polygon(ticker):
    url = f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day/2024-01-01/2026-01-01"
    r = requests.get(url, params={"apiKey": API_KEY}).json()
    if "results" not in r:
        return None
    df = pd.DataFrame(r["results"])
    df["close"] = df["c"]
    df["high"] = df["h"]
    df["low"] = df["l"]
    return df

st.title("🎯 Coach Swing – Scanner Polygon")

if st.button("🚀 Scanner"):
    for t in TICKERS:
        df = load_polygon(t)
        if df is None or len(df) < 200:
            continue

        ut = ut_bot(df)
        macd_val, macd_sig = macd(df["close"])
        k, d = stochastic(df)
        rsi_val = rsi(df["close"], 12)
        rsi_ma = sma(rsi_val, 5)
        cci_val = cci(df)
        adx_val = adx(df)

        i = -1

        ut_recent = any(
            df["close"].iloc[i-j] > ut.iloc[i-j] and
            df["close"].iloc[i-j-1] <= ut.iloc[i-j-1]
            for j in range(3)
        )

        macd_ok = any(
            macd_val.iloc[i-j] > macd_sig.iloc[i-j] and macd_val.iloc[i-j] < 0
            for j in range(5)
        )

        stoch_ok = any(
            k.iloc[i-j] > d.iloc[i-j]
            for j in range(3)
        )

        score = 0
        score += rsi_val.iloc[i] < 40
        score += cci_val.iloc[i] > cci_val.iloc[i-1]
        score += adx_val.iloc[i] > 20
        score += rsi_val.iloc[i] > rsi_ma.iloc[i]

        if ut_recent and macd_ok and stoch_ok:
            if score >= 3:
                send_discord(WEBHOOK, f"🟢 **BUY VERT** {t}")
            elif score >= 1:
                send_discord(WEBHOOK, f"🟡 **BUY JAUNE** {t}")
            else:
                send_discord(WEBHOOK, f"🔴 **BUY ROUGE** {t}")

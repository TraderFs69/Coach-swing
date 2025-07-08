
import streamlit as st
import pandas as pd
import numpy as np
import asyncio
import aiohttp
import random
import datetime

SLEEP_MIN = 0.1
SLEEP_MAX = 0.5
TIMEOUT_SECONDS = 15
import os
from dotenv import load_dotenv
load_dotenv()
API_KEY = os.getenv("POLYGON_API_KEY")

st.title("📊 Scanner Swing S&P 500 (Polygon.io)")
st.markdown("Ce scanner utilise UT Bot, MACD, Stochastique, ADX et OBV pour détecter des signaux d'achat sur le S&P 500.")

results = []
failed = []

@st.cache_data
def load_tickers():
    sp500_url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    return pd.read_html(sp500_url)[0]["Symbol"].tolist()

tickers = load_tickers()
st.success(f"✅ {len(tickers)} tickers récupérés pour le S&P500")

async def fetch_ticker(session, ticker):
    url = f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day/2024-07-08/2025-07-08?adjusted=true&sort=asc&apiKey={API_KEY}"
    try:
        async with session.get(url, timeout=TIMEOUT_SECONDS) as resp:
            if resp.status != 200:
                return ticker, None
            data = await resp.json()
            if 'results' not in data or not data['results']:
                return ticker, None
            df = pd.DataFrame(data['results'])
            df["t"] = pd.to_datetime(df["t"], unit="ms")
            df.set_index("t", inplace=True)
            df.rename(columns={"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"}, inplace=True)
            return ticker, df
    except:
        return ticker, None

def calculate_indicators(df):
    if df is None or df.empty or len(df) < 200:
        return False
    df.dropna(inplace=True)

    high_low = df["high"] - df["low"]
    high_close = np.abs(df["high"] - df["close"].shift())
    low_close = np.abs(df["low"] - df["close"].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = tr.rolling(window=10).mean()

    upper_band = df["close"] + 0.5 * atr
    lower_band = df["close"] - 0.5 * atr
    trail_price = df["close"].copy()
    for i in range(1, len(df)):
        if df["close"].iloc[i] > trail_price.iloc[i-1]:
            trail_price.iloc[i] = max(trail_price.iloc[i-1], lower_band.iloc[i])
        else:
            trail_price.iloc[i] = min(trail_price.iloc[i-1], upper_band.iloc[i])
    ut_buy = (df["close"] > trail_price) & (df["close"].shift(1) <= trail_price.shift(1))

    ema_fast = df["close"].ewm(span=5, adjust=False).mean()
    ema_slow = df["close"].ewm(span=13, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    macd_signal = macd_line.ewm(span=4, adjust=False).mean()
    macd_cond = macd_line > macd_signal

    low_min = df["low"].rolling(window=8).min()
    high_max = df["high"].rolling(window=8).max()
    k = 100 * ((df["close"] - low_min) / (high_max - low_min))
    k_smooth = k.rolling(window=5).mean()
    d = k_smooth.rolling(window=3).mean()
    stoch_cond = (k_smooth > d) & (k_smooth < 50)

    up_move = df["high"].diff()
    down_move = df["low"].diff().abs()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)
    tr = pd.concat([
        df["high"] - df["low"],
        np.abs(df["high"] - df["close"].shift()),
        np.abs(df["low"] - df["close"].shift())
    ], axis=1).max(axis=1)
    atr14 = tr.rolling(window=14).mean()
    plus_di = 100 * pd.Series(plus_dm).rolling(window=14).sum() / atr14
    minus_di = 100 * pd.Series(minus_dm).rolling(window=14).sum() / atr14
    dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di)
    adx = dx.rolling(window=14).mean()
    adx_cond = adx > 20

    obv = df["volume"].copy()
    obv[df["close"].diff() > 0] = df["volume"]
    obv[df["close"].diff() < 0] = -df["volume"]
    obv = obv.fillna(0).cumsum()
    obv_sma20 = obv.rolling(window=20).mean()
    obv_cond = obv > obv_sma20

    buy_signal = ut_buy & macd_cond & stoch_cond & adx_cond & obv_cond
    return buy_signal.iloc[-1]

async def run_scan():
    async with aiohttp.ClientSession() as session:
        for i in range(0, len(tickers), 5):
            batch = tickers[i:i+5]
            tasks = [fetch_ticker(session, t) for t in batch]
            responses = await asyncio.gather(*tasks)
            for ticker, df in responses:
                if df is None:
                    failed.append(ticker)
                elif calculate_indicators(df):
                    results.append(ticker)
            await asyncio.sleep(random.uniform(SLEEP_MIN, SLEEP_MAX))

if st.button("🚀 Lancer le scan"):
    asyncio.run(run_scan())
    st.success(f"🎯 {len(results)} tickers avec signaux détectés.")
    df_res = pd.DataFrame(results, columns=["Ticker"])
    st.dataframe(df_res)
    st.download_button("📥 Télécharger les résultats", df_res.to_csv(index=False), "signals.csv", "text/csv")

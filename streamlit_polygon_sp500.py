
import os
import pandas as pd
import streamlit as st
import asyncio
import aiohttp
from datetime import datetime, timedelta

API_KEY = os.getenv("POLYGON_API_KEY")

@st.cache_data
def load_tickers():
    sp500_url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    return pd.read_html(sp500_url)[0]["Symbol"].tolist()

async def fetch_ticker(session, ticker, from_date, to_date):
    url = f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day/{from_date}/{to_date}?adjusted=true&sort=asc&limit=365&apiKey={API_KEY}"
    try:
        async with session.get(url) as resp:
            if resp.status != 200:
                return ticker, None
            data = await resp.json()
            if not data.get("results"):
                return ticker, None
            df = pd.DataFrame(data["results"])
            df["t"] = pd.to_datetime(df["t"], unit="ms")
            df.rename(columns={"t": "date", "o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"}, inplace=True)
            df.set_index("date", inplace=True)
            return ticker, df
    except Exception as e:
        return ticker, None

def calculate_indicators(df):
    if df is None or df.empty or len(df) < 200:
        return None

    high_low = df["high"] - df["low"]
    high_close = abs(df["high"] - df["close"].shift())
    low_close = abs(df["low"] - df["close"].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = tr.rolling(window=10).mean()

    upper_band = df["close"] + 0.5 * atr
    lower_band = df["close"] - 0.5 * atr
    trail_price = df["close"].copy()
    for i in range(1, len(df)):
        if df["close"].iloc[i] > trail_price.iloc[i - 1]:
            trail_price.iloc[i] = max(trail_price.iloc[i - 1], lower_band.iloc[i])
        else:
            trail_price.iloc[i] = min(trail_price.iloc[i - 1], upper_band.iloc[i])
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
    plus_dm = (up_move > down_move) & (up_move > 0) * up_move
    minus_dm = (down_move > up_move) & (down_move > 0) * down_move
    tr = pd.concat([df["high"] - df["low"], abs(df["high"] - df["close"].shift()), abs(df["low"] - df["close"].shift())], axis=1).max(axis=1)
    atr14 = tr.rolling(window=14).mean()
    plus_di = 100 * pd.Series(plus_dm).rolling(window=14).sum() / atr14
    minus_di = 100 * pd.Series(minus_dm).rolling(window=14).sum() / atr14
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
    adx = dx.rolling(window=14).mean()
    adx_cond = adx > 20

    obv = df["volume"].copy()
    obv[df["close"].diff() > 0] = df["volume"]
    obv[df["close"].diff() < 0] = -df["volume"]
    obv = obv.fillna(0).cumsum()
    obv_sma20 = obv.rolling(window=20).mean()
    obv_cond = obv > obv_sma20

    count = ut_buy.astype(int) + macd_cond.astype(int) + stoch_cond.astype(int) + adx_cond.astype(int) + obv_cond.astype(int)
    return count.iloc[-1]

async def main(min_conditions):
    tickers = load_tickers()
    from_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
    to_date = datetime.now().strftime("%Y-%m-%d")
    conditions_summary = []

    async with aiohttp.ClientSession() as session:
        tasks = [fetch_ticker(session, ticker, from_date, to_date) for ticker in tickers]
        responses = await asyncio.gather(*tasks)
        for ticker, df in responses:
            result = calculate_indicators(df)
            if result is not None:
                conditions_summary.append({"Ticker": ticker, "Conditions Remplies": result})
    return conditions_summary

st.title("📊 Scanner S&P 500 avec Polygon.io")
min_conditions = st.slider("Nombre minimum de conditions remplies", 3, 5, 4)
conditions_summary = asyncio.run(main(min_conditions))

df_summary = pd.DataFrame(conditions_summary)
if not df_summary.empty:
    st.subheader("📋 Résumé des conditions par ticker")
    st.dataframe(df_summary[df_summary["Conditions Remplies"] >= min_conditions])
else:
    st.warning("Aucun ticker ne remplit les conditions minimales.")

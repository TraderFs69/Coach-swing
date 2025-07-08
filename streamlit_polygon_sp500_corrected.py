
import streamlit as st
import pandas as pd
import numpy as np
import os
import requests
import datetime
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("POLYGON_API_KEY")
BASE_URL = "https://api.polygon.io"

@st.cache_data
def load_tickers():
    sp500_url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    return pd.read_html(sp500_url)[0]["Symbol"].tolist()

def fetch_data(ticker, timespan="day", from_date=None, to_date=None):
    endpoint = f"/v2/aggs/ticker/{ticker}/range/1/{timespan}/{from_date}/{to_date}"
    url = f"{BASE_URL}{endpoint}?adjusted=true&sort=asc&apiKey={API_KEY}"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()["results"]
        df = pd.DataFrame(data)
        df["t"] = pd.to_datetime(df["t"], unit="ms")
        df.rename(columns={"t": "date", "v": "volume", "o": "open", "c": "close", "h": "high", "l": "low"}, inplace=True)
        df.set_index("date", inplace=True)
        return df
    else:
        return None

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
    tr14 = pd.concat([
        df["high"] - df["low"],
        np.abs(df["high"] - df["close"].shift()),
        np.abs(df["low"] - df["close"].shift())
    ], axis=1).max(axis=1)
    atr14 = tr14.rolling(window=14).mean()
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

    count = ut_buy.astype(int) + macd_cond.astype(int) + stoch_cond.astype(int) + adx_cond.astype(int) + obv_cond.astype(int)
    return count.iloc[-1] >= st.session_state.min_indicators

# Interface Streamlit
st.title("🔍 Scanner technique - S&P 500 via Polygon.io")
st.caption("Détection de signaux swing selon UT Bot, MACD, Stochastique, ADX, OBV")

min_indicators = st.slider("Nombre minimum d'indicateurs pour un signal", min_value=3, max_value=5, value=4)
st.session_state.min_indicators = min_indicators

start_date = st.date_input("Date de début", value=datetime.date.today() - datetime.timedelta(days=365))
end_date = st.date_input("Date de fin", value=datetime.date.today())

tickers = load_tickers()
results = []
failed = []

progress = st.progress(0)
for i, ticker in enumerate(tickers):
    df = fetch_data(ticker, from_date=start_date, to_date=end_date)
    if df is None:
        failed.append(ticker)
    elif calculate_indicators(df):
        results.append(ticker)
    progress.progress((i + 1) / len(tickers))

st.success(f"{len(results)} signaux détectés.")
st.dataframe(pd.DataFrame(results, columns=["Ticker"]))


# ➕ Affichage du tableau des tickers avec nombre de conditions remplies
df_summary = pd.DataFrame(conditions_summary)
if not df_summary.empty:
    st.subheader("📋 Résumé des conditions par ticker")
    st.dataframe(df_summary)

    # ➕ Export CSV
    csv = df_summary.to_csv(index=False).encode("utf-8")
    st.download_button("📥 Télécharger CSV", csv, "coach_swing_signaux.csv", "text/csv")

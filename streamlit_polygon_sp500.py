
import streamlit as st
import pandas as pd
import numpy as np
import os
import requests
from datetime import datetime, timedelta
from io import BytesIO

# 📌 Chargement de la clé API depuis le fichier .env
from dotenv import load_dotenv
load_dotenv()
API_KEY = os.getenv("POLYGON_API_KEY")

st.set_page_config(page_title="Coach Swing Scanner", layout="wide")

st.title("📊 Coach Swing – Scanner S&P 500 avec Polygon.io")
st.markdown("Scanne les tickers du S&P 500 pour repérer les signaux techniques combinés (UT Bot, MACD, RSI, etc.).")

# 🎯 Paramètres utilisateur
min_conditions = st.slider("Nombre minimal de conditions à remplir pour afficher un signal", min_value=1, max_value=5, value=4)

@st.cache_data
def load_tickers():
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    return pd.read_html(url)[0]["Symbol"].tolist()

tickers = load_tickers()
st.write(f"🔍 Nombre total de tickers à analyser : {len(tickers)}")

def fetch_polygon_data(ticker):
    end = datetime.today()
    start = end - timedelta(days=365)
    url = f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day/{start.strftime('%Y-%m-%d')}/{end.strftime('%Y-%m-%d')}?adjusted=true&sort=asc&limit=365&apiKey={API_KEY}"
    try:
        response = requests.get(url)
        if response.status_code != 200:
            return None
        data = response.json().get("results", [])
        if not data:
            return None
        df = pd.DataFrame(data)
        df.rename(columns={"t": "timestamp", "o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"}, inplace=True)
        df["date"] = pd.to_datetime(df["timestamp"], unit="ms")
        df.set_index("date", inplace=True)
        return df[["open", "high", "low", "close", "volume"]]
    except:
        return None

def calculate_signals(df):
    result = {}
    if df is None or df.empty or len(df) < 50:
        return None

    df = df.copy()
    # ATR
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

    # MACD
    ema_fast = df["close"].ewm(span=5, adjust=False).mean()
    ema_slow = df["close"].ewm(span=13, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    macd_signal = macd_line.ewm(span=4, adjust=False).mean()
    macd_cond = macd_line > macd_signal

    # Stochastique
    low_min = df["low"].rolling(window=8).min()
    high_max = df["high"].rolling(window=8).max()
    k = 100 * ((df["close"] - low_min) / (high_max - low_min))
    k_smooth = k.rolling(window=5).mean()
    d = k_smooth.rolling(window=3).mean()
    stoch_cond = (k_smooth > d) & (k_smooth < 50)

    # ADX
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

    # OBV
    obv = df["volume"].copy()
    obv[df["close"].diff() > 0] = df["volume"]
    obv[df["close"].diff() < 0] = -df["volume"]
    obv = obv.fillna(0).cumsum()
    obv_sma20 = obv.rolling(window=20).mean()
    obv_cond = obv > obv_sma20

    result["ut_buy"] = ut_buy.iloc[-1]
    result["macd_cond"] = macd_cond.iloc[-1]
    result["stoch_cond"] = stoch_cond.iloc[-1]
    result["adx_cond"] = adx_cond.iloc[-1]
    result["obv_cond"] = obv_cond.iloc[-1]
    result["count"] = sum(result.values())
    return result

scan_results = []
with st.spinner("🔍 Scan des tickers en cours..."):
    for ticker in tickers:
        df = fetch_polygon_data(ticker)
        result = calculate_signals(df)
        if result:
            result["Ticker"] = ticker
            scan_results.append(result)

if scan_results:
    df_summary = pd.DataFrame(scan_results)
    df_filtered = df_summary[df_summary["count"] >= min_conditions]
    st.success(f"🎉 {len(df_filtered)} tickers répondent à au moins {min_conditions} conditions.")
    st.dataframe(df_filtered[["Ticker", "count", "ut_buy", "macd_cond", "stoch_cond", "adx_cond", "obv_cond"]])

    # 💾 Télécharger en Excel
    excel_buffer = BytesIO()
    df_filtered.to_excel(excel_buffer, index=False)
    st.download_button("📥 Télécharger les résultats en Excel", data=excel_buffer.getvalue(), file_name="signals_sp500.xlsx")
else:
    st.warning("Aucun ticker ne remplit les conditions minimales.")

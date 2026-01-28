# =====================================================
# COACH SWING — POLYGON (STABLE)
# =====================================================
import streamlit as st
import pandas as pd
import requests
import time
from datetime import date, timedelta

st.set_page_config(layout="wide")
st.title("🧭 Coach Swing — Polygon")

POLYGON_KEY = st.secrets["POLYGON_API_KEY"]

LOOKBACK = 200

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "TradingEnAction-CoachSwing/1.0"})

@st.cache_data
def load_tickers():
    df = pd.read_excel("russell3000_constituents.xlsx")
    return df.iloc[:, 0].dropna().astype(str).str.upper().unique().tolist()

TICKERS = load_tickers()

def get_ohlc(ticker, retries=2):
    end = date.today()
    start = end - timedelta(days=LOOKBACK)

    url = (
        f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day/"
        f"{start}/{end}?adjusted=true&sort=asc&limit=50000&apiKey={POLYGON_KEY}"
    )

    for _ in range(retries):
        try:
            r = SESSION.get(url, timeout=20)
            if r.status_code != 200:
                return None

            data = r.json()
            if not data.get("results"):
                return None

            df = pd.DataFrame(data["results"])
            df["Close"] = df["c"]
            return df

        except requests.exceptions.Timeout:
            time.sleep(0.5)

        except Exception:
            return None

    return None

limit = st.slider("Nombre de tickers", 50, len(TICKERS), 150)

if st.button("🚀 Scanner Coach Swing"):
    rows = []
    progress = st.progress(0)

    for i, t in enumerate(TICKERS[:limit]):
        df = get_ohlc(t)
        if df is not None and len(df) > 100:
            rows.append([t, round(df["Close"].iloc[-1], 2)])

        progress.progress((i + 1) / limit)

    st.dataframe(pd.DataFrame(rows, columns=["Ticker", "Close"]))

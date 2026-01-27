# ============================================================
# Coach Swing – Heikin Ashi Scanner (Polygon + Russell 3000)
# ============================================================
import streamlit as st
import pandas as pd
import numpy as np
import requests
from datetime import date, timedelta

# =====================================================
# CONFIG
# =====================================================
st.set_page_config(page_title="Coach Swing – Heikin Ashi (Polygon)", layout="wide")
st.title("🧭 Coach Swing – Heikin Ashi (Russell 3000)")

POLYGON_KEY = st.secrets["POLYGON_API_KEY"]
DISCORD_WEBHOOK = st.secrets.get("DISCORD_WEBHOOK_URL")

LOOKBACK = 300  # suffisant pour EMA200
INTERVAL = "1/day"  # daily swing

# =====================================================
# LOAD TICKERS — RUSSELL 3000
# =====================================================
@st.cache_data
def load_russell():
    df = pd.read_excel("russell3000_constituents.xlsx")
    tickers = (
        df.iloc[:, 0]
        .dropna()
        .astype(str)
        .str.upper()
        .unique()
        .tolist()
    )
    return [t for t in tickers if t != "SYMBOL"]

TICKERS = load_russell()

# =====================================================
# POLYGON OHLC
# =====================================================
@st.cache_data(ttl=3600)
def get_ohlc(ticker):
    end = date.today()
    start = end - timedelta(days=LOOKBACK)

    url = (
        f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day/"
        f"{start}/{end}?adjusted=true&sort=asc&limit=50000&apiKey={POLYGON_KEY}"
    )

    r = requests.get(url, timeout=10)
    if r.status_code != 200:
        return None

    data = r.json()
    if "results" not in data:
        return None

    df = pd.DataFrame(data["results"])
    df["Open"] = df["o"]
    df["High"] = df["h"]
    df["Low"] = df["l"]
    df["Close"] = df["c"]
    df["Volume"] = df["v"]
    return df[["Open", "High", "Low", "Close", "Volume"]]

# =====================================================
# HEIKIN ASHI
# =====================================================
def to_heikin_ashi(df):
    ha = df.copy()
    ha["Close"] = (df["Open"] + df["High"] + df["Low"] + df["Close"]) / 4

    ha_open = [ (df["Open"].iloc[0] + df["Close"].iloc[0]) / 2 ]
    for i in range(1, len(df)):
        ha_open.append((ha_open[i-1] + ha["Close"].iloc[i-1]) / 2)

    ha["Open"] = ha_open
    ha["High"] = pd.concat([df["High"], ha["Open"], ha["Close"]], axis=1).max(axis=1)
    ha["Low"] = pd.concat([df["Low"], ha["Open"], ha["Close"]], axis=1).min(axis=1)
    return ha

# =====================================================
# INDICATORS
# =====================================================
def ema(s, n): return s.ewm(span=n, adjust=False).mean()

def rsi_wilder(c, n=12):
    d = c.diff()
    g = d.clip(lower=0)
    l = -d.clip(upper=0)
    rs = g.ewm(alpha=1/n, adjust=False).mean() / l.ewm(alpha=1/n, adjust=False).mean()
    return 100 - (100 / (1 + rs))

def macd_5134(c):
    macd = ema(c, 5) - ema(c, 13)
    signal = ema(macd, 4)
    return macd, signal

def crossover(a, b):
    return (a > b) & (a.shift(1) <= b.shift(1))

def cross_recent(cross, n=3):
    out = cross.copy()
    for i in range(1, n+1):
        out |= cross.shift(i)
    return out.fillna(False)

# =====================================================
# COACH SWING LOGIC
# =====================================================
def coach_swing(df):
    c, o = df["Close"], df["Open"]

    macd, sig = macd_5134(c)
    macd_up = cross_recent(crossover(macd, sig), 3)

    rsi = rsi_wilder(c, 12)
    rsi_s = rsi.rolling(5).mean()
    rsi_sig = rsi_s.rolling(2).mean()
    rsi_up = cross_recent(crossover(rsi_s, rsi_sig), 3)

    is_green = c > o
    is_red = c < o

    buy = macd_up & rsi_up & is_green

    pos = False
    buy_now = sell_now = False

    for i in range(len(df)):
        if buy.iloc[i] and not pos:
            pos = True
            buy_now = i == len(df) - 1
        elif is_red.iloc[i] and pos:
            pos = False
            sell_now = i == len(df) - 1

    return buy_now, sell_now

# =====================================================
# DISCORD
# =====================================================
def send_to_discord(rows):
    if not DISCORD_WEBHOOK or not rows:
        return

    msg = "**🚀 Coach Swing – Heikin Ashi Signals**\n\n"
    for r in rows[:20]:
        msg += f"{r['Signal']} **{r['Ticker']}** @ {r['Close']}\n"

    requests.post(DISCORD_WEBHOOK, json={"content": msg})

# =====================================================
# UI
# =====================================================
limit = st.slider("Nombre de tickers à analyser", 50, len(TICKERS), 200)

if st.button("🚀 Scanner"):
    results = []

    with st.spinner("Scan en cours…"):
        for t in TICKERS[:limit]:
            df = get_ohlc(t)
            if df is None or len(df) < 200:
                continue

            ha = to_heikin_ashi(df)
            buy, sell = coach_swing(ha)

            if buy or sell:
                results.append({
                    "Ticker": t,
                    "Signal": "🟢 BUY" if buy else "🔴 SELL",
                    "Close": round(ha["Close"].iloc[-1], 2)
                })

    if results:
        res_df = pd.DataFrame(results)
        st.dataframe(res_df, use_container_width=True)
        send_to_discord(results)
    else:
        st.info("Aucun signal aujourd’hui.")

# =====================================================
# COACH SWING — POLYGON (SIGNALS RÉELS + DISCORD)
# =====================================================
import streamlit as st
import pandas as pd
import numpy as np
import requests
import time
from datetime import date, timedelta

# ---------------- CONFIG ----------------
st.set_page_config(layout="wide")
st.title("🧭 Coach Swing — Polygon")

POLYGON_KEY = st.secrets["POLYGON_API_KEY"]
DISCORD_WEBHOOK = st.secrets["DISCORD_WEBHOOK_URL"]
LOOKBACK = 220

# ---------------- SESSION ----------------
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "TradingEnAction-CoachSwing/1.0"})

# ---------------- SIGNAL MEMORY ----------------
if "last_signals" not in st.session_state:
    st.session_state.last_signals = {}

# ---------------- LOAD TICKERS ----------------
@st.cache_data
def load_tickers():
    df = pd.read_excel("russell3000_constituents.xlsx")
    return (
        df.iloc[:, 0]
        .dropna()
        .astype(str)
        .str.upper()
        .unique()
        .tolist()
    )

TICKERS = load_tickers()

# ---------------- POLYGON OHLC ----------------
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
            df["Open"] = df["o"]
            df["High"] = df["h"]
            df["Low"] = df["l"]
            df["Close"] = df["c"]
            return df

        except requests.exceptions.Timeout:
            time.sleep(0.5)
        except Exception:
            return None

    return None

# ---------------- INDICATEURS ----------------
def EMA(s, n): 
    return s.ewm(span=n, adjust=False).mean()

def macd_5134(close):
    macd = EMA(close, 5) - EMA(close, 13)
    signal = EMA(macd, 4)
    return macd, signal

def rsi_wilder(close, n=12):
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/n, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/n, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def crossover(a, b):
    return (a > b) & (a.shift(1) <= b.shift(1))

def recent_cross(series, bars=3):
    out = series.copy().fillna(False)
    for i in range(1, bars + 1):
        out |= series.shift(i).fillna(False)
    return out

# ---------------- LOGIQUE COACH SWING ----------------
def coach_swing_signal(df):
    if len(df) < 100:
        return "—"

    o, c = df["Open"], df["Close"]

    macd, signal = macd_5134(c)
    macd_cross = recent_cross(crossover(macd, signal), 3)

    rsi = rsi_wilder(c, 12)
    rsi_sma5 = rsi.rolling(5).mean()
    rsi_sig = rsi_sma5.rolling(2).mean()
    rsi_cross = recent_cross(crossover(rsi_sma5, rsi_sig), 3)

    is_green = c.iloc[-1] > o.iloc[-1]
    is_red = c.iloc[-1] < o.iloc[-1]

    if macd_cross.iloc[-1] and rsi_cross.iloc[-1] and is_green:
        return "🟢 BUY"

    if is_red:
        return "🔴 SELL"

    return "—"

# ---------------- DISCORD ----------------
def send_discord_signal(ticker, price, signal):
    emoji = "🟢" if "BUY" in signal else "🔴"
    msg = f"{emoji} **{signal}**\n**{ticker}** @ ${price}"
    payload = {"content": msg}

    try:
        requests.post(DISCORD_WEBHOOK, json=payload, timeout=5)
    except Exception:
        pass

# ---------------- UI ----------------
limit = st.slider("Nombre de tickers", 50, len(TICKERS), 150)
show = st.selectbox("Afficher", ["Tous", "BUY seulement", "SELL seulement"])

if st.button("🚀 Scanner Coach Swing"):
    rows = []
    progress = st.progress(0)

    for i, t in enumerate(TICKERS[:limit]):
        df = get_ohlc(t)
        if df is None:
            continue

        signal = coach_swing_signal(df)
        close = round(df["Close"].iloc[-1], 2)

        prev_signal = st.session_state.last_signals.get(t)

        # 🚨 DISCORD — seulement NOUVEAU signal
        if signal in ["🟢 BUY", "🔴 SELL"] and signal != prev_signal:
            send_discord_signal(t, close, signal)

        st.session_state.last_signals[t] = signal

        rows.append([t, close, signal])
        progress.progress((i + 1) / limit)

    df_out = pd.DataFrame(rows, columns=["Ticker", "Close", "Signal"])

    if show == "BUY seulement":
        df_out = df_out[df_out["Signal"] == "🟢 BUY"]
    elif show == "SELL seulement":
        df_out = df_out[df_out["Signal"] == "🔴 SELL"]

    if df_out.empty:
        st.warning("Aucun signal Coach Swing aujourd’hui.")
    else:
        st.dataframe(df_out, use_container_width=True)

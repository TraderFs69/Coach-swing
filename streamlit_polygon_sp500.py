# =====================================================
# COACH SWING — POLYGON (VERSION RÉALISTE & ACTIVE)
# =====================================================
import streamlit as st
import pandas as pd
import numpy as np
import requests
from datetime import date, timedelta

# ================= CONFIG =================
st.set_page_config(layout="wide")
st.title("🧭 Coach Swing — Polygon (FIX FINAL)")

POLYGON_KEY = st.secrets["POLYGON_API_KEY"]
DISCORD_WEBHOOK = st.secrets["DISCORD_WEBHOOK_URL"]

LOOKBACK = 260

# ================= SESSION =================
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "TradingEnAction-CoachSwing/FINAL"})

# ================= LOAD TICKERS =================
@st.cache_data
def load_tickers():
    df = pd.read_excel("russell3000_constituents.xlsx")
    return df.iloc[:, 0].dropna().astype(str).str.upper().unique().tolist()

TICKERS = load_tickers()

# ================= POLYGON =================
def get_ohlc(ticker):
    end = date.today()
    start = end - timedelta(days=LOOKBACK)

    url = (
        f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day/"
        f"{start}/{end}?adjusted=true&sort=asc&limit=50000&apiKey={POLYGON_KEY}"
    )

    try:
        r = SESSION.get(url, timeout=15)
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

    except Exception:
        return None

# ================= INDICATEURS =================
def EMA(s, n):
    return s.ewm(span=n, adjust=False).mean()

def macd_5134(c):
    macd = EMA(c, 5) - EMA(c, 13)
    signal = EMA(macd, 4)
    return macd, signal

def rsi_wilder(c, n=14):
    d = c.diff()
    g = d.clip(lower=0)
    l = -d.clip(upper=0)
    ag = g.ewm(alpha=1/n, adjust=False).mean()
    al = l.ewm(alpha=1/n, adjust=False).mean()
    rs = ag / al.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

# ================= COACH SWING LOGIC =================
def coach_swing_signal(df):
    if len(df) < 150:
        return "—"

    # ❗ On travaille sur données clôturées
    df = df.iloc[:-1]

    o, c = df["Open"], df["Close"]

    ema20 = EMA(c, 20)
    ema50 = EMA(c, 50)
    macd, macd_sig = macd_5134(c)
    rsi = rsi_wilder(c)

    # -------- SETUP (CONTEXTE)
    setup = (
        c.iloc[-1] > ema20.iloc[-1] and
        ema20.iloc[-1] > ema50.iloc[-1] and
        rsi.iloc[-1] > 45 and
        macd.iloc[-1] > macd_sig.iloc[-1]
    )

    if not setup:
        return "—"

    # -------- BUY (TIMING SOUPLE)
    momentum = (
        rsi.iloc[-1] > rsi.iloc[-2] or
        c.iloc[-1] > c.iloc[-2]
    )

    if momentum:
        return "🟢 BUY"

    # -------- SELL
    if macd.iloc[-1] < macd_sig.iloc[-1] and rsi.iloc[-1] < 45:
        return "🔴 SELL"

    return "—"

# ================= DISCORD =================
def send_discord(t, p, s):
    emoji = "🟢" if "BUY" in s else "🔴"
    msg = f"{emoji} **{s}**\n**{t}** @ ${p}"
    try:
        requests.post(DISCORD_WEBHOOK, json={"content": msg}, timeout=5)
    except:
        pass

# ================= UI =================
limit = st.slider("Nombre de tickers", 50, len(TICKERS), 200)

if st.button("🚀 Scanner Coach Swing"):
    rows = []
    buys = sells = setups = 0

    for t in TICKERS[:limit]:
        df = get_ohlc(t)
        if df is None:
            continue

        sig = coach_swing_signal(df)
        price = round(df["Close"].iloc[-2], 2)

        if sig == "🟢 BUY":
            buys += 1
            send_discord(t, price, sig)

        if sig == "🔴 SELL":
            sells += 1
            send_discord(t, price, sig)

        rows.append([t, price, sig])

    st.success(f"🟢 BUY: {buys} | 🔴 SELL: {sells}")
    st.dataframe(
        pd.DataFrame(rows, columns=["Ticker", "Price", "Signal"]),
        use_container_width=True
    )

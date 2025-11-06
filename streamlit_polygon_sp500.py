import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import time
import random
import numpy as np

# ============================================================
#  Coach Swing Scanner (S&P 500) – Yahoo Finance + Wikipedia
#  - Scrape S&P 500 list (Wiki w/ headers + retry) or fallback CSV via st.secrets
#  - Download OHLCV with yfinance
#  - Replicate Coach Swing buy/sell logic (Pine) on the latest bar
#  - Filter/sort/export
# ============================================================

st.set_page_config(page_title="Coach Swing – S&P 500 Scanner", layout="wide")
st.title("🧭 Coach Swing – Scanner S&P 500 (Yahoo Finance)")

# -----------------------------
# Helpers – S&P500 constituents
# -----------------------------
@st.cache_data(show_spinner=False, ttl=60*60)
def get_sp500_constituents():
    """Get S&P500 table from Wikipedia with a real User-Agent, with optional CSV fallback.
    Returns (df, tickers_yf).
    """
    # Fallback CSV (optional)
    csv_url = st.secrets.get("SP500_CSV_URL")
    if csv_url:
        try:
            df = pd.read_csv(csv_url)
            if "Symbol" not in df.columns or "Security" not in df.columns:
                raise ValueError("CSV must include 'Symbol' and 'Security'")
            df["Symbol_yf"] = df["Symbol"].astype(str).str.replace(".", "-", regex=False)
            df = df.rename(columns={
                "Security": "Company",
                "GICS Sector": "Sector",
                "GICS Sub-Industry": "SubIndustry",
                "Headquarters Location": "HQ",
                "Date first added": "DateAdded",
            })
            return df, df["Symbol_yf"].tolist()
        except Exception as e:
            st.warning(f"CSV fallback failed ({e}). Trying Wikipedia…")

    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; StreamlitApp/1.0; +https://streamlit.io)",
        "Accept-Language": "en-US,en;q=0.9",
    }
    WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"

    last_err = None
    for _ in range(3):
        try:
            resp = requests.get(WIKI_URL, headers=headers, timeout=20)
            resp.raise_for_status()
            tables = pd.read_html(resp.text)
            df = tables[0].copy()
            df["Symbol_yf"] = df["Symbol"].astype(str).str.replace(".", "-", regex=False)
            df = df.rename(columns={
                "Security": "Company",
                "GICS Sector": "Sector",
                "GICS Sub-Industry": "SubIndustry",
                "Headquarters Location": "HQ",
                "Date first added": "DateAdded",
            })
            return df, df["Symbol_yf"].tolist()
        except Exception as e:
            last_err = e
            time.sleep(1.2 + random.random())
    raise RuntimeError(f"Failed to fetch S&P500 from Wikipedia: {last_err}")

# -------------------------------------
# Tech – Indicators & signal replication
# -------------------------------------

def ema(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(span=length, adjust=False, min_periods=length).mean()

# Wilder RSI (like TradingView ta.rsi)
def rsi_wilder(close: pd.Series, length: int = 12) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1/length, adjust=False, min_periods=length).mean()
    avg_loss = loss.ewm(alpha=1/length, adjust=False, min_periods=length).mean()
    rs = avg_gain / (avg_loss.replace(0, np.nan))
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(0)

# Pine MACD(5,13,4): macdLine=EMA5-EMA13, signalLine=EMA(macd,4)
def macd_5134(close: pd.Series):
    ema5 = ema(close, 5)
    ema13 = ema(close, 13)
    macd_line = ema5 - ema13
    signal_line = ema(macd_line, 4)
    return macd_line, signal_line

# crossover(a,b): a crosses above b this bar
def crossover(a: pd.Series, b: pd.Series) -> pd.Series:
    return (a > b) & (a.shift(1) <= b.shift(1))

# crossRecent: cross happened in last 0..3 bars

def cross_recent(cross: pd.Series, lookback: int = 3) -> pd.Series:
    out = cross.copy().astype(bool)
    for i in range(1, lookback+1):
        out = out | cross.shift(i).fillna(False)
    return out

# Simulate Coach Swing state machine over the series and return buy/sell on last bar

def coach_swing_signals(df_ohlc: pd.DataFrame) -> tuple[bool, bool, dict]:
    """Given OHLCV DataFrame (index ascending), compute indicators, emulate position state,
    and return (buy_now, sell_now, last_values_dict)."""
    # Ensure required columns
    req = {"Open", "Close"}
    if not req.issubset(df_ohlc.columns):
        return False, False, {}

    o = df_ohlc["Open"].astype(float)
    c = df_ohlc["Close"].astype(float)

    # EMAs (not strictly needed for signal but matches your Pine context)
    ema9 = ema(c, 9)
    ema20 = ema(c, 20)
    ema50 = ema(c, 50)
    ema200 = ema(c, 200)

    # MACD(5,13,4)
    macd_line, signal_line = macd_5134(c)
    macd_cross_up = crossover(macd_line, signal_line)

    # RSI 12 → SMA 5 → SMA 2
    rsi_raw = rsi_wilder(c, 12)
    rsi_sma5 = rsi_raw.rolling(5, min_periods=5).mean()
    rsi_signal = rsi_sma5.rolling(2, min_periods=2).mean()
    rsi_cross_up = crossover(rsi_sma5, rsi_signal)

    macd_recent = cross_recent(macd_cross_up, 3)
    rsi_recent = cross_recent(rsi_cross_up, 3)

    is_green = c > o
    is_red = c < o

    buy_condition = macd_recent & rsi_recent & is_green

    # Emulate position state
    position_open = False
    buy_series = pd.Series(False, index=df_ohlc.index)
    sell_series = pd.Series(False, index=df_ohlc.index)

    for idx in df_ohlc.index:
        buy_signal = bool(buy_condition.loc[idx] and (not position_open))
        if buy_signal:
            position_open = True
            buy_series.loc[idx] = True
            continue
        # simplified UT BOT sell: red candle
        sell_signal = bool(is_red.loc[idx] and position_open)
        if sell_signal:
            position_open = False
            sell_series.loc[idx] = True

    last_idx = df_ohlc.index[-1]
    last = {
        "ema9": float(ema9.iloc[-1]) if not np.isnan(ema9.iloc[-1]) else None,
        "ema20": float(ema20.iloc[-1]) if not np.isnan(ema20.iloc[-1]) else None,
        "ema50": float(ema50.iloc[-1]) if not np.isnan(ema50.iloc[-1]) else None,
        "ema200": float(ema200.iloc[-1]) if not np.isnan(ema200.iloc[-1]) else None,
        "macd": float(macd_line.iloc[-1]) if not np.isnan(macd_line.iloc[-1]) else None,
        "macdSignal": float(signal_line.iloc[-1]) if not np.isnan(signal_line.iloc[-1]) else None,
        "rsi": float(rsi_sma5.iloc[-1]) if not np.isnan(rsi_sma5.iloc[-1]) else None,
        "rsiSignal": float(rsi_signal.iloc[-1]) if not np.isnan(rsi_signal.iloc[-1]) else None,
        "isGreen": bool(is_green.loc[last_idx]),
        "isRed": bool(is_red.loc[last_idx]),
    }

    return bool(buy_series.iloc[-1]), bool(sell_series.iloc[-1]), last

# ----------------------
# Data – Yahoo Finance
# ----------------------
@st.cache_data(show_spinner=False)
def download_bars(tickers: list[str], period: str, interval: str) -> dict:
    """Download OHLCV bars for many tickers. Returns dict[ticker] -> DataFrame(OHLCV)."""
    if not tickers:
        return {}

    df = yf.download(
        tickers=tickers,
        period=period,
        interval=interval,
        group_by="ticker",
        auto_adjust=False,
        progress=False,
        threads=True,
    )

    out: dict[str, pd.DataFrame] = {}

    if isinstance(df.columns, pd.MultiIndex):
        # Multi-ticker case
        for t in tickers:
            if t in df.columns.get_level_values(0):
                dft = df[t].dropna(how="all")
                if not dft.empty:
                    out[t] = dft
    else:
        # Single ticker case
        out[tickers[0]] = df.dropna(how="all")

    # Ensure standard column names
    for t, dft in out.items():
        cols = {c: c.capitalize() for c in dft.columns}
        dft2 = dft.rename(columns=cols)
        # Keep only Open/High/Low/Close/Volume
        keep = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in dft2.columns]
        out[t] = dft2[keep]

    return out

# ----------------------
# UI – Controls & filters
# ----------------------
with st.spinner("Chargement de la liste S&P 500 depuis Wikipedia…"):
    sp_df, all_tickers = get_sp500_constituents()

c1, c2, c3, c4 = st.columns([1,1,1,2])
with c1:
    sectors = sorted(sp_df["Sector"].dropna().unique().tolist())
    sector_sel = st.multiselect("Secteurs", sectors, [])
with c2:
    interval = st.selectbox("Intervalle", ["1d", "1h", "30m", "15m"], index=0)
with c3:
    limit = st.number_input("Nombre de tickers", min_value=5, max_value=500, value=80, step=5)
with c4:
    search = st.text_input("Recherche (ticker/nom)", "").strip().lower()

# Period suggestion per interval (enough bars for signals)
period_map = {
    "1d": "2y",
    "1h": "180d",
    "30m": "60d",
    "15m": "30d",
}
period = period_map.get(interval, "2y")

if interval != "1d" and limit > 120:
    st.warning("Limiter les tickers ≤ 120 en intraday pour des performances correctes.")

# Apply filters
base = sp_df.copy()
if sector_sel:
    base = base[base["Sector"].isin(sector_sel)]
if search:
    base = base[
        base["Company"].str.lower().str.contains(search) | base["Symbol_yf"].str.lower().str.contains(search)
    ]

sel_tickers = base["Symbol_yf"].head(int(limit)).tolist()
st.caption(f"{len(sel_tickers)} tickers sélectionnés / {len(all_tickers)} au total – Intervalle {interval}, Période {period}")

if not sel_tickers:
    st.info("Aucun ticker sélectionné. Ajuste les filtres.")
    st.stop()

with st.spinner("Téléchargement des chandelles (Yahoo Finance)…"):
    bars = download_bars(sel_tickers, period=period, interval=interval)

results = []
for t in sel_tickers:
    dft = bars.get(t)
    if dft is None or len(dft) < 60:
        continue
    buy_now, sell_now, last = coach_swing_signals(dft)
    results.append({
        "Ticker": t,
        "Company": base.loc[base["Symbol_yf"] == t, "Company"].values[0] if not base.empty else t,
        "Sector": base.loc[base["Symbol_yf"] == t, "Sector"].values[0] if not base.empty else None,
        "Buy": buy_now,
        "Sell": sell_now,
        "Close": float(dft["Close"].iloc[-1]),
        "RSI": last.get("rsi"),
        "RSI_signal": last.get("rsiSignal"),
        "MACD": last.get("macd"),
        "MACD_signal": last.get("macdSignal"),
        "isGreen": last.get("isGreen"),
        "isRed": last.get("isRed"),
    })

res_df = pd.DataFrame(results)
if res_df.empty:
    st.warning("Aucun résultat (trop peu de données ou filtrage trop strict).")
    st.stop()

# Sorting and quick filters
colA, colB, colC = st.columns([1,1,2])
with colA:
    show = st.selectbox("Afficher", ["Tous", "Buy seulement", "Sell seulement"], index=0)
with colB:
    sort_by = st.selectbox("Trier par", ["Buy", "Sell", "Close", "Ticker", "Sector"]) 
with colC:
    ascending = st.checkbox("Tri ascendant", value=False)

if show == "Buy seulement":
    res_view = res_df[res_df["Buy"]]
elif show == "Sell seulement":
    res_view = res_df[res_df["Sell"]]
else:
    res_view = res_df

res_view = res_view.sort_values(by=sort_by, ascending=ascending, na_position="last")
st.dataframe(res_view, use_container_width=True)

# Export
csv = res_view.to_csv(index=False).encode("utf-8")
st.download_button("💾 Télécharger les signaux (CSV)", data=csv, file_name="coach_swing_sp500_signals.csv", mime="text/csv")

st.markdown(
    """
    **Logique Coach Swing (Pine → Python)**
    - EMA(9/20/50/200) calculées (référence visuelle)
    - MACD(5,13,4) : `macdLine = EMA5 - EMA13`, `signal = EMA(macd, 4)`
    - RSI 12 (Wilder) → SMA 5 → SMA 2 ; **crossover** détecté
    - `crossRecent` : croisement MACD **et** RSI dans les **3 dernières barres**
    - Bougie verte (Close > Open) → autorise **BUY** si aucune position ouverte
    - Bougie rouge (Close < Open) → **SELL** si position ouverte
    - Simulation état `position_open` sur l'historique pour produire le signal **à la dernière barre**
    """
)

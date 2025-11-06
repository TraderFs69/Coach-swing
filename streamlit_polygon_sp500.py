# streamlit_yfinance_coach_swing_ha.py
import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import requests
import time
import random

# ============================================================
#  Coach Swing – Scanner S&P 500 (Heikin Ashi, Yahoo Finance)
# ============================================================

st.set_page_config(page_title="Coach Swing – Heikin Ashi Scanner S&P 500", layout="wide")
st.title("🧭 Coach Swing – Scanner S&P 500 (Heikin Ashi)")

# ---------------------------------------------
# Heikin Ashi conversion
# ---------------------------------------------
def to_heikin_ashi(df: pd.DataFrame) -> pd.DataFrame:
    """
    Convertit un DataFrame OHLC en Heikin Ashi.
    Attend des colonnes: Open, High, Low, Close.
    """
    df = df.copy()

    # HA-Close = (O+H+L+C)/4
    ha_close = (df["Open"] + df["High"] + df["Low"] + df["Close"]) / 4

    # HA-Open = (prev_HA_Open + prev_HA_Close)/2 ; pour la première barre, (O+C)/2
    ha_open = pd.Series(index=df.index, dtype=float)
    ha_open.iloc[0] = (df["Open"].iloc[0] + df["Close"].iloc[0]) / 2
    for i in range(1, len(df)):
        ha_open.iloc[i] = (ha_open.iloc[i - 1] + ha_close.iloc[i - 1]) / 2

    # HA-High = max(High, HA-Open, HA-Close)
    ha_high = pd.concat([df["High"], ha_open, ha_close], axis=1).max(axis=1)

    # HA-Low = min(Low, HA-Open, HA-Close)
    ha_low = pd.concat([df["Low"], ha_open, ha_close], axis=1).min(axis=1)

    out = df.copy()
    out["Open"] = ha_open
    out["High"] = ha_high
    out["Low"] = ha_low
    out["Close"] = ha_close
    return out

# ---------------------------------------------
# S&P 500 constituents (Wikipedia or fallback)
# ---------------------------------------------
@st.cache_data(show_spinner=False, ttl=60 * 60)
def get_sp500_constituents():
    """
    Récupère la table du S&P 500 depuis Wikipedia avec un User-Agent.
    Fallback possible via st.secrets["SP500_CSV_URL"] (CSV avec colonnes 'Symbol' & 'Security').
    Retourne (df, tickers_yf).
    """
    # Fallback CSV
    csv_url = st.secrets.get("SP500_CSV_URL")
    if csv_url:
        try:
            df = pd.read_csv(csv_url)
            if "Symbol" not in df.columns or "Security" not in df.columns:
                raise ValueError("Le CSV doit contenir 'Symbol' et 'Security'")
            df["Symbol_yf"] = df["Symbol"].astype(str).replace(".", "-", regex=False)
            df = df.rename(
                columns={
                    "Security": "Company",
                    "GICS Sector": "Sector",
                    "GICS Sub-Industry": "SubIndustry",
                    "Headquarters Location": "HQ",
                    "Date first added": "DateAdded",
                }
            )
            return df, df["Symbol_yf"].tolist()
        except Exception as e:
            st.warning(f"CSV fallback échec ({e}). On tente Wikipedia…")

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
            df = df.rename(
                columns={
                    "Security": "Company",
                    "GICS Sector": "Sector",
                    "GICS Sub-Industry": "SubIndustry",
                    "Headquarters Location": "HQ",
                    "Date first added": "DateAdded",
                }
            )
            return df, df["Symbol_yf"].tolist()
        except Exception as e:
            last_err = e
            time.sleep(1.2 + random.random())

    raise RuntimeError(f"Échec de récupération du S&P 500 sur Wikipedia : {last_err}")

# ---------------------------------------------
# Indicators & Coach Swing logic replication
# ---------------------------------------------
def ema(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(span=length, adjust=False, min_periods=length).mean()

def rsi_wilder(close: pd.Series, length: int = 12) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()
    avg_loss = loss.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(0)

def macd_5134(close: pd.Series):
    """Pine MACD (5,13,4): macdLine=EMA5-EMA13 ; signalLine=EMA(macd,4)"""
    ema5 = ema(close, 5)
    ema13 = ema(close, 13)
    macd_line = ema5 - ema13
    signal_line = ema(macd_line, 4)
    return macd_line, signal_line

def crossover(a: pd.Series, b: pd.Series) -> pd.Series:
    """a croise au-dessus de b sur cette barre."""
    return (a > b) & (a.shift(1) <= b.shift(1))

def cross_recent(cross: pd.Series, lookback: int = 3) -> pd.Series:
    """Vrai si le croisement a eu lieu dans les 0..lookback dernières barres."""
    out = cross.copy().astype(bool).fillna(False)
    for i in range(1, lookback + 1):
        out = out | cross.shift(i).fillna(False)
    return out

def coach_swing_signals(df: pd.DataFrame):
    """
    Rejoue la logique Coach Swing sur toute la série et renvoie
    (buy_now, sell_now, last_values_dict) à la dernière barre.
    """
    if df.empty:
        return False, False, {}

    o = df["Open"].astype(float)
    c = df["Close"].astype(float)

    # EMAs (pour info)
    ema9 = ema(c, 9)
    ema20 = ema(c, 20)
    ema50 = ema(c, 50)
    ema200 = ema(c, 200)

    # MACD(5,13,4)
    macd_line, signal_line = macd_5134(c)
    macd_cross_up = crossover(macd_line, signal_line)

    # RSI 12 Wilder → SMA5 → SMA2
    rsi_raw = rsi_wilder(c, 12)
    rsi_sma5 = rsi_raw.rolling(5, min_periods=5).mean()
    rsi_signal = rsi_sma5.rolling(2, min_periods=2).mean()
    rsi_cross_up = crossover(rsi_sma5, rsi_signal)

    macd_recent = cross_recent(macd_cross_up, 3)
    rsi_recent = cross_recent(rsi_cross_up, 3)

    is_green = c > o
    is_red = c < o

    buy_condition = macd_recent & rsi_recent & is_green

    # État de position
    position_open = False
    buy_series = pd.Series(False, index=df.index)
    sell_series = pd.Series(False, index=df.index)

    for idx in df.index:
        buy_signal = bool(buy_condition.loc[idx] and (not position_open))
        if buy_signal:
            position_open = True
            buy_series.loc[idx] = True
            continue
        # UT BOT simplifié : bougie rouge -> sell si en position
        sell_signal = bool(is_red.loc[idx] and position_open)
        if sell_signal:
            position_open = False
            sell_series.loc[idx] = True

    last = {
        "ema9": float(ema9.iloc[-1]) if not np.isnan(ema9.iloc[-1]) else None,
        "ema20": float(ema20.iloc[-1]) if not np.isnan(ema20.iloc[-1]) else None,
        "ema50": float(ema50.iloc[-1]) if not np.isnan(ema50.iloc[-1]) else None,
        "ema200": float(ema200.iloc[-1]) if not np.isnan(ema200.iloc[-1]) else None,
    }
    return bool(buy_series.iloc[-1]), bool(sell_series.iloc[-1]), last

# ---------------------------------------------
# Yahoo Finance data loader
# ---------------------------------------------
@st.cache_data(show_spinner=False)
def download_bars(tickers: list[str], period: str, interval: str) -> dict:
    """
    Télécharge OHLCV pour plusieurs tickers et convertit en Heikin Ashi.
    Retourne dict[ticker] -> DataFrame(OHLCV HA).
    """
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
        # Multi-ticker
        base_names = df.columns.get_level_values(0).unique()
        for t in tickers:
            if t not in base_names:
                continue
            dft = df[t].dropna(how="all")
            if dft.empty:
                continue
            # Standardize column capitalization
            dft = dft.rename(columns={c: c.capitalize() for c in dft.columns})
            keep = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in dft.columns]
            dft = dft[keep]
            out[t] = to_heikin_ashi(dft)
    else:
        # Single-ticker
        dft = df.dropna(how="all")
        dft = dft.rename(columns={c: c.capitalize() for c in dft.columns})
        keep = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in dft.columns]
        dft = dft[keep]
        out[tickers[0]] = to_heikin_ashi(dft)

    return out

# ---------------------------------------------
# UI – Filtres & contrôles
# ---------------------------------------------
with st.spinner("Chargement de la liste S&P 500 depuis Wikipedia…"):
    sp_df, all_tickers = get_sp500_constituents()

c1, c2, c3, c4 = st.columns([1, 1, 1, 2])
with c1:
    sectors = sorted(sp_df["Sector"].dropna().unique().tolist())
    sector_sel = st.multiselect("Secteurs", sectors, [])
with c2:
    interval = st.selectbox("Intervalle", ["1d", "1h", "30m", "15m"], index=0)
with c3:
    limit = st.number_input("Nombre de tickers", min_value=5, max_value=500, value=80, step=5)
with c4:
    search = st.text_input("Recherche (ticker/nom)", "").strip().lower()

# Période par défaut selon l'intervalle (assez de barres pour déclencher la logique)
period_map = {"1d": "2y", "1h": "180d", "30m": "60d", "15m": "30d"}
period = period_map.get(interval, "2y")

if interval != "1d" and limit > 120:
    st.warning("En intraday, limite ≤ 120 tickers pour de bonnes performances.")

base = sp_df.copy()
if sector_sel:
    base = base[base["Sector"].isin(sector_sel)]
if search:
    base = base[
        base["Company"].str.lower().str.contains(search)
        | base["Symbol_yf"].str.lower().str.contains(search)
    ]

sel_tickers = base["Symbol_yf"].head(int(limit)).tolist()
st.caption(
    f"{len(sel_tickers)} tickers sélectionnés / {len(all_tickers)} au total – Heikin Ashi – Intervalle {interval}, Période {period}"
)

if not sel_tickers:
    st.info("Aucun ticker sélectionné. Ajuste les filtres.")
    st.stop()

with st.spinner("Téléchargement des chandelles (Yahoo Finance)…"):
    bars = download_bars(sel_tickers, period=period, interval=interval)

# ---------------------------------------------
# Calcul des signaux
# ---------------------------------------------
results = []
for t in sel_tickers:
    dft = bars.get(t)
    if dft is None or len(dft) < 60:
        continue
    buy_now, sell_now, last = coach_swing_signals(dft)
    results.append(
        {
            "Ticker": t,
            "Company": base.loc[base["Symbol_yf"] == t, "Company"].values[0] if not base.empty else t,
            "Sector": base.loc[base["Symbol_yf"] == t, "Sector"].values[0] if not base.empty else None,
            "Buy": buy_now,
            "Sell": sell_now,
            "Close": float(dft["Close"].iloc[-1]),
            "RSI": None,           # tu peux ajouter si tu veux exposer les valeurs
            "MACD": None,          # idem — déjà utilisé pour les signaux
        }
    )

res_df = pd.DataFrame(results)
if res_df.empty:
    st.warning("Aucun résultat (pas assez de données ou filtrage trop strict).")
    st.stop()

# ---------------------------------------------
# Affichage & export
# ---------------------------------------------
colA, colB, colC = st.columns([1, 1, 2])
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

csv = res_view.to_csv(index=False).encode("utf-8")
st.download_button("💾 Télécharger les signaux (CSV)", data=csv, file_name="coach_swing_sp500_ha_signals.csv", mime="text/csv")

st.markdown(
    """
**Important :** Toutes les analyses sont calculées en **Heikin Ashi** (et non en chandeliers classiques).

**Règles Coach Swing (Pine → Python) :**
- MACD (5,13,4) et RSI (12 Wilder → SMA 5 → SMA 2)
- BUY si croisement MACD **et** RSI récents (≤ 3 barres) **et** bougie **verte** (Close > Open) **et** pas de position ouverte
- SELL si bougie **rouge** (Close < Open) **et** position ouverte
- Simulation de l'état `position_open` sur toute la série, pour produire les signaux à la **dernière barre**.
"""
)

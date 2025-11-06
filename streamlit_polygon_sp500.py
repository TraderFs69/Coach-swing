import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import time
import random

# -----------------------------------------------
#  Récupération dynamique des composantes du S&P 500
# -----------------------------------------------

@st.cache_data(show_spinner=False, ttl=60 * 60)
def get_sp500_constituents():
    """
    Récupère la liste du S&P 500 depuis Wikipedia ou un CSV de secours.
    Retourne un tuple (DataFrame, liste_tickers).
    """

    # Fallback : si un CSV personnalisé est défini dans Streamlit Secrets
    csv_url = st.secrets.get("SP500_CSV_URL")
    if csv_url:
        try:
            df = pd.read_csv(csv_url)
            if "Symbol" not in df.columns or "Security" not in df.columns:
                raise ValueError("Le CSV doit contenir les colonnes 'Symbol' et 'Security'")
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
            st.warning(f"Impossible de charger le CSV (SP500_CSV_URL) : {e}. On tente Wikipedia…")

    # Sinon : lecture directe depuis Wikipedia avec en-têtes pour éviter le 403
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; StreamlitApp/1.0; +https://streamlit.io)",
        "Accept-Language": "en-US,en;q=0.9",
    }

    WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    last_err = None
    for attempt in range(3):
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
            tickers = df["Symbol_yf"].tolist()
            return df, tickers
        except Exception as e:
            last_err = e
            time.sleep(1.2 + random.random())

    raise RuntimeError(f"Échec de récupération du S&P 500 sur Wikipedia : {last_err}")

# -----------------------------------------------
#  Téléchargement des prix via Yahoo Finance
# -----------------------------------------------

@st.cache_data(show_spinner=False)
def download_prices(tickers: list[str], period: str = "2d", interval: str = "1d") -> pd.DataFrame:
    """
    Télécharge les prix OHLCV pour une liste de tickers via Yahoo Finance.
    Retourne un DataFrame avec les colonnes : Ticker, Close, PrevClose, ChangePct, Volume
    """
    if not tickers:
        return pd.DataFrame()

    data = yf.download(
        tickers=tickers,
        period=period,
        interval=interval,
        group_by="ticker",
        auto_adjust=False,
        progress=False,
        threads=True,
    )

    rows = []
    for t in tickers:
        try:
            if isinstance(data.columns, pd.MultiIndex):
                dft = data[t].dropna()
            else:
                dft = data.dropna()
            if len(dft) == 0:
                continue

            latest = dft.iloc[-1]
            prev = dft.iloc[-2] if len(dft) > 1 else None
            close = float(latest["Close"]) if "Close" in latest else None
            prev_close = float(prev["Close"]) if (prev is not None and "Close" in prev) else None
            vol = int(latest["Volume"]) if "Volume" in latest else None
            change_pct = ((close - prev_close) / prev_close * 100) if (close and prev_close) else None

            rows.append(
                {
                    "Ticker": t,
                    "Close": close,
                    "PrevClose": prev_close,
                    "ChangePct": change_pct,
                    "Volume": vol,
                }
            )
        except Exception:
            continue

    return pd.DataFrame(rows)

# -----------------------------------------------
#  Interface Streamlit
# -----------------------------------------------

st.set_page_config(page_title="S&P 500 – Yahoo Finance Scanner", layout="wide")
st.title("📊 S&P 500 (Yahoo Finance)")

with st.spinner("Chargement de la liste S&P 500 depuis Wikipedia…"):
    sp_df, all_tickers = get_sp500_constituents()

# Filtres
col1, col2, col3 = st.columns([1, 1, 2])
with col1:
    sectors = sorted(sp_df["Sector"].dropna().unique().tolist())
    sector_sel = st.multiselect("Filtrer par secteur", sectors, [])
with col2:
    limit = st.number_input("Nombre de titres (pour limiter le téléchargement)", 10, 500, 100, step=10)
with col3:
    search = st.text_input("Recherche (ticker ou nom)", "").strip().lower()

df = sp_df.copy()
if sector_sel:
    df = df[df["Sector"].isin(sector_sel)]
if search:
    df = df[
        df["Company"].str.lower().str.contains(search)
        | df["Symbol_yf"].str.lower().str.contains(search)
    ]

sel_tickers = df["Symbol_yf"].head(int(limit)).tolist()

st.caption(f"{len(sel_tickers)} tickers sélectionnés / {len(all_tickers)} au total")

if sel_tickers:
    with st.spinner("Téléchargement des prix (Yahoo Finance)…"):
        prices = download_prices(sel_tickers)

    merged = df.merge(prices, left_on="Symbol_yf", right_on="Ticker", how="left")

    # Colonnes dynamiques robustes


import streamlit as st
import pandas as pd
import yfinance as yf
import requests

WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"

@st.cache_data(show_spinner=False)
def get_sp500_constituents():
    """Scrape the current S&P 500 constituents from Wikipedia.
    Returns a (df, tickers) tuple.
    """
    # Use pandas to read the first table on the page
    tables = pd.read_html(WIKI_URL)
    df = tables[0].copy()

    # Normalize ticker symbols for yfinance (BRK.B -> BRK-B, BF.B -> BF-B)
    df["Symbol_yf"] = df["Symbol"].str.replace(".", "-", regex=False)

    # Standardize column names we care about
    df = df.rename(columns={
        "Security": "Company",
        "GICS Sector": "Sector",
        "GICS Sub-Industry": "SubIndustry",
        "Headquarters Location": "HQ",
        "Date first added": "DateAdded",
    })

    tickers = df["Symbol_yf"].tolist()
    return df, tickers

@st.cache_data(show_spinner=False)
def download_prices(tickers: list[str], period: str = "1d", interval: str = "1d") -> pd.DataFrame:
    """Fetch latest OHLCV for a list of tickers using yfinance.
    Returns a tidy DataFrame with columns: Ticker, Close, PrevClose, ChangePct, Volume
    """
    if not tickers:
        return pd.DataFrame()

    # yfinance can download many tickers at once. We'll fetch 2 days and compute change.
    data = yf.download(
        tickers=tickers,
        period="2d",
        interval="1d",
        group_by="ticker",
        auto_adjust=False,
        progress=False,
        threads=True,
    )

    rows = []
    for t in tickers:
        try:
            # When multiple tickers, data becomes a column MultiIndex per ticker
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
            rows.append({
                "Ticker": t,
                "Close": close,
                "PrevClose": prev_close,
                "ChangePct": change_pct,
                "Volume": vol,
            })
        except Exception:
            # Skip any problematic ticker without breaking the whole app
            continue
    out = pd.DataFrame(rows)
    return out

# ---------------- UI ----------------
st.set_page_config(page_title="S&P 500 – Yahoo Finance Scanner", layout="wide")
st.title("S&P 500 (Yahoo Finance)")

with st.spinner("Chargement de la liste S&P 500 depuis Wikipedia…"):
    sp_df, all_tickers = get_sp500_constituents()

# Filters
col1, col2, col3 = st.columns([1,1,2])
with col1:
    sectors = sorted(sp_df["Sector"].dropna().unique().tolist())
    sector_sel = st.multiselect("Filtrer par secteur", sectors, [])
with col2:
    limit = st.number_input("Nombre de titres (pour limiter le téléchargement)", 10, 500, 100, step=10)
with col3:
    search = st.text_input("Recherche (ticker ou nom)", "").strip().lower()

# Apply filters
df = sp_df.copy()
if sector_sel:
    df = df[df["Sector"].isin(sector_sel)]
if search:
    df = df[df["Company"].str.lower().str.contains(search) | df["Symbol_yf"].str.lower().str.contains(search)]

sel_tickers = df["Symbol_yf"].head(int(limit)).tolist()

st.caption(f"{len(sel_tickers)} tickers sélectionnés / {len(all_tickers)} au total")

if sel_tickers:
    with st.spinner("Téléchargement des prix (Yahoo Finance)…"):
        prices = download_prices(sel_tickers)

    # Merge with company metadata
    merged = df.merge(prices, left_on="Symbol_yf", right_on="Ticker", how="left")
    # Tidy display
    show_cols = [
        "Symbol_yf", "Company", "Sector", "SubIndustry", "HQ", "DateAdded", "Close", "ChangePct", "Volume"
    ]
    table = merged[show_cols].rename(columns={"Symbol_yf": "Ticker"})

    # Sort by daily change desc by default
    sort_by = st.selectbox("Trier par", ["ChangePct", "Volume", "Ticker", "Company"]) 
    ascending = st.checkbox("Tri ascendant", value=False)
    table = table.sort_values(by=sort_by, ascending=ascending, na_position="last")

    st.dataframe(table, use_container_width=True)

    # Download button
    csv = table.to_csv(index=False).encode("utf-8")
    st.download_button("Télécharger CSV", data=csv, file_name="sp500_yf_snapshot.csv", mime="text/csv")
else:
    st.info("Aucun ticker sélectionné. Ajuste tes filtres.")

st.markdown(
    """
    **Notes**
    - Source de la liste S&P 500: Wikipedia (mise à jour dynamique à chaque exécution).
    - Les tickers avec un point sont convertis en tiret pour Yahoo Finance (ex.: BRK.B → BRK-B).
    - Les variations quotidiennes sont calculées à partir des deux dernières clôtures disponibles.
    """
)

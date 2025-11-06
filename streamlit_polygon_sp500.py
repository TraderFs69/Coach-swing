import streamlit as st
import pandas as pd
import yfinance as yf
import requests

WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"

@st.cache_data(show_spinner=False, ttl=60*60)
def get_sp500_constituents():
    """Fetch current S&P 500 constituents.
    1) Preferred: scrape Wikipedia with a real User-Agent (avoids 403 on some hosts)
    2) Fallback: if SP500_CSV_URL is provided in st.secrets, load from that CSV (must include 'Symbol' & 'Security').
    Returns (df, tickers).
    """
    # 2) Fallback via secrets (use a personal gist/raw CSV if needed)
    csv_url = st.secrets.get("SP500_CSV_URL")
    if csv_url:
        try:
            df = pd.read_csv(csv_url)
            if "Symbol" not in df.columns or "Security" not in df.columns:
                raise ValueError("CSV must include 'Symbol' and 'Security' columns")
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
            st.warning(f"Impossible de charger le CSV (SP500_CSV_URL): {e}. On tente Wikipedia…")

    # 1) Wikipedia scrape with requests + headers (avoid urllib 403)
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; StreamlitApp/1.0; +https://streamlit.io)",
        "Accept-Language": "en-US,en;q=0.9"
    }

    import time, random, requests
    WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"

    # small retry loop for transient HTTP errors
    last_err = None
    for attempt in range(3):
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
            tickers = df["Symbol_yf"].tolist()
            return df, tickers
        except Exception as e:
            last_err = e
            time.sleep(1.2 + random.random())

    # If everything failed, surface a clear message
    raise RuntimeError(f"Échec de récupération S&P 500 sur Wikipedia: {last_err}")

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


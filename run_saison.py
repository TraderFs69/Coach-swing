import os
import json
import time
from datetime import datetime, timedelta

import pandas as pd
import requests

from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from indicators import ut_bot, macd, stochastic, rsi, sma, cci, adx
from discord import send_discord

# ======================================================
# CONFIG
# ======================================================

API_KEY = os.getenv("POLYGON_API_KEY")
WEBHOOK = os.getenv("DISCORD_WEBHOOK_URL")

if not API_KEY:
    raise Exception("POLYGON_API_KEY manquant")

if not WEBHOOK:
    raise Exception("DISCORD_WEBHOOK_URL manquant")

FILE_PATH = "russell3000_constituents.xlsx"

LOOKBACK_DAYS = 400

BATCH_SIZE = 300
SLEEP_API = 0.40

PROGRESS_FILE = "scan_progress.json"

TOLERANT_MODE = True

# ======================================================
# SESSION HTTP
# ======================================================

session = requests.Session()

retries = Retry(
    total=3,
    backoff_factor=1.5,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET"]
)

adapter = HTTPAdapter(max_retries=retries)

session.mount("https://", adapter)

# ======================================================
# POLYGON
# ======================================================

def load_polygon_daily(ticker):

    end = datetime.utcnow().date()
    start = end - timedelta(days=LOOKBACK_DAYS)

    url = (
        f"https://api.polygon.io/v2/aggs/ticker/"
        f"{ticker}/range/1/day/{start}/{end}"
    )

    try:

        r = session.get(
            url,
            params={
                "apiKey": API_KEY,
                "adjusted": "true"
            },
            timeout=30
        )

        if r.status_code != 200:
            return None

        data = r.json()

        if "results" not in data:
            return None

        df = pd.DataFrame(data["results"])

        if df.empty:
            return None

        if len(df) < 200:
            return None

        df["close"] = df["c"]
        df["high"] = df["h"]
        df["low"] = df["l"]

        df["date"] = (
            pd.to_datetime(df["t"], unit="ms")
            .dt.date
        )

        return df.reset_index(drop=True)

    except Exception:
        return None

# ======================================================
# CHARGEMENT UNIVERS
# ======================================================

print("Chargement Russell 3000")

df_tickers = pd.read_excel(
    FILE_PATH,
    engine="openpyxl"
)

if "Symbol" not in df_tickers.columns:
    raise Exception(
        "Colonne Symbol introuvable"
    )

tickers = (
    df_tickers["Symbol"]
    .dropna()
    .astype(str)
    .str.upper()
    .unique()
    .tolist()
)

print(f"{len(tickers)} titres chargés")

# ======================================================
# PROGRESSION
# ======================================================

if os.path.exists(PROGRESS_FILE):

    with open(PROGRESS_FILE, "r") as f:
        start_index = json.load(f).get(
            "index",
            0
        )

else:

    start_index = 0

end_index = min(
    start_index + BATCH_SIZE,
    len(tickers)
)

batch_tickers = tickers[
    start_index:end_index
]

print(
    f"Batch : "
    f"{start_index + 1} -> {end_index}"
)

# ======================================================
# SCAN
# ======================================================

new_buys = []

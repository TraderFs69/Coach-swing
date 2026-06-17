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

for idx, ticker in enumerate(
    batch_tickers,
    start=start_index + 1
):

    print(
        f"{idx}/{len(tickers)} "
        f"{ticker}"
    )

    df = load_polygon_daily(ticker)

    if df is None:
        continue

    try:

        # ======================
        # INDICATEURS
        # ======================

        ut = ut_bot(df)

        macd_val, macd_sig = macd(
            df["close"]
        )

        k, d = stochastic(df)

        rsi_val = rsi(
            df["close"],
            12
        )

        rsi_ma = sma(
            rsi_val,
            5
        )

        cci_val = cci(df)

        adx_val = adx(df)

        # ======================
        # DERNIÈRE BOUGIE
        # ======================

        i0 = -2
        i1 = -3

        signal_date = str(
            df["date"].iloc[i0]
        )

        # ======================
        # CONDITIONS
        # ======================

        ut_today = (
            df["close"].iloc[i0]
            > ut.iloc[i0]
            and
            df["close"].iloc[i1]
            <= ut.iloc[i1]
        )

        macd_today = (
            macd_val.iloc[i0]
            > macd_sig.iloc[i0]
            and
            macd_val.iloc[i0] < 0
        )

        stoch_today = (
            k.iloc[i0]
            > d.iloc[i0]
        )

        ut_yesterday = (
            df["close"].iloc[i1]
            > ut.iloc[i1]
            and
            df["close"].iloc[i1 - 1]
            <= ut.iloc[i1 - 1]
        )

        macd_yesterday = (
            macd_val.iloc[i1]
            > macd_sig.iloc[i1]
            and
            macd_val.iloc[i1] < 0
        )

        stoch_yesterday = (
            k.iloc[i1]
            > d.iloc[i1]
        )

        # ======================
        # MODE
        # ======================

        if TOLERANT_MODE:

            buy_today = (
                ut_today
                and
                (
                    macd_today
                    or
                    stoch_today
                )
            )

            buy_yesterday = (
                ut_yesterday
                and
                (
                    macd_yesterday
                    or
                    stoch_yesterday
                )
            )

        else:

            buy_today = (
                ut_today
                and
                macd_today
                and
                stoch_today
            )

            buy_yesterday = (
                ut_yesterday
                and
                macd_yesterday
                and
                stoch_yesterday
            )

        # ======================
        # SCORE
        # ======================

        score_today = (
            (rsi_val.iloc[i0] < 40)
            +
            (
                cci_val.iloc[i0]
                >
                cci_val.iloc[i0 - 1]
            )
            +
            (adx_val.iloc[i0] > 20)
            +
            (
                rsi_val.iloc[i0]
                >
                rsi_ma.iloc[i0]
            )
        )

        # ======================
        # NEW BUY
        # ======================

        if buy_today and not buy_yesterday:

            if score_today >= 3:
                label = "🟢 BUY VERT"

            elif score_today >= 1:
                label = "🟡 BUY JAUNE"

            else:
                label = "🔴 BUY ROUGE"

            new_buys.append(
                f"{label} "
                f"**{ticker}** "
                f"📅 {signal_date}"
            )

    except Exception as e:

        print(
            f"Erreur {ticker}: {e}"
        )

    time.sleep(SLEEP_API)

# ======================================================
# DISCORD
# ======================================================

if len(new_buys) > 0:

    message = (
        "🎯 **COACH SWING — NEW BUY DAILY**\n\n"
        f"Batch : {start_index + 1}"
        f" → {end_index}\n"
        f"Mode : "
        f"{'Tolérant' if TOLERANT_MODE else 'Strict'}\n\n"
        +
        "\n".join(new_buys)
    )

    send_discord(
        WEBHOOK,
        message
    )

    print(
        f"{len(new_buys)} signaux envoyés"
    )

else:

    print(
        "Aucun NEW BUY détecté"
    )

# ======================================================
# SAUVEGARDE PROGRESSION
# ======================================================

if end_index >= len(tickers):

    with open(
        PROGRESS_FILE,
        "w"
    ) as f:

        json.dump(
            {"index": 0},
            f
        )

    print(
        "Scan Russell 3000 terminé"
    )

else:

    with open(
        PROGRESS_FILE,
        "w"
    ) as f:

        json.dump(
            {"index": end_index},
            f
        )

    print(
        f"Prochain batch : "
        f"{end_index}"
    )

import pandas as pd
import numpy as np
import asyncio
import aiohttp
from tqdm.asyncio import tqdm
import random

SLEEP_MIN = 1.0   # Pause plus longue pour respecter les quotas Tiingo
SLEEP_MAX = 3.0
TIMEOUT_SECONDS = 15
API_KEY = "d5290e9d3b7a656b8944408846acbbb20157b3d6"

sp500_url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
tickers = pd.read_html(sp500_url)[0]["Symbol"].tolist()
print(f"✅ {len(tickers)} tickers récupérés pour le S&P500")

results = []
failed = []

async def fetch_ticker(session, ticker):
    url = f"https://api.tiingo.com/tiingo/daily/{ticker}/prices?startDate=2023-01-01&endDate=2023-06-30"
    headers = {"Authorization": f"Token {API_KEY}"}
    try:
        async with session.get(url, headers=headers, timeout=TIMEOUT_SECONDS) as resp:
            if resp.status != 200:
                print(f"❗ HTTP {resp.status} pour {ticker}")
                return ticker, None
            data = await resp.json()
            if not data:
                return ticker, None
            df = pd.DataFrame(data)
            df["date"] = pd.to_datetime(df["date"])
            df.set_index("date", inplace=True)
            return ticker, df
    except Exception as e:
        print(f"❌ Erreur sur {ticker} : {e}")
        return ticker, None

def calculate_indicators(df):
    if df is None or df.empty or len(df) < 200:
        return False

    df.dropna(inplace=True)

    # ATR(10)
    high_low = df["high"] - df["low"]
    high_close = np.abs(df["high"] - df["close"].shift())
    low_close = np.abs(df["low"] - df["close"].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = tr.rolling(window=10).mean()

    # UT Bot Trail simplifié
    upper_band = df["close"] + 0.5 * atr
    lower_band = df["close"] - 0.5 * atr
    trail_price = df["close"].copy()
    for i in range(1, len(df)):
        if df["close"].iloc[i] > trail_price.iloc[i-1]:
            trail_price.iloc[i] = max(trail_price.iloc[i-1], lower_band.iloc[i])
        else:
            trail_price.iloc[i] = min(trail_price.iloc[i-1], upper_band.iloc[i])
    ut_buy = (df["close"] > trail_price) & (df["close"].shift(1) <= trail_price.shift(1))

    # MACD(5,13,4)
    ema_fast = df["close"].ewm(span=5, adjust=False).mean()
    ema_slow = df["close"].ewm(span=13, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    macd_signal = macd_line.ewm(span=4, adjust=False).mean()
    macd_cond = macd_line > macd_signal

    # Stochastique(8,5,3)
    low_min = df["low"].rolling(window=8).min()
    high_max = df["high"].rolling(window=8).max()
    k = 100 * ((df["close"] - low_min) / (high_max - low_min))
    k_smooth = k.rolling(window=5).mean()
    d = k_smooth.rolling(window=3).mean()
    stoch_cond = (k_smooth > d) & (k_smooth < 50)

    # ADX(14)
    up_move = df["high"].diff()
    down_move = df["low"].diff().abs()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)
    tr = pd.concat([
        df["high"] - df["low"],
        np.abs(df["high"] - df["close"].shift()),
        np.abs(df["low"] - df["close"].shift())
    ], axis=1).max(axis=1)
    atr14 = tr.rolling(window=14).mean()
    plus_di = 100 * pd.Series(plus_dm).rolling(window=14).sum() / atr14
    minus_di = 100 * pd.Series(minus_dm).rolling(window=14).sum() / atr14
    dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di)
    adx = dx.rolling(window=14).mean()
    adx_cond = adx > 20

    # OBV
    obv = df["volume"].copy()
    obv[df["close"].diff() > 0] = df["volume"]
    obv[df["close"].diff() < 0] = -df["volume"]
    obv = obv.fillna(0).cumsum()
    obv_sma20 = obv.rolling(window=20).mean()
    obv_cond = obv > obv_sma20

    buy_signal = ut_buy & macd_cond & stoch_cond & adx_cond & obv_cond
    return buy_signal.iloc[-1]

async def main():
    async with aiohttp.ClientSession() as session:
        for i in tqdm(range(0, len(tickers), 2), desc="Scan par lots de 2"):  # réduis le batch à 2
            batch = tickers[i:i+2]
            tasks = [fetch_ticker(session, ticker) for ticker in batch]
            responses = await asyncio.gather(*tasks)
            for ticker, df in responses:
                if df is None:
                    failed.append(ticker)
                elif calculate_indicators(df):
                    print(f"✅ Signal détecté sur {ticker}")
                    results.append(ticker)
            sleep_time = random.uniform(SLEEP_MIN, SLEEP_MAX)
            print(f"⏳ Pause {sleep_time:.1f}s avant le prochain lot...")
            await asyncio.sleep(sleep_time)

asyncio.run(main())
pd.DataFrame(results, columns=["Ticker"]).to_csv("coach_swing_signals.csv", index=False)
pd.DataFrame(failed, columns=["FailedTicker"]).to_csv("failed_tickers.csv", index=False)
print(f"🎉 Scan terminé. Signaux détectés sur {len(results)} tickers. Échecs : {len(failed)} tickers.")

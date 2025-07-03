
import pandas as pd
import yfinance as yf
import numpy as np
import time

# Récupérer la liste S&P500 depuis Wikipedia
sp500_url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
tickers = pd.read_html(sp500_url)[0]["Symbol"].tolist()
print(f"Tickers S&P500 récupérés : {len(tickers)}")

results = []

def calculate_atr(df, period=10):
    high_low = df["High"] - df["Low"]
    high_close = np.abs(df["High"] - df["Close"].shift())
    low_close = np.abs(df["Low"] - df["Close"].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()
    return atr

def calculate_macd(close, fast=5, slow=13, signal=4):
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    macd_signal = macd_line.ewm(span=signal, adjust=False).mean()
    return macd_line, macd_signal

def calculate_stochastic(df, k_period=8, d_period=5, smooth=3):
    low_min = df["Low"].rolling(window=k_period).min()
    high_max = df["High"].rolling(window=k_period).max()
    k = 100 * ((df["Close"] - low_min) / (high_max - low_min))
    k_smooth = k.rolling(window=d_period).mean()
    d = k_smooth.rolling(window=smooth).mean()
    return k_smooth, d

def calculate_adx(df, period=14):
    up_move = df["High"].diff()
    down_move = df["Low"].diff().abs()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)
    tr = pd.concat([
        df["High"] - df["Low"],
        np.abs(df["High"] - df["Close"].shift()),
        np.abs(df["Low"] - df["Close"].shift())
    ], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()
    plus_di = 100 * pd.Series(plus_dm).rolling(window=period).sum() / atr
    minus_di = 100 * pd.Series(minus_dm).rolling(window=period).sum() / atr
    dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di)
    adx = dx.rolling(window=period).mean()
    return adx

for ticker in tickers:
    try:
        df = yf.download(ticker, period="6mo", interval="1d", progress=False)
        if df is None or df.empty or len(df) < 200:
            continue

        df.dropna(inplace=True)

        atr = calculate_atr(df, period=10)
        upper_band = df["Close"] + 0.5 * atr
        lower_band = df["Close"] - 0.5 * atr

        trail_price = df["Close"].copy()
        for i in range(1, len(df)):
            if df["Close"].iloc[i] > trail_price.iloc[i-1]:
                trail_price.iloc[i] = max(trail_price.iloc[i-1], lower_band.iloc[i])
            else:
                trail_price.iloc[i] = min(trail_price.iloc[i-1], upper_band.iloc[i])

        ut_buy = (df["Close"] > trail_price) & (df["Close"].shift(1) <= trail_price.shift(1))

        macd_line, macd_signal = calculate_macd(df["Close"])
        macd_cond = macd_line > macd_signal

        stoch_k, stoch_d = calculate_stochastic(df)
        stoch_cond = (stoch_k > stoch_d) & (stoch_k < 50)

        sma100 = df["Close"].rolling(window=100).mean()
        sma200 = df["Close"].rolling(window=200).mean()

        adx = calculate_adx(df)
        adx_cond = adx > 20

        obv = df["Volume"].copy()
        obv[df["Close"].diff() > 0] = df["Volume"]
        obv[df["Close"].diff() < 0] = -df["Volume"]
        obv = obv.fillna(0).cumsum()
        obv_sma20 = obv.rolling(window=20).mean()
        obv_cond = obv > obv_sma20

        buy_signal = ut_buy & macd_cond & stoch_cond & adx_cond & obv_cond

        if buy_signal.iloc[-1]:
            print(f"Signal détecté sur {ticker}")
            results.append(ticker)

    except Exception as e:
        print(f"Erreur sur {ticker} : {e}")
    time.sleep(1.2)

pd.DataFrame(results, columns=["Ticker"]).to_csv("coach_swing_signals.csv", index=False)
print(f"Scan terminé. Signaux détectés sur {len(results)} tickers.")

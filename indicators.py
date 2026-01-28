import numpy as np
import pandas as pd

# ======================
# INDICATEURS
# ======================

def ema(series, n):
    return series.ewm(span=n, adjust=False).mean()

def sma(series, n):
    return series.rolling(n).mean()

def atr(df, n=10):
    high, low, close = df["high"], df["low"], df["close"]
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(n).mean()

def macd(close):
    macd = ema(close, 5) - ema(close, 13)
    signal = ema(macd, 4)
    return macd, signal

def stochastic(df):
    low_min = df["low"].rolling(14).min()
    high_max = df["high"].rolling(14).max()
    k = 100 * (df["close"] - low_min) / (high_max - low_min)
    d = sma(k, 2)
    return k, d

def rsi(series, n=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(n).mean()
    avg_loss = loss.rolling(n).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def cci(df, n=20):
    tp = (df["high"] + df["low"] + df["close"]) / 3
    sma_tp = tp.rolling(n).mean()
    mad = (tp - sma_tp).abs().rolling(n).mean()
    return (tp - sma_tp) / (0.015 * mad)

def adx(df, n=14):
    high, low, close = df["high"], df["low"], df["close"]
    plus_dm = high.diff()
    minus_dm = low.diff().abs()

    plus_dm[plus_dm < 0] = 0
    minus_dm[minus_dm < 0] = 0

    tr = atr(df, n)
    plus_di = 100 * (plus_dm.rolling(n).sum() / tr)
    minus_di = 100 * (minus_dm.rolling(n).sum() / tr)
    dx = (abs(plus_di - minus_di) / (plus_di + minus_di)) * 100
    return dx.rolling(n).mean()

def ut_bot(df, key=3, atr_period=10):
    """
    Implémentation UT Bot fidèle au Pine Script
    """
    atr_val = atr(df, atr_period)
    loss = key * atr_val

    trail = pd.Series(index=df.index, dtype=float)

    for i in range(len(df)):
        close = df["close"].iloc[i]

        if i == 0 or pd.isna(atr_val.iloc[i]):
            trail.iloc[i] = close - loss.iloc[i]
            continue

        prev_trail = trail.iloc[i - 1]
        prev_close = df["close"].iloc[i - 1]

        if close > prev_trail and prev_close > prev_trail:
            trail.iloc[i] = max(prev_trail, close - loss.iloc[i])
        elif close < prev_trail and prev_close < prev_trail:
            trail.iloc[i] = min(prev_trail, close + loss.iloc[i])
        elif close > prev_trail:
            trail.iloc[i] = close - loss.iloc[i]
        else:
            trail.iloc[i] = close + loss.iloc[i]

    return trail

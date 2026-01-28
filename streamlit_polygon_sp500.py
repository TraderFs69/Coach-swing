# --------------------------------------------------
# COACH SWING LOGIC (VERSION RÉALISTE)
# --------------------------------------------------
def coach_swing_signal(df):
    if len(df) < 120:
        return "—"

    o, c = df["Open"], df["Close"]

    # INDICATEURS
    ema20 = EMA(c, 20)
    macd, macd_signal = macd_5134(c)
    rsi = rsi_wilder(c, 12)

    # CONDITIONS SETUP
    macd_ok = macd.iloc[-1] > macd_signal.iloc[-1]
    rsi_ok = rsi.iloc[-1] > 40
    trend_ok = c.iloc[-1] > ema20.iloc[-1]

    setup = macd_ok and rsi_ok and trend_ok

    # TRIGGER
    rsi_up = rsi.iloc[-1] > rsi.iloc[-2]
    green = c.iloc[-1] > o.iloc[-1]

    if setup and rsi_up and green:
        return "🟢 BUY"

    # SELL = perte de momentum
    if macd.iloc[-1] < macd_signal.iloc[-1] and rsi.iloc[-1] < 50:
        return "🔴 SELL"

    return "—"

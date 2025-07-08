
import streamlit as st
import pandas as pd
import numpy as np
import requests
from datetime import datetime, timedelta
import os

# Lire la clé API depuis le fichier .env
from dotenv import load_dotenv
load_dotenv()
API_KEY = os.getenv("POLYGON_API_KEY")

st.title("📊 Scanner technique - S&P 500")

# Choix de la date
selected_date = st.date_input("📅 Choisir une date", datetime.today())
min_conditions = st.slider("🔍 Nombre minimal de critères satisfaits", 3, 5, 3)

@st.cache_data
def load_tickers():
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    return pd.read_html(url)[0]["Symbol"].tolist()

@st.cache_data
def get_ohlc(symbol, date):
    url = f"https://api.polygon.io/v1/open-close/{symbol}/{date}?adjusted=true&apiKey={API_KEY}"
    r = requests.get(url)
    if r.status_code == 200:
        data = r.json()
        return data
    return None

def calculate_indicators(df):
    df['EMA7'] = df['close'].ewm(span=7).mean()
    df['EMA200'] = df['close'].ewm(span=200).mean()

    # MACD
    exp1 = df['close'].ewm(span=12, adjust=False).mean()
    exp2 = df['close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = exp1 - exp2
    df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()

    # RSI
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))

    # UT Bot (simplifié : close > EMA + ATR * factor)
    df['ATR'] = df['close'].rolling(10).apply(lambda x: max(x) - min(x))
    df['UT_Buy'] = df['close'] > df['EMA7'] + 0.25 * df['ATR']
    return df

sp500 = load_tickers()
results = []
raw_data = []

progress = st.progress(0)
for i, ticker in enumerate(sp500):
    try:
        ohlc = get_ohlc(ticker, selected_date.strftime("%Y-%m-%d"))
        if ohlc is None or "close" not in ohlc:
            continue
        close = ohlc["close"]
        data = {
            "symbol": ticker,
            "close": close
        }
        df = pd.DataFrame([data])
        df = calculate_indicators(df)

        last = df.iloc[-1]

        conditions = {
            "RSI < 30": last['RSI'] < 30,
            "MACD > Signal": last['MACD'] > last['Signal'],
            "Close > EMA7": last['close'] > last['EMA7'],
            "Close > EMA200 + 3%": last['close'] > 1.03 * last['EMA200'],
            "UT Bot Buy": last['UT_Buy']
        }

        score = sum(conditions.values())
        row = {"Symbol": ticker, **conditions, "Score": score}
        raw_data.append({**row, **last.to_dict()})
        if score >= min_conditions:
            results.append(row)
    except Exception as e:
        continue
    progress.progress((i + 1) / len(sp500))

if results:
    df_summary = pd.DataFrame(results)
    st.subheader("✅ Titres qui respectent les conditions")
    st.dataframe(df_summary)
    df_all = pd.DataFrame(raw_data)
    df_all.to_excel("resultats_indicateurs.xlsx", index=False)
    st.success("📁 Fichier Excel généré : resultats_indicateurs.xlsx")
    with open("resultats_indicateurs.xlsx", "rb") as f:
        st.download_button("📥 Télécharger les données Excel", f, "resultats_indicateurs.xlsx")
else:
    st.warning("Aucun titre ne respecte les conditions pour cette journée.")

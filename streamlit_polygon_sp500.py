
import streamlit as st
import pandas as pd
import numpy as np
import datetime
import os
from polygon import RESTClient

# Chargement de la clé API depuis les variables d'environnement
API_KEY = os.getenv("C5ECJcXC6KtglCOiYPUBD1LeN5ttdfa5")
client = RESTClient(API_KEY)

# 📅 Sélecteur de date
date_input = st.date_input("📆 Choisissez la date d'analyse", value=datetime.date.today())
date_str = date_input.strftime('%Y-%m-%d')

# 📊 Curseur pour nombre minimal de conditions
min_conditions = st.slider("🔎 Nombre minimal de conditions respectées", min_value=3, max_value=5, value=4)

# Liste S&P 500 (exemple minimal, remplacer par la liste complète si besoin)
tickers = ['AAPL', 'MSFT', 'GOOGL', 'NVDA', 'AMZN']

results = []

# 🔁 Analyse de chaque ticker
for ticker in tickers:
    try:
        aggs = client.get_aggs(ticker, 1, "day", from_=date_str, to=date_str, limit=1)
        if not aggs:
            continue

        close = aggs[0].c
        ema7 = close  # simplifié (normalement utiliser historique)
        ema200 = close * 0.95  # simplifié
        rsi = np.random.uniform(20, 80)  # simulation
        macd_hist = np.random.uniform(-1, 1)  # simulation
        ut_buy = close > ema7 + 0.25 * (aggs[0].h - aggs[0].l)  # approximation ATR

        # Conditions
        cond1 = rsi > 50
        cond2 = macd_hist > 0
        cond3 = close > ema7
        cond4 = close > ema200 * 1.03
        cond5 = ut_buy

        count = sum([cond1, cond2, cond3, cond4, cond5])

        if count >= min_conditions:
            results.append({
                "Ticker": ticker,
                "RSI": round(rsi, 2),
                "MACD_Hist": round(macd_hist, 2),
                "EMA7 > EMA200": close > ema200,
                "Close": close,
                "Conditions remplies": count
            })
    except Exception as e:
        st.warning(f"{ticker}: Erreur → {str(e)}")

# 📈 Résultats
df = pd.DataFrame(results)
if not df.empty:
    st.subheader("📋 Résultats filtrés")
    st.dataframe(df)

    # 📥 Export Excel
    excel_path = "/mnt/data/resultats_indicateurs.xlsx"
    df.to_excel(excel_path, index=False)
    st.success("✅ Fichier Excel exporté")
    st.download_button("📁 Télécharger Excel", data=open(excel_path, "rb"), file_name="resultats_indicateurs.xlsx")
else:
    st.info("Aucun titre ne respecte les conditions choisies.")

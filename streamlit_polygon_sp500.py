import streamlit as st
return cross | cross.shift(1) | cross.shift(2) | cross.shift(3)


def coach_swing_signals(df):
if df.empty: return False, False, {}
o, c = df['Open'], df['Close']
ema9, ema20, ema50, ema200 = ema(c,9), ema(c,20), ema(c,50), ema(c,200)
macd_line, sig_line = macd_5134(c)
macd_cross = crossover(macd_line, sig_line)
rsi_raw = rsi_wilder(c, 12)
rsi_sma5 = rsi_raw.rolling(5).mean()
rsi_sig = rsi_sma5.rolling(2).mean()
rsi_cross = crossover(rsi_sma5, rsi_sig)
buy_cond = cross_recent(macd_cross) & cross_recent(rsi_cross) & (c > o)
is_red = c < o
position = False
buy_series, sell_series = pd.Series(False, index=df.index), pd.Series(False, index=df.index)
for i in df.index:
if buy_cond.loc[i] and not position:
position, buy_series.loc[i] = True, True
elif is_red.loc[i] and position:
position, sell_series.loc[i] = False, True
last = {
"ema9": ema9.iloc[-1],
"ema20": ema20.iloc[-1],
"ema50": ema50.iloc[-1],
"ema200": ema200.iloc[-1]
}
return bool(buy_series.iloc[-1]), bool(sell_series.iloc[-1]), last


# ---------------------------------------------
# Download data and compute signals
# ---------------------------------------------
@st.cache_data(show_spinner=False)
def download_bars(tickers, period, interval):
data = yf.download(tickers=tickers, period=period, interval=interval, group_by='ticker', progress=False)
out = {}
if isinstance(data.columns, pd.MultiIndex):
for t in tickers:
if t in data.columns.get_level_values(0):
d = data[t].dropna()
out[t] = to_heikin_ashi(d)
else:
out[tickers[0]] = to_heikin_ashi(data.dropna())
return out


# ---------------------------------------------
# UI
# ---------------------------------------------
sp_df, all_tickers = get_sp500_constituents()
col1, col2, col3 = st.columns([1,1,2])
with col1:
sector_sel = st.multiselect("Secteurs", sorted(sp_df['Sector'].dropna().unique()))
with col2:
interval = st.selectbox("Intervalle", ["1d", "1h", "30m", "15m"])
with col3:
limit = st.number_input("Nombre de tickers", 5, 500, 50, step=5)


period = {"1d":"2y", "1h":"180d", "30m":"60d", "15m":"30d"}[interval]
base = sp_df.copy()
if sector_sel:
base = base[base['Sector'].isin(sector_sel)]
sel_tickers = base['Symbol_yf'].head(int(limit)).tolist()


st.caption(f"{len(sel_tickers)} tickers sélectionnés – Heikin Ashi – Intervalle {interval}")


with st.spinner("Téléchargement des données Heikin Ashi..."):
bars = download_bars(sel_tickers, period, interval)


results = []
for t, df in bars.items():
if len(df) < 60: continue
buy, sell, _ = coach_swing_signals(df)
results.append({"Ticker": t, "Buy": buy, "Sell": sell, "Close": df['Close'].iloc[-1]})


res_df = pd.DataFrame(results)


st.dataframe(res_df, use_container_width=True)


csv = res_df.to_csv(index=False).encode('utf-8')
st.download_button("💾 Télécharger (CSV)", data=csv, file_name="coach_swing_heikin_ashi_signals.csv")


st.markdown("**Toutes les analyses sont calculées en Heikin Ashi (et non Candlestick).**")

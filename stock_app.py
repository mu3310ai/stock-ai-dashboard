import streamlit as st
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
from datetime import datetime, timedelta

# --- 頁面設定 ---
st.set_page_config(page_title="專業股票分析儀表板", layout="wide")
st.title("📈 智能股票分析介面")

# --- 側邊欄：使用者輸入 ---
st.sidebar.header("設定參數")

# 預設股票 (支援台股與美股，台股請加 .TW)
ticker_input = st.sidebar.text_input("輸入股票代碼 (例如: 2330.TW 或 AAPL)", value="2330.TW")

# 時間範圍選擇
time_period = st.sidebar.selectbox("選擇時間範圍", ["1mo", "3mo", "6mo", "1y", "2y", "5y", "max"], index=3)

# 技術指標開關
st.sidebar.subheader("技術指標")
show_ma5 = st.sidebar.checkbox("顯示 MA5 (週線)", value=True)
show_ma20 = st.sidebar.checkbox("顯示 MA20 (月線)", value=True)
show_ma60 = st.sidebar.checkbox("顯示 MA60 (季線)", value=False)

# --- 數據獲取 ---
@st.cache_data
def load_data(ticker, period):
    data = yf.Ticker(ticker)
    df = data.history(period=period)
    return df, data.info

try:
    df, stock_info = load_data(ticker_input, time_period)
    
    # 顯示基本資訊
    col1, col2, col3 = st.columns(3)
    current_price = df['Close'].iloc[-1]
    prev_price = df['Close'].iloc[-2]
    change = current_price - prev_price
    pct_change = (change / prev_price) * 100

    col1.metric("當前股價", f"{current_price:.2f}", f"{change:.2f} ({pct_change:.2f}%)")
    col2.metric("最高價 (區間)", f"{df['High'].max():.2f}")
    col3.metric("最低價 (區間)", f"{df['Low'].min():.2f}")

    # --- 繪製 K 線圖與成交量 (使用 Plotly) ---
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                        vertical_spacing=0.03, subplot_titles=('股價走勢', '成交量'), 
                        row_width=[0.2, 0.7])

    # K線圖
    fig.add_trace(go.Candlestick(x=df.index,
                                 open=df['Open'], high=df['High'],
                                 low=df['Low'], close=df['Close'], name='K線'), 
                                 row=1, col=1)

    # 移動平均線
    if show_ma5:
        df['MA5'] = df['Close'].rolling(window=5).mean()
        fig.add_trace(go.Scatter(x=df.index, y=df['MA5'], opacity=0.7, line=dict(color='blue', width=1), name='MA 5'), row=1, col=1)
    
    if show_ma20:
        df['MA20'] = df['Close'].rolling(window=20).mean()
        fig.add_trace(go.Scatter(x=df.index, y=df['MA20'], opacity=0.7, line=dict(color='orange', width=1), name='MA 20'), row=1, col=1)

    if show_ma60:
        df['MA60'] = df['Close'].rolling(window=60).mean()
        fig.add_trace(go.Scatter(x=df.index, y=df['MA60'], opacity=0.7, line=dict(color='green', width=1), name='MA 60'), row=1, col=1)

    # 成交量圖
    colors = ['green' if row['Open'] - row['Close'] >= 0 else 'red' for index, row in df.iterrows()]
    fig.add_trace(go.Bar(x=df.index, y=df['Volume'], marker_color=colors, name='成交量'), row=2, col=1)

    # 圖表美化
    fig.update_layout(xaxis_rangeslider_visible=False, height=600, template="plotly_dark")
    
    st.plotly_chart(fig, use_container_width=True)

    # --- 顯示歷史數據表格 ---
    with st.expander("查看詳細歷史數據"):
        st.dataframe(df.sort_index(ascending=False))

except Exception as e:
    st.error(f"無法獲取股票數據，請確認代碼是否正確 (錯誤訊息: {e})")
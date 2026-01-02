import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import io
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- 1. 頁面設定 ---
st.set_page_config(page_title="台股全方位指揮所", layout="wide", page_icon="🏯")

st.markdown("""
<style>
    .stApp { background-color: #f1f3f6; }
    .block-container { padding-top: 1rem; padding-bottom: 2rem; }
    .css-card { background-color: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); margin-bottom: 20px; border: 1px solid #e0e0e0; }
    .report-box { background-color: white; padding: 20px; border-radius: 10px; border-left: 6px solid #1a237e; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
    .report-item { margin-bottom: 12px; border-bottom: 1px solid #eee; padding-bottom: 8px; }
    .report-label { font-weight: bold; color: #424242; }
    .report-view { color: #1565c0; font-weight: bold; }
    .report-action { color: #d84315; font-weight: bold; }
    .wash-sale-alert { background-color: #e3f2fd; color: #0d47a1; padding: 15px; border-radius: 8px; border: 2px solid #0d47a1; margin-bottom: 20px; font-weight: bold; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
    .dupont-tag { font-size: 0.8rem; padding: 4px 8px; border-radius: 4px; background: #fff3e0; color: #e65100; border: 1px solid #e65100; }
    /* 回測數據樣式 */
    .backtest-metric { font-size: 1.2rem; font-weight: bold; color: #2e7d32; }
    .backtest-loss { color: #d32f2f; }
</style>
""", unsafe_allow_html=True)

# --- 2. 定義全域股票清單 ---
DEFAULT_STOCKS = {
    "鴻海 (2317)": "2317.TW", "南亞科 (2408)": "2408.TW", "台積電 (2330)": "2330.TW",
    "聯發科 (2454)": "2454.TW", "廣達 (2382)": "2382.TW", "長榮 (2603)": "2603.TW",
    "元大台灣50 (0050)": "0050.TW", "元大高股息 (0056)": "0056.TW",
    "世界先進 (5347)": "5347.TWO", "輝達 (NVDA)": "NVDA", "蘋果 (AAPL)": "AAPL",
    "國泰永續高股息 (00878)": "00878.TW", "群益台灣精選高息 (00919)": "00919.TW",
    "復華台灣科技優息 (00929)": "00929.TW"
}
SYMBOL_TO_NAME = {v: k for k, v in DEFAULT_STOCKS.items()}

# --- 3. 輔助函數 ---
@st.cache_data(ttl=86400)
def get_stock_display_name(symbol):
    symbol = symbol.upper().strip()
    if symbol in SYMBOL_TO_NAME: return SYMBOL_TO_NAME[symbol]
    try:
        t = yf.Ticker(symbol)
        name = t.info.get('shortName') or t.info.get('longName') or symbol
        return f"{name} ({symbol.replace('.TW', '').replace('.TWO', '')})"
    except: return symbol

# --- 4. Google Sheets 連線 ---
SHEET_NAME = "我的持股庫存"

def get_gspread_client():
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        return client
    except: return None

def load_portfolio_gs():
    client = get_gspread_client()
    if not client: return pd.DataFrame()
    try:
        sheet = client.open(SHEET_NAME).sheet1
        data = sheet.get_all_records()
        if not data: return pd.DataFrame({'代號': ['2330.TW'], '買入均價': [500.0], '持有股數': [1000]})
        return pd.DataFrame(data)
    except: return pd.DataFrame()

def save_portfolio_gs(df):
    client = get_gspread_client()
    if not client: return
    try:
        sheet = client.open(SHEET_NAME).sheet1
        sheet.clear()
        sheet.update([df.columns.values.tolist()] + df.values.tolist())
        st.success("✅ 資料已同步寫入 Google Sheets！")
    except Exception as e: st.error(f"寫入試算表失敗：{str(e)}")

# --- 5. 回測引擎 (核心新功能) ---
def run_backtest(df, initial_capital=100000):
    # 策略：MA5 黃金交叉 MA20 買進，死亡交叉賣出
    df = df.copy()
    df['Signal'] = 0
    # 產生訊號：1=買, -1=賣
    # 當 MA5 > MA20 且 前一天 MA5 < MA20 -> 黃金交叉 (買)
    df.loc[(df['MA5'] > df['MA20']) & (df['MA5'].shift(1) <= df['MA20'].shift(1)), 'Signal'] = 1
    # 當 MA5 < MA20 且 前一天 MA5 > MA20 -> 死亡交叉 (賣)
    df.loc[(df['MA5'] < df['MA20']) & (df['MA5'].shift(1) >= df['MA20'].shift(1)), 'Signal'] = -1
    
    cash = initial_capital
    position = 0 # 持有股數
    trade_log = []
    equity_curve = []
    
    for i in range(len(df)):
        price = df['Close'].iloc[i]
        date = df.index[i]
        signal = df['Signal'].iloc[i]
        
        # 買進訊號 (且空手)
        if signal == 1 and position == 0:
            # 全倉買進 (簡單模擬)
            position = int(cash // price)
            cash -= position * price
            trade_log.append({'Date': date, 'Type': 'Buy', 'Price': price, 'Shares': position})
            
        # 賣出訊號 (且有持股)
        elif signal == -1 and position > 0:
            cash += position * price
            trade_log.append({'Date': date, 'Type': 'Sell', 'Price': price, 'Shares': position})
            position = 0
            
        # 計算每日總資產
        current_equity = cash + (position * price)
        equity_curve.append(current_equity)
        
    df['Equity'] = equity_curve
    
    # 計算 KPI
    total_return = (df['Equity'].iloc[-1] - initial_capital) / initial_capital * 100
    trades_df = pd.DataFrame(trade_log)
    win_rate = 0
    if not trades_df.empty:
        # 計算每筆交易盈虧
        # 這裡簡化計算：只看賣出時的資產變化
        pass # (實際盈虧需配對買賣，此處主要展示總回報)
        
    return df, total_return, trades_df

# --- 6. 側邊欄 ---
with st.sidebar:
    st.header("🏯 指揮中心")
    search_input = st.text_input("🔍 輸入代號搜尋 (Enter 確認)", placeholder="例如 2330.TW, NVDA")
    final_options = {}
    try:
        my_portfolio = load_portfolio_gs()
        if not my_portfolio.empty and '代號' in my_portfolio.columns:
            my_stocks = my_portfolio['代號'].astype(str).unique().tolist()
            for stock_symbol in my_stocks:
                if stock_symbol and stock_symbol.strip():
                    display_name = get_stock_display_name(stock_symbol)
                    final_options[f"💰 [庫存] {display_name}"] = stock_symbol
    except: pass
    existing_symbols = list(final_options.values())
    for name, symbol in DEFAULT_STOCKS.items():
        if symbol not in existing_symbols: final_options[name] = symbol
    
    if final_options:
        selected_stock_label = st.selectbox("📂 快速選單 (庫存/熱門)", list(final_options.keys()))
        selected_from_menu = final_options[selected_stock_label]
    else: selected_from_menu = "2330.TW"

    if search_input: ticker_symbol = search_input.upper().strip()
    else: ticker_symbol = selected_from_menu

    days_to_show = st.slider("戰場範圍 (天)", 90, 360, 180)
    st.markdown("---")
    st.info("💡 提示：上市請加 .TW，上櫃請加 .TWO，美股直接打代號。")
    if st.button("🔄 刷新數據"): st.cache_data.clear()

# --- 7. 資料引擎 ---
@st.cache_data(ttl=300)
def load_data(symbol, days):
    end_date = datetime.now()
    # 回測需要更長的資料，這裡預設多抓 365 天供回測用，但顯示只顯示 days
    fetch_start_date = end_date - timedelta(days=max(days + 150, 730)) 
    try:
        data = yf.download(symbol, start=fetch_start_date, end=end_date, progress=False)
        if data.empty: return pd.DataFrame(), 0
        if isinstance(data.columns, pd.MultiIndex): data.columns = data.columns.get_level_values(0)
        
        data['MA5'] = data['Close'].rolling(window=5).mean()
        data['MA20'] = data['Close'].rolling(window=20).mean()
        data['STD20'] = data['Close'].rolling(window=20).std()
        data['BB_Upper'] = data['MA20'] + (2 * data['STD20'])
        data['BB_Lower'] = data['MA20'] - (2 * data['STD20'])
        exp12 = data['Close'].ewm(span=12, adjust=False).mean()
        exp26 = data['Close'].ewm(span=26, adjust=False).mean()
        data['DIF'] = exp12 - exp26
        data['DEA'] = data['DIF'].ewm(span=9, adjust=False).mean()
        data['MACD_Hist'] = data['DIF'] - data['DEA']
        data['OBV'] = (np.sign(data['Close'].diff()) * data['Volume']).fillna(0).cumsum()
        data['OBV_MA'] = data['OBV'].rolling(window=20).mean()
        data['Returns'] = data['Close'].pct_change()
        var_95 = data['Returns'].quantile(0.05)
        
        # 回傳完整資料供回測，以及切片資料供繪圖
        return data, var_95
    except: return pd.DataFrame(), 0

@st.cache_data(ttl=3600)
def load_fundamentals(symbol):
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        bs = ticker.balance_sheet
        is_stmt = ticker.income_stmt
    except:
        info = {}
        bs = pd.DataFrame()
        is_stmt = pd.DataFrame()
    return info, bs, is_stmt

def generate_signals(df, high, low):
    last_close = df['Close'].iloc[-1]
    last_vol = df['Volume'].iloc[-1]
    wash_sale_msg = ""
    wash_detected = False
    recent_df = df.iloc[-20:-1] 
    avg_vol_20 = df['Volume'].rolling(window=20).mean().iloc[-1]
    bullish_candles = recent_df[(recent_df['Close'] > recent_df['Open'] * 1.03) & (recent_df['Volume'] > avg_vol_20 * 1.5)]
    if not bullish_candles.empty:
        key_candle = bullish_candles.iloc[-1]
        key_low = key_candle['Low']
        key_vol = key_candle['Volume']
        key_date = key_candle.name.strftime('%Y-%m-%d')
        if last_close >= key_low and last_vol < key_vol * 0.6:
            wash_detected = True
            wash_sale_msg = f"""<div class="wash-sale-alert">🌊 偵測到「主力洗盤」訊號！<br>1. 發動日：{key_date} (低點 {key_low:.1f})<br>2. 狀態：量縮守支撐</div>"""

    diff = high - low
    fib_levels = [low + diff*0.786, low + diff*0.618, low + diff*0.236]
    pos_view, pos_action = "", ""
    if last_close >= fib_levels[0]:
        pos_view = "🚨 價格進入 78.6%~88.6% 主力誘多獵殺區。"
        pos_action = "嚴禁追高，隨時準備反轉做空或獲利了結。"
    elif last_close > fib_levels[1]:
        pos_view = "⚠️ 價格突破 61.8%，處於相對高檔。"
        pos_action = "多單續抱，但需提高警覺。"
    elif last_close < fib_levels[2]:
        pos_view = "🟢 價格處於低檔底部區。"
        pos_action = "分批佈局，尋找長線買點。"
    else:
        pos_view = "⚖️ 價格處於中間震盪區域。"
        pos_action = "依照均線趨勢順勢操作。"
    
    bb_upper = df['BB_Upper'].iloc[-1]
    bb_view = "🔥 股價衝破布林上軌，極短線過熱。" if last_close > bb_upper else "🌊 股價在布林通道內運行。"
    bb_action = "不宜追價，考慮調節。" if last_close > bb_upper else "觀望或區間操作。"
    
    last_obv = df['OBV'].iloc[-1]
    last_obv_ma = df['OBV_MA'].iloc[-1]
    obv_view = "📈 OBV 位於均線之上，籌碼流入。" if last_obv > last_obv_ma else "📉 OBV 位於均線之下，籌碼流出。"
    obv_action = "主力心態偏多。" if last_obv > last_obv_ma else "主力心態保守。"
    
    hist = df['MACD_Hist'].iloc[-1]
    prev_hist = df['MACD_Hist'].iloc[-2]
    macd_view = "🚀 紅柱持續放大，動能強勁。" if hist > 0 and hist > prev_hist else ("⚠️ 紅柱縮短，背離警戒。" if hist > 0 and hist < prev_hist else "✨ 多空膠著或空方控盤。")
    macd_action = "積極操作。" if hist > 0 and hist > prev_hist else ("設好停利。" if hist > 0 and hist < prev_hist else "保守應對。")

    return {
        "wash_detected": wash_detected, "wash_sale_msg": wash_sale_msg,
        "position": (pos_view, pos_action), "bollinger": (bb_view, bb_action),
        "obv": (obv_view, obv_action), "macd": (macd_view, macd_action)
    }

def get_live_prices(ticker_list):
    prices = {}
    if not ticker_list: return prices
    try:
        data = yf.download(ticker_list, period="1d", progress=False)['Close']
        if len(ticker_list) == 1: prices[ticker_list[0]] = data.iloc[-1]
        else:
            for t in ticker_list:
                try: prices[t] = data[t].iloc[-1]
                except: prices[t] = 0
    except: pass
    return prices

# --- 主畫面 ---
try:
    full_df, var_95 = load_data(ticker_symbol, days_to_show)
    
    if full_df.empty:
        st.error(f"❌ 無法取得數據：{ticker_symbol}。請確認代號是否正確。")
    else:
        # 繪圖只取最近 N 天
        df = full_df.tail(days_to_show)
        
        last_close = df['Close'].iloc[-1]
        pct_change = df['Returns'].iloc[-1] * 100
        high_price = df['High'].max()
        low_price = df['Low'].min()
        signals = generate_signals(df, high_price, low_price)
        
        display_name_main = get_stock_display_name(ticker_symbol)
        title_col, tag_col = st.columns([3, 1])
        with title_col: st.markdown(f"## 🏯 {display_name_main} 戰略指揮所")
        with tag_col:
            if signals['wash_detected']:
                st.markdown('<div style="background:#e3f2fd; color:#0d47a1; padding:5px; border-radius:10px; text-align:center;">🌊 主力洗盤中</div>', unsafe_allow_html=True)
        
        tab1, tab2, tab3, tab4, tab5 = st.tabs(["📈 技術戰情室", "🤖 AI 策略雷達", "📊 基本面體檢", "💰 我的庫存管理", "🧪 策略實驗室"])

        with tab1:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("最新收盤", f"{last_close:.1f}", f"{pct_change:.1f}%")
            c2.metric("風險值 (VaR)", f"{var_95*100:.1f}%")
            c3.metric("高點", f"{high_price:.1f}")
            c4.metric("低點", f"{low_price:.1f}")
            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3])
            fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='K線', increasing_line_color='#ef4444', decreasing_line_color='#22c55e'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['MA20'], line=dict(color='orange'), name='MA20'), row=1, col=1)
            colors = ['#ef4444' if v >= 0 else '#22c55e' for v in df['MACD_Hist']]
            fig.add_trace(go.Bar(x=df.index, y=df['MACD_Hist'], marker_color=colors, name='MACD'), row=2, col=1)
            fig.update_layout(height=600, showlegend=False, margin=dict(l=20, r=20, t=10, b=10))
            st.plotly_chart(fig, use_container_width=True)

        with tab2:
            st.subheader("🤖 AI 首席分析師綜合診斷報告")
            if signals['wash_detected']: st.markdown(signals['wash_sale_msg'], unsafe_allow_html=True)
            else: st.info("🌊 目前未偵測到明顯的「主力洗盤」訊號。")

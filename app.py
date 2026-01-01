import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import io

# --- 新增：Google Sheets 連線套件 ---
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
    .wash-sale-alert { background-color: #e3f2fd; color: #0d47a1; padding: 15px; border-radius: 8px; border: 2px solid #0d47a1; margin-bottom: 20px; font-weight: bold; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
    .dupont-tag { font-size: 0.8rem; padding: 4px 8px; border-radius: 4px; background: #fff3e0; color: #e65100; border: 1px solid #e65100; }
</style>
""", unsafe_allow_html=True)

# --- 2. Google Sheets 連線與讀取 (搬到最上方以便側邊欄使用) ---
SHEET_NAME = "我的持股庫存"

def get_gspread_client():
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        # 若連線失敗不報錯，避免影響主畫面渲染，僅在 Tab 4 提示
        return None

def load_portfolio_gs():
    client = get_gspread_client()
    if not client: return pd.DataFrame()
    try:
        sheet = client.open(SHEET_NAME).sheet1
        data = sheet.get_all_records()
        if not data: return pd.DataFrame({'代號': ['2330.TW'], '買入均價': [500.0], '持有股數': [1000]})
        return pd.DataFrame(data)
    except:
        return pd.DataFrame()

def save_portfolio_gs(df):
    client = get_gspread_client()
    if not client: return
    try:
        sheet = client.open(SHEET_NAME).sheet1
        sheet.clear()
        sheet.update([df.columns.values.tolist()] + df.values.tolist())
        st.success("✅ 資料已同步寫入 Google Sheets！")
    except Exception as e:
        st.error(f"寫入試算表失敗：{str(e)}")

# --- 3. 側邊欄 (動態選單邏輯) ---
with st.sidebar:
    st.header("🏯 指揮中心")
    
    # A. 預設觀察名單
    default_options = {
        "鴻海 (2317)": "2317.TW", "南亞科 (2408)": "2408.TW", "台積電 (2330)": "2330.TW",
        "聯發科 (2454)": "2454.TW", "廣達 (2382)": "2382.TW", "長榮 (2603)": "2603.TW",
        "元大台灣50 (0050)": "0050.TW", "元大高股息 (0056)": "0056.TW",
        "世界先進 (5347)": "5347.TWO", "輝達 (NVDA)": "NVDA", "蘋果 (AAPL)": "AAPL"
    }
    
    # B. 從 Google Sheet 抓取庫存名單
    portfolio_options = {}
    try:
        my_portfolio = load_portfolio_gs()
        if not my_portfolio.empty and '代號' in my_portfolio.columns:
            my_stocks = my_portfolio['代號'].astype(str).unique().tolist()
            for stock in my_stocks:
                # 簡單過濾空值
                if stock and stock.strip():
                    portfolio_options[f"💰 [庫存] {stock}"] = stock
    except:
        pass # 讀取失敗就算了，用預設的
    
    # C. 合併名單 (庫存優先顯示)
    # 這裡做一個反向查找，避免重複加入已在預設名單中的股票
    final_options = portfolio_options.copy()
    existing_tickers = list(portfolio_options.values())
    
    for name, ticker in default_options.items():
        if ticker not in existing_tickers:
            final_options[name] = ticker
            
    # 顯示選單
    selected_stock_name = st.sidebar.selectbox("標的選擇", list(final_options.keys()))
    ticker_symbol = final_options[selected_stock_name]
    
    days_to_show = st.sidebar.slider("戰場範圍 (天)", 90, 360, 180)
    st.markdown("---")
    if st.button("🔄 刷新數據"): st.cache_data.clear()

# --- 4. 資料引擎 ---
@st.cache_data(ttl=300)
def load_data(symbol, days):
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days + 150)
    data = yf.download(symbol, start=start_date, end=end_date, progress=False)
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
    return data.tail(days), var_95

@st.cache_data(ttl=3600)
def load_fundamentals(symbol):
    ticker = yf.Ticker(symbol)
    try:
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
    pos_view = "🚨 誘多區" if last_close >= fib_levels[0] else ("⚠️ 高檔區" if last_close > fib_levels[1] else ("🟢 低檔區" if last_close < fib_levels[2] else "⚖️ 震盪區"))
    return {"wash_detected": wash_detected, "wash_sale_msg": wash_sale_msg, "position": pos_view}

def get_live_prices(ticker_list):
    prices = {}
    if not ticker_list: return prices
    try:
        data = yf.download(ticker_list, period="1d", progress=False)['Close']
        if len(ticker_list) == 1:
            prices[ticker_list[0]] = data.iloc[-1]
        else:
            for t in ticker_list:
                try: prices[t] = data[t].iloc[-1]
                except: prices[t] = 0
    except: pass
    return prices

# --- 主畫面 ---
try:
    df, var_95 = load_data(ticker_symbol, days_to_show)
    if df.empty:
        st.error("無法取得技術數據。")
    else:
        last_close = df['Close'].iloc[-1]
        pct_change = df['Returns'].iloc[-1] * 100
        high_price = df['High'].max()
        low_price = df['Low'].min()
        signals = generate_signals(df, high_price, low_price)
        
        title_col, tag_col = st.columns([3, 1])
        with title_col: st.markdown(f"## 🏯 {selected_stock_name} 戰略指揮所")
        with tag_col:
            if signals['wash_detected']:
                st.markdown('<div style="background:#e3f2fd; color:#0d47a1; padding:5px; border-radius:10px; text-align:center;">🌊 主力洗盤中</div>', unsafe_allow_html=True)
        
        tab1, tab2, tab3, tab4 = st.tabs(["📈 技術戰情室", "🤖 AI 策略雷達", "📊 基本面體檢", "💰 我的庫存管理"])

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
            if signals['wash_detected']: st.markdown(signals['wash_sale_msg'], unsafe_allow_html=True)
            st.info(f"目前位階：{signals['position']}")
            st.write("(詳細 AI 診斷請參閱前版)")

        with tab3:
            try:
                with st.spinner('分析財報中...'):
                    info, bs, is_stmt = load_fundamentals(ticker_symbol)
                    pe = info.get('trailingPE', 0)
                    try: rev = is_stmt.loc['Total Revenue'].iloc[0]
                    except: rev = info.get('totalRevenue', 0)
                    try: net = is_stmt.loc['Net Income'].iloc[0]
                    except: net = rev * info.get('profitMargins', 0)
                    try: equity = bs.loc['Stockholders Equity'].iloc[0]
                    except: equity = info.get('totalStockholderEquity', 0)
                    roe = net / equity if equity else 0
                    m1, m2 = st.columns(2)
                    m1.metric("本益比 (PE)", f"{pe:.1f}" if pe else "N/A")
                    m2.metric("ROE", f"{roe*100:.2f}%" if roe else "N/A")
            except: st.warning("暫無財報數據")

        with tab4:
            st.subheader("💰 雲端庫存管理 (Google Sheets 同步)")
            portfolio_df = load_portfolio_gs()

            if not portfolio_df.empty:
                edited_df = st.data_editor(
                    portfolio_df,
                    num_rows="dynamic",
                    column_config={
                        "代號": st.column_config.TextColumn(help="請輸入完整代號，如 2330.TW"),
                        "買入均價": st.column_config.NumberColumn(format="$%.2f"),
                        "持有股數": st.column_config.NumberColumn(format="%d"),
                    },
                    use_container_width=True,
                    key="gs_editor"
                )

                c1, c2 = st.columns([1, 1])
                with c1: save_btn = st.button("💾 儲存回 Google Sheets", type="primary")
                with c2: calc_btn = st.button("🚀 僅計算損益 (不存檔)")

                if save_btn:
                    save_portfolio_gs(edited_df)
                    st.rerun() # 儲存後重新整理頁面，讓左側選單同步更新

                if save_btn or calc_btn:
                    tickers = edited_df['代號'].astype(str).unique().tolist()
                    live_prices = get_live_prices(tickers)
                    res_df = edited_df.copy()
                    res_df['現價'] = res_df['代號'].map(live_prices).fillna(0)
                    res_df['市值'] = res_df['現價'] * res_df['持有股數']
                    res_df['成本'] = res_df['買入均價'] * res_df['持有股數']
                    res_df['損益'] = res_df['市值'] - res_df['成本']
                    res_df['報酬率%'] = ((res_df['損益'] / res_df['成本']) * 100).fillna(0)
                    
                    total_val = res_df['市值'].sum()
                    total_pl = res_df['損益'].sum()
                    st.divider()
                    st.metric("總資產市值", f"${total_val:,.0f}", f"{total_pl:+,.0f}")
                    
                    def color_pl(val):
                        color = '#d32f2f' if val > 0 else '#2e7d32' if val < 0 else 'black'
                        return f'color: {color}; font-weight: bold'
                    st.dataframe(
                        res_df.style.map(color_pl, subset=['損益', '報酬率%'])
                        .format({'現價':"{:.2f}", '市值':"{:,.0f}", '損益':"{:+,.0f}", '報酬率%':"{:+.2f}%"}),
                        use_container_width=True
                    )
            else:
                st.warning("無法讀取 Google Sheet，請檢查 Secrets 設定。")

except Exception as e:
    st.error(f"系統錯誤：{str(e)}")
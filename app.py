import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import textwrap

# --- 1. 頁面設定 ---
st.set_page_config(page_title="台股全方位指揮所", layout="wide", page_icon="🏯")

st.markdown("""
<style>
    .stApp { background-color: #f1f3f6; }
    .block-container { padding-top: 1rem; padding-bottom: 2rem; }
    
    /* 卡片樣式 */
    .css-card {
        background-color: white; padding: 20px; border-radius: 8px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05); margin-bottom: 20px; border: 1px solid #e0e0e0;
    }
    .report-box {
        background-color: white; padding: 20px; border-radius: 10px;
        border-left: 6px solid #1a237e; box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .wash-sale-alert {
        background-color: #e3f2fd; color: #0d47a1; padding: 15px; border-radius: 8px; 
        border: 2px solid #0d47a1; margin-bottom: 20px; font-weight: bold;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .dupont-tag {
        font-size: 0.8rem; padding: 4px 8px; border-radius: 4px; background: #fff3e0; color: #e65100; border: 1px solid #e65100;
    }
    
    /* 文字顏色輔助 */
    .report-title { font-size: 1.2rem; font-weight: bold; color: #1a237e; margin-bottom: 10px; }
    .report-item { margin-bottom: 12px; border-bottom: 1px solid #eee; padding-bottom: 8px; }
    .report-label { font-weight: bold; color: #424242; }
    .report-view { color: #1565c0; font-weight: bold; }
    .report-action { color: #d84315; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# --- 2. 側邊欄 ---
with st.sidebar:
    st.header("🏯 指揮中心")
    stock_options = {
        "鴻海 (2317)": "2317.TW",
        "南亞科 (2408)": "2408.TW",
        "台積電 (2330)": "2330.TW",
        "聯發科 (2454)": "2454.TW",
        "廣達 (2382)": "2382.TW",
        "長榮 (2603)": "2603.TW",
        "元大台灣50 (0050)": "0050.TW",
        "元大高股息 (0056)": "0056.TW",
        "世界先進 (5347)": "5347.TWO",
        "輝達 (NVDA)": "NVDA",
        "蘋果 (AAPL)": "AAPL"
    }
    selected_stock_name = st.sidebar.selectbox("標的選擇", list(stock_options.keys()))
    ticker_symbol = stock_options[selected_stock_name]
    days_to_show = st.sidebar.slider("戰場範圍 (天)", 90, 360, 180)
    st.markdown("---")
    if st.button("🔄 刷新數據"):
        st.cache_data.clear()

# --- 3. 資料引擎 (技術面) ---
@st.cache_data(ttl=300)
def load_data(symbol, days):
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days + 150)
    data = yf.download(symbol, start=start_date, end=end_date, progress=False)
    
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)
    
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

# --- 4. 資料引擎 (基本面 + 強力財報抓取) ---
@st.cache_data(ttl=3600)
def load_fundamentals(symbol):
    ticker = yf.Ticker(symbol)
    info = ticker.info
    
    # 強制抓取資產負債表 (Balance Sheet) 和 損益表 (Income Statement)
    # 這是解決 N/A 的關鍵
    try:
        bs = ticker.balance_sheet
        is_stmt = ticker.income_stmt
    except:
        bs = pd.DataFrame()
        is_stmt = pd.DataFrame()
        
    return info, bs, is_stmt

# --- 5. AI 訊號產生器 ---
def generate_signals(df, high, low):
    last_close = df['Close'].iloc[-1]
    last_vol = df['Volume'].iloc[-1]
    
    # 洗盤偵測
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
            wash_sale_msg = f"""
            <div class="wash-sale-alert">
            🌊 偵測到「主力洗盤」訊號！<br>
            <div style="font-size:0.9rem; margin-top:5px;">
            1. 關鍵發動日：<b>{key_date}</b> (爆量長紅，低點 {key_low:.1f})<br>
            2. 今日狀態：<b>量縮整理</b> (成交量僅關鍵日的 {last_vol/key_vol*100:.0f}%)<br>
            3. 防守情況：<b>股價成功守住關鍵低點</b>
            </div>
            </div>
            """

    # 訊號生成 (簡化版)
    diff = high - low
    fib_0786 = low + (diff * 0.786)
    fib_0886 = low + (diff * 0.886)
    fib_0618 = low + (diff * 0.618)
    
    pos_view, pos_action = "", ""
    if last_close >= fib_0786 and last_close <= fib_0886:
        pos_view = "🚨 價格進入 78.6%~88.6% 主力誘多獵殺區。"
        pos_action = "嚴禁追高，隨時準備反轉做空或獲利了結。"
    elif last_close > fib_0618:
        pos_view = "⚠️ 價格突破 61.8%，處於相對高檔。"
        pos_action = "多單續抱，但需提高警覺。"
    elif last_close < (low + diff * 0.236):
        pos_view = "🟢 價格處於低檔底部區。"
        pos_action = "分批佈局，尋找長線買點。"
    else:
        pos_view = "⚖️ 價格處於中間震盪區域。"
        pos_action = "依照均線趨勢順勢操作。"

    bb_upper = df['BB_Upper'].iloc[-1]
    bb_view, bb_action = "", ""
    if last_close > bb_upper:
        bb_view = "🔥 股價衝破布林上軌，極短線過熱。"
        bb_action = "不宜追價。"
    else:
        bb_view = "🌊 股價在布林通道內運行。"
        bb_action = "觀望或區間操作。"

    last_obv = df['OBV'].iloc[-1]
    last_obv_ma = df['OBV_MA'].iloc[-1]
    obv_view, obv_action = "", ""
    if last_obv > last_obv_ma:
        obv_view = "📈 OBV 位於均線之上，籌碼流入。"
        obv_action = "主力心態偏多。"
    else:
        obv_view = "📉 OBV 位於均線之下，籌碼流出。"
        obv_action = "主力心態保守。"

    hist = df['MACD_Hist'].iloc[-1]
    prev_hist = df['MACD_Hist'].iloc[-2]
    macd_view, macd_action = "", ""
    if hist > 0 and hist > prev_hist:
        macd_view = "🚀 紅柱持續放大，動能強勁。"
        macd_action = "積極操作。"
    elif hist > 0 and hist < prev_hist:
        macd_view = "⚠️ 紅柱縮短，背離警戒。"
        macd_action = "設好停利。"
    else:
        macd_view = "✨ 多空膠著或空方控盤。"
        macd_action = "保守應對。"

    return {
        "wash_detected": wash_detected,
        "wash_sale_msg": wash_sale_msg,
        "position": (pos_view, pos_action),
        "bollinger": (bb_view, bb_action),
        "obv": (obv_view, obv_action),
        "macd": (macd_view, macd_action)
    }

# --- 6. 主畫面呈現 ---
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
        with title_col:
            st.markdown(f"## 🏯 {selected_stock_name} 戰略指揮所")
        with tag_col:
            if signals['wash_detected']:
                st.markdown('<div style="background:#e3f2fd; color:#0d47a1; padding:5px; border-radius:10px; text-align:center; font-weight:bold; border:1px solid #0d47a1;">🌊 主力洗盤中</div>', unsafe_allow_html=True)
        
        tab1, tab2, tab3 = st.tabs(["📈 技術戰情室", "🤖 AI 策略雷達", "📊 基本面體檢"])

        # === Tab 1: 技術戰情室 ===
        with tab1:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("最新收盤", f"{last_close:.1f}", f"{pct_change:.1f}%")
            c2.metric("風險值 (VaR 95%)", f"{var_95*100:.1f}%", help="明日潛在最大跌幅")
            c3.metric("區間高點", f"{high_price:.1f}")
            c4.metric("區間低點", f"{low_price:.1f}")

            fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.5, 0.25, 0.25])
            fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='K線', increasing_line_color='#ef4444', decreasing_line_color='#22c55e'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['BB_Upper'], line=dict(color='gray', width=1), name='上軌'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['BB_Lower'], line=dict(color='gray', width=1), fill='tonexty', fillcolor='rgba(200,200,200,0.1)', name='下軌'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['MA20'], line=dict(color='#ff6d00', width=1), name='MA20'), row=1, col=1)
            diff = high_price - low_price
            fig.add_hrect(y0=low_price + diff*0.786, y1=low_price + diff*0.886, fillcolor="red", opacity=0.1, layer="below", line_width=0, row=1, col=1)
            colors = ['#ef4444' if v >= 0 else '#22c55e' for v in df['MACD_Hist']]
            fig.add_trace(go.Bar(x=df.index, y=df['MACD_Hist'], marker_color=colors, name='MACD'), row=2, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['DIF'], line=dict(color='#eab308', width=1), name='DIF'), row=2, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['DEA'], line=dict(color='#a855f7', width=1), name='DEA'), row=2, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['OBV'], line=dict(color='purple', width=1.5), name='OBV'), row=3, col=1)
            fig.add_trace(go.Scatter(x=df.index, y=df['OBV_MA'], line=dict(color='gray', width=1, dash='dot'), name='OBV均線'), row=3, col=1)
            fig.update_layout(height=800, paper_bgcolor='white', plot_bgcolor='white', margin=dict(l=40, r=40, t=10, b=10), showlegend=False)
            st.plotly_chart(fig, use_container_width=True)

        # === Tab 2: AI 策略雷達 ===
        with tab2:
            st.subheader("🤖 AI 首席分析師綜合診斷報告")
            if signals['wash_detected']:
                st.markdown(signals['wash_sale_msg'], unsafe_allow_html=True)
            else:
                st.info("🌊 目前未偵測到明顯的「主力洗盤」訊號。")
            report_html = f"""
            <div class="report-box">
            <div class="report-item"><span class="report-label">1. 戰略位階 (Fibonacci)：</span><br>觀點：<span class="report-view">{signals['position'][0]}</span><br>💡 建議：<span class="report-action">{signals['position'][1]}</span></div>
            <div class="report-item"><span class="report-label">2. 波動風險 (Bollinger)：</span><br>觀點：<span class="report-view">{signals['bollinger'][0]}</span><br>💡 建議：<span class="report-action">{signals['bollinger'][1]}</span></div>
            <div class="report-item"><span class="report-label">3. 籌碼流向 (OBV)：</span><br>觀點：<span class="report-view">{signals['obv'][0]}</span><br>💡 建議：<span class="report-action">{signals['obv'][1]}</span></div>
            <div class="report-item"><span class="report-label">4. 市場動能 (MACD)：</span><br>觀點：<span class="report-view">{signals['macd'][0]}</span><br>💡 建議：<span class="report-action">{signals['macd'][1]}</span></div>
            </div>
            """
            st.markdown(report_html, unsafe_allow_html=True)

        # === Tab 3: 基本面體檢 (修復 N/A 問題) ===
        with tab3:
            try:
                with st.spinner('正在進行杜邦分析...'):
                    # 讀取 .info 以及 .balance_sheet, .income_stmt
                    info, bs, is_stmt = load_fundamentals(ticker_symbol)
                
                # --- 數據提取與清洗 ---
                
                # 1. 營收 (Revenue) - 優先從損益表抓
                try:
                    # yfinance 的 key 可能是 "Total Revenue"
                    revenue = is_stmt.loc['Total Revenue'].iloc[0]
                except:
                    revenue = info.get('totalRevenue', 0)

                # 2. 總資產 (Total Assets) - 優先從資產負債表抓
                try:
                    assets = bs.loc['Total Assets'].iloc[0]
                except:
                    assets = info.get('totalAssets', 0)

                # 3. 股東權益 (Stockholders Equity) - 優先從資產負債表抓
                try:
                    # key 可能是 "Stockholders Equity" 或 "Total Equity Gross Minority Interest"
                    if 'Stockholders Equity' in bs.index:
                        equity = bs.loc['Stockholders Equity'].iloc[0]
                    elif 'Total Equity Gross Minority Interest' in bs.index:
                        equity = bs.loc['Total Equity Gross Minority Interest'].iloc[0]
                    else:
                        equity = info.get('totalStockholderEquity', 0)
                except:
                    equity = info.get('totalStockholderEquity', 0)

                # 其他基本指標
                pe_ratio = info.get('trailingPE', 'N/A')
                div_yield = info.get('dividendYield', 0)
                if div_yield: div_yield = round(div_yield * 100, 2)
                mkt_cap = info.get('marketCap', 0)
                mkt_cap_fmt = f"{mkt_cap / 100000000:.1f} 億" if mkt_cap else "N/A"
                sector = info.get('sector', '未知產業')
                summary = info.get('longBusinessSummary', '無公司簡介')

                # --- 杜邦分析計算 (使用抓取到的數據) ---
                
                # A. 淨利 (Net Income) - 用於計算純益率
                try:
                     net_income = is_stmt.loc['Net Income'].iloc[0]
                except:
                     # 簡易推算：營收 * 純益率
                     net_income = revenue * info.get('profitMargins', 0)

                # 計算指標
                # ROE
                if equity and equity > 0 and net_income:
                    roe = net_income / equity
                else:
                    roe = info.get('returnOnEquity', 0)

                # 純益率
                if revenue and revenue > 0:
                    net_margin = net_income / revenue
                else:
                    net_margin = info.get('profitMargins', 0)
                
                # 總資產週轉率 = 營收 / 總資產
                asset_turnover = revenue / assets if (assets and revenue) else 0
                
                # 權益乘數 = 總資產 / 股東權益
                equity_multiplier = assets / equity if (assets and equity) else 0

                # 格式化顯示
                roe_fmt = f"{roe*100:.2f}%" if roe else "N/A"
                net_margin_fmt = f"{net_margin*100:.2f}%" if net_margin else "N/A"
                asset_turnover_fmt = f"{asset_turnover:.2f} 次" if asset_turnover else "N/A"
                equity_multiplier_fmt = f"{equity_multiplier:.2f} 倍" if equity_multiplier else "N/A"

                st.subheader("📊 財務概況")
                c1, c2 = st.columns([1, 2])
                with c1:
                    st.info(f"**市值：** {mkt_cap_fmt}")
                    st.info(f"**產業：** {sector}")
                with c2:
                    with st.expander("📖 公司簡介", expanded=False):
                        st.write(summary)

                st.divider()

                st.subheader("📐 杜邦分析 (DuPont Analysis)")
                st.caption("ROE = 純益率 × 總資產週轉率 × 權益乘數")
                
                d1, d2, d3, d4 = st.columns(4)
                d1.metric("🏆 ROE (股東權益報酬率)", roe_fmt)
                d2.metric("1️⃣ 純益率 (獲利能力)", net_margin_fmt)
                d3.metric("2️⃣ 總資產週轉率 (經營效率)", asset_turnover_fmt)
                d4.metric("3️⃣ 權益乘數 (財務槓桿)", equity_multiplier_fmt)

                dupont_msg = ""
                if roe > 0.15: dupont_msg += "<span class='dupont-tag'>🔥 高 ROE 資優生</span> "
                if net_margin > 0.2: dupont_msg += "<span class='dupont-tag'>💎 高毛利護城河</span> "
                elif asset_turnover > 1.5: dupont_msg += "<span class='dupont-tag'>⚡ 高周轉效率型</span> "
                elif equity_multiplier > 4: dupont_msg += "<span class='dupont-tag'>⚠️ 高槓桿風險型</span> "
                
                if dupont_msg:
                    st.markdown(f"<div style='margin-top:10px;'><b>AI 杜邦診斷：</b> {dupont_msg}</div>", unsafe_allow_html=True)

                st.divider()
                st.subheader("💰 價值評估")
                v1, v2 = st.columns(2)
                pe_color = "normal"
                if isinstance(pe_ratio, (int, float)):
                    if pe_ratio < 15: pe_color = "off"
                    elif pe_ratio > 25: pe_color = "inverse"
                v1.metric("本益比 (PE)", pe_ratio, delta_color=pe_color)
                v2.metric("殖利率 (Yield)", f"{div_yield}%" if div_yield else "N/A")

            except Exception as e:
                st.error(f"讀取基本面資料時發生錯誤: {str(e)}")

except Exception as e:
    st.error(f"系統嚴重錯誤：{str(e)}")
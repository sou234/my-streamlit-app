import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import FinanceDataReader as fdr
from pykrx import stock  # [NEW] pykrx 추가
from datetime import datetime, timedelta

# ---------------------------------------------------------
# 1. 페이지 설정
# ---------------------------------------------------------
st.set_page_config(
    page_title="MAS Decision Support System",
    page_icon="🍊",
    layout="wide"
)

# ---------------------------------------------------------
# 2. 데이터 수집 함수들
# ---------------------------------------------------------

# (1) 시황 및 신호 분석 함수
@st.cache_data(ttl=600)
def fetch_and_analyze_data():
    tickers = {"KOSPI": "KS11", "S&P500": "US500", "USD/KRW": "USD/KRW"}
    market_data = {}
    history_data = {}
    
    start_date = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')

    for name, ticker in tickers.items():
        try:
            df = fdr.DataReader(ticker, start_date)
            if not df.empty:
                current = df['Close'].iloc[-1]
                prev = df['Close'].iloc[-2]
                change = current - prev
                pct = (change / prev * 100) if prev != 0 else 0
                
                df['MA20'] = df['Close'].rolling(window=20).mean()
                df['MA60'] = df['Close'].rolling(window=60).mean()
                
                trend = "상승 (Bull)" if current > df['MA20'].iloc[-1] else "조정 (Bear)"
                signal = "매수 우위 (Golden Cross)" if df['MA20'].iloc[-1] > df['MA60'].iloc[-1] else "보수적 접근"

                market_data[name] = {
                    "price": current, "change": change, "pct_change": pct,
                    "trend": trend, "signal": signal
                }
                history_data[name] = df
        except Exception:
            pass
    return market_data, history_data

# (2) 타임폴리오 PDF 크롤링 함수 (pykrx 사용 버전으로 교체됨)
@st.cache_data(ttl=3600) 
def get_timefolio_pdf(code):
    try:
        # pykrx를 이용해 가장 최신일자의 PDF(구성종목) 가져오기
        df = stock.get_etf_portfolio_deposit_file(code)
        
        # 시각화 코드와 호환되도록 컬럼 이름 변경 ('비중' -> '구성비중(%)')
        df = df.reset_index() # 티커를 컬럼으로 빼내기
        if '비중' in df.columns:
            df = df.rename(columns={'비중': '구성비중(%)'})
            
        return df
    except Exception as e:
        # 에러 발생 시 (휴일 등) None 반환
        return None

# 데이터 로딩
with st.spinner('시장 데이터 및 ETF 포트폴리오 분석 중...'):
    metrics, histories = fetch_and_analyze_data()

# ---------------------------------------------------------
# 3. 사이드바
# ---------------------------------------------------------
with st.sidebar:
    st.title("🍊 Mirae Asset")
    st.subheader("고객자산배분본부")
    st.caption("고객상품전략팀 인턴 프로젝트")
    st.markdown("---")
    
    menu = st.radio(
        "시스템 메뉴",
        [
            "1. 시황 모니터링 (Market)", 
            "2. 의사결정 지원 (Signal)", 
            "3. MBTI 리포트 (Report)",
            "4. 타임폴리오(TIMEFOLIO) PDF" 
        ]
    )
    
    st.markdown("---")
    if st.button("🔄 데이터 최신화"):
        st.cache_data.clear()

# ---------------------------------------------------------
# 4. 메인 화면
# ---------------------------------------------------------

# [메뉴 1] 시황 모니터링
if menu == "1. 시황 모니터링 (Market)":
    st.title("📈 Global Market Monitor")
    st.markdown(f"**기준일:** {datetime.now().strftime('%Y-%m-%d')}")
    st.markdown("---")
    col1, col2, col3 = st.columns(3)
    with col1:
        if "KOSPI" in metrics:
            d = metrics["KOSPI"]
            st.metric("KOSPI", f"{d['price']:,.2f}", f"{d['change']:.2f} ({d['pct_change']:.2f}%)")
    with col2:
        if "S&P500" in metrics:
            d = metrics["S&P500"]
            st.metric("S&P 500", f"{d['price']:,.2f}", f"{d['change']:.2f} ({d['pct_change']:.2f}%)")
    with col3:
        if "USD/KRW" in metrics:
            d = metrics["USD/KRW"]
            st.metric("원/달러 환율", f"{d['price']:,.2f} 원", f"{d['change']:.2f} 원", delta_color="inverse")
    
    tab1, tab2 = st.tabs(["주가지수 비교", "환율 추이"])
    with tab1:
        if "KOSPI" in histories or "S&P500" in histories:
            fig = go.Figure()
            if "KOSPI" in histories:
                fig.add_trace(go.Scatter(x=histories['KOSPI'].index, y=histories['KOSPI']['Close'], name='KOSPI', line=dict(color='#FF6600')))
            if "S&P500" in histories:
                fig.add_trace(go.Scatter(x=histories['S&P500'].index, y=histories['S&P500']['Close'], name='S&P500', line=dict(color='#003594'), yaxis='y2'))
            
            fig.update_layout(title="KOSPI vs S&P500", yaxis=dict(title="KOSPI"), yaxis2=dict(title="S&P500", overlaying='y', side='right'), template="plotly_white", height=450)
            st.plotly_chart(fig, use_container_width=True)
    with tab2:
        if "USD/KRW" in histories:
            fig_r = px.area(histories['USD/KRW'], x=histories['USD/KRW'].index, y='Close', title="원/달러 환율")
            fig_r.update_traces(line_color='green')
            st.plotly_chart(fig_r, use_container_width=True)

# [메뉴 2] 의사결정 지원
elif menu == "2. 의사결정 지원 (Signal)":
    st.title("🚦 의사결정 지원 시스템")
    st.subheader("Asset Trend Signal")
    
    signal_list = []
    for name, data in metrics.items():
        signal_list.append({
            "자산명": name,
            "현재가": f"{data['price']:,.2f}",
            "추세 (MA20)": data['trend'],
            "신호 (MA20 vs 60)": data['signal']
        })
    st.dataframe(pd.DataFrame(signal_list), use_container_width=True, hide_index=True)
    
    st.subheader("AI Insight")
    st.info("S&P500 상승 추세 지속에 따른 선진국 주식 비중 확대 및 환리스크 관리 필요")

# [메뉴 3] MBTI 리포트
elif menu == "3. MBTI 리포트 (Report)":
    st.title("📑 Global IB 리포트 (MBTI)")
    with st.expander("📌 [Goldman Sachs] AI 반도체 슈퍼사이클", expanded=True):
        st.write("HBM 공급 부족 지속 및 온디바이스 AI 시장 개화로 반도체 비중 확대 권고")

# [메뉴 4] 타임폴리오 PDF (pykrx 적용됨)
elif menu == "4. 타임폴리오(TIMEFOLIO) PDF":
    st.title("📊 타임폴리오(TIMEFOLIO) PDF 분석")
    st.markdown("**Powered by pykrx** (실시간 보유종목 분석)")
    st.markdown("---")

    etf_dict = {
        "TIMEFOLIO 코스피액티브 (385720)": "385720",
        "TIMEFOLIO 미국S&P500액티브 (426020)": "426020",
        "TIMEFOLIO 글로벌AI인공지능액티브 (456600)": "456600",
        "TIMEFOLIO Korea플러스배당액티브 (441800)": "441800"
    }
    
    selected_etf_name = st.selectbox("분석할 ETF를 선택하세요", list(etf_dict.keys()))
    selected_code = etf_dict[selected_etf_name]

    pdf_df = get_timefolio_pdf(selected_code)

    if pdf_df is not None and not pdf_df.empty:
        col_pdf1, col_pdf2 = st.columns([1, 1])
        
        with col_pdf1:
            st.subheader(f"🔍 Top 10 보유 종목")
            # 구성비중(%) 컬럼 기준으로 정렬
            if '구성비중(%)' in pdf_df.columns:
                top10 = pdf_df.sort_values(by="구성비중(%)", ascending=False).head(10)
                fig_donut = px.pie(top10, values="구성비중(%)", names="종목명", title="Top 10 Holdings", hole=0.4)
                fig_donut.update_traces(textposition='inside', textinfo='percent+label')
                st.plotly_chart(fig_donut, use_container_width=True)
            else:
                st.warning("비중 데이터를 찾을 수 없습니다.")
            
        with col_pdf2:
            st.subheader("📋 전체 구성 종목")
            st.dataframe(pdf_df, use_container_width=True, height=500, hide_index=True)
    else:
        st.warning("데이터를 가져오는 중입니다. (장 시작 전이거나 휴일일 수 있습니다)")
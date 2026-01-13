import streamlit as st
import pandas as pd
import plotly.express as px
import FinanceDataReader as fdr
import requests
import urllib3
from io import StringIO
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

# 보안 인증서 경고 무시
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ---------------------------------------------------------
# 1. 페이지 설정
# ---------------------------------------------------------
st.set_page_config(
    page_title="MAS Decision Support System",
    page_icon="🍊",
    layout="wide"
)

# ---------------------------------------------------------
# 2. 데이터 수집 함수
# ---------------------------------------------------------

@st.cache_data(ttl=600)
def fetch_market_data():
    """시장 지수 수집"""
    tickers = {"KOSPI": "KS11", "S&P500": "US500", "USD/KRW": "USD/KRW"}
    market_data, history_data = {}, {}
    start_date = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')

    for name, ticker in tickers.items():
        try:
            df = fdr.DataReader(ticker, start_date)
            if not df.empty:
                current = df['Close'].iloc[-1]
                prev = df['Close'].iloc[-2]
                pct = ((current - prev) / prev * 100) if prev != 0 else 0
                df['MA20'] = df['Close'].rolling(window=20).mean()
                trend = "상승 (Bull)" if current > df['MA20'].iloc[-1] else "조정 (Bear)"
                market_data[name] = {"price": current, "change": current - prev, "pct_change": pct, "trend": trend}
                history_data[name] = df
        except: pass
    return market_data, history_data

@st.cache_data(ttl=1800)
def get_timefolio_data_ultimate(idx):
    """
    타임폴리오 공식 홈페이지 데이터 추출 및 리밸런싱 분석
    """
    try:
        session = requests.Session()
        main_url = "https://timefolioetf.co.kr/m11.php"
        view_url = f"https://timefolioetf.co.kr/m11_view.php?idx={idx}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': main_url,
        }
        
        session.get(main_url, headers=headers, verify=False, timeout=10)
        response = session.get(view_url, headers=headers, verify=False, timeout=20)
        response.encoding = 'utf-8'
        
        if response.status_code != 200:
            return None

        soup = BeautifulSoup(response.text, 'html.parser')
        target_table = None
        for table in soup.find_all('table'):
            if '종목명' in table.get_text() and '비중' in table.get_text():
                target_table = table
                break
        
        if target_table:
            rows = target_table.find_all('tr')
            table_data = []
            for row in rows:
                cols = [c.get_text().strip() for c in row.find_all(['th', 'td'])]
                if cols: table_data.append(cols)
            
            if table_data:
                df = pd.DataFrame(table_data)
                df.columns = df.iloc[0]
                df = df[1:].reset_index(drop=True)
                
                df.columns = [str(c).strip() for c in df.columns]
                name_col = next((c for c in df.columns if "종목명" in c), None)
                weight_col = next((c for c in df.columns if "비중" in c), None)
                change_col = next((c for c in df.columns if any(k in c for k in ["대비", "증감", "전일"])), None)
                
                if name_col and weight_col:
                    cols_to_show = [name_col, weight_col]
                    if change_col: cols_to_show.append(change_col)
                    
                    final_df = df[cols_to_show].head(10).copy()
                    final_df.columns = ["종목명", "비중(%)", "증감"] if len(cols_to_show) == 3 else ["종목명", "비중(%)"]
                    
                    # 데이터 정제 (숫자화)
                    final_df["비중(%)"] = final_df["비중(%)"].str.replace('%', '').str.strip()
                    final_df["비중(%)"] = pd.to_numeric(final_df["비중(%)"], errors='coerce')
                    
                    if "증감" in final_df.columns:
                        final_df["증감"] = final_df["증감"].str.replace('+', '', regex=False).str.replace('%', '').str.strip()
                        final_df["증감"] = pd.to_numeric(final_df["증감"], errors='coerce').fillna(0)
                    
                    final_df = final_df.dropna(subset=["종목명"])
                    final_df.index = range(1, len(final_df) + 1)
                    return final_df

        return None
            
    except Exception as e:
        return None

# 데이터 로드
metrics, histories = fetch_market_data()

# ---------------------------------------------------------
# 3. 사이드바 구성
# ---------------------------------------------------------
with st.sidebar:
    st.title("🍊 Mirae Asset")
    st.subheader("고객자산배분본부")
    st.caption("인턴 프로젝트 - 타임폴리오 리밸런싱")
    st.markdown("---")
    
    menu = st.radio("메뉴 선택", ["📌 시장 동향", "📊 타임폴리오 실시간 PDF"])
    
    if st.button("🔄 데이터 새로고침"):
        st.cache_data.clear()

# ---------------------------------------------------------
# 4. 메인 화면
# ---------------------------------------------------------

if menu == "📌 시장 동향":
    st.title("📈 Global Market Monitor")
    col1, col2, col3 = st.columns(3)
    with col1:
        if "KOSPI" in metrics:
            d = metrics["KOSPI"]
            st.metric("KOSPI", f"{d['price']:,.2f}", f"{d['pct_change']:.2f}%")
    with col2:
        if "S&P500" in metrics:
            d = metrics["S&P500"]
            st.metric("S&P 500", f"{d['price']:,.2f}", f"{d['pct_change']:.2f}%")
    with col3:
        if "USD/KRW" in metrics:
            d = metrics["USD/KRW"]
            st.metric("원/달러 환율", f"{d['price']:,.2f}", f"{d['pct_change']:.2f}%", delta_color="inverse")
    
    if "KOSPI" in histories:
        st.line_chart(histories['KOSPI']['Close'])

elif menu == "📊 타임폴리오 실시간 PDF":
    st.title("📊 TIMEFOLIO Official Portfolio & Rebalancing")
    
    etf_categories = {
        "해외주식형 (10종)": {
            "글로벌탑픽": "22", "글로벌바이오": "9", "우주테크&방산": "20",
            "S&P500": "5", "나스닥100": "2", "글로벌AI": "6",
            "차이나AI": "19", "미국배당다우존스": "18",
            "미국나스닥100채권혼합50": "10", "글로벌소비트렌드": "8"
        },
        "국내주식형 (7종)": {
            "K신재생에너지": "16", "K바이오": "13", "Korea플러스배당": "12",
            "코스피": "11", "코리아밸류업": "15", "K이노베이션": "17", "K컬처": "1"
        }
    }
    
    c1, c2 = st.columns(2)
    with c1:
        cat = st.selectbox("분류", list(etf_categories.keys()))
    with c2:
        name = st.selectbox("상품명", list(etf_categories[cat].keys()))
    
    target_idx = etf_categories[cat][name]
    
    if st.button("데이터 분석 및 리밸런싱 요약"):
        with st.spinner(f"'{name}' 데이터를 분석 중입니다..."):
            df = get_timefolio_data_ultimate(target_idx)
            
        if df is not None and not df.empty:
            st.success(f"✅ {name} 데이터 분석 완료")
            
            # --- [신규 기능: 리밸런싱 요약] ---
            st.subheader("🔄 리밸런싱 요약 (전일 대비)")
            
            # 요약 수치 계산
            increased = df[df["증감"] > 0]
            decreased = df[df["증감"] < 0]
            new_in = df[df["비중(%)"] == df["증감"]] # 현재 비중과 증감이 같으면 신규 편입으로 간주
            
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("비중 확대", f"{len(increased)} 종목", delta=f"{len(increased)}", delta_color="normal")
            m2.metric("비중 축소", f"{len(decreased)} 종목", delta=f"-{len(decreased)}", delta_color="inverse")
            m3.metric("신규 편입", f"{len(new_in)} 종목")
            m4.metric("편출/기타", "-")

            # 상세 내역 (비중 확대 종목 수치 비교)
            if not increased.empty:
                st.markdown("#### 🚀 주요 비중 확대 종목 (상세)")
                for _, row in increased.iterrows():
                    prev_w = round(row["비중(%)"] - row["증감"], 2)
                    curr_w = round(row["비중(%)"], 2)
                    change = round(row["증감"], 2)
                    st.write(f"- **{row['종목명']}**: {prev_w}% → {curr_w}% (**+{change}%**)")
            
            st.markdown("---")
            
            # 기존 테이블 및 차트
            l, r = st.columns([1, 1.2])
            with l:
                st.subheader("📍 포트폴리오 비중")
                fig = px.pie(df, values="비중(%)", names="종목명", hole=0.5,
                             color_discrete_sequence=px.colors.qualitative.Pastel)
                st.plotly_chart(fig, use_container_width=True)
            with r:
                st.subheader("📋 전체 TOP 10 상세")
                # 스타일링 (증감에 따른 색상)
                def color_change(val):
                    color = 'red' if val > 0 else 'blue' if val < 0 else 'black'
                    return f'color: {color}'
                
                st.dataframe(df.style.applymap(color_change, subset=['증감']), 
                             use_container_width=True, height=400)
        else:
            st.error("❌ 데이터를 가져오는 데 실패했습니다.")

    st.markdown("---")
    st.link_button("🌐 공식 상세페이지 바로가기", f"https://timefolioetf.co.kr/m11_view.php?idx={target_idx}")

import streamlit as st
import pandas as pd
import plotly.express as px
import FinanceDataReader as fdr
import requests
import urllib3
from io import StringIO
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

# 보안 인증서 경고 무시 (회사 보안망 환경 대응 필수)
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
# 2. 데이터 수집 함수 (강화된 세션 관리 버전)
# ---------------------------------------------------------

@st.cache_data(ttl=600)
def fetch_market_data():
    """주요 시장 지수 데이터 수집"""
    tickers = {"KOSPI": "KS11", "S&P500": "US500", "USD/KRW": "USD/KRW"}
    market_data = {}
    history_data = {}
    start_date = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')

    for name, ticker in tickers.items():
        try:
            df = fdr.DataReader(ticker, start_date)
            if not df.empty:
                current = df['Close'].iloc[-1]
                prev = df['Close'].iloc[-2]
                change = current - prev
                pct = (change / prev * 100) if prev != 0 else 0
                df['MA20'] = df['Close'].rolling(window=20).mean()
                trend = "상승 (Bull)" if current > df['MA20'].iloc[-1] else "조정 (Bear)"
                market_data[name] = {"price": current, "change": change, "pct_change": pct, "trend": trend}
                history_data[name] = df
        except: pass
    return market_data, history_data

@st.cache_data(ttl=1800)
def get_timefolio_official_pdf(idx):
    """
    타임폴리오 공식 홈페이지 상세 페이지에서 TOP 10 데이터 추출
    세션 유지 및 브라우저 모사 강화 버전
    """
    try:
        # 1. 세션 생성 (쿠키 및 연결 유지)
        session = requests.Session()
        
        # 메인 페이지를 먼저 방문하여 기본 쿠키 생성 시도
        main_url = "https://timefolioetf.co.kr/m11.php"
        view_url = f"https://timefolioetf.co.kr/m11_view.php?idx={idx}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
            'Referer': main_url,
            'Connection': 'keep-alive'
        }
        
        # 메인 방문
        session.get(main_url, headers=headers, verify=False, timeout=10)
        
        # 2. 상세 페이지 요청
        response = session.get(view_url, headers=headers, verify=False, timeout=20)
        response.encoding = 'utf-8' 
        
        if response.status_code != 200:
            return None

        # 3. BeautifulSoup으로 분석
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # '종목명' 텍스트를 포함하는 테이블 찾기
        target_table = None
        for table in soup.find_all('table'):
            table_text = table.get_text()
            if '종목명' in table_text and '비중' in table_text:
                target_table = table
                break
        
        if not target_table:
            # 테이블을 못 찾은 경우 pandas로 재시도
            try:
                all_tables = pd.read_html(StringIO(response.text))
                for t in all_tables:
                    t_str = str(t.values)
                    if '종목명' in t_str and '비중' in t_str:
                        target_table_df = t
                        break
                else: return None
            except: return None
        else:
            # BS4 테이블을 DataFrame으로 변환
            rows = target_table.find_all('tr')
            table_data = []
            for row in rows:
                cells = row.find_all(['th', 'td'])
                cells = [c.get_text().strip() for c in cells]
                if cells: table_data.append(cells)
            
            if not table_data: return None
            
            # 첫 번째 행을 헤더로 설정
            temp_df = pd.DataFrame(table_data)
            temp_df.columns = temp_df.iloc[0]
            target_table_df = temp_df[1:].reset_index(drop=True)

        # 4. 필수 컬럼 필터링 및 이름 정리
        df = target_table_df.copy()
        df.columns = [str(c).strip() for c in df.columns]

        # 컬럼 인덱스 찾기
        name_idx = next((i for i, v in enumerate(df.columns) if "종목명" in v), 1)
        weight_idx = next((i for i, v in enumerate(df.columns) if "비중" in v), 2)
        change_idx = next((i for i, v in enumerate(df.columns) if any(k in v for k in ["대비", "증감", "전일"])), None)

        cols_to_use = [df.columns[name_idx], df.columns[weight_idx]]
        if change_idx is not None:
            cols_to_use.append(df.columns[change_idx])
            
        final_df = df[cols_to_use].head(10).reset_index(drop=True)
        final_df.columns = ["종목명", "비중(%)", "증감"] if len(cols_to_use) == 3 else ["종목명", "비중(%)"]
        
        # 5. 비중 숫자 변환 및 정제
        final_df["비중(%)"] = final_df["비중(%)"].astype(str).str.replace('%', '').str.strip()
        final_df["비중(%)"] = pd.to_numeric(final_df["비중(%)"], errors='coerce')
        
        # 종목명이 비어있는 행 제거
        final_df = final_df[final_df["종목명"].str.len() > 0].dropna(subset=["종목명"])
        
        final_df.index = range(1, len(final_df) + 1)
        return final_df
            
    except Exception as e:
        return None

# 데이터 로드
with st.spinner('시장 데이터를 분석 중입니다...'):
    metrics, histories = fetch_market_data()

# ---------------------------------------------------------
# 3. 사이드바 구성 (사용자 지정 10+7 정확한 idx 반영)
# ---------------------------------------------------------
with st.sidebar:
    st.title("🍊 Mirae Asset")
    st.subheader("고객자산배분본부")
    st.caption("인턴 프로젝트 - 타임폴리오 연동")
    st.markdown("---")
    
    menu = st.radio("메뉴 선택", ["📌 시장 동향", "🚦 의사결정 지원", "📊 타임폴리오 실시간 PDF"])
    
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
            st.metric("KOSPI", f"{d['price']:,.2f}", f"{d['change']:.2f} ({d['pct_change']:.2f}%)")
    with col2:
        if "S&P500" in metrics:
            d = metrics["S&P500"]
            st.metric("S&P 500", f"{d['price']:,.2f}", f"{d['change']:.2f} ({d['pct_change']:.2f}%)")
    with col3:
        if "USD/KRW" in metrics:
            d = metrics["USD/KRW"]
            st.metric("원/달러 환율", f"{d['price']:,.2f} 원", f"{d['change']:.2f} 원", delta_color="inverse")
    
    if "KOSPI" in histories:
        st.line_chart(histories['KOSPI']['Close'])

elif menu == "🚦 의사결정 지원":
    st.title("🚦 자산별 시그널 분석")
    data_list = [{"자산": k, "현재가": f"{v['price']:,.2f}", "추세(MA20)": v['trend']} for k, v in metrics.items()]
    st.dataframe(pd.DataFrame(data_list), use_container_width=True, hide_index=True)

elif menu == "📊 타임폴리오 실시간 PDF":
    st.title("📊 TIMEFOLIO Official Portfolio (10+7 Line-up)")
    
    # [사용자가 제공한 정확한 10+7 라인업 및 idx]
    etf_categories = {
        "해외주식형 (10종)": {
            "글로벌탑픽": "22",
            "글로벌바이오": "9",
            "우주테크&방산": "20",
            "미국S&P500": "5",
            "미국나스닥100": "2",
            "글로벌AI": "6",
            "차이나AI": "19",
            "미국배당다우존스": "18",
            "미국나스닥100채권혼합50": "10",
            "글로벌소비트렌드": "8"
        },
        "국내주식형 (7종)": {
            "K신재생에너지": "16",
            "K바이오": "13",
            "Korea플러스배당": "12",
            "코스피": "11",
            "코리아밸류업": "15",
            "K이노베이션": "17",
            "K컬처": "1"
        }
    }
    
    c1, c2 = st.columns(2)
    with c1:
        category = st.selectbox("투자 분류", list(etf_categories.keys()))
    with c2:
        target_name = st.selectbox("상품명 선택", list(etf_categories[category].keys()))
    
    target_idx = etf_categories[category][target_name]
    
    if st.button("실시간 데이터 조회"):
        with st.spinner(f"타임폴리오 '{target_name}'(idx:{target_idx}) 분석 중..."):
            df = get_timefolio_official_pdf(target_idx)
            
        if df is not None and not df.empty:
            st.success(f"✅ {target_name} 데이터 연동 성공")
            
            l, r = st.columns([1, 1.2])
            with l:
                st.subheader("📍 TOP 10 비중")
                fig = px.pie(df, values="비중(%)", names="종목명", hole=0.5,
                             color_discrete_sequence=px.colors.qualitative.Pastel)
                fig.update_traces(textinfo='percent+label')
                st.plotly_chart(fig, use_container_width=True)
            with r:
                st.subheader("📋 실시간 구성 종목 상세")
                st.dataframe(df, use_container_width=True, height=450)
                st.caption("※ 증감 수치는 공식 홈페이지의 '대비' 항목입니다.")
        else:
            st.error("❌ 데이터 로드 실패")
            st.info("💡 **조치 방법**: 잠시 후 다시 시도하거나, 아래 링크 버튼을 눌러 사이트가 정상 작동하는지 확인하세요.")

    st.markdown("---")
    st.link_button("🌐 타임폴리오 공식 상세페이지 확인", f"https://timefolioetf.co.kr/m11_view.php?idx={target_idx}")

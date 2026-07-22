# main.py
# ------------------------------------------------------------
# 어제 박스오피스 분석 대시보드 (KOBIS 공공 API 사용)
# - 스트림릿 클라우드 배포 기준으로 작성했습니다.
# - 초보자를 위해 각 단계마다 한국어 주석을 달아두었습니다.
# ------------------------------------------------------------

import requests                    # KOBIS API에 HTTP 요청을 보내기 위한 라이브러리
import pandas as pd                # 표 형태 데이터 처리
import streamlit as st             # 웹 대시보드 UI
import plotly.express as px        # 막대그래프 그리기
from datetime import datetime, timedelta   # 날짜 계산
from zoneinfo import ZoneInfo      # 시간대(타임존) 계산 - 파이썬 기본 내장 모듈


# ------------------------------------------------------------
# 1) 화면 기본 설정
# ------------------------------------------------------------
st.set_page_config(
    page_title="어제 박스오피스 대시보드",
    page_icon="🎬",
    layout="wide",
)


# ------------------------------------------------------------
# 2) '어제' 날짜를 한국 시간(Asia/Seoul) 기준으로 계산
#    - 스트림릿 클라우드 서버는 시간대가 한국이 아닐 수 있으므로
#      반드시 Asia/Seoul 타임존을 명시해서 계산합니다.
# ------------------------------------------------------------
def get_yesterday_kst() -> str:
    """한국 시간 기준으로 '어제' 날짜를 yyyymmdd 문자열로 반환합니다."""
    now_kst = datetime.now(ZoneInfo("Asia/Seoul"))
    yesterday_kst = now_kst - timedelta(days=1)
    return yesterday_kst.strftime("%Y%m%d")


target_dt = get_yesterday_kst()


# ------------------------------------------------------------
# 3) KOBIS API 호출 함수
#    - 인증키는 코드에 직접 쓰지 않고, 스트림릿 secrets에서 불러옵니다.
#      (스트림릿 클라우드 배포 시 [Settings] > [Secrets]에
#       KOBIS_KEY = "발급받은키값" 형태로 등록해두면 됩니다.)
# ------------------------------------------------------------
KOBIS_URL = "http://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json"


@st.cache_data(ttl=3600)  # 같은 날짜로는 1시간 동안 재요청하지 않고 캐시 사용 (API 호출 절약)
def fetch_box_office(target_dt: str):
    """
    KOBIS 일별 박스오피스 API를 호출합니다.
    성공 시 (True, DataFrame) 을,
    실패 시 (False, 에러메시지) 를 반환합니다.
    """
    # secrets에 키가 없는 경우를 대비한 안전장치
    if "KOBIS_KEY" not in st.secrets:
        return False, "KOBIS_KEY가 secrets에 설정되어 있지 않습니다. 스트림릿 클라우드의 Settings > Secrets에 등록해주세요."

    api_key = st.secrets["KOBIS_KEY"]

    params = {
        "key": api_key,
        "targetDt": target_dt,
    }

    # 3-1) 네트워크 요청 자체가 실패하는 경우 (타임아웃, 연결 오류 등)
    try:
        response = requests.get(KOBIS_URL, params=params, timeout=10)
        response.raise_for_status()  # 4xx, 5xx 응답이면 예외 발생
    except requests.exceptions.RequestException as e:
        return False, f"KOBIS 서버에 요청하는 중 오류가 발생했습니다: {e}"

    # 3-2) 응답이 JSON 형식이 아닌 경우
    try:
        data = response.json()
    except ValueError:
        return False, "KOBIS 서버 응답을 해석할 수 없습니다. (JSON 형식이 아닙니다)"

    # 3-3) API 자체 오류 응답 처리 (faultInfo가 오는 경우)
    #      예: 인증키가 잘못되었거나, 날짜 형식이 잘못된 경우 등
    if "faultInfo" in data:
        message = data["faultInfo"].get("message", "알 수 없는 오류")
        return False, f"KOBIS API 오류: {message} (인증키 또는 요청 값을 확인해주세요.)"

    # 3-4) 정상 응답이지만 예상한 구조가 아닌 경우 방어 코드
    try:
        movie_list = data["boxOfficeResult"]["dailyBoxOfficeList"]
    except KeyError:
        return False, "예상한 형식의 데이터를 찾을 수 없습니다. KOBIS 응답 구조가 변경되었을 수 있습니다."

    if not movie_list:
        return False, "해당 날짜의 박스오피스 데이터가 없습니다."

    df = pd.DataFrame(movie_list)
    return True, df


# ------------------------------------------------------------
# 4) 숫자형 컬럼 변환
#    - API 응답은 모든 값이 문자열(string)로 오기 때문에,
#      정렬/그래프에 쓰려면 숫자(int)로 바꿔줘야 합니다.
# ------------------------------------------------------------
def convert_numeric_columns(df: pd.DataFrame) -> pd.DataFrame:
    numeric_cols = ["rank", "audiCnt", "audiAcc", "scrnCnt", "showCnt"]
    for col in numeric_cols:
        if col in df.columns:
            # errors="coerce": 혹시 숫자로 못 바꾸는 값이 있으면 에러 대신 NaN 처리
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


# ------------------------------------------------------------
# 5) 화면 타이틀 영역
# ------------------------------------------------------------
st.title("🎬 어제 박스오피스 대시보드")

# 화면에 보여줄 날짜는 yyyy-mm-dd 형태로 보기 좋게 변환
display_date = f"{target_dt[:4]}-{target_dt[4:6]}-{target_dt[6:]}"
st.caption(f"기준일(한국시간 기준 어제): {display_date}  ·  출처: 영화진흥위원회(KOBIS) 오픈API")


# ------------------------------------------------------------
# 6) 데이터 조회 및 화면 표시
# ------------------------------------------------------------
with st.spinner("박스오피스 데이터를 불러오는 중입니다..."):
    success, result = fetch_box_office(target_dt)

if not success:
    # 실패 또는 faultInfo 응답인 경우 -> 친절한 안내 메시지 표시
    st.error(f"😥 데이터를 불러오지 못했습니다.\n\n{result}")
    st.stop()  # 이후 코드는 실행하지 않고 여기서 중단

df = result
df = convert_numeric_columns(df)

# 순위 기준으로 정렬 (혹시 순서가 뒤섞여 있을 경우 대비)
df = df.sort_values("rank").reset_index(drop=True)


# ------------------------------------------------------------
# 7) 1위 영화 지표 카드
# ------------------------------------------------------------
top_movie = df.iloc[0]

st.subheader("👑 어제의 1위 영화")

col1, col2, col3 = st.columns(3)
col1.metric(label=top_movie["movieNm"], value=f"{int(top_movie['audiCnt']):,} 명")
col2.metric(label="누적 관객수", value=f"{int(top_movie['audiAcc']):,} 명")
col3.metric(label="스크린수", value=f"{int(top_movie['scrnCnt']):,} 개")

st.divider()


# ------------------------------------------------------------
# 8) 표: 순위 / 영화명 / 개봉일 / 관객수 / 누적관객 / 스크린수
# ------------------------------------------------------------
st.subheader("📋 일별 박스오피스 순위표")

table_df = df[["rank", "movieNm", "openDt", "audiCnt", "audiAcc", "scrnCnt"]].copy()
table_df.columns = ["순위", "영화명", "개봉일", "관객수(명)", "누적관객수(명)", "스크린수"]

st.dataframe(
    table_df,
    use_container_width=True,
    hide_index=True,
    column_config={
        "관객수(명)": st.column_config.NumberColumn(format="%d"),
        "누적관객수(명)": st.column_config.NumberColumn(format="%d"),
        "스크린수": st.column_config.NumberColumn(format="%d"),
    },
)

st.divider()


# ------------------------------------------------------------
# 9) 그래프: 관객수 상위 5편 막대그래프
# ------------------------------------------------------------
st.subheader("📊 관객수 상위 5편")

top5_df = df.sort_values("audiCnt", ascending=False).head(5)

fig = px.bar(
    top5_df,
    x="movieNm",
    y="audiCnt",
    text="audiCnt",
    labels={"movieNm": "영화명", "audiCnt": "관객수(명)"},
    color="movieNm",
)
fig.update_traces(texttemplate="%{text:,}", textposition="outside")
fig.update_layout(showlegend=False, yaxis_title="관객수(명)", xaxis_title="")

st.plotly_chart(fig, use_container_width=True)

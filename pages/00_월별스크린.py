# main.py
# ------------------------------------------------------------
# 박스오피스 분석 대시보드 (KOBIS 공공 API 사용)
# - 달력에서 날짜를 골라 그날의 박스오피스를 조회합니다.
# - 오늘 데이터는 아직 집계되지 않았으므로, 조회 가능한 가장
#   최신 날짜는 '어제(한국시간 기준)'로 제한합니다.
# - 초보자를 위해 각 단계마다 한국어 주석을 달아두었습니다.
# ------------------------------------------------------------

import requests                    # KOBIS API에 HTTP 요청을 보내기 위한 라이브러리
import pandas as pd                # 표 형태 데이터 처리
import streamlit as st             # 웹 대시보드 UI
import plotly.express as px        # 막대그래프 그리기
from datetime import datetime, timedelta, date   # 날짜 계산
from zoneinfo import ZoneInfo      # 시간대(타임존) 계산 - 파이썬 기본 내장 모듈


# ------------------------------------------------------------
# 1) 화면 기본 설정
# ------------------------------------------------------------
st.set_page_config(
    page_title="박스오피스 대시보드",
    page_icon="🎬",
    layout="wide",
)

# 표/카드에 쓰는 색을 한 곳에 모아두면 나중에 톤을 바꾸기 편합니다.
ACCENT_COLOR = "#E50914"  # 포인트 컬러 (극장/영화 느낌의 레드 톤)


# ------------------------------------------------------------
# 2) 한국 시간(Asia/Seoul) 기준 '어제' 계산
#    - 스트림릿 클라우드 서버는 시간대가 한국이 아닐 수 있으므로
#      반드시 Asia/Seoul 타임존을 명시해서 계산합니다.
#    - 오늘/미래 날짜는 아직 집계 전이므로 선택할 수 없게 막습니다.
# ------------------------------------------------------------
def get_yesterday_kst() -> date:
    """한국 시간 기준으로 '어제' 날짜(date 객체)를 반환합니다."""
    now_kst = datetime.now(ZoneInfo("Asia/Seoul"))
    return (now_kst - timedelta(days=1)).date()


YESTERDAY_KST = get_yesterday_kst()
EARLIEST_DATE = date(2004, 1, 1)  # KOBIS 박스오피스 데이터가 존재하는 대략적인 시작 시점


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
#      정렬/그래프/계산에 쓰려면 숫자로 바꿔줘야 합니다.
#    - audiChange(전일 대비 관객수 증감 비율)는 소수점이 있을 수
#      있으므로 실수(float)로, 나머지는 정수(int 가능한 float)로 변환합니다.
# ------------------------------------------------------------
def convert_numeric_columns(df: pd.DataFrame) -> pd.DataFrame:
    int_cols = ["rank", "rankInten", "audiCnt", "audiInten", "audiAcc", "scrnCnt", "showCnt"]
    float_cols = ["audiChange"]

    for col in int_cols:
        if col in df.columns:
            # errors="coerce": 혹시 숫자로 못 바꾸는 값이 있으면 에러 대신 NaN 처리
            df[col] = pd.to_numeric(df[col], errors="coerce")

    for col in float_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


# ------------------------------------------------------------
# 5) 화면 타이틀
# ------------------------------------------------------------
st.title("🎬 박스오피스 대시보드")
st.caption("출처: 영화진흥위원회(KOBIS) 오픈API")

st.divider()


# ------------------------------------------------------------
# 6) 날짜 선택용 달력 (화면 중앙 위쪽에 배치)
#    - 좌우에 빈 컬럼을 두고 가운데 컬럼에만 달력을 넣어 중앙 정렬합니다.
# ------------------------------------------------------------
left_space, center_area, right_space = st.columns([1, 1.4, 1])

with center_area:
    st.markdown(
        "<h4 style='text-align:center; margin-bottom:0.3rem;'>📅 조회할 날짜를 선택하세요</h4>",
        unsafe_allow_html=True,
    )
    selected_date = st.date_input(
        label="조회 날짜",
        value=YESTERDAY_KST,
        min_value=EARLIEST_DATE,
        max_value=YESTERDAY_KST,       # 오늘/미래는 아직 집계 전이므로 선택 불가
        format="YYYY-MM-DD",
        label_visibility="collapsed",
    )
    st.markdown(
        "<p style='text-align:center; color:gray; font-size:0.85rem;'>"
        "※ 오늘 데이터는 아직 집계되지 않아 어제까지만 조회할 수 있어요."
        "</p>",
        unsafe_allow_html=True,
    )

st.divider()

target_dt = selected_date.strftime("%Y%m%d")
display_date = selected_date.strftime("%Y-%m-%d")


# ------------------------------------------------------------
# 7) 데이터 조회
# ------------------------------------------------------------
with st.spinner(f"{display_date} 박스오피스 데이터를 불러오는 중입니다..."):
    success, result = fetch_box_office(target_dt)

if not success:
    # 실패 또는 faultInfo 응답인 경우 -> 친절한 안내 메시지 표시
    st.error(f"😥 데이터를 불러오지 못했습니다.\n\n{result}")
    st.stop()  # 이후 코드는 실행하지 않고 여기서 중단

df = result
df = convert_numeric_columns(df)
df = df.sort_values("rank").reset_index(drop=True)

st.subheader(f"📌 {display_date} 박스오피스 현황")


# ------------------------------------------------------------
# 8) 1위 영화 지표 카드
# ------------------------------------------------------------
top_movie = df.iloc[0]

card_left, card_mid, card_right = st.columns(3)
card_left.metric(
    label=f"👑 1위  ·  {top_movie['movieNm']}",
    value=f"{int(top_movie['audiCnt']):,} 명",
    delta=f"{int(top_movie['audiInten']):,} 명 ({top_movie['audiChange']:+.1f}%)"
    if pd.notna(top_movie["audiInten"]) else None,
)
card_mid.metric(
    label="누적 관객수",
    value=f"{int(top_movie['audiAcc']):,} 명",
)
card_right.metric(
    label="스크린수",
    value=f"{int(top_movie['scrnCnt']):,} 개",
)

st.write("")


# ------------------------------------------------------------
# 9) 그래프: 관객수 상위 5편 막대그래프 (예쁘게 스타일링)
# ------------------------------------------------------------
st.subheader("📊 관객수 상위 5편")

top5_df = df.sort_values("audiCnt", ascending=False).head(5).copy()

fig = px.bar(
    top5_df,
    x="movieNm",
    y="audiCnt",
    text="audiCnt",
    labels={"movieNm": "", "audiCnt": "관객수(명)"},
    color="audiCnt",
    color_continuous_scale=["#FFD9DC", ACCENT_COLOR],
)
fig.update_traces(
    texttemplate="%{text:,}명",
    textposition="outside",
    marker_line_width=0,
)
fig.update_layout(
    showlegend=False,
    coloraxis_showscale=False,
    plot_bgcolor="rgba(0,0,0,0)",
    paper_bgcolor="rgba(0,0,0,0)",
    yaxis=dict(showgrid=True, gridcolor="rgba(0,0,0,0.08)", title="관객수(명)"),
    xaxis=dict(tickfont=dict(size=13)),
    margin=dict(t=30, b=10, l=10, r=10),
    font=dict(size=13),
)

st.plotly_chart(fig, use_container_width=True)

st.divider()


# ------------------------------------------------------------
# 10) 결과표: 순위 / 영화명 / 개봉일 / 관객수 / 전일 대비 증감(분·비율) / 누적관객수 / 스크린수
#     - audiInten(증감분), audiChange(증감비율)는 KOBIS가 이미 계산해서
#       내려주는 값이라 그대로 가져와 씁니다.
# ------------------------------------------------------------
st.subheader("📋 박스오피스 순위표")

table_df = df[
    ["rank", "movieNm", "openDt", "audiCnt", "audiInten", "audiChange", "audiAcc", "scrnCnt"]
].copy()

# 증감분/증감비율을 보기 좋은 문자열로 가공 (▲▼ 표시)
def format_change(inten, change_pct):
    if pd.isna(inten) or pd.isna(change_pct):
        return "-"
    arrow = "▲" if inten > 0 else ("▼" if inten < 0 else "―")
    return f"{arrow} {abs(int(inten)):,}명 ({change_pct:+.1f}%)"

table_df["전일 대비 증감"] = table_df.apply(
    lambda row: format_change(row["audiInten"], row["audiChange"]), axis=1
)

table_df = table_df.drop(columns=["audiInten", "audiChange"])
table_df = table_df[["rank", "movieNm", "openDt", "audiCnt", "전일 대비 증감", "audiAcc", "scrnCnt"]]
table_df.columns = ["순위", "영화명", "개봉일", "관객수(명)", "전일 대비 증감", "누적관객수(명)", "스크린수"]

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

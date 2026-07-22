import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

st.set_page_config(page_title="박스오피스 대시보드", layout="wide")
st.title("🎬 어제의 박스오피스")

KOBIS_KEY = st.secrets["KOBIS_KEY"]
# 한국 시간 기준 어제 (서버 시계가 외국 기준이어도 정확)
yesterday = (datetime.now(ZoneInfo("Asia/Seoul")) - timedelta(days=1)).strftime("%Y%m%d")

url = "http://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json"
response = requests.get(url, params={"key": KOBIS_KEY, "targetDt": yesterday})

# JSON 상자에서 영화 목록 꺼내기: boxOfficeResult → dailyBoxOfficeList
movies = response.json()["boxOfficeResult"]["dailyBoxOfficeList"]
df = pd.DataFrame(movies)

# 따옴표에 싸여 온 숫자들을 진짜 숫자로 바꾸기 (1절에서 본 함정!)
for col in ["rank", "audiCnt", "audiAcc", "scrnCnt"]:
    df[col] = pd.to_numeric(df[col])

# 1위 영화를 지표 카드 세 장으로
top = df.sort_values("rank").iloc[0]
col1, col2, col3 = st.columns(3)
col1.metric("어제 1위", top["movieNm"])
col2.metric("어제 관객수", f"{top['audiCnt']:,}명")
col3.metric("누적 관객", f"{top['audiAcc']:,}명")

# TOP 10 관객수 막대그래프
st.subheader("📊 TOP 10 관객수")
st.bar_chart(df.set_index("movieNm")["audiCnt"])

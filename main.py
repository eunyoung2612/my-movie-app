import streamlit as st
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

st.title("🎬 박스오피스 원본 JSON 보기")

KOBIS_KEY = st.secrets["KOBIS_KEY"]      # 금고에서 열쇠 꺼내기

# 한국 시간 기준 어제 날짜를 여덟 자리(예: 20260721)로 만들기
# (배포 서버의 시계는 외국 기준이라, 한국 시간을 콕 집어 줘야 함)
yesterday = (datetime.now(ZoneInfo("Asia/Seoul")) - timedelta(days=1)).strftime("%Y%m%d")

url = "http://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json"
response = requests.get(url, params={"key": KOBIS_KEY, "targetDt": yesterday})

st.write("상태코드:", response.status_code)
st.json(response.json())                 # 응답 JSON을 접었다 펼 수 있게 표시

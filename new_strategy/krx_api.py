import os
import time
import re
import requests
import pandas as pd
from datetime import datetime, timedelta

# =========================================================
# 설정
# =========================================================
KRX_ENDPOINT = "https://data-dbg.krx.co.kr/svc/apis/sto/stk_bydd_trd"
SAVE_DIR = "./Stock"  # 일별 파일 저장 폴더
FILE_PREFIX = "basic_"  # basic_YYYYMMDD.xlsx

# =========================================================
# [영문 -> 한글] 컬럼 매핑
# =========================================================
COLUMN_KR_MAP = {
    "BAS_DD": "일자",
    "basDd": "일자",

    "ISU_CD": "종목코드",
    "ISU_NM": "종목명",
    "MKT_NM": "시장구분",
    "SECT_TP_NM": "소속부",

    "TDD_CLSPRC": "종가",
    "CMPPREVDD_PRC": "대비",
    "FLUC_RT": "등락률",
    "TDD_OPNPRC": "시가",
    "TDD_HGPRC": "고가",
    "TDD_LWPRC": "저가",

    "ACC_TRDVOL": "거래량",
    "ACC_TRDVAL": "거래대금",

    "MKTCAP": "시가총액",
    "LIST_SHRS": "상장주식수",
}

FINAL_KR_COLUMNS = [
    "종목코드",
    "종목명",
    "종가",
    "대비",
    "등락률",
    "시가",
    "고가",
    "저가",
    "거래량",
    "거래대금",
    "시가총액",
    "상장주식수",
    "일자",
]

# =========================================================
# 숫자변환
# =========================================================
TEXT_COLS = ["종목코드", "일자"]
NUM_COLS = [
    "종가", "대비", "등락률", "시가", "고가", "저가",
    "거래량", "거래대금", "시가총액", "상장주식수"
]

def cast_excel_types(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # 텍스트 컬럼 고정
    for c in TEXT_COLS:
        if c in df.columns:
            df[c] = df[c].astype(str).str.strip()

    # 숫자 컬럼 변환
    for c in NUM_COLS:
        if c in df.columns:
            s = df[c].astype(str).str.replace(",", "", regex=False).str.strip()
            s = s.replace({"": None, "-": None, "nan": None, "None": None})
            df[c] = pd.to_numeric(s, errors="coerce")

    return df

# =========================================================
# 한글 컬럼 스키마 강제
# =========================================================
def to_korean_table(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns=COLUMN_KR_MAP)

    for col in FINAL_KR_COLUMNS:
        if col not in df.columns:
            df[col] = None

    df = df[FINAL_KR_COLUMNS]
    return df

# =========================================================
# 날짜 유틸
# =========================================================
def generate_dates(start: str, end: str):
    d0 = datetime.strptime(start, "%Y%m%d")
    d1 = datetime.strptime(end, "%Y%m%d")
    dates = []
    cur = d0
    while cur <= d1:
        if cur.weekday() < 5:  # 월~금만
            dates.append(cur.strftime("%Y%m%d"))
        cur += timedelta(days=1)
    return dates

def next_day_yyyymmdd(yyyymmdd: str) -> str:
    dt = datetime.strptime(yyyymmdd, "%Y%m%d") + timedelta(days=1)
    return dt.strftime("%Y%m%d")

# =========================================================
# ★ 핵심: 저장 폴더에서 마지막 파일 날짜 찾아 자동 start 계산
# =========================================================
def get_last_saved_date_from_files(save_dir):
    """
    ./Stock/basic_YYYYMMDD.xlsx 들 중 가장 큰 날짜를 찾아 반환.
    없으면 None.
    """
    if not os.path.exists(save_dir):
        return None

    pat = re.compile(rf"^{re.escape(FILE_PREFIX)}(\d{{8}})\.xlsx$", re.IGNORECASE)
    max_date = None

    for name in os.listdir(save_dir):
        m = pat.match(name)
        if not m:
            continue
        d = m.group(1)
        if max_date is None or d > max_date:
            max_date = d

    return max_date

def get_auto_start_for_daily_files(save_dir: str, fallback_start: str) -> str:
    last = get_last_saved_date_from_files(save_dir)
    if not last:
        return fallback_start
    return next_day_yyyymmdd(last)

# =========================================================
# 단일 날짜 조회 (★ 일자 중복 방지 포함)
# =========================================================
def fetch_one_day(basDd: str, auth_key: str, timeout: int = 20) -> pd.DataFrame:
    headers = {
        "AUTH_KEY": auth_key,
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0",
    }
    params = {"basDd": basDd}

    r = requests.get(KRX_ENDPOINT, headers=headers, params=params, timeout=timeout)
    r.raise_for_status()

    data = r.json()
    out = data.get("OutBlock_1", [])
    if not out:
        return pd.DataFrame()

    df = pd.json_normalize(out)

    # ✅ 응답에 BAS_DD가 없을 때만 보정 → '일자' 중복 방지
    if "BAS_DD" not in df.columns and "basDd" not in df.columns:
        df["basDd"] = basDd

    df = to_korean_table(df)
    df = cast_excel_types(df)
    return df

# =========================================================
# 일별 파일 생성 (자동 start 적용)
# =========================================================
def fetch_and_save_by_day_auto(
    auth_key,
    fallback_start="20260225",
    end=None,
    sleep_sec=0.4,
    retry=3,
):
    os.makedirs(SAVE_DIR, exist_ok=True)

    if end is None:
        end = datetime.today().strftime("%Y%m%d")

    # ✅ 파일 존재하면 자동 start(마지막 파일 다음날), 없으면 fallback_start
    start = get_auto_start_for_daily_files(SAVE_DIR, fallback_start)

    # start > end면 신규 생성 없음
    if start > end:
        print(f"✅ 이미 최신입니다. (start={start} > end={end})")
        return

    dates = generate_dates(start, end)
    print(f"📁 저장 폴더: {SAVE_DIR}")
    print(f"🚀 자동 생성 구간: {start} ~ {end} (영업일 {len(dates)}일)")

    for i, basDd in enumerate(dates, 1):
        file_path = os.path.join(SAVE_DIR, f"{FILE_PREFIX}{basDd}.xlsx")

        # 이미 파일 있으면 스킵(안전)
        if os.path.exists(file_path):
            print(f"[{i}/{len(dates)}] {basDd} ⏭ 이미 존재 → 스킵")
            continue

        print(f"[{i}/{len(dates)}] {basDd} 조회/저장 중...")

        for attempt in range(1, retry + 1):
            try:
                df = fetch_one_day(basDd, auth_key)

                if df.empty:
                    print("  ⚠ 데이터 없음 (휴일/미제공 가능)")
                else:
                    df.to_excel(file_path, index=False)
                    print(f"  💾 저장 완료 → {file_path}")

                break

            except Exception as e:
                print(f"  ⚠ 실패 ({attempt}/{retry}): {e}")
                if attempt == retry:
                    print(f"  ❌ {basDd} 최종 실패 (스킵)")
                else:
                    time.sleep(2)

        time.sleep(sleep_sec)

# =========================================================
# 실행
# =========================================================
if __name__ == "__main__":
    auth_key = "A85FD6442B6D45BFADFD66B9581B4A13C04C729A"

    fetch_and_save_by_day_auto(
        auth_key=auth_key,
        fallback_start="20260225",              # 파일이 없을 때 최초 시작일
        end=datetime.today().strftime("%Y%m%d"),
        sleep_sec=0.4,
        retry=3,
    )
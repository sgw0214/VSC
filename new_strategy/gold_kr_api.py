import os
import time
import requests
import pandas as pd
from datetime import datetime, timedelta

from new_strategy.paths import data_root

# =========================================================
# 설정
# =========================================================
KRX_ENDPOINT = "https://data-dbg.krx.co.kr/svc/apis/gen/gold_bydd_trd"

SAVE_DIR = str(data_root())
OUT_FILE = os.path.join(SAVE_DIR, "gold_kr_daily.xlsx")  # 1개 파일로 누적 저장

TARGET_ISU_CD = "04020000"  # 금 99.99K (필터 유지)

# =========================================================
# [영문 -> 한글] 컬럼 매핑
# =========================================================
COLUMN_KR_MAP = {
    "BAS_DD": "일자",
    "basDd": "일자",

    "ISU_CD": "종목코드",
    "ISU_NM": "종목명",

    "TDD_CLSPRC": "종가",
    "CMPPREVDD_PRC": "대비",
    "FLUC_RT": "등락률",
    "TDD_OPNPRC": "시가",
    "TDD_HGPRC": "고가",
    "TDD_LWPRC": "저가",

    "ACC_TRDVOL": "거래량",
    "ACC_TRDVAL": "거래대금",
}

# =========================================================
# 최종 저장 컬럼(엑셀 컬럼 순서)
# =========================================================
FINAL_KR_COLUMNS = [
    "종목코드",
    "종목명",
    "종가",
    "등락률",
    "거래량",
    "거래대금",
    "일자",
]

# =========================================================
# 타입 변환
# =========================================================
TEXT_COLS = ["종목코드", "일자"]
NUM_COLS = ["종가", "대비", "등락률", "거래량", "거래대금"]


def cast_excel_types(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # 텍스트 컬럼 고정(종목코드 0 유지)
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
# 날짜 정규화 (엑셀에서 읽을 때 타입이 섞여도 YYYYMMDD로 통일)
# =========================================================
def normalize_yyyymmdd(x) -> str:
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return ""

    if isinstance(x, (datetime, pd.Timestamp)):
        return x.strftime("%Y%m%d")

    s = str(x).strip()

    # 2026-02-25 / 2026.02.25 / 2026/02/25 -> 20260225
    s2 = s.replace("-", "").replace(".", "").replace("/", "")

    # "20260225.0" 처리
    if s2.endswith(".0"):
        s2 = s2[:-2]

    if len(s2) == 8 and s2.isdigit():
        return s2

    # 최후 파싱 시도
    try:
        dt = pd.to_datetime(s, errors="raise")
        return dt.strftime("%Y%m%d")
    except Exception:
        return ""


# =========================================================
# 한글 컬럼 스키마로 변환 + 필터 + 컬럼 순서 고정
# =========================================================
def to_korean_table(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns=COLUMN_KR_MAP)

    # 누락 컬럼 생성
    for col in FINAL_KR_COLUMNS:
        if col not in df.columns:
            df[col] = None

    # 컬럼 순서 고정
    df = df[FINAL_KR_COLUMNS]

    # 종목코드 필터(금 99.99K)
    if "종목코드" in df.columns:
        df = df[df["종목코드"].astype(str) == TARGET_ISU_CD]

    return df


# =========================================================
# 단일 날짜 조회 (★ 일자 중복 방지 로직 포함)
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

    # ✅ 핵심: 응답에 날짜가 없을 때만 basDd를 보정(중복 100% 방지)
    if "BAS_DD" not in df.columns and "basDd" not in df.columns:
        df["basDd"] = basDd

    df = to_korean_table(df)

    # 일자 정규화 + 타입 변환
    if "일자" in df.columns:
        df["일자"] = df["일자"].apply(normalize_yyyymmdd)

    df = cast_excel_types(df)

    return df


# =========================================================
# 날짜 범위 생성 (주말 제외)
# =========================================================
def generate_dates(start: str, end: str):
    d0 = datetime.strptime(start, "%Y%m%d")
    d1 = datetime.strptime(end, "%Y%m%d")

    dates = []
    cur = d0
    while cur <= d1:
        if cur.weekday() < 5:
            dates.append(cur.strftime("%Y%m%d"))
        cur += timedelta(days=1)
    return dates


# =========================================================
# 기존 파일 읽기
# =========================================================
def load_existing_excel(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        return pd.DataFrame(columns=FINAL_KR_COLUMNS)

    df = pd.read_excel(path, dtype=object)

    # 스키마 보정
    for col in FINAL_KR_COLUMNS:
        if col not in df.columns:
            df[col] = None
    df = df[FINAL_KR_COLUMNS]

    # 일자 정규화
    if "일자" in df.columns:
        df["일자"] = df["일자"].apply(normalize_yyyymmdd)

    df = cast_excel_types(df)
    df = df[df["일자"] != ""]
    return df


# =========================================================
# 파일이 있으면 자동 start 계산 (마지막 일자 + 1)
# =========================================================
def get_auto_start_from_file(path: str, fallback_start: str) -> str:
    if not os.path.exists(path):
        return fallback_start

    df = load_existing_excel(path)
    if df.empty:
        return fallback_start

    last = df["일자"].max()
    if not last:
        return fallback_start

    last_dt = datetime.strptime(last, "%Y%m%d")
    next_dt = last_dt + timedelta(days=1)
    return next_dt.strftime("%Y%m%d")


# =========================================================
# 매일 실행용: 기존 유지 + 신규만 추가 + 정렬 + 저장
# =========================================================
def update_gold_excel_daily(
    auth_key: str,
    fallback_start: str = "20160101",   # 파일 없을 때 최초 시작일
    end: str = None,                   # None이면 오늘
    sleep_sec: float = 0.4,
    retry: int = 3,
):
    os.makedirs(SAVE_DIR, exist_ok=True)

    if end is None:
        end = datetime.today().strftime("%Y%m%d")

    # ✅ 자동 start
    start = get_auto_start_from_file(OUT_FILE, fallback_start=fallback_start)

    # start > end면 신규 없음
    if start > end:
        print(f"✅ 이미 최신입니다. (start={start} > end={end})")
        return

    existing = load_existing_excel(OUT_FILE)

    dates = generate_dates(start, end)
    print(f"📌 파일: {OUT_FILE}")
    print(f"🚀 자동 수집 구간: {start} ~ {end} (영업일 {len(dates)}일)")

    new_rows = []

    for i, basDd in enumerate(dates, 1):
        print(f"[{i}/{len(dates)}] {basDd} 조회 중...")

        for attempt in range(1, retry + 1):
            try:
                df = fetch_one_day(basDd, auth_key)

                if df.empty:
                    print("  ⚠ 데이터 없음 (휴일/미제공 가능)")
                else:
                    new_rows.append(df)
                    print(f"  ✅ 추가 예정 rows={len(df)}")

                break

            except Exception as e:
                print(f"  ⚠ 실패 ({attempt}/{retry}): {e}")
                if attempt == retry:
                    print(f"  ❌ {basDd} 최종 실패 (스킵)")
                else:
                    time.sleep(2)

        time.sleep(sleep_sec)

    if not new_rows:
        print("✅ 신규로 추가할 데이터가 없습니다.")
        return

    new_data = pd.concat(new_rows, ignore_index=True)

    merged = pd.concat([existing, new_data], ignore_index=True)

    # 중복 제거(신규 우선)
    merged["일자"] = merged["일자"].apply(normalize_yyyymmdd)
    merged["종목코드"] = merged["종목코드"].astype(str).str.strip()
    merged = merged.drop_duplicates(subset=["일자", "종목코드"], keep="last")

    # 정렬
    merged = merged.sort_values(["일자", "종목코드"], ascending=[True, True])

    # 저장
    merged = merged[FINAL_KR_COLUMNS]
    merged.to_excel(OUT_FILE, index=False)

    print(f"💾 업데이트 완료 → {OUT_FILE} (총 rows={len(merged)})")


# =========================================================
# 실행
# =========================================================
if __name__ == "__main__":
    auth_key = "A85FD6442B6D45BFADFD66B9581B4A13C04C729A"

    update_gold_excel_daily(
        auth_key=auth_key,
        fallback_start="20260101",                # 파일 없을 때만 사용
        end=datetime.today().strftime("%Y%m%d"),  # 보통 오늘
        sleep_sec=0.4,
        retry=3,
    )

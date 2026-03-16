import argparse
import io
import os
import re
import time
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from new_strategy.paths import data_path


CORP_CODE_URL = "https://opendart.fss.or.kr/api/corpCode.xml"
FNLTT_URL = "https://opendart.fss.or.kr/api/fnlttMultiAcnt.json"
REPORT_CODES = ["11013", "11012", "11014", "11011"]
REPORT_LABEL = {"11013": "Q1", "11012": "H1", "11014": "Q3", "11011": "Y"}
REPORT_ORDER = {code: idx for idx, code in enumerate(REPORT_CODES)}

COL_ALIASES = {
    "code": ["code", "종목코드"],
    "corp_code": ["corp_code", "법인코드"],
    "corp_name": ["corp_name", "법인명"],
    "bsns_year": ["bsns_year", "사업연도"],
    "reprt_code": ["reprt_code", "보고서코드"],
    "rcept_no": ["rcept_no", "접수번호"],
    "rcept_dt": ["rcept_dt", "공시일"],
    "revenue": ["revenue", "매출액"],
    "op_income": ["op_income", "영업이익"],
    "net_income": ["net_income", "당기순이익"],
    "total_assets": ["total_assets", "자산총계"],
    "total_equity": ["total_equity", "자본총계"],
    "total_liab": ["total_liab", "부채총계"],
    "period": ["period", "기간"],
    "op_margin": ["op_margin", "영업이익률"],
    "roe_simple": ["roe_simple", "ROE(단순)"],
    "quarter_revenue": ["quarter_revenue", "분기매출액"],
    "quarter_op_income": ["quarter_op_income", "분기영업이익"],
    "quarter_net_income": ["quarter_net_income", "분기당기순이익"],
    "quarter_op_margin": ["quarter_op_margin", "분기영업이익률"],
    "quarter_roe_simple": ["quarter_roe_simple", "분기ROE(단순)"],
}

KR_COLS = {
    "code": "종목코드",
    "corp_code": "법인코드",
    "corp_name": "법인명",
    "bsns_year": "사업연도",
    "reprt_code": "보고서코드",
    "rcept_no": "접수번호",
    "rcept_dt": "공시일",
    "revenue": "매출액",
    "op_income": "영업이익",
    "net_income": "당기순이익",
    "total_assets": "자산총계",
    "total_equity": "자본총계",
    "total_liab": "부채총계",
    "period": "기간",
    "op_margin": "영업이익률",
    "roe_simple": "ROE(단순)",
    "quarter_revenue": "분기매출액",
    "quarter_op_income": "분기영업이익",
    "quarter_net_income": "분기당기순이익",
    "quarter_op_margin": "분기영업이익률",
    "quarter_roe_simple": "분기ROE(단순)",
}


def _norm_reprt_code(x: object) -> str:
    s = str(x).strip()
    m = re.search(r"(\d{5})", s)
    if m:
        return m.group(1)
    digits = re.sub(r"\D", "", s)
    return digits[:5] if len(digits) >= 5 else s


def _norm_corp_code(x: object) -> str:
    if pd.isna(x):
        return ""
    s = str(x).strip()
    if not s:
        return ""
    if s.endswith(".0"):
        s = s[:-2]
    try:
        s = str(int(float(s)))
    except Exception:
        pass
    return s.zfill(8)


def _to_english_cols(df: pd.DataFrame) -> pd.DataFrame:
    ren = {}
    for eng, aliases in COL_ALIASES.items():
        for a in aliases:
            if a in df.columns:
                ren[a] = eng
                break
    return df.rename(columns=ren).copy()


def _to_num(x: object) -> Optional[float]:
    if x is None:
        return None
    s = str(x).strip().replace(",", "")
    if s in ("", "-", "nan", "None"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _pick_metric_key(account_id: str, account_nm: str) -> Optional[str]:
    aid = (account_id or "").lower()
    anm = (account_nm or "").strip()

    if "ifrs-full_revenue" in aid or "매출" in anm or "영업수익" in anm:
        return "revenue"
    if "operatingprofitloss" in aid or "영업이익" in anm:
        return "op_income"
    if "profitloss" in aid or "당기순이익" in anm:
        return "net_income"
    if ("assets" in aid and "total" in aid) or "자산총계" in anm:
        return "total_assets"
    if ("liabilities" in aid and "total" in aid) or "부채총계" in anm:
        return "total_liab"
    if ("equity" in aid and "total" in aid) or "자본총계" in anm:
        return "total_equity"
    return None


def _norm_name(name: object) -> str:
    return str(name or "").strip().upper().replace(" ", "")


def _base_name_for_preferred(name: object) -> str:
    s = _norm_name(name)
    return re.sub(r"(?:\d+)?우(?:[A-Z])?$", "", s)


def _make_session() -> requests.Session:
    s = requests.Session()
    # Hidden adapter retries can violate external rate caps.
    # Keep retries at 0 so one function call equals one HTTP call.
    retry = Retry(total=0, connect=0, read=0, redirect=0, status=0, raise_on_status=False)
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    return s


def _enforce_rate_limit(call_times: List[float], rpm: int) -> None:
    if rpm <= 0:
        return
    now = time.time()
    window_start = now - 60.0
    call_times[:] = [t for t in call_times if t >= window_start]
    if len(call_times) >= rpm:
        sleep_for = 60.0 - (now - call_times[0]) + 0.01
        if sleep_for > 0:
            time.sleep(sleep_for)
        now = time.time()
        window_start = now - 60.0
        call_times[:] = [t for t in call_times if t >= window_start]
    call_times.append(time.time())


def load_universe(price_panel: Path, max_codes: int = 0) -> pd.DataFrame:
    df = pd.read_csv(price_panel, usecols=["code", "name"], low_memory=False, dtype={"code": str})
    df["code"] = df["code"].astype(str).str.zfill(6)
    df["name"] = df["name"].astype(str).str.strip()
    uni = df.drop_duplicates(subset=["code"], keep="last").sort_values("code").reset_index(drop=True)
    if max_codes > 0:
        uni = uni.head(max_codes).copy()
    return uni


def fetch_corp_codes(api_key: str, session: requests.Session, timeout: int = 30) -> pd.DataFrame:
    r = session.get(CORP_CODE_URL, params={"crtfc_key": api_key}, timeout=timeout)
    r.raise_for_status()

    zf = zipfile.ZipFile(io.BytesIO(r.content))
    with zf.open("CORPCODE.xml") as fp:
        xml_bytes = fp.read()

    root = ET.fromstring(xml_bytes)
    rows = []
    for node in root.findall("list"):
        corp_code = (node.findtext("corp_code") or "").strip()
        corp_name = (node.findtext("corp_name") or "").strip()
        stock_code = (node.findtext("stock_code") or "").strip()
        modify_date = (node.findtext("modify_date") or "").strip()
        if stock_code:
            rows.append(
                {
                    "corp_code": corp_code,
                    "corp_name": corp_name,
                    "stock_code": stock_code,
                    "modify_date": modify_date,
                }
            )
    if not rows:
        raise RuntimeError("No rows parsed from DART corp code XML.")
    return pd.DataFrame(rows)


def build_code_corp_mapping(corp_df: pd.DataFrame, universe: pd.DataFrame) -> pd.DataFrame:
    c = corp_df.copy()
    c["stock_code"] = c["stock_code"].astype(str).str.zfill(6)
    c["corp_name_norm"] = c["corp_name"].map(_norm_name)
    c = c.drop_duplicates(subset=["stock_code"], keep="last")

    u = universe.copy()
    u["code"] = u["code"].astype(str).str.zfill(6)
    u["name_norm"] = u["name"].map(_norm_name)
    u["base_name_norm"] = u["name"].map(_base_name_for_preferred)

    direct = u.merge(
        c[["stock_code", "corp_code", "corp_name"]],
        left_on="code",
        right_on="stock_code",
        how="left",
    )
    direct["map_method"] = direct["corp_code"].notna().map({True: "direct_stock_code", False: ""})

    unresolved = direct["corp_code"].isna()
    if unresolved.any():
        base_to_corp = (
            direct[direct["corp_code"].notna()]
            .groupby("base_name_norm", as_index=False)[["corp_code", "corp_name"]]
            .first()
        )
        base_to_corp = {r.base_name_norm: (r.corp_code, r.corp_name) for r in base_to_corp.itertuples(index=False)}
        corp_name_map = {r.corp_name_norm: (r.corp_code, r.corp_name) for r in c.itertuples(index=False)}

        idx = direct[unresolved].index
        mapped_code = []
        mapped_name = []
        mapped_method = []
        for r in direct.loc[idx].itertuples(index=False):
            v = base_to_corp.get(r.base_name_norm)
            m = "preferred_base_to_common"
            if v is None:
                v = corp_name_map.get(r.base_name_norm)
                m = "preferred_base_to_corp_name"
            if v is None:
                mapped_code.append(None)
                mapped_name.append(None)
                mapped_method.append("")
            else:
                mapped_code.append(v[0])
                mapped_name.append(v[1])
                mapped_method.append(m)

        direct.loc[idx, "corp_code"] = mapped_code
        direct.loc[idx, "corp_name"] = mapped_name
        direct.loc[idx, "map_method"] = mapped_method

    return direct[["code", "name", "corp_code", "corp_name", "map_method"]].copy()


def fetch_one_statement(
    api_key: str,
    corp_code: str,
    bsns_year: int,
    reprt_code: str,
    session: requests.Session,
    fs_div: str = "CFS",
    timeout: int = 30,
) -> pd.DataFrame:
    params = {
        "crtfc_key": api_key,
        "corp_code": corp_code,
        "bsns_year": str(bsns_year),
        "reprt_code": reprt_code,
        "fs_div": fs_div,
    }
    r = session.get(FNLTT_URL, params=params, timeout=timeout)
    r.raise_for_status()
    j = r.json()

    status = j.get("status")
    if status in ("013", "020", "021", "100"):
        return pd.DataFrame()
    if status != "000":
        raise RuntimeError(f"DART error status={status}, message={j.get('message')}")

    items = j.get("list", [])
    if not items:
        return pd.DataFrame()
    return pd.DataFrame(items)


def _iter_targets(
    code_map: pd.DataFrame,
    stock_codes: Iterable[str],
    start_year: int,
    end_year: int,
    report_codes: Optional[List[str]] = None,
    existing_corp_keys: Optional[Set[Tuple[str, int, str]]] = None,
    max_requests: int = 0,
) -> Iterable[Dict[str, object]]:
    # Request once per (corp_code, year, report), then fan out to all mapped stock codes.
    stock_set = set(stock_codes)
    base = code_map[code_map["code"].isin(stock_set) & code_map["corp_code"].notna()][
        ["code", "corp_code", "corp_name"]
    ].copy()
    base["corp_code"] = base["corp_code"].map(_norm_corp_code)
    corp_groups = (
        base.groupby(["corp_code", "corp_name"], as_index=False)
        .agg(codes=("code", lambda s: sorted(pd.unique(s.astype(str).str.zfill(6)))))
    )
    report_codes = report_codes or REPORT_CODES

    emitted = 0
    for r in corp_groups.itertuples(index=False):
        for year in range(start_year, end_year + 1):
            for reprt_code in report_codes:
                key = (_norm_corp_code(r.corp_code), int(year), str(reprt_code))
                if existing_corp_keys and key in existing_corp_keys:
                    continue
                if max_requests and emitted >= max_requests:
                    return
                emitted += 1
                yield {
                    "corp_code": _norm_corp_code(r.corp_code),
                    "corp_name": str(r.corp_name),
                    "codes": list(r.codes),
                    "bsns_year": year,
                    "reprt_code": reprt_code,
                }


def build_quarterly(raw_df: pd.DataFrame) -> pd.DataFrame:
    if raw_df.empty:
        return pd.DataFrame()

    work = raw_df.copy()
    # fnlttMultiAcnt responses can omit account_id for some filings.
    if "account_id" not in work.columns:
        work["account_id"] = ""
    if "account_nm" not in work.columns:
        work["account_nm"] = ""
    work["amount"] = work["thstrm_amount"].apply(_to_num)
    work["amount_add"] = work.get("thstrm_add_amount", pd.Series(index=work.index, dtype=object)).apply(_to_num)
    work["metric"] = [_pick_metric_key(aid, anm) for aid, anm in zip(work["account_id"], work["account_nm"])]
    work = work[work["metric"].notna()].copy()
    if work.empty:
        return pd.DataFrame()

    work["reprt_code"] = work["reprt_code"].map(_norm_reprt_code)
    work = work.sort_values(["code", "bsns_year", "reprt_code", "metric", "ord"], ascending=True)

    pick = (
        work.groupby(
            ["code", "corp_code", "corp_name", "bsns_year", "reprt_code", "rcept_no", "rcept_dt", "metric"],
            as_index=False,
        )
        .first()[
            [
                "code",
                "corp_code",
                "corp_name",
                "bsns_year",
                "reprt_code",
                "rcept_no",
                "rcept_dt",
                "metric",
                "amount",
                "amount_add",
            ]
        ]
    )

    out = pick.pivot_table(
        index=["code", "corp_code", "corp_name", "bsns_year", "reprt_code", "rcept_no", "rcept_dt"],
        columns="metric",
        values="amount",
        aggfunc="first",
    ).reset_index()
    out.columns.name = None
    out_add = pick.pivot_table(
        index=["code", "corp_code", "corp_name", "bsns_year", "reprt_code", "rcept_no", "rcept_dt"],
        columns="metric",
        values="amount_add",
        aggfunc="first",
    ).reset_index()
    out_add.columns.name = None
    out_add = out_add.rename(
        columns={
            "revenue": "revenue_add",
            "op_income": "op_income_add",
            "net_income": "net_income_add",
        }
    )
    for col in ["revenue_add", "op_income_add", "net_income_add"]:
        if col not in out_add.columns:
            out_add[col] = pd.NA
    out = out.merge(
        out_add[
            [
                "code",
                "corp_code",
                "corp_name",
                "bsns_year",
                "reprt_code",
                "rcept_no",
                "rcept_dt",
                "revenue_add",
                "op_income_add",
                "net_income_add",
            ]
        ],
        on=["code", "corp_code", "corp_name", "bsns_year", "reprt_code", "rcept_no", "rcept_dt"],
        how="left",
    )
    out["period"] = out["bsns_year"].astype(str) + "-" + out["reprt_code"].map(REPORT_LABEL).fillna(out["reprt_code"])
    out["op_margin"] = out["op_income"] / out["revenue"]
    out["roe_simple"] = out["net_income"] / out["total_equity"]
    out["_report_order"] = out["reprt_code"].map(REPORT_ORDER).fillna(999)
    out = out.sort_values(["code", "bsns_year", "_report_order"]).reset_index(drop=True)

    for quarter_col, src_col in [
        ("quarter_revenue", "revenue"),
        ("quarter_op_income", "op_income"),
        ("quarter_net_income", "net_income"),
    ]:
        out[quarter_col] = out[src_col]

    group_keys = ["code", "bsns_year"]
    q1_mask = out["reprt_code"].eq("11013")
    h1_mask = out["reprt_code"].eq("11012")
    q3_mask = out["reprt_code"].eq("11014")
    y_mask = out["reprt_code"].eq("11011")

    group_index = pd.MultiIndex.from_frame(out[group_keys])
    for quarter_col, src_col, add_col in [
        ("quarter_revenue", "revenue", "revenue_add"),
        ("quarter_op_income", "op_income", "op_income_add"),
        ("quarter_net_income", "net_income", "net_income_add"),
    ]:
        q3_add_lookup = (
            out.loc[q3_mask, group_keys + [add_col]]
            .drop_duplicates(group_keys)
            .set_index(group_keys)[add_col]
        )
        out.loc[q1_mask, quarter_col] = out.loc[q1_mask, src_col]
        out.loc[h1_mask, quarter_col] = out.loc[h1_mask, src_col]
        out.loc[q3_mask, quarter_col] = out.loc[q3_mask, src_col]
        out.loc[y_mask, quarter_col] = out.loc[y_mask, src_col].to_numpy() - q3_add_lookup.reindex(group_index[y_mask]).to_numpy()

    out["quarter_op_margin"] = out["quarter_op_income"] / out["quarter_revenue"]
    out["quarter_roe_simple"] = out["quarter_net_income"] / out["total_equity"]
    out = out.drop(columns=["_report_order", "revenue_add", "op_income_add", "net_income_add"])
    return out


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Fetch quarterly fundamentals from DART OpenAPI.")
    p.add_argument("--api-key", default="", help="DART API key (or use DART_API_KEY env)")
    p.add_argument("--price-panel", default=str(data_path("price_panel.csv")))
    p.add_argument("--codes", default="", help="Comma-separated stock codes. If set, ignore price-panel universe.")
    p.add_argument("--max-codes", type=int, default=0, help="Limit number of codes for test runs.")
    p.add_argument("--start-year", type=int, default=2015)
    p.add_argument("--end-year", type=int, default=2026)
    p.add_argument("--sleep-sec", type=float, default=0.0, help="Extra sleep after each successful request.")
    p.add_argument("--rpm", type=int, default=90, help="Max requests per minute to DART.")
    p.add_argument("--max-requests", type=int, default=38000, help="Hard cap to avoid DART daily call limit.")
    p.add_argument("--no-skip-existing", action="store_true", help="Do not skip code/year/report already in output.")
    p.add_argument(
        "--ignore-skip-keys",
        action="store_true",
        help="Requery matching year/report targets even if they were previously logged.",
    )
    p.add_argument(
        "--report-codes",
        default="",
        help="Comma-separated report codes to fetch. Default is all report codes.",
    )
    p.add_argument("--raw-output", default=str(data_path("fundamental_quarterly_raw_retry.csv")))
    p.add_argument("--output", default=str(data_path("fundamental_quarterly_multi.csv")))
    p.add_argument("--corp-map-cache", default=str(data_path("dart_corp_codes.csv")))
    p.add_argument("--no-korean-columns", action="store_true", help="Save output with English columns.")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    api_key = (args.api_key or os.getenv("DART_API_KEY", "")).strip()
    if not api_key:
        raise RuntimeError("Set DART_API_KEY env var or pass --api-key.")
    report_codes = [_norm_reprt_code(x) for x in args.report_codes.split(",") if str(x).strip()]
    report_codes = [x for x in report_codes if x]
    if not report_codes:
        report_codes = REPORT_CODES.copy()

    if args.codes.strip():
        stock_codes = [x.strip().zfill(6) for x in args.codes.split(",") if x.strip()]
        if args.max_codes > 0:
            stock_codes = stock_codes[: args.max_codes]
        universe = pd.DataFrame({"code": stock_codes, "name": stock_codes})
    else:
        universe = load_universe(Path(args.price_panel), max_codes=args.max_codes)
        stock_codes = universe["code"].tolist()

    sess = _make_session()
    cache_path = Path(args.corp_map_cache)
    # Per requirement: stop immediately if DART connection fails.
    corp_df = fetch_corp_codes(api_key=api_key, session=sess)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    corp_df.to_csv(cache_path, index=False, encoding="utf-8-sig")
    print(f"[saved] corp map cache: {cache_path} rows={len(corp_df):,}")

    code_map = build_code_corp_mapping(corp_df, universe)

    mapped = int(code_map["corp_code"].notna().sum())
    print(f"[corp-map] rows={len(corp_df):,}, universe_codes={len(stock_codes):,}, mapped={mapped:,}")
    for k, v in code_map["map_method"].value_counts().items():
        if str(k).strip():
            print(f"[corp-map-method] {k}: {int(v):,}")

    existing_corp_keys: Set[Tuple[str, int, str]] = set()
    out_path = Path(args.output)
    raw_out = Path(args.raw_output)
    request_log_path = out_path.with_name(f"{out_path.stem}_request_log.csv")
    if (not args.no_skip_existing) and (not args.ignore_skip_keys) and out_path.exists():
        prev = _to_english_cols(pd.read_csv(out_path, low_memory=False))
        if {"corp_code", "bsns_year", "reprt_code"}.issubset(set(prev.columns)):
            prev["corp_code"] = prev["corp_code"].map(_norm_corp_code)
            prev["bsns_year"] = pd.to_numeric(prev["bsns_year"], errors="coerce").astype("Int64")
            prev["reprt_code"] = prev["reprt_code"].map(_norm_reprt_code)
            prev = prev.dropna(subset=["corp_code", "bsns_year", "reprt_code"])
            existing_corp_keys = set(zip(prev["corp_code"], prev["bsns_year"].astype(int), prev["reprt_code"]))
    # Also skip already-requested corp/year/report keys seen in raw responses.
    # This prevents retrying the same calls when a filing has no mapped metrics.
    if (not args.no_skip_existing) and (not args.ignore_skip_keys) and raw_out.exists():
        try:
            prev_raw = pd.read_csv(raw_out, low_memory=False)
            if {"corp_code", "bsns_year", "reprt_code"}.issubset(set(prev_raw.columns)):
                prev_raw["corp_code"] = prev_raw["corp_code"].map(_norm_corp_code)
                prev_raw["bsns_year"] = pd.to_numeric(prev_raw["bsns_year"], errors="coerce").astype("Int64")
                prev_raw["reprt_code"] = prev_raw["reprt_code"].map(_norm_reprt_code)
                prev_raw = prev_raw.dropna(subset=["corp_code", "bsns_year", "reprt_code"])
                existing_corp_keys |= set(
                    zip(prev_raw["corp_code"], prev_raw["bsns_year"].astype(int), prev_raw["reprt_code"])
                )
        except Exception as exc:
            print(f"[warn] raw skip-key load failed: {exc}")
    # Skip keys that were already requested previously, including empty responses.
    if (not args.no_skip_existing) and (not args.ignore_skip_keys) and request_log_path.exists():
        try:
            prev_log = pd.read_csv(request_log_path, low_memory=False)
            if {"corp_code", "bsns_year", "reprt_code"}.issubset(set(prev_log.columns)):
                prev_log["corp_code"] = prev_log["corp_code"].map(_norm_corp_code)
                prev_log["bsns_year"] = pd.to_numeric(prev_log["bsns_year"], errors="coerce").astype("Int64")
                prev_log["reprt_code"] = prev_log["reprt_code"].map(_norm_reprt_code)
                prev_log = prev_log.dropna(subset=["corp_code", "bsns_year", "reprt_code"])
                existing_corp_keys |= set(
                    zip(prev_log["corp_code"], prev_log["bsns_year"].astype(int), prev_log["reprt_code"])
                )
        except Exception as exc:
            print(f"[warn] request-log load failed: {exc}")

    n_corps = int(code_map.loc[code_map["corp_code"].notna(), "corp_code"].map(_norm_corp_code).nunique())
    total_candidate = n_corps * (args.end_year - args.start_year + 1) * len(report_codes)
    to_request_est = max(0, total_candidate - len(existing_corp_keys))
    if args.max_requests and to_request_est > args.max_requests:
        print(f"[plan] estimated_requests={to_request_est:,} exceeds cap={args.max_requests:,}; capped.")
    else:
        print(f"[plan] estimated_requests={to_request_est:,}, existing_skipped={len(existing_corp_keys):,}")

    rows = []
    completed_keys: Set[Tuple[str, int, str]] = set()
    done = 0
    call_times: List[float] = []
    for t in _iter_targets(
        code_map,
        stock_codes,
        args.start_year,
        args.end_year,
        report_codes=report_codes,
        existing_corp_keys=existing_corp_keys,
        max_requests=args.max_requests,
    ):
        done += 1
        if done % 500 == 0:
            print(f"[progress] requests={done:,}, rows={len(rows):,}")

        try:
            _enforce_rate_limit(call_times, args.rpm)
            one = fetch_one_statement(
                api_key=api_key,
                corp_code=t["corp_code"],
                bsns_year=t["bsns_year"],
                reprt_code=t["reprt_code"],
                session=sess,
                fs_div="CFS",
            )
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            raise RuntimeError(
                f"DART connection failed; stopped at corp={t['corp_code']} year={t['bsns_year']} reprt={t['reprt_code']}: {e}"
            )
        except Exception as e:
            print(f"[warn] corp={t['corp_code']} year={t['bsns_year']} reprt={t['reprt_code']} err={e}")
            time.sleep(max(args.sleep_sec, 0.1))
            continue

        completed_keys.add((_norm_corp_code(t["corp_code"]), int(t["bsns_year"]), str(t["reprt_code"])))
        if one.empty:
            if args.sleep_sec > 0:
                time.sleep(args.sleep_sec)
            continue

        one["rcept_dt"] = pd.to_datetime(
            one.get("rcept_no", pd.Series(index=one.index, dtype=object)).astype(str).str[:8],
            format="%Y%m%d",
            errors="coerce",
        ).dt.strftime("%Y-%m-%d")
        one["corp_code"] = t["corp_code"]
        one["corp_name"] = t["corp_name"]
        one["bsns_year"] = t["bsns_year"]
        one["reprt_code"] = t["reprt_code"]
        for code in t["codes"]:
            copy_df = one.copy()
            copy_df["code"] = str(code).zfill(6)
            rows.append(copy_df)
        if args.sleep_sec > 0:
            time.sleep(args.sleep_sec)

    raw_df_new = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    raw_out.parent.mkdir(parents=True, exist_ok=True)
    if (not args.no_skip_existing) and raw_out.exists():
        try:
            raw_prev = pd.read_csv(raw_out, low_memory=False)
            raw_df = pd.concat([raw_prev, raw_df_new], ignore_index=True, sort=False).drop_duplicates()
        except Exception:
            raw_df = raw_df_new
    else:
        raw_df = raw_df_new
    raw_df.to_csv(raw_out, index=False, encoding="utf-8-sig")
    print(f"[saved] {raw_out} rows={len(raw_df):,} (new={len(raw_df_new):,})")
    # Persist request log so empty-response keys are not requested again.
    if completed_keys:
        log_new = pd.DataFrame(
            [{"corp_code": k[0], "bsns_year": k[1], "reprt_code": k[2]} for k in sorted(completed_keys)]
        )
        if (not args.no_skip_existing) and request_log_path.exists():
            try:
                log_prev = pd.read_csv(request_log_path, low_memory=False)
                log_all = pd.concat([log_prev, log_new], ignore_index=True, sort=False).drop_duplicates()
            except Exception:
                log_all = log_new
        else:
            log_all = log_new
        log_all.to_csv(request_log_path, index=False, encoding="utf-8-sig")
        print(f"[saved] {request_log_path} rows={len(log_all):,} (new={len(log_new):,})")

    q_df_new = build_quarterly(raw_df_new)

    if (not args.no_skip_existing) and out_path.exists():
        q_prev = _to_english_cols(pd.read_csv(out_path, low_memory=False))
        q_df = pd.concat([q_prev, q_df_new], ignore_index=True, sort=False)
    else:
        q_df = q_df_new

    if not q_df.empty:
        q_df["code"] = q_df["code"].astype(str).str.zfill(6)
        q_df["bsns_year"] = pd.to_numeric(q_df["bsns_year"], errors="coerce")
        q_df["reprt_code"] = q_df["reprt_code"].map(_norm_reprt_code)
        q_df = q_df.sort_values(["code", "bsns_year", "reprt_code", "rcept_no"]).drop_duplicates(
            subset=["code", "bsns_year", "reprt_code"], keep="last"
        )
        q_df = q_df.reset_index(drop=True)

    save_df = q_df if args.no_korean_columns else q_df.rename(columns=KR_COLS)
    try:
        save_df.to_csv(out_path, index=False, encoding="utf-8-sig")
        print(f"[saved] {out_path} rows={len(q_df):,}")
    except PermissionError as exc:
        alt = out_path.with_name(f"{out_path.stem}.updated_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
        save_df.to_csv(alt, index=False, encoding="utf-8-sig")
        print(f"[warn] target locked: {exc}")
        print(f"[saved] {alt} rows={len(q_df):,}")


if __name__ == "__main__":
    main()

import argparse
from pathlib import Path

import pandas as pd

from new_strategy.paths import data_path


COL_ALIASES = {
    "code": ["code", "종목코드"],
    "name": ["name", "종목명"],
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
    "has_fundamental": ["has_fundamental", "실적보유"],
    "missing_reason": ["missing_reason", "누락사유"],
}

KR_COLS = {
    "code": "종목코드",
    "name": "종목명",
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
    "op_margin": "영업이익률",
    "roe_simple": "ROE(단순)",
    "has_fundamental": "실적보유",
    "missing_reason": "누락사유",
    "corp_member_count": "동일법인종목수",
    "corp_member_codes": "동일법인종목코드",
    "corp_member_names": "동일법인종목명",
}


def _to_eng_cols(df: pd.DataFrame) -> pd.DataFrame:
    ren = {}
    for eng, aliases in COL_ALIASES.items():
        for a in aliases:
            if a in df.columns:
                ren[a] = eng
                break
    return df.rename(columns=ren).copy()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build all-KOSPI fundamental snapshot from current dataset.")
    p.add_argument("--price-panel", default=str(data_path("price_panel.csv")))
    p.add_argument("--fundamental", default=str(data_path("fundamental_quarterly_multi.csv")))
    p.add_argument("--asof", default="2026-02-23")
    p.add_argument("--snapshot-output", default=str(data_path("fundamental_universe_snapshot.csv")))
    p.add_argument("--missing-output", default=str(data_path("fundamental_missing_codes.csv")))
    p.add_argument("--coverage-output", default=str(data_path("fundamental_coverage_report.csv")))
    p.add_argument("--no-korean-columns", action="store_true")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    asof = pd.Timestamp(args.asof)

    price = pd.read_csv(args.price_panel, usecols=["code", "name"], low_memory=False, dtype={"code": str})
    price["code"] = price["code"].astype(str).str.zfill(6)
    price["name"] = price["name"].astype(str)
    universe = price.drop_duplicates("code", keep="last").sort_values("code").reset_index(drop=True)

    fund = pd.read_csv(args.fundamental, low_memory=False)
    fund = _to_eng_cols(fund)
    need = [
        "code", "corp_code", "corp_name", "bsns_year", "reprt_code", "rcept_no", "rcept_dt",
        "revenue", "op_income", "net_income", "total_assets", "total_equity", "total_liab", "op_margin", "roe_simple",
    ]
    for c in need:
        if c not in fund.columns:
            fund[c] = pd.NA

    fund["code"] = fund["code"].astype(str).str.zfill(6)
    fund["rcept_dt"] = pd.to_datetime(fund["rcept_dt"], errors="coerce")
    fund["bsns_year"] = pd.to_numeric(fund["bsns_year"], errors="coerce")
    fund["reprt_code"] = fund["reprt_code"].astype(str)

    available = fund[fund["rcept_dt"].notna() & (fund["rcept_dt"] <= asof)].copy()
    latest = available.sort_values(["code", "rcept_dt", "bsns_year", "reprt_code"]).groupby("code", as_index=False).tail(1)
    latest = latest.drop_duplicates("code", keep="last")

    snap = universe.merge(latest[need], on="code", how="left")

    # Corp-level membership map for duplicated/common shares (e.g., common/preferred).
    members = snap[snap["corp_code"].notna()][["corp_code", "code", "name"]].copy()
    members["corp_code"] = members["corp_code"].astype(str).str.strip()
    corp_codes_map = (
        members.groupby("corp_code")["code"]
        .apply(lambda s: "|".join(sorted(pd.unique(s.astype(str).str.zfill(6)))))
        .to_dict()
    )
    corp_names_map = (
        members.groupby("corp_code")["name"]
        .apply(lambda s: "|".join(sorted(pd.unique(s.astype(str)))))
        .to_dict()
    )
    corp_count_map = (
        members.groupby("corp_code")["code"]
        .apply(lambda s: int(pd.unique(s.astype(str).str.zfill(6)).size))
        .to_dict()
    )

    snap["corp_code"] = snap["corp_code"].astype(str).str.strip()
    snap["corp_member_count"] = snap["corp_code"].map(corp_count_map)
    snap["corp_member_codes"] = snap["corp_code"].map(corp_codes_map)
    snap["corp_member_names"] = snap["corp_code"].map(corp_names_map)

    snap["has_fundamental"] = snap["rcept_dt"].notna().astype(int)
    snap["missing_reason"] = ""
    snap.loc[snap["has_fundamental"] == 0, "missing_reason"] = "no_fundamental_in_current_dataset"

    pref_mask = snap["name"].astype(str).str.contains(r"(?:\d+)?우(?:B|C)?$", regex=True, na=False)
    snap.loc[(snap["has_fundamental"] == 0) & pref_mask, "missing_reason"] = "preferred_share_mapping_or_source_gap"

    missing = snap[snap["has_fundamental"] == 0].copy()

    coverage = pd.DataFrame(
        [
            {"metric": "asof", "value": args.asof},
            {"metric": "universe_codes", "value": int(snap["code"].nunique())},
            {"metric": "has_fundamental_codes", "value": int(snap[snap["has_fundamental"] == 1]["code"].nunique())},
            {
                "metric": "coverage_ratio",
                "value": round(float(snap[snap["has_fundamental"] == 1]["code"].nunique()) / float(snap["code"].nunique()), 4),
            },
            {"metric": "missing_codes", "value": int(missing["code"].nunique())},
        ]
    )

    out_snap = Path(args.snapshot_output)
    out_snap.parent.mkdir(parents=True, exist_ok=True)
    out_missing = Path(args.missing_output)
    out_missing.parent.mkdir(parents=True, exist_ok=True)
    out_cov = Path(args.coverage_output)
    out_cov.parent.mkdir(parents=True, exist_ok=True)

    save_snap = snap if args.no_korean_columns else snap.rename(columns=KR_COLS)
    save_missing = missing if args.no_korean_columns else missing.rename(columns=KR_COLS)

    save_snap.to_csv(out_snap, index=False, encoding="utf-8-sig")
    print(f"[saved] {out_snap} rows={len(save_snap):,}")
    save_missing.to_csv(out_missing, index=False, encoding="utf-8-sig")
    print(f"[saved] {out_missing} rows={len(save_missing):,}")
    coverage.to_csv(out_cov, index=False, encoding="utf-8-sig")
    print(f"[saved] {out_cov}")
    print(coverage.to_string(index=False))


if __name__ == "__main__":
    main()

import argparse
from pathlib import Path

import pandas as pd

from new_strategy.paths import data_path


def load_gold(path: Path) -> pd.DataFrame:
    df = pd.read_excel(path)
    rename_map = {
        "일자": "date",
        "종가": "gold_kr_close",
        "등락률": "gold_kr_ret",
        "거래량": "gold_kr_volume",
        "거래대금": "gold_kr_trading_value",
    }
    missing = [k for k in rename_map if k not in df.columns]
    if missing:
        raise ValueError(f"gold file missing columns: {missing}")

    df = df.rename(columns=rename_map)
    df["date"] = pd.to_datetime(df["date"].astype(str), format="%Y%m%d", errors="coerce")
    keep = ["date", "gold_kr_close", "gold_kr_ret", "gold_kr_volume", "gold_kr_trading_value"]
    df = df[keep].copy()
    for col in keep[1:]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.dropna(subset=["date"]).sort_values("date").drop_duplicates("date", keep="last")


def merge_gold_into_macro(macro_path: Path, gold_path: Path, output_path: Path) -> pd.DataFrame:
    if not macro_path.exists():
        raise FileNotFoundError(f"macro file not found: {macro_path}")
    if not gold_path.exists():
        raise FileNotFoundError(f"gold file not found: {gold_path}")

    macro = pd.read_csv(macro_path)
    macro["date"] = pd.to_datetime(macro["date"], errors="coerce")
    macro = macro.dropna(subset=["date"]).sort_values("date")
    old_cols = [c for c in macro.columns if str(c).endswith("_old")]
    if old_cols:
        macro = macro.drop(columns=old_cols)
    prior_gold_cols = [c for c in macro.columns if str(c).startswith("gold_kr_")]
    if prior_gold_cols:
        macro = macro.drop(columns=prior_gold_cols)

    gold = load_gold(gold_path)
    merged = macro.merge(gold, on="date", how="left")
    merged = merged.sort_values("date").reset_index(drop=True)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"[saved] {output_path}")
    print(
        "[gold-non-null]",
        {
            "gold_kr_close": int(merged["gold_kr_close"].notna().sum()),
            "gold_kr_ret": int(merged["gold_kr_ret"].notna().sum()),
            "gold_kr_volume": int(merged["gold_kr_volume"].notna().sum()),
            "gold_kr_trading_value": int(merged["gold_kr_trading_value"].notna().sum()),
        },
    )
    return merged


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Merge KRX gold daily data into macro_daily.csv.")
    p.add_argument("--macro", default=str(data_path("macro_daily.csv")))
    p.add_argument("--gold", default=str(data_path("gold_kr_daily.xlsx")))
    p.add_argument("--output", default=str(data_path("macro_daily.csv")))
    return p.parse_args()


def main() -> None:
    args = parse_args()
    merge_gold_into_macro(Path(args.macro), Path(args.gold), Path(args.output))


if __name__ == "__main__":
    main()

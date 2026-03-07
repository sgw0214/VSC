import argparse
from pathlib import Path

import pandas as pd

from new_strategy.paths import data_path, output_path

from strategy_rules import StrategyConfig, add_features, pick_candidates


def load_price_panel(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".parquet":
        df = pd.read_parquet(path)
    else:
        df = pd.read_csv(path, dtype={"code": str}, low_memory=False)
    df["date"] = pd.to_datetime(df["date"])
    return df


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generate latest stock picks from strategy rules.")
    p.add_argument("--price-panel", default=str(data_path("price_panel.csv")))
    p.add_argument("--date", default="", help="Optional date (YYYY-MM-DD). default=latest available date")
    p.add_argument("--top-n", type=int, default=10)
    p.add_argument("--macro", default="", help="Optional macro regime csv with date,exposure")
    p.add_argument("--min-exposure", type=float, default=0.5, help="Skip picks when exposure is below this level")
    p.add_argument("--output", default=str(output_path("latest_picks.csv")))
    return p.parse_args()


def main() -> None:
    args = parse_args()
    df = load_price_panel(Path(args.price_panel))

    cfg = StrategyConfig(top_n=args.top_n, stop_mode="fixed", fixed_stop_loss=-0.08)
    feat = add_features(df, cfg)
    selected = pick_candidates(feat, cfg)

    target_date = pd.to_datetime(args.date) if args.date else selected["date"].max()
    if args.macro:
        macro = pd.read_csv(args.macro)
        macro["date"] = pd.to_datetime(macro["date"])
        exposure = macro.loc[macro["date"] == target_date, "exposure"]
        if not exposure.empty and float(exposure.iloc[0]) < args.min_exposure:
            out = pd.DataFrame(columns=["date", "code", "name", "industry", "close", "adv20", "adv60", "ma60", "ma120", "momentum_score", "rank"])
            output = Path(args.output)
            output.parent.mkdir(parents=True, exist_ok=True)
            out.to_csv(output, index=False, encoding="utf-8-sig")
            print(f"[saved] {output}")
            print(f"[date] {target_date.date()}")
            print(f"[info] skipped by macro exposure ({float(exposure.iloc[0]):.2f} < {args.min_exposure:.2f})")
            return

    out = selected[selected["date"] == target_date].copy()
    out = out.sort_values("rank")

    keep_cols = [
        "date",
        "code",
        "name",
        "industry",
        "close",
        "adv20",
        "adv60",
        "ma_mid",
        "ma_long",
        "momentum_score",
        "rank",
    ]
    out = out[keep_cols]

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(output, index=False, encoding="utf-8-sig")
    print(f"[saved] {output}")
    print(f"[date] {target_date.date()}")
    if out.empty:
        print("[info] no candidates on target date")
    else:
        print(out[["rank", "code", "name", "industry", "momentum_score"]].to_string(index=False))


if __name__ == "__main__":
    main()

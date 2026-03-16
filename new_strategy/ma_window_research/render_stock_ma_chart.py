from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

from new_strategy.paths import data_path, output_path


def load_price_frame(source: Path, code: str) -> pd.DataFrame:
    df = pd.read_pickle(source)[["date", "code", "name", "close"]].copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["code"] = df["code"].astype(str).str.zfill(6)
    out = (
        df[df["code"] == code]
        .dropna(subset=["date", "close"])
        .sort_values("date")
        .reset_index(drop=True)
    )
    if out.empty:
        raise ValueError(f"code not found in source dataset: {code}")
    return out


def build_monthly_frame(frame: pd.DataFrame, windows: list[int]) -> pd.DataFrame:
    monthly = (
        frame.set_index("date")["close"]
        .resample("M")
        .last()
        .dropna()
        .to_frame(name="close")
        .reset_index()
    )
    for window in windows:
        monthly[f"ma_{window}"] = monthly["close"].rolling(window, min_periods=window).mean()
    return monthly


def render_chart(monthly: pd.DataFrame, stock_name: str, code: str, out_path: Path, windows: list[int]) -> None:
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["font.family"] = ["Malgun Gothic", "AppleGothic", "DejaVu Sans"]

    fig, ax = plt.subplots(figsize=(14, 8), dpi=160)
    fig.patch.set_facecolor("#f6f4ee")
    ax.set_facecolor("#fffdf8")
    x = monthly["date"].to_numpy()

    ax.plot(
        x,
        monthly["close"].to_numpy(),
        color="#202939",
        linewidth=2.2,
        label="월 종가",
        alpha=0.95,
    )

    palette = {
        3: "#1f77b4",
        5: "#2ca02c",
        10: "#ff7f0e",
        20: "#d62728",
    }
    for window in windows:
        ax.plot(
            x,
            monthly[f"ma_{window}"].to_numpy(),
            linewidth=2.0,
            color=palette.get(window, "#6b7280"),
            label=f"{window}개월 이평",
        )

    ax.set_title(f"{stock_name}({code}) 월봉 종가 및 3·5·10·20 이동평균선", fontsize=18, fontweight="bold", pad=18)
    ax.set_xlabel("날짜", fontsize=11)
    ax.set_ylabel("가격", fontsize=11)
    ax.grid(True, axis="y", color="#d9d5cc", linewidth=0.8, alpha=0.6)
    ax.grid(False, axis="x")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#b9b2a6")
    ax.spines["bottom"].set_color("#b9b2a6")
    ax.legend(loc="upper left", frameon=False, ncol=3)
    ax.xaxis.set_major_locator(mdates.YearLocator(base=1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right")
    plt.tight_layout()
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description="Render monthly close with selected moving averages for one stock.")
    parser.add_argument("--code", default="000020")
    parser.add_argument("--windows", default="3,5,10,20")
    parser.add_argument("--source", type=Path, default=data_path("feature_daily.pkl"))
    parser.add_argument("--out-dir", type=Path, default=output_path("ma_window_research", "charts"))
    args = parser.parse_args()

    windows = [int(x.strip()) for x in args.windows.split(",") if x.strip()]
    frame = load_price_frame(args.source, args.code)
    stock_name = str(frame["name"].dropna().iloc[-1])
    monthly = build_monthly_frame(frame, windows)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    base_name = f"{args.code}_{stock_name}_monthly_ma_" + "_".join(str(w) for w in windows)
    chart_path = args.out_dir / f"{base_name}.png"
    csv_path = args.out_dir / f"{base_name}.csv"

    render_chart(monthly, stock_name, args.code, chart_path, windows)
    monthly.to_csv(csv_path, index=False, encoding="utf-8-sig")

    print(f"[done] chart: {chart_path}")
    print(f"[done] data : {csv_path}")


if __name__ == "__main__":
    main()

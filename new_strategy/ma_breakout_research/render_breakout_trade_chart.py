from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import pandas as pd

from new_strategy.paths import data_path, output_path


def load_price_frame(source: Path, code: str) -> pd.DataFrame:
    if source.suffix.lower() == ".pkl":
        df = pd.read_pickle(source)
    else:
        df = pd.read_csv(source, low_memory=False)
    cols = ["date", "code", "name", "open", "high", "low", "close"]
    missing = [col for col in cols if col not in df.columns]
    if missing:
        raise ValueError(f"source missing required columns: {missing}")
    out = df[cols].copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out["code"] = out["code"].astype(str).str.zfill(6)
    for col in ["open", "high", "low", "close"]:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out = (
        out.loc[out["code"] == code]
        .dropna(subset=["date", "open", "high", "low", "close"])
        .sort_values("date")
        .reset_index(drop=True)
    )
    if out.empty:
        raise ValueError(f"code not found in source dataset: {code}")
    return out


def build_monthly_ohlc(frame: pd.DataFrame, window: int) -> pd.DataFrame:
    temp = frame.copy()
    temp["period"] = temp["date"].dt.to_period("M")
    monthly = (
        temp.groupby("period", as_index=False)
        .agg(
            date=("date", "max"),
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            name=("name", "last"),
        )
        .dropna(subset=["date", "open", "high", "low", "close"])
        .reset_index(drop=True)
    )
    monthly["ma"] = monthly["close"].rolling(window, min_periods=window).mean()
    valid = monthly["ma"].notna()
    monthly["signal"] = monthly["close"] > monthly["ma"]
    prev_signal = monthly["signal"].shift(1).fillna(False)
    prev_valid = valid.shift(1, fill_value=False)
    cross_up = valid & prev_valid & monthly["signal"] & (~prev_signal)
    cross_down = valid & prev_valid & (~monthly["signal"]) & prev_signal
    event_state = pd.Series(pd.NA, index=monthly.index, dtype="Float64")
    event_state.loc[cross_up] = 1.0
    event_state.loc[cross_down] = 0.0
    monthly["state_after_close"] = event_state.ffill().fillna(0.0).astype(float)
    prev_state = monthly["state_after_close"].shift(1, fill_value=0.0)
    monthly["buy"] = (monthly["state_after_close"] == 1.0) & (prev_state == 0.0)
    monthly["sell"] = (monthly["state_after_close"] == 0.0) & (prev_state == 1.0)
    monthly["action"] = ""
    monthly.loc[monthly["buy"], "action"] = "BUY"
    monthly.loc[monthly["sell"], "action"] = "SELL"
    return monthly


def attach_trade_returns(monthly: pd.DataFrame) -> pd.DataFrame:
    out = monthly.copy()
    out["entry_date"] = pd.NaT
    out["entry_close"] = pd.NA
    out["trade_return"] = pd.NA
    out["cumulative_return"] = pd.NA

    entry_date = None
    entry_close = None
    cumulative = 1.0
    trade_rows: list[dict[str, object]] = []

    for row in out.itertuples(index=False):
        if bool(row.buy):
            entry_date = row.date
            entry_close = float(row.close)
            continue
        if bool(row.sell) and entry_date is not None and entry_close is not None:
            trade_return = float(row.close) / entry_close - 1.0
            cumulative *= 1.0 + trade_return
            trade_rows.append(
                {
                    "sell_date": row.date,
                    "entry_date": entry_date,
                    "entry_close": entry_close,
                    "trade_return": trade_return,
                    "cumulative_return": cumulative - 1.0,
                }
            )
            entry_date = None
            entry_close = None

    if not trade_rows:
        return out

    trades = pd.DataFrame(trade_rows)
    sell_index = out.index[out["sell"]]
    out.loc[sell_index, "entry_date"] = pd.to_datetime(trades["entry_date"]).to_numpy()
    out.loc[sell_index, "entry_close"] = trades["entry_close"].to_numpy()
    out.loc[sell_index, "trade_return"] = trades["trade_return"].to_numpy()
    out.loc[sell_index, "cumulative_return"] = trades["cumulative_return"].to_numpy()
    return out


def render_chart(monthly: pd.DataFrame, stock_name: str, code: str, window: int, out_path: Path) -> None:
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["font.family"] = ["Malgun Gothic", "AppleGothic", "DejaVu Sans"]

    fig, ax = plt.subplots(figsize=(16, 9), dpi=160)
    fig.patch.set_facecolor("#f5f3ee")
    ax.set_facecolor("#fffdf9")

    dates = mdates.date2num(monthly["date"].dt.to_pydatetime())
    width = 18

    for x, row in zip(dates, monthly.itertuples(index=False)):
        candle_color = "#0f766e" if row.close >= row.open else "#b91c1c"
        edge_color = "#134e4a" if row.close >= row.open else "#7f1d1d"
        ax.vlines(x, row.low, row.high, color=edge_color, linewidth=1.2, alpha=0.9, zorder=1)
        body_low = min(row.open, row.close)
        body_height = max(abs(row.close - row.open), 1.0)
        ax.add_patch(
            Rectangle(
                (x - width / 2, body_low),
                width,
                body_height,
                facecolor=candle_color,
                edgecolor=edge_color,
                linewidth=0.8,
                alpha=0.9,
                zorder=2,
            )
        )

    ax.plot(
        monthly["date"].to_numpy(),
        monthly["ma"].to_numpy(),
        color="#f59e0b",
        linewidth=2.2,
        label=f"월봉 {window}이평",
        zorder=3,
    )
    ax.plot(
        monthly["date"].to_numpy(),
        monthly["close"].to_numpy(),
        color="#1f2937",
        linewidth=1.2,
        alpha=0.45,
        label="월봉 종가",
        zorder=2.5,
    )

    buy_df = monthly.loc[monthly["buy"]].copy()
    sell_df = monthly.loc[monthly["sell"]].copy()
    if not buy_df.empty:
        ax.scatter(
            buy_df["date"].to_numpy(),
            buy_df["close"].to_numpy(),
            marker="^",
            s=120,
            color="#16a34a",
            edgecolors="white",
            linewidths=0.9,
            label="매수 시점",
            zorder=4,
        )
    if not sell_df.empty:
        ax.scatter(
            sell_df["date"].to_numpy(),
            sell_df["close"].to_numpy(),
            marker="v",
            s=120,
            color="#dc2626",
            edgecolors="white",
            linewidths=0.9,
            label="매도 시점",
            zorder=4,
        )
        for row in sell_df.itertuples(index=False):
            if pd.isna(row.cumulative_return):
                continue
            ax.annotate(
                f"누적 {float(row.cumulative_return):.1%}",
                (row.date, row.close),
                xytext=(0, -18),
                textcoords="offset points",
                ha="center",
                va="top",
                fontsize=8.5,
                color="#991b1b",
                bbox={
                    "boxstyle": "round,pad=0.25",
                    "fc": "#fef2f2",
                    "ec": "#fecaca",
                    "alpha": 0.9,
                },
                zorder=5,
            )

    latest = monthly.iloc[-1]
    signal_text = "매수 우세" if bool(latest["signal"]) else "매도 경계"
    ax.set_title(
        f"{stock_name}({code}) 월봉 차트 및 {window}이평 매수/매도 시점\n"
        f"기준: 전월말 대비 월말 종가가 {window}이평을 상향 돌파하면 매수, 하향 돌파하면 매도 | 현재 상태: {signal_text}",
        fontsize=17,
        fontweight="bold",
        pad=18,
    )
    ax.set_xlabel("날짜", fontsize=11)
    ax.set_ylabel("가격(원)", fontsize=11)
    ax.grid(True, axis="y", color="#d6d3d1", linewidth=0.8, alpha=0.6)
    ax.grid(False, axis="x")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#b9b2a6")
    ax.spines["bottom"].set_color("#b9b2a6")
    ax.xaxis.set_major_locator(mdates.YearLocator(base=1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right")
    ax.legend(loc="upper left", frameon=False, ncol=4)
    plt.tight_layout()
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description="Render monthly OHLC with MA crossover buy/sell points.")
    parser.add_argument("--code", default="004310")
    parser.add_argument("--window", type=int, default=74)
    parser.add_argument("--source", type=Path, default=data_path("feature_daily.pkl"))
    parser.add_argument("--out-dir", type=Path, default=output_path("ma_breakout_research", "charts"))
    args = parser.parse_args()

    frame = load_price_frame(args.source, args.code)
    stock_name = str(frame["name"].dropna().iloc[-1])
    monthly = build_monthly_ohlc(frame, args.window)
    monthly = attach_trade_returns(monthly)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    base = f"{args.code}_{stock_name}_monthly_ma_{args.window}_signals"
    chart_path = args.out_dir / f"{base}.png"
    data_path_out = args.out_dir / f"{base}.csv"
    trades_path = args.out_dir / f"{base}_trades.csv"

    render_chart(monthly, stock_name, args.code, args.window, chart_path)
    monthly.to_csv(data_path_out, index=False, encoding="utf-8-sig")
    monthly.loc[
        monthly["action"] != "",
        [
            "date",
            "open",
            "high",
            "low",
            "close",
            "ma",
            "action",
            "entry_date",
            "entry_close",
            "trade_return",
            "cumulative_return",
        ],
    ].to_csv(
        trades_path,
        index=False,
        encoding="utf-8-sig",
    )

    print(f"[done] chart : {chart_path}")
    print(f"[done] data  : {data_path_out}")
    print(f"[done] trades: {trades_path}")


if __name__ == "__main__":
    main()

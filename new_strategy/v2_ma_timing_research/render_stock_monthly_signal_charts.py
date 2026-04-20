from __future__ import annotations

from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd


PRICE_PANEL_PATH = Path(r"E:\VSC\python\new_strategy\price_panel.csv")
SIGNAL_POINTS_PATH = Path(
    r"E:\VSC\python\new_strategy\output\v2_stock_check_skinnovation\096770_monthly_signal_points.csv"
)
OUTPUT_DIR = Path(r"E:\VSC\python\new_strategy\output\v2_stock_check_skinnovation")


def load_daily_ohlc(code: str) -> pd.DataFrame:
    df = pd.read_csv(
        PRICE_PANEL_PATH,
        usecols=["code", "date", "open", "high", "low", "close"],
        dtype={"code": str},
    )
    df["code"] = df["code"].str.zfill(6)
    df = df[df["code"] == code].copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    return df


def build_monthly_ohlc(daily_df: pd.DataFrame) -> pd.DataFrame:
    daily_df = daily_df.copy()
    daily_df["month"] = daily_df["date"].dt.to_period("M")
    monthly = (
        daily_df.groupby("month")
        .agg(
            month_end=("date", "max"),
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
        )
        .reset_index(drop=True)
    )
    return monthly


def add_monthly_ma(monthly_df: pd.DataFrame, window: int) -> pd.DataFrame:
    out = monthly_df.copy()
    out["ma"] = out["close"].rolling(window=window, min_periods=window).mean()
    return out


def load_signal_points(window: int) -> pd.DataFrame:
    df = pd.read_csv(SIGNAL_POINTS_PATH)
    df = df[df["window"] == window].copy()
    if df.empty:
        return df
    # Candles are centered at the month-end trading date, so plot action markers
    # on that candle's x-position while keeping the y-value at the execution open.
    df["plot_date"] = pd.to_datetime(df["execution_month_close_date"])
    df["plot_price"] = pd.to_numeric(df["execution_open"], errors="coerce")
    return df


def plot_candles(ax: plt.Axes, monthly_df: pd.DataFrame) -> None:
    x = mdates.date2num(monthly_df["month_end"])
    width = 18
    for xi, row in zip(x, monthly_df.itertuples(index=False)):
        color = "#1f77b4" if row.close >= row.open else "#e15759"
        ax.vlines(xi, row.low, row.high, color=color, linewidth=1.2, alpha=0.75, zorder=1)
        body_low = min(row.open, row.close)
        body_height = max(abs(row.close - row.open), 1)
        rect = plt.Rectangle(
            (xi - width / 2, body_low),
            width,
            body_height,
            facecolor=color,
            edgecolor=color,
            linewidth=0.9,
            alpha=0.9,
            zorder=2,
        )
        ax.add_patch(rect)


def plot_actions(ax: plt.Axes, signal_df: pd.DataFrame) -> None:
    if signal_df.empty:
        return
    buy_df = signal_df[signal_df["signal"] == "BUY"].copy()
    sell_df = signal_df[signal_df["signal"] == "SELL"].copy()

    if not buy_df.empty:
        ax.scatter(
            buy_df["plot_date"],
            buy_df["plot_price"],
            marker="^",
            s=140,
            color="#1aaf5d",
            edgecolor="white",
            linewidth=0.8,
            zorder=4,
            label="BUY(exec month)",
        )
        for row in buy_df.itertuples(index=False):
            ax.annotate(
                "BUY",
                (row.plot_date, row.plot_price),
                textcoords="offset points",
                xytext=(0, -18),
                ha="center",
                color="#1a7f44",
                fontsize=9,
                fontweight="bold",
                zorder=5,
            )

    if not sell_df.empty:
        ax.scatter(
            sell_df["plot_date"],
            sell_df["plot_price"],
            marker="v",
            s=140,
            color="#d62728",
            edgecolor="white",
            linewidth=0.8,
            zorder=4,
            label="SELL(exec month)",
        )
        for row in sell_df.itertuples(index=False):
            ax.annotate(
                "SELL",
                (row.plot_date, row.plot_price),
                textcoords="offset points",
                xytext=(0, 8),
                ha="center",
                color="#b22222",
                fontsize=9,
                fontweight="bold",
                zorder=5,
            )


def render_chart(code: str, name: str, window: int, monthly_df: pd.DataFrame, signal_df: pd.DataFrame) -> Path:
    fig, ax = plt.subplots(figsize=(18, 8))
    plot_candles(ax, monthly_df)
    ax.plot(
        monthly_df["month_end"].to_numpy(),
        monthly_df["ma"].to_numpy(),
        color="#6a40c9",
        linewidth=2.2,
        label=f"MA {window}",
        zorder=3,
    )
    plot_actions(ax, signal_df)

    ax.set_title(f"{name} ({code}) monthly MA {window}", fontsize=18, pad=18)
    ax.set_ylabel("Price")
    ax.grid(axis="y", alpha=0.25)
    ax.legend(loc="upper left")
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    fig.autofmt_xdate()
    fig.tight_layout()

    output_path = OUTPUT_DIR / f"{code}_{window}m_monthly_signal_chart.png"
    fig.savefig(output_path, dpi=160)
    plt.close(fig)
    return output_path


def main() -> None:
    code = "096770"
    name = "SK Innovation"
    daily_df = load_daily_ohlc(code)
    monthly_base = build_monthly_ohlc(daily_df)

    for window in [5, 33, 103]:
        monthly_df = add_monthly_ma(monthly_base, window)
        signal_df = load_signal_points(window)
        render_chart(code, name, window, monthly_df, signal_df)


if __name__ == "__main__":
    main()


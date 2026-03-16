from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from time import perf_counter

import pandas as pd

from new_strategy.earnings_signal_engine import (
    EarningsStrategyConfig,
    default_inputs,
    evaluate_backtest,
    prepare_strategy_frame,
    simulate_signals,
)
from new_strategy.paths import output_path


COMPARE_DIR = output_path("strategy_compare")
STRATEGY_META_PATH = output_path("strategy_v1", "strategy_metadata.json")
HORIZONS = [1, 5, 20, 60, 90]


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _base_config() -> dict:
    cfg = asdict(EarningsStrategyConfig())
    cfg.update(_read_json(STRATEGY_META_PATH).get("config", {}))
    return cfg


def _build_cfg(base_cfg: dict, *, strategy_id: str, trend_mode: str) -> EarningsStrategyConfig:
    payload = asdict(EarningsStrategyConfig())
    payload.update(base_cfg)
    payload["strategy_id"] = strategy_id
    payload["trend_mode"] = trend_mode
    return EarningsStrategyConfig(**payload)


def _add_short_horizon_returns(strategy_df: pd.DataFrame) -> pd.DataFrame:
    cols = ["date", "code", "close", "fwd_ret_20d", "fwd_ret_60d", "fwd_ret_90d"]
    px = strategy_df.loc[:, cols].copy()
    px = px.sort_values(["code", "date"]).reset_index(drop=True)
    grp = px.groupby("code", sort=False)["close"]
    px["fwd_ret_1d"] = grp.shift(-1) / px["close"] - 1.0
    px["fwd_ret_5d"] = grp.shift(-5) / px["close"] - 1.0
    return px


def _signal_quality(strategy_df: pd.DataFrame, signal_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    px = _add_short_horizon_returns(strategy_df)
    events = signal_df.loc[signal_df["signal"].isin(["BUY", "SELL"]), ["date", "code", "signal", "conviction_score"]].copy()
    merged = events.merge(px, on=["date", "code"], how="left")

    rows: list[dict[str, object]] = []
    for signal in ["BUY", "SELL"]:
        subset = merged.loc[merged["signal"] == signal].copy()
        for horizon in HORIZONS:
            col = f"fwd_ret_{horizon}d"
            valid = subset.loc[subset[col].notna(), col]
            if valid.empty:
                rows.append(
                    {
                        "signal": signal,
                        "horizon_days": horizon,
                        "obs": 0,
                        "avg_return": float("nan"),
                        "median_return": float("nan"),
                        "hit_rate": float("nan"),
                    }
                )
                continue
            hit_mask = valid > 0 if signal == "BUY" else valid < 0
            rows.append(
                {
                    "signal": signal,
                    "horizon_days": horizon,
                    "obs": int(len(valid)),
                    "avg_return": float(valid.mean()),
                    "median_return": float(valid.median()),
                    "hit_rate": float(hit_mask.mean()),
                }
            )
    return pd.DataFrame(rows), merged


def _portfolio_summary(eval_df: pd.DataFrame, trade_df: pd.DataFrame, signal_df: pd.DataFrame) -> pd.DataFrame:
    metric_map = dict(zip(eval_df["metric"], eval_df["value"]))
    return pd.DataFrame(
        [
            {"metric": "cagr", "value": metric_map.get("cagr")},
            {"metric": "mdd", "value": metric_map.get("mdd")},
            {"metric": "sharpe", "value": metric_map.get("sharpe")},
            {"metric": "win_rate", "value": metric_map.get("win_rate")},
            {"metric": "num_closed_trades", "value": metric_map.get("num_closed_trades")},
            {"metric": "num_open_trades", "value": metric_map.get("num_open_trades")},
            {"metric": "avg_holding_days", "value": metric_map.get("avg_holding_days")},
            {"metric": "final_equity", "value": metric_map.get("final_equity")},
            {"metric": "buy_signal_count", "value": int((signal_df["signal"] == "BUY").sum())},
            {"metric": "sell_signal_count", "value": int((signal_df["signal"] == "SELL").sum())},
            {"metric": "open_position_count", "value": int((trade_df["status"] == "OPEN").sum())},
        ]
    )


def _run_variant(name: str, cfg: EarningsStrategyConfig, compare_dir: Path) -> dict[str, object]:
    started = perf_counter()
    inputs = default_inputs()
    strategy_df, metadata = prepare_strategy_frame(inputs["feature"], inputs["fundamental"], cfg)
    signal_df, trade_df, decision_df, curve_df = simulate_signals(strategy_df, cfg)
    eval_df = evaluate_backtest(curve_df, trade_df)
    quality_df, signal_detail_df = _signal_quality(strategy_df, signal_df)
    summary_df = _portfolio_summary(eval_df, trade_df, signal_df)

    variant_dir = compare_dir / name
    variant_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([metadata]).to_csv(variant_dir / "runtime_metadata.csv", index=False, encoding="utf-8-sig")
    summary_df.to_csv(variant_dir / "portfolio_summary.csv", index=False, encoding="utf-8-sig")
    eval_df.to_csv(variant_dir / "eval_metrics.csv", index=False, encoding="utf-8-sig")
    quality_df.to_csv(variant_dir / "signal_quality.csv", index=False, encoding="utf-8-sig")
    signal_df.to_csv(variant_dir / "signals.csv", index=False, encoding="utf-8-sig")
    trade_df.to_csv(variant_dir / "trades.csv", index=False, encoding="utf-8-sig")
    decision_df.to_csv(variant_dir / "decisions.csv", index=False, encoding="utf-8-sig")
    curve_df.to_csv(variant_dir / "equity_curve.csv", index=False, encoding="utf-8-sig")
    signal_detail_df.to_csv(variant_dir / "signal_detail_quality.csv", index=False, encoding="utf-8-sig")

    return {
        "name": name,
        "cfg": cfg,
        "metadata": metadata,
        "summary_df": summary_df,
        "quality_df": quality_df,
        "duration_seconds": perf_counter() - started,
        "output_dir": variant_dir,
    }


def _comparison_rows(left: dict[str, object], right: dict[str, object]) -> pd.DataFrame:
    left_summary = left["summary_df"].rename(columns={"value": "baseline_value"})
    right_summary = right["summary_df"].rename(columns={"value": "enhanced_value"})
    portfolio = left_summary.merge(right_summary, on="metric", how="outer")
    portfolio["section"] = "portfolio"

    left_quality = left["quality_df"].rename(
        columns={
            "obs": "baseline_obs",
            "avg_return": "baseline_avg_return",
            "median_return": "baseline_median_return",
            "hit_rate": "baseline_hit_rate",
        }
    )
    right_quality = right["quality_df"].rename(
        columns={
            "obs": "enhanced_obs",
            "avg_return": "enhanced_avg_return",
            "median_return": "enhanced_median_return",
            "hit_rate": "enhanced_hit_rate",
        }
    )
    quality = left_quality.merge(right_quality, on=["signal", "horizon_days"], how="outer")
    quality["section"] = "signal_quality"

    return pd.concat([portfolio, quality], ignore_index=True, sort=False)


def _format_pct(value: object) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{float(value):.2%}"


def _format_num(value: object) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{float(value):,.3f}"


def _summary_markdown(left: dict[str, object], right: dict[str, object], comparison_df: pd.DataFrame) -> str:
    port = comparison_df.loc[comparison_df["section"] == "portfolio"].copy()
    port = port.set_index("metric")
    quality = comparison_df.loc[comparison_df["section"] == "signal_quality"].copy()

    buy20 = quality.loc[(quality["signal"] == "BUY") & (quality["horizon_days"] == 20)].iloc[0]
    sell20 = quality.loc[(quality["signal"] == "SELL") & (quality["horizon_days"] == 20)].iloc[0]

    lines = [
        "# 전략 비교 요약",
        "",
        "## 비교 정의",
        f"- 기존전략: `{left['cfg'].strategy_id}` / `trend_mode={left['cfg'].trend_mode}`",
        f"- 기존전략+신규요소: `{right['cfg'].strategy_id}` / `trend_mode={right['cfg'].trend_mode}`",
        "",
        "## 포트폴리오 성과",
        f"- 기존전략 CAGR: {_format_pct(port.at['cagr', 'baseline_value'])}",
        f"- 개선전략 CAGR: {_format_pct(port.at['cagr', 'enhanced_value'])}",
        f"- 기존전략 MDD: {_format_pct(port.at['mdd', 'baseline_value'])}",
        f"- 개선전략 MDD: {_format_pct(port.at['mdd', 'enhanced_value'])}",
        f"- 기존전략 Sharpe: {_format_num(port.at['sharpe', 'baseline_value'])}",
        f"- 개선전략 Sharpe: {_format_num(port.at['sharpe', 'enhanced_value'])}",
        f"- 기존전략 승률: {_format_pct(port.at['win_rate', 'baseline_value'])}",
        f"- 개선전략 승률: {_format_pct(port.at['win_rate', 'enhanced_value'])}",
        "",
        "## 신호 품질 핵심",
        f"- BUY 20일 평균수익률: 기존 {_format_pct(buy20['baseline_avg_return'])} / 개선 {_format_pct(buy20['enhanced_avg_return'])}",
        f"- BUY 20일 적중률: 기존 {_format_pct(buy20['baseline_hit_rate'])} / 개선 {_format_pct(buy20['enhanced_hit_rate'])}",
        f"- SELL 20일 평균후속수익률: 기존 {_format_pct(sell20['baseline_avg_return'])} / 개선 {_format_pct(sell20['enhanced_avg_return'])}",
        f"- SELL 20일 적중률: 기존 {_format_pct(sell20['baseline_hit_rate'])} / 개선 {_format_pct(sell20['enhanced_hit_rate'])}",
        "",
        "## 실행 시간",
        f"- 기존전략 실행: {left['duration_seconds']:.1f}초",
        f"- 개선전략 실행: {right['duration_seconds']:.1f}초",
        "",
        "## 산출물 경로",
        f"- `{left['output_dir']}`",
        f"- `{right['output_dir']}`",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    compare_dir = COMPARE_DIR
    compare_dir.mkdir(parents=True, exist_ok=True)

    base_cfg = _base_config()
    baseline_cfg = _build_cfg(
        base_cfg,
        strategy_id="earnings_pti_v1_baseline",
        trend_mode="legacy_mid",
    )
    enhanced_cfg = _build_cfg(
        base_cfg,
        strategy_id="earnings_pti_v1_plus_monthly_weekly_ma",
        trend_mode="monthly_weekly",
    )

    print("[1/2] 기존전략 실행")
    baseline = _run_variant("baseline", baseline_cfg, compare_dir)
    print("[2/2] 기존전략+신규요소 실행")
    enhanced = _run_variant("baseline_plus_ma", enhanced_cfg, compare_dir)

    comparison_df = _comparison_rows(baseline, enhanced)
    comparison_df.to_csv(compare_dir / "comparison_summary.csv", index=False, encoding="utf-8-sig")
    (compare_dir / "comparison_summary.md").write_text(
        _summary_markdown(baseline, enhanced, comparison_df),
        encoding="utf-8",
    )
    print(f"[done] comparison saved to {compare_dir}")


if __name__ == "__main__":
    main()

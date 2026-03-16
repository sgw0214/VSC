from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from time import perf_counter

import numpy as np
import pandas as pd

from new_strategy.compare_strategy_variants import (
    _add_short_horizon_returns,
    _portfolio_summary,
    _read_json,
)
from new_strategy.earnings_signal_engine import (
    EarningsStrategyConfig,
    default_inputs,
    evaluate_backtest,
    prepare_strategy_frame,
    simulate_signals,
)
from new_strategy.ma_breakout_research.backtest_ma_breakout_modes import (
    _map_period_ma_to_daily,
    _rolling_mean,
    build_completed_period_frame,
)
from new_strategy.paths import output_path


STRATEGY_META_PATH = output_path("strategy_v1", "strategy_metadata.json")
MA_RAW_PATH = output_path("ma_breakout_research", "all_action_modes_returns_by_stock.csv")
OUT_DIR = output_path("strategy_compare_optimal_ma")
HORIZONS = [1, 5, 20, 60, 90]


def _base_config() -> dict:
    cfg = asdict(EarningsStrategyConfig())
    cfg.update(_read_json(STRATEGY_META_PATH).get("config", {}))
    cfg["trend_mode"] = "legacy_mid"
    return cfg


def _build_cfg(base_cfg: dict, *, strategy_id: str) -> EarningsStrategyConfig:
    payload = asdict(EarningsStrategyConfig())
    payload.update(base_cfg)
    payload["strategy_id"] = strategy_id
    payload["trend_mode"] = "legacy_mid"
    return EarningsStrategyConfig(**payload)


def _action_mode_priority(series: pd.Series) -> pd.Series:
    return series.map({"native_timeframe_close": 0, "daily_close_action": 1}).fillna(9).astype(int)


def _timeframe_priority(series: pd.Series) -> pd.Series:
    return series.map({"monthly": 0, "weekly": 1, "daily": 2}).fillna(9).astype(int)


def load_optimal_ma_selection(path: Path, allowed_timeframes: list[str] | None = None) -> pd.DataFrame:
    df = pd.read_csv(path, dtype={"code": str})
    df["code"] = df["code"].astype(str).str.zfill(6)
    if allowed_timeframes:
        allowed = {str(x).strip().lower() for x in allowed_timeframes}
        df = df.loc[df["ma_timeframe"].astype(str).str.lower().isin(allowed)].copy()
    ranked = df.copy()
    ranked["action_mode_priority"] = _action_mode_priority(ranked["action_mode"])
    ranked["timeframe_priority"] = _timeframe_priority(ranked["ma_timeframe"])
    ranked = ranked.sort_values(
        [
            "code",
            "excess_return",
            "annualized_return",
            "max_drawdown",
            "win_rate",
            "completed_trade_count",
            "action_mode_priority",
            "timeframe_priority",
            "ma_window",
        ],
        ascending=[True, False, False, False, False, False, True, True, True],
    )
    selected = ranked.groupby("code", as_index=False).head(1).reset_index(drop=True)
    return selected[
        [
            "code",
            "name",
            "ma_timeframe",
            "action_mode",
            "ma_window",
            "excess_return",
            "annualized_return",
            "max_drawdown",
            "win_rate",
            "completed_trade_count",
            "trade_count",
            "exposure_ratio",
        ]
    ].copy()


def _map_period_signal_to_daily(
    daily_dates: np.ndarray,
    period_dates: np.ndarray,
    period_signal: np.ndarray,
) -> np.ndarray:
    out = np.full(len(daily_dates), np.nan, dtype=float)
    if len(period_dates) == 0:
        return out
    idx = np.searchsorted(period_dates, daily_dates, side="right") - 1
    valid = idx >= 0
    out[valid] = period_signal[idx[valid]].astype(float)
    return out


def build_optimal_ma_state(price_df: pd.DataFrame, selection_df: pd.DataFrame) -> pd.DataFrame:
    source = price_df.loc[:, ["date", "code", "close"]].dropna().copy()
    source["date"] = pd.to_datetime(source["date"])
    source["code"] = source["code"].astype(str).str.zfill(6)
    source = source.sort_values(["code", "date"]).reset_index(drop=True)
    today = pd.Timestamp(source["date"].max())

    selection_map = selection_df.set_index("code").to_dict(orient="index")
    states: list[pd.DataFrame] = []
    for code, grp in source.groupby("code", sort=False):
        selected = selection_map.get(code)
        if selected is None:
            block = grp.copy()
            block["optimal_ma_ok"] = np.nan
            block["optimal_ma_timeframe"] = None
            block["optimal_ma_action_mode"] = None
            block["optimal_ma_window"] = np.nan
            states.append(block)
            continue

        timeframe = str(selected["ma_timeframe"])
        action_mode = str(selected["action_mode"])
        window = int(selected["ma_window"])
        grp = grp.sort_values("date").reset_index(drop=True)
        dates = grp["date"].to_numpy()
        prices = grp["close"].to_numpy(dtype=float)

        signal = np.full(len(grp), np.nan, dtype=float)
        if timeframe == "daily":
            daily_ma = _rolling_mean(prices, window)
            signal = (prices > daily_ma).astype(float)
            signal[~np.isfinite(daily_ma)] = np.nan
        elif action_mode == "daily_close_action":
            period_df = build_completed_period_frame(grp[["date", "close"]], timeframe, today=today)
            period_dates = period_df["decision_date"].to_numpy()
            period_prices = period_df["close"].to_numpy(dtype=float)
            period_ma = _rolling_mean(period_prices, window)
            daily_ma = _map_period_ma_to_daily(dates, period_dates, period_ma)
            signal = (prices > daily_ma).astype(float)
            signal[~np.isfinite(daily_ma)] = np.nan
        else:
            period_df = build_completed_period_frame(grp[["date", "close"]], timeframe, today=today)
            period_dates = period_df["decision_date"].to_numpy()
            period_prices = period_df["close"].to_numpy(dtype=float)
            period_ma = _rolling_mean(period_prices, window)
            period_signal = (period_prices > period_ma).astype(float)
            period_signal[~np.isfinite(period_ma)] = np.nan
            signal = _map_period_signal_to_daily(dates, period_dates, period_signal)

        block = grp.copy()
        block["optimal_ma_ok"] = signal
        block["optimal_ma_timeframe"] = timeframe
        block["optimal_ma_action_mode"] = action_mode
        block["optimal_ma_window"] = window
        states.append(block)

    out = pd.concat(states, ignore_index=True)
    out["optimal_ma_ok"] = out["optimal_ma_ok"].map({1.0: True, 0.0: False})
    return out


def _apply_optimal_ma_blend(strategy_df: pd.DataFrame, state_df: pd.DataFrame) -> pd.DataFrame:
    overlay = state_df[["date", "code", "optimal_ma_ok", "optimal_ma_timeframe", "optimal_ma_action_mode", "optimal_ma_window"]].copy()
    blended = strategy_df.merge(overlay, on=["date", "code"], how="left")
    ok = blended["optimal_ma_ok"].fillna(True)
    blended["buy_candidate"] = blended["buy_candidate"] & ok
    blended["watch_candidate"] = blended["watch_candidate"] & ok
    blended["ma_mid"] = blended["ma_mid"].where(ok, np.inf)
    return blended


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
                rows.append({"signal": signal, "horizon_days": horizon, "obs": 0, "avg_return": np.nan, "hit_rate": np.nan})
                continue
            hit = valid > 0 if signal == "BUY" else valid < 0
            rows.append(
                {
                    "signal": signal,
                    "horizon_days": horizon,
                    "obs": int(len(valid)),
                    "avg_return": float(valid.mean()),
                    "hit_rate": float(hit.mean()),
                }
            )
    return pd.DataFrame(rows), merged


def _indicator_review(strategy_df: pd.DataFrame, signal_df: pd.DataFrame, state_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    px = _add_short_horizon_returns(strategy_df)
    overlay = state_df[["date", "code", "optimal_ma_ok", "optimal_ma_timeframe", "optimal_ma_action_mode", "optimal_ma_window"]]
    events = signal_df.loc[signal_df["signal"].isin(["BUY", "SELL"]), ["date", "code", "signal", "conviction_score"]].copy()
    merged = events.merge(px, on=["date", "code"], how="left").merge(overlay, on=["date", "code"], how="left")

    def _align(row: pd.Series) -> str:
        if pd.isna(row.get("optimal_ma_ok")):
            return "no_selection"
        if row["signal"] == "BUY":
            return "agree" if bool(row["optimal_ma_ok"]) else "disagree"
        return "agree" if (not bool(row["optimal_ma_ok"])) else "disagree"

    merged["indicator_alignment"] = merged.apply(_align, axis=1)

    rows: list[dict[str, object]] = []
    for signal in ["BUY", "SELL"]:
        signal_df_local = merged.loc[merged["signal"] == signal].copy()
        for alignment in ["agree", "disagree", "no_selection"]:
            aligned = signal_df_local.loc[signal_df_local["indicator_alignment"] == alignment].copy()
            for horizon in HORIZONS:
                col = f"fwd_ret_{horizon}d"
                valid = aligned.loc[aligned[col].notna(), col]
                if valid.empty:
                    rows.append(
                        {
                            "signal": signal,
                            "indicator_alignment": alignment,
                            "horizon_days": horizon,
                            "obs": 0,
                            "avg_return": np.nan,
                            "hit_rate": np.nan,
                        }
                    )
                    continue
                hit = valid > 0 if signal == "BUY" else valid < 0
                rows.append(
                    {
                        "signal": signal,
                        "indicator_alignment": alignment,
                        "horizon_days": horizon,
                        "obs": int(len(valid)),
                        "avg_return": float(valid.mean()),
                        "hit_rate": float(hit.mean()),
                    }
                )
    return pd.DataFrame(rows), merged


def _run_variant(name: str, cfg: EarningsStrategyConfig, strategy_df: pd.DataFrame) -> dict[str, object]:
    started = perf_counter()
    signal_df, trade_df, decision_df, curve_df = simulate_signals(strategy_df, cfg)
    eval_df = evaluate_backtest(curve_df, trade_df)
    quality_df, signal_detail_df = _signal_quality(strategy_df, signal_df)
    summary_df = _portfolio_summary(eval_df, trade_df, signal_df)

    out_dir = OUT_DIR / name
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_df.to_csv(out_dir / "portfolio_summary.csv", index=False, encoding="utf-8-sig")
    eval_df.to_csv(out_dir / "eval_metrics.csv", index=False, encoding="utf-8-sig")
    quality_df.to_csv(out_dir / "signal_quality.csv", index=False, encoding="utf-8-sig")
    signal_df.to_csv(out_dir / "signals.csv", index=False, encoding="utf-8-sig")
    trade_df.to_csv(out_dir / "trades.csv", index=False, encoding="utf-8-sig")
    decision_df.to_csv(out_dir / "decisions.csv", index=False, encoding="utf-8-sig")
    curve_df.to_csv(out_dir / "equity_curve.csv", index=False, encoding="utf-8-sig")
    signal_detail_df.to_csv(out_dir / "signal_detail_quality.csv", index=False, encoding="utf-8-sig")

    return {
        "name": name,
        "summary_df": summary_df,
        "quality_df": quality_df,
        "signal_df": signal_df,
        "trade_df": trade_df,
        "duration_seconds": perf_counter() - started,
        "output_dir": out_dir,
    }


def _format_pct(value: object) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{float(value):.2%}"


def _format_num(value: object) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{float(value):,.3f}"


def _summary_markdown(
    selection_df: pd.DataFrame,
    baseline: dict[str, object],
    blended: dict[str, object],
    indicator_review_df: pd.DataFrame,
) -> str:
    base_port = baseline["summary_df"].set_index("metric")
    blend_port = blended["summary_df"].set_index("metric")
    base_quality = baseline["quality_df"]
    blend_quality = blended["quality_df"]

    buy20_base = base_quality.loc[(base_quality["signal"] == "BUY") & (base_quality["horizon_days"] == 20)].iloc[0]
    buy20_blend = blend_quality.loc[(blend_quality["signal"] == "BUY") & (blend_quality["horizon_days"] == 20)].iloc[0]
    sell20_base = base_quality.loc[(base_quality["signal"] == "SELL") & (base_quality["horizon_days"] == 20)].iloc[0]
    sell20_blend = blend_quality.loc[(blend_quality["signal"] == "SELL") & (blend_quality["horizon_days"] == 20)].iloc[0]

    lines = [
        "# 기존전략 vs 최적 MA 정보 비교",
        "",
        "## 비교 정의",
        "- 전략 1: 기존전략",
        "- 전략 2: 기존전략 + 종목별 최적 MA 정보 블렌드",
        "- 전략 3: 기존전략 + 종목별 최적 MA 정보 별도 지표 검토",
        "",
        "## 종목별 최적 MA 선정 규칙",
        "- 입력: all_action_modes_returns_by_stock.csv",
        "- 순위: excess_return > annualized_return > max_drawdown(덜 나쁜 쪽) > win_rate > completed_trade_count",
        "- 동률 보정: native_timeframe_close 우선, monthly > weekly > daily, 더 짧은 window 우선",
        f"- 선택 종목 수: {selection_df['code'].nunique():,}",
        "",
        "## 선택된 최적 MA 분포",
    ]
    tf = selection_df["ma_timeframe"].value_counts()
    am = selection_df["action_mode"].value_counts()
    for key, value in tf.items():
        lines.append(f"- timeframe {key}: {int(value)}")
    for key, value in am.items():
        lines.append(f"- action_mode {key}: {int(value)}")

    lines += [
        "",
        "## 포트폴리오 성과",
        f"- 기존 CAGR: {_format_pct(base_port.at['cagr', 'value'])}",
        f"- 블렌드 CAGR: {_format_pct(blend_port.at['cagr', 'value'])}",
        f"- 기존 MDD: {_format_pct(base_port.at['mdd', 'value'])}",
        f"- 블렌드 MDD: {_format_pct(blend_port.at['mdd', 'value'])}",
        f"- 기존 Sharpe: {_format_num(base_port.at['sharpe', 'value'])}",
        f"- 블렌드 Sharpe: {_format_num(blend_port.at['sharpe', 'value'])}",
        f"- 기존 승률: {_format_pct(base_port.at['win_rate', 'value'])}",
        f"- 블렌드 승률: {_format_pct(blend_port.at['win_rate', 'value'])}",
        "",
        "## 신호 품질",
        f"- BUY 20일 평균수익률: 기존 {_format_pct(buy20_base['avg_return'])} / 블렌드 {_format_pct(buy20_blend['avg_return'])}",
        f"- BUY 20일 적중률: 기존 {_format_pct(buy20_base['hit_rate'])} / 블렌드 {_format_pct(buy20_blend['hit_rate'])}",
        f"- SELL 20일 평균후속수익률: 기존 {_format_pct(sell20_base['avg_return'])} / 블렌드 {_format_pct(sell20_blend['avg_return'])}",
        f"- SELL 20일 적중률: 기존 {_format_pct(sell20_base['hit_rate'])} / 블렌드 {_format_pct(sell20_blend['hit_rate'])}",
        "",
        "## 별도 지표 검토",
    ]

    for signal in ["BUY", "SELL"]:
        for horizon in [5, 20]:
            subset = indicator_review_df.loc[
                (indicator_review_df["signal"] == signal)
                & (indicator_review_df["horizon_days"] == horizon)
                & (indicator_review_df["indicator_alignment"].isin(["agree", "disagree"]))
            ].copy()
            if subset.empty:
                continue
            agree = subset.loc[subset["indicator_alignment"] == "agree"].iloc[0]
            disagree = subset.loc[subset["indicator_alignment"] == "disagree"].iloc[0]
            lines.append(
                f"- {signal} {horizon}일: agree 평균 {_format_pct(agree['avg_return'])} / hit {_format_pct(agree['hit_rate'])} | "
                f"disagree 평균 {_format_pct(disagree['avg_return'])} / hit {_format_pct(disagree['hit_rate'])}"
            )

    lines += [
        "",
        "## 실행 시간",
        f"- 기존전략: {baseline['duration_seconds']:.1f}초",
        f"- 블렌드전략: {blended['duration_seconds']:.1f}초",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    base_cfg = _base_config()
    baseline_cfg = _build_cfg(base_cfg, strategy_id="earnings_pti_v1_baseline")
    blended_cfg = _build_cfg(base_cfg, strategy_id="earnings_pti_v1_plus_optimal_ma")

    inputs = default_inputs()
    print("[1/5] baseline strategy frame")
    strategy_df, metadata = prepare_strategy_frame(inputs["feature"], inputs["fundamental"], baseline_cfg)
    pd.DataFrame([metadata]).to_csv(OUT_DIR / "runtime_metadata.csv", index=False, encoding="utf-8-sig")

    print("[2/5] optimal MA selection")
    selection_df = load_optimal_ma_selection(MA_RAW_PATH)
    selection_df.to_csv(OUT_DIR / "optimal_ma_selection.csv", index=False, encoding="utf-8-sig")

    print("[3/5] build optimal MA state")
    state_df = build_optimal_ma_state(strategy_df, selection_df)
    state_df.to_csv(OUT_DIR / "optimal_ma_state.csv", index=False, encoding="utf-8-sig")

    print("[4/5] run baseline")
    baseline = _run_variant("baseline", baseline_cfg, strategy_df)

    print("[5/5] run baseline + optimal MA blend")
    blended_strategy_df = _apply_optimal_ma_blend(strategy_df, state_df)
    blended = _run_variant("baseline_plus_optimal_ma", blended_cfg, blended_strategy_df)

    print("[review] indicator-only review")
    indicator_review_df, indicator_detail_df = _indicator_review(strategy_df, baseline["signal_df"], state_df)
    indicator_review_df.to_csv(OUT_DIR / "indicator_review_summary.csv", index=False, encoding="utf-8-sig")
    indicator_detail_df.to_csv(OUT_DIR / "indicator_review_detail.csv", index=False, encoding="utf-8-sig")

    (OUT_DIR / "comparison_summary.md").write_text(
        _summary_markdown(selection_df, baseline, blended, indicator_review_df),
        encoding="utf-8",
    )

    meta = {
        "selection_source": str(MA_RAW_PATH),
        "baseline_output_dir": str(baseline["output_dir"]),
        "blended_output_dir": str(blended["output_dir"]),
        "selection_rule": "excess_return > annualized_return > max_drawdown > win_rate > completed_trade_count",
    }
    (OUT_DIR / "run_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[done] saved to {OUT_DIR}")


if __name__ == "__main__":
    main()

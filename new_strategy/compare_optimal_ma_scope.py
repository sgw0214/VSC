from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from new_strategy.compare_strategy_with_optimal_ma import (
    MA_RAW_PATH,
    OUT_DIR,
    _base_config,
    _build_cfg,
    _format_num,
    _format_pct,
    _indicator_review,
    _run_variant,
    build_optimal_ma_state,
    load_optimal_ma_selection,
    _apply_optimal_ma_blend,
)
from new_strategy.earnings_signal_engine import default_inputs, prepare_strategy_frame


OUT_SCOPE_DIR = OUT_DIR.parent / "strategy_compare_optimal_ma_scope"


def _selection_mix(df: pd.DataFrame) -> pd.DataFrame:
    timeframe = (
        df["ma_timeframe"]
        .value_counts()
        .rename_axis("bucket")
        .reset_index(name="count")
        .assign(kind="timeframe")
    )
    action = (
        df["action_mode"]
        .value_counts()
        .rename_axis("bucket")
        .reset_index(name="count")
        .assign(kind="action_mode")
    )
    return pd.concat([timeframe, action], ignore_index=True)


def _summary_markdown(
    baseline: dict[str, object],
    mw_only: dict[str, object],
    all_mix: dict[str, object],
    mw_selection: pd.DataFrame,
    all_selection: pd.DataFrame,
    mw_indicator: pd.DataFrame,
    all_indicator: pd.DataFrame,
) -> str:
    base_port = baseline["summary_df"].set_index("metric")
    mw_port = mw_only["summary_df"].set_index("metric")
    all_port = all_mix["summary_df"].set_index("metric")

    def q(variant: dict[str, object], signal: str, horizon: int, col: str):
        row = variant["quality_df"].loc[
            (variant["quality_df"]["signal"] == signal) & (variant["quality_df"]["horizon_days"] == horizon)
        ].iloc[0]
        return row[col]

    def ind(df: pd.DataFrame, signal: str, horizon: int, alignment: str, col: str):
        row = df.loc[
            (df["signal"] == signal)
            & (df["horizon_days"] == horizon)
            & (df["indicator_alignment"] == alignment)
        ].iloc[0]
        return row[col]

    lines = [
        "# 최적 MA 범위 비교",
        "",
        "## 비교 정의",
        "- 기존전략",
        "- 기존전략 + 종목별 최적 MA(월봉/주봉만)",
        "- 기존전략 + 종목별 최적 MA(월봉/주봉/일봉 전체)",
        "",
        "## 선택 종목 수",
        f"- 월/주 전용 selection: {mw_selection['code'].nunique():,}",
        f"- 월/주/일 전체 selection: {all_selection['code'].nunique():,}",
        "",
        "## 포트폴리오 성과",
        f"- 기존 CAGR: {_format_pct(base_port.at['cagr', 'value'])}",
        f"- 월/주 블렌드 CAGR: {_format_pct(mw_port.at['cagr', 'value'])}",
        f"- 월/주/일 블렌드 CAGR: {_format_pct(all_port.at['cagr', 'value'])}",
        f"- 기존 MDD: {_format_pct(base_port.at['mdd', 'value'])}",
        f"- 월/주 블렌드 MDD: {_format_pct(mw_port.at['mdd', 'value'])}",
        f"- 월/주/일 블렌드 MDD: {_format_pct(all_port.at['mdd', 'value'])}",
        f"- 기존 Sharpe: {_format_num(base_port.at['sharpe', 'value'])}",
        f"- 월/주 블렌드 Sharpe: {_format_num(mw_port.at['sharpe', 'value'])}",
        f"- 월/주/일 블렌드 Sharpe: {_format_num(all_port.at['sharpe', 'value'])}",
        "",
        "## 신호 품질",
        f"- BUY 20일 평균수익률: 기존 {_format_pct(q(baseline, 'BUY', 20, 'avg_return'))} / 월주 {_format_pct(q(mw_only, 'BUY', 20, 'avg_return'))} / 월주일 {_format_pct(q(all_mix, 'BUY', 20, 'avg_return'))}",
        f"- BUY 20일 적중률: 기존 {_format_pct(q(baseline, 'BUY', 20, 'hit_rate'))} / 월주 {_format_pct(q(mw_only, 'BUY', 20, 'hit_rate'))} / 월주일 {_format_pct(q(all_mix, 'BUY', 20, 'hit_rate'))}",
        f"- SELL 20일 평균후속수익률: 기존 {_format_pct(q(baseline, 'SELL', 20, 'avg_return'))} / 월주 {_format_pct(q(mw_only, 'SELL', 20, 'avg_return'))} / 월주일 {_format_pct(q(all_mix, 'SELL', 20, 'avg_return'))}",
        f"- SELL 20일 적중률: 기존 {_format_pct(q(baseline, 'SELL', 20, 'hit_rate'))} / 월주 {_format_pct(q(mw_only, 'SELL', 20, 'hit_rate'))} / 월주일 {_format_pct(q(all_mix, 'SELL', 20, 'hit_rate'))}",
        "",
        "## 별도 지표 검토(agree vs disagree)",
        f"- 월/주 BUY 20일: agree {_format_pct(ind(mw_indicator,'BUY',20,'agree','avg_return'))} / disagree {_format_pct(ind(mw_indicator,'BUY',20,'disagree','avg_return'))}",
        f"- 월/주 SELL 20일: agree {_format_pct(ind(mw_indicator,'SELL',20,'agree','avg_return'))} / disagree {_format_pct(ind(mw_indicator,'SELL',20,'disagree','avg_return'))}",
        f"- 월/주/일 BUY 20일: agree {_format_pct(ind(all_indicator,'BUY',20,'agree','avg_return'))} / disagree {_format_pct(ind(all_indicator,'BUY',20,'disagree','avg_return'))}",
        f"- 월/주/일 SELL 20일: agree {_format_pct(ind(all_indicator,'SELL',20,'agree','avg_return'))} / disagree {_format_pct(ind(all_indicator,'SELL',20,'disagree','avg_return'))}",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    OUT_SCOPE_DIR.mkdir(parents=True, exist_ok=True)

    base_cfg = _base_config()
    baseline_cfg = _build_cfg(base_cfg, strategy_id="earnings_pti_v1_baseline")
    mw_cfg = _build_cfg(base_cfg, strategy_id="earnings_pti_v1_plus_optimal_ma_monthly_weekly")
    all_cfg = _build_cfg(base_cfg, strategy_id="earnings_pti_v1_plus_optimal_ma_all")

    inputs = default_inputs()
    print("[1/6] baseline strategy frame")
    strategy_df, metadata = prepare_strategy_frame(inputs["feature"], inputs["fundamental"], baseline_cfg)
    pd.DataFrame([metadata]).to_csv(OUT_SCOPE_DIR / "runtime_metadata.csv", index=False, encoding="utf-8-sig")

    print("[2/6] baseline run")
    baseline = _run_variant("baseline", baseline_cfg, strategy_df)

    print("[3/6] monthly+weekly selection")
    mw_selection = load_optimal_ma_selection(MA_RAW_PATH, allowed_timeframes=["monthly", "weekly"])
    mw_selection.to_csv(OUT_SCOPE_DIR / "optimal_ma_selection_monthly_weekly.csv", index=False, encoding="utf-8-sig")
    mw_state = build_optimal_ma_state(strategy_df, mw_selection)
    mw_blended_df = _apply_optimal_ma_blend(strategy_df, mw_state)
    mw_only = _run_variant("baseline_plus_optimal_ma_monthly_weekly", mw_cfg, mw_blended_df)
    mw_indicator, mw_detail = _indicator_review(strategy_df, baseline["signal_df"], mw_state)
    mw_indicator.to_csv(OUT_SCOPE_DIR / "indicator_review_monthly_weekly.csv", index=False, encoding="utf-8-sig")
    mw_detail.to_csv(OUT_SCOPE_DIR / "indicator_review_monthly_weekly_detail.csv", index=False, encoding="utf-8-sig")

    print("[4/6] monthly+weekly+daily selection")
    all_selection = load_optimal_ma_selection(MA_RAW_PATH, allowed_timeframes=["monthly", "weekly", "daily"])
    all_selection.to_csv(OUT_SCOPE_DIR / "optimal_ma_selection_all.csv", index=False, encoding="utf-8-sig")
    all_state = build_optimal_ma_state(strategy_df, all_selection)
    all_blended_df = _apply_optimal_ma_blend(strategy_df, all_state)
    all_mix = _run_variant("baseline_plus_optimal_ma_all", all_cfg, all_blended_df)
    all_indicator, all_detail = _indicator_review(strategy_df, baseline["signal_df"], all_state)
    all_indicator.to_csv(OUT_SCOPE_DIR / "indicator_review_all.csv", index=False, encoding="utf-8-sig")
    all_detail.to_csv(OUT_SCOPE_DIR / "indicator_review_all_detail.csv", index=False, encoding="utf-8-sig")

    print("[5/6] selection mix export")
    _selection_mix(mw_selection).to_csv(OUT_SCOPE_DIR / "selection_mix_monthly_weekly.csv", index=False, encoding="utf-8-sig")
    _selection_mix(all_selection).to_csv(OUT_SCOPE_DIR / "selection_mix_all.csv", index=False, encoding="utf-8-sig")

    print("[6/6] summary")
    (OUT_SCOPE_DIR / "comparison_summary.md").write_text(
        _summary_markdown(baseline, mw_only, all_mix, mw_selection, all_selection, mw_indicator, all_indicator),
        encoding="utf-8",
    )
    run_meta = {
        "ma_raw_path": str(MA_RAW_PATH),
        "baseline_output_dir": str(baseline["output_dir"]),
        "monthly_weekly_output_dir": str(mw_only["output_dir"]),
        "all_output_dir": str(all_mix["output_dir"]),
    }
    (OUT_SCOPE_DIR / "run_meta.json").write_text(json.dumps(run_meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[done] saved to {OUT_SCOPE_DIR}")


if __name__ == "__main__":
    main()

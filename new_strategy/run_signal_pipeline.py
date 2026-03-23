from __future__ import annotations

import argparse
import json
import os
import traceback
from datetime import datetime, time
from pathlib import Path
from typing import List

import pandas as pd

from new_strategy.data_health import build_data_health
from new_strategy.earnings_signal_engine import (
    EarningsStrategyConfig,
    build_condition_performance,
    build_rule_candidates,
    default_inputs,
    default_output_dir,
    evaluate_backtest,
    prepare_latest_strategy_frame,
    prepare_strategy_frame,
    simulate_fast_alert_cycle,
    simulate_signals,
    write_fast_alert_outputs,
    write_strategy_outputs,
)
from new_strategy.notifiers import AlertEvent, TelegramNotifier, build_notifiers, dispatch_alerts
from new_strategy.paths import data_path
from new_strategy.refresh_runtime_data import run_refresh_pipeline


def _write_progress(progress_file: Path | None, *, status: str, percent: int, stage: str, detail: str = "") -> None:
    if progress_file is None:
        return
    progress_file.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[str, object] = {}
    if progress_file.exists():
        try:
            existing = json.loads(progress_file.read_text(encoding="utf-8"))
        except Exception:
            existing = {}
    started_at = str(existing.get("started_at") or datetime.now().isoformat(timespec="seconds"))
    finished_at = datetime.now().isoformat(timespec="seconds") if status in {"completed", "failed"} else ""
    duration_seconds = None
    try:
        start_dt = datetime.fromisoformat(started_at)
        end_dt = datetime.fromisoformat(finished_at) if finished_at else datetime.now()
        duration_seconds = int((end_dt - start_dt).total_seconds())
    except Exception:
        duration_seconds = None
    payload = dict(existing)
    payload.update(
        {
            "pid": os.getpid(),
            "started_at": started_at,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "finished_at": finished_at,
            "status": status,
            "percent": int(percent),
            "stage": stage,
            "detail": detail,
            "duration_seconds": duration_seconds,
        }
    )
    progress_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _send_job_feedback(label: str, status: str, detail: str = "") -> None:
    title = str(label or "").strip()
    if not title:
        return
    notifier = TelegramNotifier()
    if not notifier.is_configured():
        return
    message = f"{title} 완료" if status == "completed" else f"{title} 실패"
    if status != "completed":
        short_detail = str(detail or "").strip()
        if short_detail:
            message = f"{message}\n{short_detail[:180]}"
    try:
        notifier.send("Strategy Report", message)
    except Exception:
        pass


def _build_alert_events(signal_df: pd.DataFrame, decision_df: pd.DataFrame, cfg: EarningsStrategyConfig) -> List[AlertEvent]:
    if signal_df.empty:
        return []
    latest_date = signal_df["date"].max()
    latest = signal_df[signal_df["date"] == latest_date].copy()
    now = datetime.now()
    execution_window = now.weekday() < 5 and time(8, 0) <= now.time() <= time(20, 0)
    opening_window = now.weekday() < 5 and time(8, 0) <= now.time() <= time(8, 30)
    guide_col = "intraday_action_guide" if execution_window else "next_day_action_guide"
    events: List[AlertEvent] = []

    for _, row in latest[latest["signal"].isin(["BUY", "SELL"])].iterrows():
        reasons = [x for x in [row["reason_1"], row["reason_2"], row["reason_3"]] if isinstance(x, str) and x]
        guide = str(row.get(guide_col) or "").strip()
        opening_line = "Opening risk: 장 초반 매도 우선 점검 구간입니다." if opening_window and str(row.get("signal")) == "SELL" else ""
        message = "\n".join(
            [
                f"Signal date: {pd.Timestamp(row['date']).date()}",
                f"Signal: {row['signal']}",
                f"Score: {float(row['conviction_score']):.2f}",
                f"Risk flag: {row['risk_flag'] or 'none'}",
                *( [opening_line] if opening_line else [] ),
                *( [f"Action guide: {guide}"] if guide else [] ),
                *[f"- {reason}" for reason in reasons[:3]],
            ]
        )
        events.append(
            AlertEvent(
                event_type="TRIGGER",
                event_time=now,
                signal_date=str(pd.Timestamp(row["date"]).date()),
                code=str(row["code"]).zfill(6),
                name=str(row["name"]),
                signal=str(row["signal"]),
                strategy_id=str(row["strategy_id"]),
                conviction_score=float(row["conviction_score"]),
                message=message,
            )
        )

    for _, row in latest[(latest["signal"] == "WATCH") & (latest["conviction_score"] >= cfg.pre_signal_threshold)].iterrows():
        reasons = [x for x in [row["reason_1"], row["reason_2"], row["reason_3"]] if isinstance(x, str) and x]
        guide = str(row.get(guide_col) or "").strip()
        message = "\n".join(
            [
                f"Signal date: {pd.Timestamp(row['date']).date()}",
                "Status: near buy threshold",
                f"Score: {float(row['conviction_score']):.2f}",
                *( [f"Action guide: {guide}"] if guide else [] ),
                *[f"- {reason}" for reason in reasons[:3]],
            ]
        )
        events.append(
            AlertEvent(
                event_type="PRE_SIGNAL",
                event_time=now,
                signal_date=str(pd.Timestamp(row["date"]).date()),
                code=str(row["code"]).zfill(6),
                name=str(row["name"]),
                signal="WATCH",
                strategy_id=str(row["strategy_id"]),
                conviction_score=float(row["conviction_score"]),
                message=message,
            )
        )

    if not decision_df.empty:
        last = decision_df.sort_values("date").iloc[-1]
        message = "\n".join(
            [
                f"Daily close summary {pd.Timestamp(last['date']).date()}",
                f"regime={last['market_regime']}, exposure={float(last['exposure']):.2f}",
                f"BUY={int(last['buy_count'])}, SELL={int(last['sell_count'])}, HOLD={int(last['hold_count'])}, WATCH={int(last['watch_count'])}",
                f"BUY: {last['buy_codes'] or '-'}",
                f"SELL: {last['sell_codes'] or '-'}",
                f"WATCH: {last['watch_codes'] or '-'}",
            ]
        )
        events.append(
            AlertEvent(
                event_type="DAILY_SUMMARY",
                event_time=now,
                signal_date=str(pd.Timestamp(last["date"]).date()),
                code="MARKET",
                name="Market Summary",
                signal="SUMMARY",
                strategy_id=str(last["strategy_id"]),
                conviction_score=0.0,
                message=message,
            )
        )
    return events


def parse_args() -> argparse.Namespace:
    inputs = default_inputs()
    out_dir = default_output_dir()
    defaults = EarningsStrategyConfig()
    p = argparse.ArgumentParser(description="Run earnings-based signal pipeline and optional alerts.")
    p.add_argument("--feature", default=str(inputs["feature"]))
    p.add_argument("--fundamental", default=str(inputs["fundamental"]))
    p.add_argument("--output-dir", default=str(out_dir))
    p.add_argument("--send-alerts", action="store_true")
    p.add_argument("--strategy-id", default=defaults.strategy_id)
    p.add_argument("--trend-mode", default=defaults.trend_mode)
    p.add_argument("--min-adv20", type=float, default=defaults.min_adv20)
    p.add_argument("--recent-filing-days", type=int, default=defaults.recent_filing_days)
    p.add_argument("--watchlist-size", type=int, default=defaults.watchlist_size)
    p.add_argument("--max-positions", type=int, default=defaults.max_positions)
    p.add_argument("--min-hold-days", type=int, default=defaults.min_hold_days)
    p.add_argument("--max-holding-days", type=int, default=defaults.max_holding_days)
    p.add_argument("--fixed-stop-loss", type=float, default=defaults.fixed_stop_loss)
    p.add_argument("--max-ret-5", type=float, default=defaults.max_ret_5)
    p.add_argument("--max-atr-ratio", type=float, default=defaults.max_atr_ratio)
    p.add_argument("--max-dist-ma-mid", type=float, default=defaults.max_dist_ma_mid)
    p.add_argument("--neutral-target-ratio", type=float, default=defaults.neutral_target_ratio)
    p.add_argument("--riskoff-target-ratio", type=float, default=defaults.riskoff_target_ratio)
    p.add_argument("--buy-threshold", type=float, default=defaults.buy_threshold)
    p.add_argument("--watch-threshold", type=float, default=defaults.watch_threshold)
    p.add_argument("--sell-threshold", type=float, default=defaults.sell_threshold)
    p.add_argument("--min-timing-score", type=float, default=defaults.min_timing_score)
    p.add_argument("--pre-signal-threshold", type=float, default=defaults.pre_signal_threshold)
    p.add_argument("--research-min-obs", type=int, default=defaults.research_min_obs)
    p.add_argument("--ml-backend", default=defaults.ml_backend)
    p.add_argument("--ml-train-window-days", type=int, default=defaults.ml_train_window_days)
    p.add_argument("--ml-horizon-days", type=int, default=defaults.ml_horizon_days)
    p.add_argument("--riskoff-exposure-cutoff", type=float, default=defaults.riskoff_exposure_cutoff)
    p.add_argument("--monthly-buy-threshold", type=float, default=defaults.monthly_buy_threshold)
    p.add_argument("--weekly-sell-threshold", type=float, default=defaults.weekly_sell_threshold)
    p.add_argument("--fast-alerts", action="store_true")
    p.add_argument("--refresh-data", action="store_true")
    p.add_argument("--refresh-macro", action="store_true")
    p.add_argument("--refresh-gold", action="store_true")
    p.add_argument("--refresh-db", action="store_true")
    p.add_argument("--prefer-kiwoom-eod", action="store_true")
    p.add_argument("--live-quotes", default=str(data_path("live_quotes.csv")))
    p.add_argument("--progress-file", default="")
    p.add_argument("--job-feedback-label", default="")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    progress_file = Path(args.progress_file) if str(args.progress_file).strip() else None
    output_dir = Path(args.output_dir)
    job_feedback_label = str(args.job_feedback_label or "").strip()
    cfg = EarningsStrategyConfig(
        strategy_id=args.strategy_id,
        trend_mode=args.trend_mode,
        min_adv20=args.min_adv20,
        recent_filing_days=args.recent_filing_days,
        watchlist_size=args.watchlist_size,
        max_positions=args.max_positions,
        min_hold_days=args.min_hold_days,
        max_holding_days=args.max_holding_days,
        fixed_stop_loss=args.fixed_stop_loss,
        max_ret_5=args.max_ret_5,
        max_atr_ratio=args.max_atr_ratio,
        max_dist_ma_mid=args.max_dist_ma_mid,
        neutral_target_ratio=args.neutral_target_ratio,
        riskoff_target_ratio=args.riskoff_target_ratio,
        buy_threshold=args.buy_threshold,
        watch_threshold=args.watch_threshold,
        sell_threshold=args.sell_threshold,
        min_timing_score=args.min_timing_score,
        pre_signal_threshold=args.pre_signal_threshold,
        research_min_obs=args.research_min_obs,
        ml_backend=args.ml_backend,
        ml_train_window_days=args.ml_train_window_days,
        ml_horizon_days=args.ml_horizon_days,
        riskoff_exposure_cutoff=args.riskoff_exposure_cutoff,
        monthly_buy_threshold=args.monthly_buy_threshold,
        weekly_sell_threshold=args.weekly_sell_threshold,
    )
    try:
        _write_progress(progress_file, status="running", percent=1, stage="시작", detail="파이프라인을 시작했습니다.")

        if args.refresh_data or args.refresh_macro or args.refresh_gold or args.refresh_db:
            _write_progress(progress_file, status="running", percent=10, stage="데이터 최신화", detail="주가/매크로/금 데이터를 갱신합니다.")
            refresh_meta = run_refresh_pipeline(
                refresh_stock=args.refresh_data,
                refresh_macro=args.refresh_macro,
                refresh_gold=args.refresh_gold,
                rebuild_db=args.refresh_db,
                prefer_kiwoom_eod=args.prefer_kiwoom_eod,
            )
            print(f"[refresh] meta={refresh_meta['refresh_meta']}")
        else:
            _write_progress(progress_file, status="running", percent=10, stage="데이터 확인", detail="기존 최신 데이터를 사용합니다.")

        if args.fast_alerts:
            _write_progress(progress_file, status="running", percent=35, stage="최신 프레임 준비", detail="장중/장후 fast alert 입력셋을 준비합니다.")
            fast_cfg = EarningsStrategyConfig(
                strategy_id=cfg.strategy_id,
                min_adv20=cfg.min_adv20,
                recent_filing_days=cfg.recent_filing_days,
                watchlist_size=cfg.watchlist_size,
                max_positions=cfg.max_positions,
                min_hold_days=cfg.min_hold_days,
                max_holding_days=cfg.max_holding_days,
                fixed_stop_loss=cfg.fixed_stop_loss,
                max_ret_5=cfg.max_ret_5,
                max_atr_ratio=cfg.max_atr_ratio,
                max_dist_ma_mid=cfg.max_dist_ma_mid,
                neutral_target_ratio=cfg.neutral_target_ratio,
                riskoff_target_ratio=cfg.riskoff_target_ratio,
                buy_threshold=cfg.buy_threshold,
                watch_threshold=cfg.watch_threshold,
                sell_threshold=cfg.sell_threshold,
                min_timing_score=cfg.min_timing_score,
                pre_signal_threshold=cfg.pre_signal_threshold,
                research_min_obs=cfg.research_min_obs,
                ml_backend="none",
                ml_train_window_days=cfg.ml_train_window_days,
                ml_horizon_days=cfg.ml_horizon_days,
                riskoff_exposure_cutoff=cfg.riskoff_exposure_cutoff,
            )
            live_quotes_path = Path(args.live_quotes) if args.live_quotes else None
            latest_df, metadata = prepare_latest_strategy_frame(
                Path(args.feature),
                Path(args.fundamental),
                fast_cfg,
                live_quotes_path=live_quotes_path,
            )
            _write_progress(progress_file, status="running", percent=60, stage="fast alert 계산", detail="최신 신호와 의사결정을 계산합니다.")
            signal_df, decision_df, state_df, fast_meta = simulate_fast_alert_cycle(latest_df, fast_cfg, output_dir)
            _write_progress(progress_file, status="running", percent=85, stage="결과 저장", detail="fast alert 결과 파일을 저장합니다.")
            written = write_fast_alert_outputs(signal_df, decision_df, state_df, {**metadata, **fast_meta}, output_dir)
            if args.send_alerts:
                _write_progress(progress_file, status="running", percent=93, stage="알림 발송", detail="텔레그램/이메일 알림을 전송합니다.")
                alert_log_path = output_dir / "alert_log.csv"
                events = _build_alert_events(signal_df, decision_df, fast_cfg)
                notifiers = build_notifiers()
                dispatch_alerts(events, notifiers, alert_log_path)
                written["alert_log"] = alert_log_path
            for key, path in written.items():
                print(f"[saved] {key}={path}")
            _write_progress(progress_file, status="completed", percent=100, stage="완료", detail="fast alert 실행을 마쳤습니다.")
            _send_job_feedback(job_feedback_label, "completed")
            return

        _write_progress(progress_file, status="running", percent=25, stage="데이터 상태 점검", detail="데이터 상태 요약을 생성합니다.")
        health_paths = build_data_health(output_dir=output_dir)
        _write_progress(progress_file, status="running", percent=40, stage="전략 입력 준비", detail="전략 입력 프레임을 구성합니다.")
        strategy_df, metadata = prepare_strategy_frame(Path(args.feature), Path(args.fundamental), cfg)
        _write_progress(progress_file, status="running", percent=55, stage="연구실 산출물 생성", detail="조건 성과와 규칙 후보를 계산합니다.")
        research_overall, research_industry = build_condition_performance(strategy_df, cfg)
        rule_overall, rule_industry, rule_top = build_rule_candidates(strategy_df, cfg)
        _write_progress(progress_file, status="running", percent=72, stage="백테스트 계산", detail="전략 신호와 거래 로그를 시뮬레이션합니다.")
        signal_df, trade_df, decision_df, curve_df = simulate_signals(strategy_df, cfg)
        eval_df = evaluate_backtest(curve_df, trade_df)
        _write_progress(progress_file, status="running", percent=88, stage="결과 저장", detail="전략 산출물을 파일로 저장합니다.")
        written = write_strategy_outputs(
            signal_df=signal_df,
            trade_df=trade_df,
            decision_df=decision_df,
            curve_df=curve_df,
            eval_df=eval_df,
            research_overall=research_overall,
            research_industry=research_industry,
            rule_overall=rule_overall,
            rule_industry=rule_industry,
            rule_top=rule_top,
            metadata=metadata,
            cfg=cfg,
            output_dir=output_dir,
        )

        latest_summary = output_dir / "daily_close_summary_latest.txt"
        if not decision_df.empty:
            last = decision_df.sort_values("date").iloc[-1]
            latest_summary.write_text(last["summary_text"], encoding="utf-8")

        if args.send_alerts:
            _write_progress(progress_file, status="running", percent=95, stage="알림 발송", detail="텔레그램/이메일 알림을 전송합니다.")
            alert_log_path = output_dir / "alert_log.csv"
            events = _build_alert_events(signal_df, decision_df, cfg)
            notifiers = build_notifiers()
            dispatch_alerts(events, notifiers, alert_log_path)
            written["alert_log"] = alert_log_path

        print(f"[saved] data_health={health_paths['csv']}")
        for key, path in written.items():
            print(f"[saved] {key}={path}")
        _write_progress(progress_file, status="completed", percent=100, stage="완료", detail="전체 재계산을 마쳤습니다.")
        _send_job_feedback(job_feedback_label, "completed")
    except Exception as exc:
        _write_progress(progress_file, status="failed", percent=100, stage="실패", detail=f"{type(exc).__name__}: {exc}")
        _send_job_feedback(job_feedback_label, "failed", f"{type(exc).__name__}: {exc}")
        traceback.print_exc()
        raise


if __name__ == "__main__":
    main()

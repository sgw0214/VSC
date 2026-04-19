from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import traceback
from datetime import datetime, time
from pathlib import Path
from typing import List

import pandas as pd

from new_strategy.data_health import build_data_health
from new_strategy.dashboard_operational_snapshot import write_dashboard_operational_snapshot
from new_strategy.earnings_signal_engine import (
    EarningsStrategyConfig,
    build_condition_performance,
    build_rule_candidates,
    dedupe_signal_rows,
    default_inputs,
    default_output_dir,
    evaluate_backtest,
    prepare_latest_strategy_frame,
    prepare_strategy_frame,
    simulate_fast_alert_cycle,
    simulate_signals,
    sync_decision_summary,
    write_fast_alert_outputs,
    write_operational_latest_outputs,
    write_strategy_outputs,
)
from new_strategy.notifiers import AlertEvent, TelegramNotifier, build_notifiers, dispatch_alerts
from new_strategy.paths import data_path, output_path
from new_strategy.price_latest_snapshot import (
    PRICE_PANEL_INDUSTRY_SNAPSHOT_PATH,
    PRICE_SNAPSHOT_PATH,
    read_price_latest_snapshot,
    refresh_price_latest_snapshot,
    refresh_price_panel_industry_snapshot,
)
from new_strategy.refresh_runtime_data import run_refresh_pipeline
from new_strategy.telegram_bridge_tools import render_fast_trigger_image


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


def _dispatch_alerts_safely(
    *,
    signal_df: pd.DataFrame,
    decision_df: pd.DataFrame,
    cfg: EarningsStrategyConfig,
    output_dir: Path,
    alert_log_path: Path,
) -> Path | None:
    try:
        events = _build_alert_events(signal_df, decision_df, cfg, output_dir)
        notifiers = build_notifiers()
        dispatch_alerts(events, notifiers, alert_log_path)
        return alert_log_path
    except Exception as exc:
        print(f"[warn] alert_dispatch_failed={type(exc).__name__}: {exc}", file=sys.stderr)
        traceback.print_exc()
        return None


def _build_latest_only_cfg(cfg: EarningsStrategyConfig) -> EarningsStrategyConfig:
    return EarningsStrategyConfig(
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
        monthly_buy_threshold=cfg.monthly_buy_threshold,
        weekly_sell_threshold=cfg.weekly_sell_threshold,
    )


def _allowed_operational_chat_ids() -> set[str]:
    raw = os.getenv("NEW_STRATEGY_TELEGRAM_BRIDGE_ALLOWED_CHAT_IDS", "").strip()
    if not raw:
        raw = os.getenv("NEW_STRATEGY_TELEGRAM_CHAT_ID", "").strip()
    return {item.strip() for item in raw.split(",") if item.strip()}


def _load_real_holding_codes(output_dir: Path) -> set[str]:
    positions_path = output_dir / "telegram_bridge" / "manual_portfolio_positions.csv"
    if not positions_path.exists():
        return set()
    try:
        positions = pd.read_csv(positions_path, dtype={"code": str}, low_memory=False)
    except Exception:
        return set()
    if positions.empty or "code" not in positions.columns:
        return set()
    allowed_chat_ids = _allowed_operational_chat_ids()
    if allowed_chat_ids and "chat_id" in positions.columns:
        positions = positions[positions["chat_id"].astype(str).isin(allowed_chat_ids)].copy()
    if "quantity" in positions.columns:
        qty = pd.to_numeric(positions["quantity"], errors="coerce").fillna(0.0)
        positions = positions[qty > 0].copy()
    if positions.empty:
        return set()
    return set(positions["code"].astype(str).str.zfill(6))


def _load_latest_price_lookup(output_dir: Path) -> pd.DataFrame:
    snap = read_price_latest_snapshot(allow_refresh=False)
    if snap.empty:
        return pd.DataFrame(columns=["code", "close", "date"])
    snap = snap.copy()
    snap["code"] = snap["code"].astype(str).str.zfill(6)
    return snap


def _load_real_holding_snapshot(output_dir: Path) -> pd.DataFrame:
    positions_path = output_dir / "telegram_bridge" / "manual_portfolio_positions.csv"
    if not positions_path.exists():
        return pd.DataFrame()
    try:
        positions = pd.read_csv(positions_path, dtype={"code": str}, low_memory=False)
    except Exception:
        return pd.DataFrame()
    if positions.empty or "code" not in positions.columns:
        return pd.DataFrame()
    positions["code"] = positions["code"].astype(str).str.zfill(6)
    allowed_chat_ids = _allowed_operational_chat_ids()
    if allowed_chat_ids and "chat_id" in positions.columns:
        positions = positions[positions["chat_id"].astype(str).isin(allowed_chat_ids)].copy()
    if "quantity" in positions.columns:
        qty = pd.to_numeric(positions["quantity"], errors="coerce").fillna(0.0)
        positions = positions[qty > 0].copy()
    return positions


def _non_nan_float(value: object) -> float | None:
    try:
        numeric = float(value)
    except Exception:
        return None
    if pd.isna(numeric):
        return None
    return numeric


def _sell_price_hint(row: pd.Series, *, code: str, output_dir: Path) -> str:
    prices = _load_latest_price_lookup(output_dir)
    basis_price = None
    basis_label = "기준가"
    if not prices.empty:
        hit = prices[prices["code"] == code]
        if not hit.empty:
            basis_price = _non_nan_float(hit.iloc[-1].get("close"))
            date_val = hit.iloc[-1].get("date")
            if pd.notna(date_val):
                try:
                    basis_label = f"기준가 {pd.to_datetime(date_val).date()}"
                except Exception:
                    basis_label = "기준가"
    positions = _load_real_holding_snapshot(output_dir)
    entry_price = None
    if not positions.empty:
        pos = positions[positions["code"] == code]
        if not pos.empty:
            entry_price = _non_nan_float(pos.iloc[-1].get("avg_price"))
    weekly_ma = _non_nan_float(row.get("v2_week_ma")) or _non_nan_float(row.get("week_10_ma"))
    monthly_ma = _non_nan_float(row.get("v2_month_ma")) or _non_nan_float(row.get("month_10_ma"))
    parts: list[str] = []
    if basis_price is not None:
        parts.append(f"제안 매도가 {basis_price:,.0f}원({basis_label})")
    if entry_price is not None:
        parts.append(f"매수손절가 {entry_price * 0.90:,.0f}원")
    if weekly_ma is not None:
        parts.append(f"주이평손절가 {weekly_ma * 0.95:,.0f}원")
    if monthly_ma is not None:
        parts.append(f"월이평손절가 {monthly_ma * 0.95:,.0f}원")
    return " / ".join(parts)


def _refresh_optimal_ma_artifacts() -> dict[str, str]:
    backtest_cmd = [
        sys.executable,
        "-m",
        "new_strategy.ma_breakout_research.backtest_ma_breakout_modes",
        "--source",
        str(data_path("feature_daily.pkl")),
        "--out-dir",
        str(output_path("ma_breakout_research")),
        "--daily-range",
        "1-120",
        "--weekly-range",
        "1-120",
        "--monthly-range",
        "1-120",
        "--min-bars",
        "24",
    ]
    subprocess.run(backtest_cmd, check=True)
    from new_strategy.ma_breakout_research.publish_optimal_ma_selection import publish
    from new_strategy.optimal_ma_overlay import OVERLAY_SNAPSHOT_PATH, build_latest_optimal_ma_snapshot

    publish()
    snapshot_df = build_latest_optimal_ma_snapshot()
    return {
        "selection_path": str(output_path("ma_breakout_research", "published", "optimal_ma_selection_monthly_weekly.csv")),
        "snapshot_path": str(OVERLAY_SNAPSHOT_PATH),
        "snapshot_rows": str(len(snapshot_df)),
    }


def _build_alert_events(
    signal_df: pd.DataFrame,
    decision_df: pd.DataFrame,
    cfg: EarningsStrategyConfig,
    output_dir: Path,
) -> List[AlertEvent]:
    if signal_df.empty:
        return []
    latest_date = signal_df["date"].max()
    latest = signal_df[signal_df["date"] == latest_date].copy()
    now = datetime.now()
    execution_window = now.weekday() < 5 and time(8, 0) <= now.time() <= time(20, 0)
    # TRIGGER alerts must start only after the cash market open.
    # This prevents pre-open runs from sending stale previous-close prices
    # as if they were today's executable intraday levels.
    trigger_notification_window = now.weekday() < 5 and time(9, 0) <= now.time() <= time(20, 0)
    opening_window = now.weekday() < 5 and time(8, 0) <= now.time() <= time(8, 30)
    guide_col = "intraday_action_guide" if execution_window else "next_day_action_guide"
    held_codes = _load_real_holding_codes(output_dir)
    events: List[AlertEvent] = []
    trigger_rows = latest[latest["signal"].isin(["BUY", "SELL"])].copy()
    if not trigger_rows.empty:
        trigger_rows["code"] = trigger_rows["code"].astype(str).str.zfill(6)
        trigger_rows = trigger_rows[
            ((trigger_rows["signal"].astype(str).str.upper() == "SELL") & trigger_rows["code"].isin(held_codes))
            | ((trigger_rows["signal"].astype(str).str.upper() == "BUY") & (~trigger_rows["code"].isin(held_codes)))
        ].copy()
    trigger_image_path = ""
    trigger_caption = ""
    if trigger_notification_window and not trigger_rows.empty:
        slot_label = now.strftime("%H:%M")
        image_path, caption = render_fast_trigger_image(trigger_rows, slot_label=slot_label)
        trigger_image_path = "" if image_path is None else str(image_path)
        trigger_caption = caption

    if trigger_notification_window:
        for _, row in latest[latest["signal"].isin(["BUY", "SELL"])].iterrows():
            code = str(row["code"]).zfill(6)
            signal_value = str(row.get("signal") or "").upper()
            if signal_value == "SELL" and code not in held_codes:
                continue
            if signal_value == "BUY" and code in held_codes:
                continue
            alert_current_price = _non_nan_float(row.get("alert_current_price"))
            if alert_current_price is None:
                # No fallback: skip trigger when executable price is unavailable.
                continue
            reasons = [x for x in [row["reason_1"], row["reason_2"], row["reason_3"]] if isinstance(x, str) and x]
            guide = str(row.get(guide_col) or "").strip()
            opening_line = "Opening risk: 장 초반 매도 우선 점검 구간입니다." if opening_window and signal_value == "SELL" else ""
            sell_hint = _sell_price_hint(row, code=code, output_dir=output_dir) if signal_value == "SELL" else ""
            message = "\n".join(
                [
                    f"Signal date: {pd.Timestamp(row['date']).date()}",
                    f"Signal: {signal_value}",
                    f"Risk flag: {row['risk_flag'] or '위험없음'}",
                    *([opening_line] if opening_line else []),
                    *([f"Action guide: {guide}"] if guide else []),
                    *([f"Price guide: {sell_hint}"] if sell_hint else []),
                    *[f"- {reason}" for reason in reasons[:3]],
                ]
            )
            events.append(
                AlertEvent(
                    event_type="TRIGGER",
                    event_time=now,
                    signal_date=str(pd.Timestamp(row["date"]).date()),
                    code=code,
                    name=str(row["name"]),
                    signal=signal_value,
                    strategy_id=str(row["strategy_id"]),
                    conviction_score=float(row["conviction_score"]),
                    message=message,
                    current_price=alert_current_price,
                    low_price=_non_nan_float(row.get("alert_low_price")),
                    entry_price=_non_nan_float(row.get("alert_entry_price")),
                    weekly_ma=_non_nan_float(row.get("alert_weekly_ma")),
                    weekly_trigger_price=_non_nan_float(row.get("alert_weekly_trigger_price")),
                    monthly_ma=_non_nan_float(row.get("alert_monthly_ma")),
                    stop_loss_price=_non_nan_float(row.get("alert_stop_loss_price")),
                    exit_reason=str(row.get("alert_exit_reason") or ""),
                    position_source=str(row.get("alert_position_source") or ""),
                    quote_time="" if pd.isna(row.get("alert_quote_time")) else str(row.get("alert_quote_time")),
                    image_path=trigger_image_path if execution_window else "",
                    caption=trigger_caption if execution_window else "",
                )
            )

    if not decision_df.empty and not execution_window:
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
    p.add_argument("--daily-latest", action="store_true")
    p.add_argument("--refresh-optimal-ma", action="store_true")
    p.add_argument("--refresh-data", action="store_true")
    p.add_argument("--refresh-data-only", action="store_true")
    p.add_argument("--refresh-stock-end-date", default="")
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
                rebuild_feature_after_refresh=not args.refresh_data_only,
                stock_end=(str(args.refresh_stock_end_date).strip() or None),
            )
            print(f"[refresh] meta={refresh_meta['refresh_meta']}")
        else:
            _write_progress(progress_file, status="running", percent=10, stage="데이터 확인", detail="기존 최신 데이터를 사용합니다.")

        _write_progress(progress_file, status="running", percent=18, stage="가격 스냅샷 갱신", detail="대시보드/브리지용 최신 가격 스냅샷을 정리합니다.")
        latest_price_snapshot = refresh_price_latest_snapshot(force=False)
        print(f"[price_snapshot] rows={len(latest_price_snapshot)} path={PRICE_SNAPSHOT_PATH}")
        latest_price_industry_snapshot = refresh_price_panel_industry_snapshot(force=False)
        print(f"[price_industry_snapshot] rows={len(latest_price_industry_snapshot)} path={PRICE_PANEL_INDUSTRY_SNAPSHOT_PATH}")

        if args.refresh_data_only:
            _write_progress(progress_file, status="completed", percent=100, stage="완료", detail="주가 원천/price panel 경량 갱신을 마쳤습니다.")
            _send_job_feedback(job_feedback_label, "completed")
            return

        if args.refresh_optimal_ma:
            _write_progress(progress_file, status="running", percent=25, stage="최적 MA 산출", detail="최적 MA 백테스트와 published snapshot을 갱신합니다.")
            optimal_meta = _refresh_optimal_ma_artifacts()
            print(f"[optimal_ma] {optimal_meta}")

        if args.fast_alerts:
            _write_progress(progress_file, status="running", percent=40, stage="최신 프레임 준비", detail="장중/장후 fast alert 입력셋을 준비합니다.")
            fast_cfg = _build_latest_only_cfg(cfg)
            live_quotes_path = Path(args.live_quotes) if args.live_quotes else None
            latest_df, metadata = prepare_latest_strategy_frame(
                Path(args.feature),
                Path(args.fundamental),
                fast_cfg,
                live_quotes_path=live_quotes_path,
            )
            _write_progress(progress_file, status="running", percent=65, stage="fast alert 계산", detail="최신 신호와 의사결정을 계산합니다.")
            signal_df, decision_df, state_df, fast_meta = simulate_fast_alert_cycle(latest_df, fast_cfg, output_dir)
            signal_df = dedupe_signal_rows(signal_df)
            decision_df = sync_decision_summary(decision_df, signal_df)
            _write_progress(progress_file, status="running", percent=85, stage="결과 저장", detail="fast alert 결과 파일을 저장합니다.")
            written = write_fast_alert_outputs(signal_df, decision_df, state_df, {**metadata, **fast_meta}, output_dir)
            try:
                written["dashboard_execution_snapshot"] = write_dashboard_operational_snapshot(
                    execution_window=True,
                    output_dir=output_dir,
                )
            except Exception as exc:
                print(f"[warn] dashboard_execution_snapshot={type(exc).__name__}: {exc}")
            if args.send_alerts:
                _write_progress(progress_file, status="running", percent=93, stage="알림 발송", detail="텔레그램/이메일 알림을 전송합니다.")
                alert_log_path = output_dir / "alert_log.csv"
                sent_path = _dispatch_alerts_safely(
                    signal_df=signal_df,
                    decision_df=decision_df,
                    cfg=fast_cfg,
                    output_dir=output_dir,
                    alert_log_path=alert_log_path,
                )
                if sent_path is not None:
                    written["alert_log"] = sent_path
            for key, path in written.items():
                print(f"[saved] {key}={path}")
            _write_progress(progress_file, status="completed", percent=100, stage="완료", detail="fast alert 실행을 마쳤습니다.")
            _send_job_feedback(job_feedback_label, "completed")
            return

        if args.daily_latest:
            _write_progress(progress_file, status="running", percent=40, stage="최신 프레임 준비", detail="장후 최신 의사결정 입력셋을 준비합니다.")
            latest_cfg = _build_latest_only_cfg(cfg)
            latest_df, metadata = prepare_latest_strategy_frame(
                Path(args.feature),
                Path(args.fundamental),
                latest_cfg,
                live_quotes_path=None,
            )
            _write_progress(progress_file, status="running", percent=65, stage="장후 최신 판단", detail="고정 최적 MA 기준으로 최신 의사결정을 계산합니다.")
            signal_df, decision_df, state_df, latest_meta = simulate_fast_alert_cycle(latest_df, latest_cfg, output_dir)
            signal_df = dedupe_signal_rows(signal_df)
            decision_df = sync_decision_summary(decision_df, signal_df)
            _write_progress(progress_file, status="running", percent=85, stage="결과 저장", detail="일일 최신 의사결정 결과를 저장합니다.")
            written = write_operational_latest_outputs(
                signal_df=signal_df,
                decision_df=decision_df,
                state_df=state_df,
                metadata={**metadata, **latest_meta, "fast_mode": False, "daily_latest_mode": True},
                cfg=latest_cfg,
                output_dir=output_dir,
            )
            try:
                written["dashboard_postclose_snapshot"] = write_dashboard_operational_snapshot(
                    execution_window=False,
                    output_dir=output_dir,
                )
            except Exception as exc:
                print(f"[warn] dashboard_postclose_snapshot={type(exc).__name__}: {exc}")
            latest_summary = output_dir / "daily_close_summary_latest.txt"
            if not decision_df.empty:
                last = decision_df.sort_values("date").iloc[-1]
                latest_summary.write_text(str(last.get("summary_text") or ""), encoding="utf-8")
                written["daily_summary_latest"] = latest_summary
            if args.send_alerts:
                _write_progress(progress_file, status="running", percent=93, stage="알림 발송", detail="텔레그램/이메일 알림을 전송합니다.")
                alert_log_path = output_dir / "alert_log.csv"
                sent_path = _dispatch_alerts_safely(
                    signal_df=signal_df,
                    decision_df=decision_df,
                    cfg=latest_cfg,
                    output_dir=output_dir,
                    alert_log_path=alert_log_path,
                )
                if sent_path is not None:
                    written["alert_log"] = sent_path
            for key, path in written.items():
                print(f"[saved] {key}={path}")
            _write_progress(progress_file, status="completed", percent=100, stage="완료", detail="일일 최신 의사결정 갱신을 마쳤습니다.")
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
        signal_df = dedupe_signal_rows(signal_df)
        decision_df = sync_decision_summary(decision_df, signal_df)
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
        try:
            written["dashboard_postclose_snapshot"] = write_dashboard_operational_snapshot(
                execution_window=False,
                output_dir=output_dir,
            )
        except Exception as exc:
            print(f"[warn] dashboard_postclose_snapshot={type(exc).__name__}: {exc}")

        latest_summary = output_dir / "daily_close_summary_latest.txt"
        if not decision_df.empty:
            last = decision_df.sort_values("date").iloc[-1]
            latest_summary.write_text(last["summary_text"], encoding="utf-8")

        if args.send_alerts:
            _write_progress(progress_file, status="running", percent=95, stage="알림 발송", detail="텔레그램/이메일 알림을 전송합니다.")
            alert_log_path = output_dir / "alert_log.csv"
            sent_path = _dispatch_alerts_safely(
                signal_df=signal_df,
                decision_df=decision_df,
                cfg=cfg,
                output_dir=output_dir,
                alert_log_path=alert_log_path,
            )
            if sent_path is not None:
                written["alert_log"] = sent_path

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

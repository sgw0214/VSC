from __future__ import annotations

import json
import os
import re
import io
import requests
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Dict, Optional

import holidays
import pandas as pd

from new_strategy.build_feature_dataset import build_feature_dataset, build_feature_dataset_incremental
from new_strategy.build_market_db import (
    _connect,
    create_tables,
    load_fundamental,
    load_macro,
    load_price,
)
from new_strategy.build_price_panel import build_panel, save_panel
from new_strategy.fetch_macro_investing import build_macro
from new_strategy.gold_kr_api import update_gold_excel_daily
from new_strategy.kiwoom_rest_client import fetch_current_quotes
from new_strategy.macro_pipeline import build_macro_features
from new_strategy.merge_gold_to_macro import merge_gold_into_macro
from new_strategy.paths import cache_path, data_path, output_path, stock_root, strategy_output_path
from new_strategy.update_yearly_stock_files import update_yearly_files


DEFAULT_KRX_AUTH_KEY = "A85FD6442B6D45BFADFD66B9581B4A13C04C729A"
YEAR_FILE_RE = re.compile(r"^(20\d{2})\.xlsx$")
KRX_ENDPOINT = "https://data-dbg.krx.co.kr/svc/apis/sto/stk_bydd_trd"


def _krx_auth_key() -> str:
    return os.getenv("NEW_STRATEGY_KRX_AUTH_KEY", DEFAULT_KRX_AUTH_KEY)


def _latest_basic_date(stock_dir: Path) -> Optional[str]:
    dates = []
    for path in stock_dir.glob("basic_*.xlsx"):
        m = re.match(r"basic_(\d{8})\.xlsx$", path.name)
        if m:
            dates.append(m.group(1))
    return max(dates) if dates else None


@lru_cache(maxsize=8)
def _kr_public_holidays(year: int) -> set:
    return set(holidays.country_holidays("KR", years=[year]).keys())


def _is_kr_trading_day(dt: datetime) -> bool:
    if dt.weekday() >= 5:
        return False
    return dt.date() not in _kr_public_holidays(dt.year)


def _previous_kr_trading_day_yyyymmdd(base: Optional[datetime] = None) -> str:
    current = (base or datetime.now()) - timedelta(days=1)
    while not _is_kr_trading_day(current):
        current -= timedelta(days=1)
    return current.strftime("%Y%m%d")


def _year_range(stock_dir: Path, fallback_start: int = 2015) -> tuple[int, int]:
    years = []
    for path in stock_dir.glob("*.xlsx"):
        m = YEAR_FILE_RE.match(path.name)
        if m:
            years.append(int(m.group(1)))
    if not years:
        return fallback_start, fallback_start
    return min(years), max(years)


def _load_price_tail_map(price_panel_path: Path) -> pd.DataFrame:
    df = pd.read_csv(
        price_panel_path,
        usecols=[
            "date",
            "code",
            "name",
            "market",
            "industry",
            "close",
            "market_cap",
            "shares_outstanding",
            "is_trading_day",
        ],
        dtype={"code": str},
        low_memory=False,
    )
    if df.empty:
        return df
    df["code"] = df["code"].astype(str).str.zfill(6)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).sort_values(["code", "date"])
    return df.groupby("code", as_index=False).tail(1).copy()


def _recalc_market_cap(close: pd.Series, shares: pd.Series, fallback: pd.Series) -> pd.Series:
    out = close * shares
    return out.where(shares.notna(), fallback)


def _fetch_krx_daily_rows(trade_date: str) -> pd.DataFrame:
    headers = {
        "AUTH_KEY": _krx_auth_key(),
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0",
    }
    params = {"basDd": trade_date.replace("-", "")}
    resp = requests.get(KRX_ENDPOINT, headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    payload = resp.json()
    rows = payload.get("OutBlock_1", [])
    if not rows:
        return pd.DataFrame()
    df = pd.json_normalize(rows)
    if df.empty:
        return df

    rename_map = {
        "BAS_DD": "date",
        "basDd": "date",
        "ISU_CD": "code",
        "ISU_NM": "name",
        "MKT_NM": "market",
        "SECT_TP_NM": "industry",
        "TDD_CLSPRC": "close",
        "TDD_OPNPRC": "open",
        "TDD_HGPRC": "high",
        "TDD_LWPRC": "low",
        "ACC_TRDVOL": "volume",
        "ACC_TRDVAL": "trading_value",
        "MKTCAP": "market_cap",
        "LIST_SHRS": "shares_outstanding",
    }
    df = df.rename(columns=rename_map)
    for col in ["date", "code", "name", "market", "industry"]:
        if col not in df.columns:
            df[col] = None
    for col in ["close", "open", "high", "low", "volume", "trading_value", "market_cap", "shares_outstanding"]:
        if col not in df.columns:
            df[col] = None
        df[col] = pd.to_numeric(df[col].astype(str).str.replace(",", "", regex=False), errors="coerce")

    df["date"] = pd.to_datetime(df["date"].astype(str), format="%Y%m%d", errors="coerce")
    df["code"] = df["code"].astype(str).str.replace(".0", "", regex=False).str.zfill(6)
    df["market"] = df["market"].fillna("KOSPI")
    df["industry"] = df["industry"].fillna("")
    df["is_trading_day"] = True
    return df[
        [
            "date",
            "code",
            "name",
            "market",
            "industry",
            "close",
            "open",
            "high",
            "low",
            "volume",
            "trading_value",
            "market_cap",
            "shares_outstanding",
            "is_trading_day",
        ]
    ].copy()


def refresh_price_panel_via_kiwoom_eod(
    price_panel_path: Path,
    *,
    min_coverage_ratio: float = 0.70,
    per_request_sleep_seconds: float = 0.22,
    recent_backfill_days: int = 14,
) -> Dict[str, object]:
    if not price_panel_path.exists():
        raise FileNotFoundError(f"price panel not found: {price_panel_path}")

    tail = _load_price_tail_map(price_panel_path)
    if tail.empty:
        raise RuntimeError("price panel has no rows; cannot perform kiwoom EOD refresh")

    codes = tail["code"].dropna().astype(str).str.zfill(6).tolist()
    prev_latest = str(tail["date"].max().date())
    quotes = fetch_current_quotes(codes, per_request_sleep_seconds=per_request_sleep_seconds)
    if quotes.empty:
        raise RuntimeError("Kiwoom EOD returned no quotes")

    quotes["date"] = pd.to_datetime(quotes["date"], errors="coerce")
    quotes = quotes.dropna(subset=["date", "code", "close"]).copy()
    if quotes.empty:
        raise RuntimeError("Kiwoom EOD quotes had no usable rows")

    target_date = str(quotes["date"].max().date())
    latest_quotes = quotes.loc[quotes["date"] == quotes["date"].max()].copy()
    latest_quotes["code"] = latest_quotes["code"].astype(str).str.zfill(6)
    kiwoom_quote_rows = int(len(latest_quotes))
    coverage_ratio = len(latest_quotes) / max(len(codes), 1)

    tail["code"] = tail["code"].astype(str).str.zfill(6)
    merged = latest_quotes.merge(
        tail[["code", "name", "market", "industry", "market_cap", "shares_outstanding", "is_trading_day"]],
        on="code",
        how="left",
        suffixes=("", "_prev"),
    )
    merged["name"] = merged["name"].combine_first(merged["name_prev"])
    merged["market"] = merged["market"].fillna("KOSPI")
    merged["industry"] = merged["industry"].combine_first(pd.Series(index=merged.index, dtype="object"))
    merged["shares_outstanding"] = pd.to_numeric(merged["shares_outstanding"], errors="coerce")
    merged["market_cap"] = _recalc_market_cap(
        pd.to_numeric(merged["close"], errors="coerce"),
        merged["shares_outstanding"],
        pd.to_numeric(merged["market_cap"], errors="coerce"),
    )
    merged["is_trading_day"] = True
    target_rows = merged[
        [
            "date",
            "code",
            "name",
            "market",
            "industry",
            "close",
            "open",
            "high",
            "low",
            "volume",
            "trading_value",
            "market_cap",
            "shares_outstanding",
            "is_trading_day",
        ]
    ].copy()

    missing_codes = sorted(set(codes) - set(target_rows["code"].astype(str)))
    krx_fallback_rows = 0
    krx_fallback_used = False
    if missing_codes:
        try:
            krx_df = _fetch_krx_daily_rows(target_date)
            if not krx_df.empty:
                krx_missing = krx_df[krx_df["code"].astype(str).isin(missing_codes)].copy()
                if not krx_missing.empty:
                    krx_fallback_rows = int(len(krx_missing))
                    krx_fallback_used = True
                    target_rows = (
                        pd.concat([target_rows, krx_missing], ignore_index=True)
                        .drop_duplicates(subset=["date", "code"], keep="first")
                        .reset_index(drop=True)
                    )
        except Exception:
            pass

    final_coverage_ratio = len(target_rows) / max(len(codes), 1)
    if final_coverage_ratio < min_coverage_ratio:
        raise RuntimeError(
            f"Kiwoom EOD coverage too low after KRX fallback: {len(target_rows)}/{len(codes)} ({final_coverage_ratio:.1%})"
        )

    price_df = pd.read_csv(price_panel_path, dtype={"code": str}, low_memory=False)
    price_df["code"] = price_df["code"].astype(str).str.zfill(6)
    price_df["date"] = pd.to_datetime(price_df["date"], errors="coerce")
    backfill_rows = pd.DataFrame(columns=target_rows.columns)
    backfill_dates: list[str] = []
    if recent_backfill_days > 0:
        target_dt = pd.to_datetime(target_date, errors="coerce")
        if pd.notna(target_dt):
            present_dates = set(price_df["date"].dropna().dt.date.unique().tolist())
            # Target date is already included via Kiwoom/KRX fallback rows.
            present_dates.add(target_dt.date())
            cursor = (target_dt - timedelta(days=max(1, int(recent_backfill_days)))).date()
            while cursor <= target_dt.date():
                probe = datetime(cursor.year, cursor.month, cursor.day)
                if _is_kr_trading_day(probe) and cursor not in present_dates:
                    day_iso = cursor.isoformat()
                    try:
                        krx_day = _fetch_krx_daily_rows(day_iso)
                        if not krx_day.empty:
                            backfill_rows = pd.concat([backfill_rows, krx_day], ignore_index=True)
                            backfill_dates.append(day_iso)
                    except Exception:
                        pass
                cursor += timedelta(days=1)
    rows_to_append = target_rows if backfill_rows.empty else pd.concat([target_rows, backfill_rows], ignore_index=True)
    combined = (
        pd.concat([price_df, rows_to_append], ignore_index=True)
        .dropna(subset=["date", "code", "close"])
        .drop_duplicates(subset=["date", "code"], keep="last")
        .sort_values(["date", "code"])
        .reset_index(drop=True)
    )
    combined.to_csv(price_panel_path, index=False, encoding="utf-8-sig")
    bounds = {
        "date_min": str(combined["date"].min().date()) if not combined.empty else None,
        "date_max": str(combined["date"].max().date()) if not combined.empty else None,
        "rows": int(len(combined)),
        "codes": int(combined["code"].nunique()) if not combined.empty else 0,
    }
    _write_bounds_meta(price_panel_path, bounds)
    return {
        "source": "kiwoom_eod",
        "price_before": prev_latest,
        "price_after": target_date,
        "kiwoom_quote_rows": kiwoom_quote_rows,
        "quote_rows": int(len(target_rows)),
        "universe_codes": int(len(codes)),
        "coverage_ratio": float(final_coverage_ratio),
        "kiwoom_coverage_ratio": float(coverage_ratio),
        "krx_fallback_used": krx_fallback_used,
        "krx_fallback_rows": krx_fallback_rows,
        "krx_backfill_days": int(len(backfill_dates)),
        "krx_backfill_dates": backfill_dates,
        "krx_backfill_rows": int(len(backfill_rows)),
        "price_bounds": bounds,
    }


def _date_bounds_from_csv(path: Path) -> Dict[str, Optional[str]]:
    if not path.exists():
        return {"date_min": None, "date_max": None, "rows": 0}
    df = pd.read_csv(path, usecols=["date"], low_memory=False)
    if df.empty:
        return {"date_min": None, "date_max": None, "rows": 0}
    dates = pd.to_datetime(df["date"], errors="coerce").dropna()
    return {
        "date_min": None if dates.empty else str(dates.min().date()),
        "date_max": None if dates.empty else str(dates.max().date()),
        "rows": int(len(df)),
    }


def _bounds_meta_path(path: Path) -> Path:
    return path.with_name(f"{path.stem}_meta.json")


def _write_bounds_meta(path: Path, bounds: Dict[str, Optional[str]]) -> None:
    meta_path = _bounds_meta_path(path)
    payload = {
        "source_path": str(path),
        "source_mtime_ns": path.stat().st_mtime_ns if path.exists() else None,
        "bounds": bounds,
    }
    meta_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_bounds(path: Path) -> Dict[str, Optional[str]]:
    meta_path = _bounds_meta_path(path)
    if path.exists() and meta_path.exists():
        try:
            payload = json.loads(meta_path.read_text(encoding="utf-8"))
            if payload.get("source_mtime_ns") == path.stat().st_mtime_ns:
                bounds = payload.get("bounds", {})
                return {
                    "date_min": bounds.get("date_min"),
                    "date_max": bounds.get("date_max"),
                    "rows": int(bounds.get("rows", 0)),
                }
        except Exception:
            pass
    bounds = _date_bounds_from_csv(path)
    if path.exists():
        _write_bounds_meta(path, bounds)
    return bounds


def refresh_stock_raw(
    stock_dir: Path,
    fallback_start: str = "20150101",
    end: Optional[str] = None,
    sleep_sec: float = 0.4,
    retry: int = 3,
) -> Dict[str, Optional[str]]:
    import new_strategy.krx_api as krx_api

    before = _latest_basic_date(stock_dir)
    original_save_dir = krx_api.SAVE_DIR
    try:
        krx_api.SAVE_DIR = str(stock_dir)
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            krx_api.fetch_and_save_by_day_auto(
                auth_key=_krx_auth_key(),
                fallback_start=fallback_start,
                end=end or datetime.today().strftime("%Y%m%d"),
                sleep_sec=sleep_sec,
                retry=retry,
            )
    finally:
        krx_api.SAVE_DIR = original_save_dir
    after = _latest_basic_date(stock_dir)
    return {"basic_before": before, "basic_after": after}


def refresh_gold_daily(
    end: Optional[str] = None,
    fallback_start: str = "20160101",
    sleep_sec: float = 0.4,
    retry: int = 3,
) -> Dict[str, Optional[str]]:
    gold_path = data_path("gold_kr_daily.xlsx")
    before = None
    if gold_path.exists():
        try:
            before_df = pd.read_excel(gold_path, usecols=["일자"])
            before_dates = pd.to_datetime(before_df["일자"].astype(str), format="%Y%m%d", errors="coerce").dropna()
            before = None if before_dates.empty else str(before_dates.max().date())
        except Exception:
            before = None

    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        update_gold_excel_daily(
            auth_key=_krx_auth_key(),
            fallback_start=fallback_start,
            end=end or datetime.today().strftime("%Y%m%d"),
            sleep_sec=sleep_sec,
            retry=retry,
        )

    after = None
    if gold_path.exists():
        try:
            after_df = pd.read_excel(gold_path, usecols=["일자"])
            after_dates = pd.to_datetime(after_df["일자"].astype(str), format="%Y%m%d", errors="coerce").dropna()
            after = None if after_dates.empty else str(after_dates.max().date())
        except Exception:
            after = None
    return {"gold_before": before, "gold_after": after}


def refresh_macro_bundle(
    price_panel_path: Path,
    refresh_gold: bool = False,
) -> Dict[str, object]:
    macro_path = data_path("macro_daily.csv")
    gold_path = data_path("gold_kr_daily.xlsx")
    regime_path = data_path("macro_regime_v3_rec.csv")
    today = datetime.today().strftime("%Y-%m-%d")

    build_macro(
        start="2015-01-01",
        end=today,
        output=macro_path,
        price_panel=price_panel_path,
        merge_existing=True,
        allow_local_proxy=True,
    )
    if gold_path.exists():
        merge_gold_into_macro(macro_path, gold_path, macro_path)
    elif refresh_gold:
        raise FileNotFoundError(f"gold file not found after refresh: {gold_path}")

    raw_macro = pd.read_csv(macro_path)
    regime_df = build_macro_features(raw_macro)
    regime_df.to_csv(regime_path, index=False, encoding="utf-8-sig")
    coverage = regime_df.attrs.get("coverage_report")
    coverage_path = data_path("macro_coverage_report.csv")
    if coverage is not None:
        coverage.to_csv(coverage_path, index=False, encoding="utf-8-sig")

    return {
        "macro_daily": str(macro_path),
        "macro_regime": str(regime_path),
        "macro_bounds": _date_bounds_from_csv(macro_path),
    }


def rebuild_price_panel_from_yearly(stock_dir: Path) -> Dict[str, object]:
    start_year, end_year = _year_range(stock_dir)
    panel = build_panel(
        stock_dir=stock_dir,
        start_year=start_year,
        end_year=end_year,
        market="KOSPI",
        trading_only=True,
        cache_dir=cache_path("yearly"),
        use_cache=True,
    )
    price_panel_path = data_path("price_panel.csv")
    save_panel(panel, price_panel_path)
    bounds = {
        "date_min": str(panel["date"].min().date()) if not panel.empty else None,
        "date_max": str(panel["date"].max().date()) if not panel.empty else None,
        "rows": int(len(panel)),
        "codes": int(panel["code"].nunique()) if not panel.empty else 0,
    }
    _write_bounds_meta(price_panel_path, bounds)
    return {
        "price_panel": str(price_panel_path),
        "start_year": start_year,
        "end_year": end_year,
        "price_bounds": bounds,
    }


def rebuild_feature_and_optional_db(
    stock_dir: Path,
    rebuild_feature: bool = True,
    rebuild_db: bool = False,
    prefer_incremental: bool = False,
) -> Dict[str, object]:
    price_panel_path = data_path("price_panel.csv")
    macro_regime_path = data_path("macro_regime_v3_rec.csv")
    fundamental_path = data_path("fundamental_quarterly_multi.csv")
    feature_path = data_path("feature_daily.csv")

    out: Dict[str, object] = {"feature": str(feature_path)}
    if rebuild_feature or not feature_path.exists():
        if prefer_incremental and feature_path.with_suffix(".pkl").exists():
            feature_df = build_feature_dataset_incremental(
                price_path=price_panel_path,
                macro_path=macro_regime_path,
                fund_path=fundamental_path,
                output_path=feature_path,
                history_rows=140,
                write_csv=True,
                write_pickle=True,
                write_parquet=False,
            )
            out["feature_incremental"] = True
        else:
            feature_df = build_feature_dataset(
                price_path=price_panel_path,
                macro_path=macro_regime_path,
                fund_path=fundamental_path,
                output_path=feature_path,
            )
            out["feature_incremental"] = False
        out["feature_bounds"] = {
            "date_min": str(feature_df["date"].min().date()) if not feature_df.empty else None,
            "date_max": str(feature_df["date"].max().date()) if not feature_df.empty else None,
            "rows": int(len(feature_df)),
            "codes": int(feature_df["code"].nunique()) if not feature_df.empty else 0,
        }
        _write_bounds_meta(feature_path, out["feature_bounds"])
        out["feature_rebuilt"] = True
    else:
        out["feature_bounds"] = _load_bounds(feature_path)
        out["feature_rebuilt"] = False

    if rebuild_db:
        db_path = data_path("market_data.db")
        conn = _connect(db_path)
        try:
            create_tables(conn)
            start_year, end_year = _year_range(stock_dir)
            price = build_panel(
                stock_dir=stock_dir,
                start_year=start_year,
                end_year=end_year,
                market="KOSPI",
                trading_only=True,
                cache_dir=cache_path("yearly"),
                use_cache=True,
            )
            load_price(conn, price, source=f"xlsx:{stock_dir}/{start_year}..{end_year}")
            load_macro(conn, data_path("macro_daily.csv"), source=f"csv:{data_path('macro_daily.csv')}")
            load_fundamental(conn, fundamental_path, source=f"csv:{fundamental_path}")
            cur = conn.cursor()
            out["db"] = str(db_path)
            out["db_counts"] = {
                "symbols": int(cur.execute("SELECT COUNT(*) FROM dim_symbol").fetchone()[0]),
                "price": int(cur.execute("SELECT COUNT(*) FROM fact_price_daily").fetchone()[0]),
                "macro": int(cur.execute("SELECT COUNT(*) FROM fact_macro_daily").fetchone()[0]),
                "fundamental": int(cur.execute("SELECT COUNT(*) FROM fact_fundamental_quarterly").fetchone()[0]),
            }
        finally:
            conn.close()

    return out


def run_refresh_pipeline(
    refresh_stock: bool = True,
    refresh_macro: bool = False,
    refresh_gold: bool = False,
    rebuild_db: bool = False,
    prefer_kiwoom_eod: bool = False,
    rebuild_feature_after_refresh: bool = True,
    stock_end: Optional[str] = None,
) -> Dict[str, object]:
    stock_dir = stock_root()
    meta: Dict[str, object] = {
        "run_started_at": datetime.now().isoformat(),
        "stock_dir": str(stock_dir),
    }
    price_panel_path = data_path("price_panel.csv")
    feature_path = data_path("feature_daily.csv")
    existing_price_bounds = _load_bounds(price_panel_path)
    existing_feature_bounds = _load_bounds(feature_path)
    price_rebuilt = False
    macro_rebuilt = False

    if refresh_stock:
        kiwoom_used = False
        if prefer_kiwoom_eod and price_panel_path.exists():
            try:
                meta["price_panel"] = refresh_price_panel_via_kiwoom_eod(price_panel_path)
                meta["stock_refresh_source"] = "kiwoom_eod"
                price_rebuilt = True
                kiwoom_used = True
            except Exception as exc:
                meta["kiwoom_eod_error"] = str(exc)

        if kiwoom_used:
            latest_basic_before = _latest_basic_date(stock_dir)
            target_basic = (str(stock_end).strip() if stock_end else "") or _previous_kr_trading_day_yyyymmdd()
            needs_krx_reconcile = (latest_basic_before is None) or (latest_basic_before < target_basic)
            if needs_krx_reconcile:
                meta["stock_raw"] = refresh_stock_raw(stock_dir=stock_dir, end=target_basic)
                meta["stock_raw"]["reconcile_target"] = target_basic
                meta["stock_raw"]["reconcile_trigger"] = "refresh_data_with_kiwoom"
            else:
                meta["stock_raw"] = {
                    "basic_before": latest_basic_before,
                    "basic_after": latest_basic_before,
                    "reconcile_target": target_basic,
                    "reconcile_trigger": "refresh_data_with_kiwoom",
                    "skipped": True,
                }

        if not kiwoom_used:
            meta["stock_raw"] = refresh_stock_raw(stock_dir=stock_dir, end=stock_end)
            latest_basic = meta["stock_raw"]["basic_after"]
            latest_basic_iso = None
            if latest_basic:
                latest_basic_iso = f"{latest_basic[:4]}-{latest_basic[4:6]}-{latest_basic[6:8]}"
            needs_price_rebuild = (not price_panel_path.exists()) or (latest_basic_iso != existing_price_bounds["date_max"])
            meta["price_rebuild_needed"] = needs_price_rebuild
            if needs_price_rebuild:
                update_yearly_files(stock_dir)
                meta["price_panel"] = rebuild_price_panel_from_yearly(stock_dir)
                price_rebuilt = True
                meta["stock_refresh_source"] = "krx_raw"
            else:
                meta["price_panel"] = {
                    "price_panel": str(price_panel_path),
                    "start_year": _year_range(stock_dir)[0],
                    "end_year": _year_range(stock_dir)[1],
                    "price_bounds": existing_price_bounds,
                    "skipped_rebuild": True,
                }
                meta["stock_refresh_source"] = "krx_raw"

    if refresh_gold:
        meta["gold"] = refresh_gold_daily()

    if refresh_macro or refresh_gold:
        meta["macro"] = refresh_macro_bundle(
            price_panel_path=data_path("price_panel.csv"),
            refresh_gold=refresh_gold,
        )
        macro_rebuilt = True

    latest_price_max = None
    latest_feature_max = existing_feature_bounds["date_max"]
    if "price_panel" in meta and isinstance(meta["price_panel"], dict):
        latest_price_max = meta["price_panel"].get("price_bounds", {}).get("date_max")
    if latest_price_max is None:
        latest_price_max = existing_price_bounds["date_max"]
    feature_rebuild_needed = (
        not feature_path.exists()
        or price_rebuilt
        or macro_rebuilt
        or (latest_price_max is not None and latest_price_max != latest_feature_max)
    )
    meta["feature_rebuild_needed"] = feature_rebuild_needed
    meta["feature_rebuild_skipped"] = bool(feature_rebuild_needed and not rebuild_feature_after_refresh)

    if rebuild_feature_after_refresh or rebuild_db:
        meta["feature"] = rebuild_feature_and_optional_db(
            stock_dir=stock_dir,
            rebuild_feature=feature_rebuild_needed if rebuild_feature_after_refresh else False,
            rebuild_db=rebuild_db,
            prefer_incremental=feature_rebuild_needed and not macro_rebuilt,
        )
    else:
        meta["feature"] = {
            "feature": str(feature_path),
            "feature_bounds": existing_feature_bounds,
            "feature_rebuilt": False,
            "feature_incremental": False,
            "skipped": True,
        }
    meta["run_finished_at"] = datetime.now().isoformat()

    refresh_meta_path = strategy_output_path("refresh_runtime_metadata.json")
    refresh_meta_path.parent.mkdir(parents=True, exist_ok=True)
    refresh_meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    meta["refresh_meta"] = str(refresh_meta_path)
    return meta

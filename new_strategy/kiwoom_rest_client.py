from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd
import requests

from new_strategy.paths import data_path


def _default_kiwoom_api_root() -> Path:
    base = Path.home() / "OneDrive" / "python"
    if not base.exists():
        raise FileNotFoundError(f"Kiwoom base directory not found: {base}")
    for candidate in base.iterdir():
        if not candidate.is_dir():
            continue
        try:
            has_appkey = any(candidate.glob("*appkey.txt"))
            has_secret = any(candidate.glob("*secretkey.txt"))
            if has_appkey and has_secret:
                return candidate
        except OSError:
            continue
    raise FileNotFoundError(f"Could not locate Kiwoom API directory under {base}")


DEFAULT_KIWOOM_API_ROOT = _default_kiwoom_api_root()
TOKEN_CACHE_NAME = "domestic_token_cache.json"


@dataclass
class KiwoomRestConfig:
    api_root: Path = DEFAULT_KIWOOM_API_ROOT
    production_base_url: str = "https://api.kiwoom.com"
    mock_base_url: str = "https://mockapi.kiwoom.com"
    token_leeway_minutes: int = 30

    @property
    def token_cache_path(self) -> Path:
        return self.api_root / TOKEN_CACHE_NAME


def _find_single(root: Path, kind: str) -> Path:
    matches = sorted(root.glob(f"*{kind}.txt"))
    if not matches:
        raise FileNotFoundError(f"missing Kiwoom credential file for kind={kind}: {root}")
    preferred = [path for path in matches if "국내" in path.name]
    return preferred[0] if preferred else matches[0]


def load_domestic_credentials(api_root: Path | None = None) -> tuple[str, str]:
    root = Path(api_root or DEFAULT_KIWOOM_API_ROOT)
    app_path = _find_single(root, "appkey")
    secret_path = _find_single(root, "secretkey")
    appkey = app_path.read_text(encoding="utf-8").strip()
    secretkey = secret_path.read_text(encoding="utf-8").strip()
    if not appkey or not secretkey:
        raise ValueError("Kiwoom domestic appkey/secretkey is empty")
    return appkey, secretkey


def _parse_expires_dt(value: str) -> datetime:
    return datetime.strptime(value, "%Y%m%d%H%M%S")


def _token_is_valid(payload: dict, leeway_minutes: int) -> bool:
    token = payload.get("token")
    expires_dt = payload.get("expires_dt")
    if not token or not expires_dt:
        return False
    try:
        expires_at = _parse_expires_dt(str(expires_dt))
    except Exception:
        return False
    return datetime.now() + timedelta(minutes=leeway_minutes) < expires_at


class KiwoomRestClient:
    def __init__(self, config: KiwoomRestConfig | None = None, *, use_mock: bool = False):
        self.config = config or KiwoomRestConfig()
        self.use_mock = use_mock
        self.base_url = self.config.mock_base_url if use_mock else self.config.production_base_url
        self.appkey, self.secretkey = load_domestic_credentials(self.config.api_root)

    def _issue_token(self) -> dict:
        url = f"{self.base_url}/oauth2/token"
        payload = {
            "grant_type": "client_credentials",
            "appkey": self.appkey,
            "secretkey": self.secretkey,
        }
        resp = requests.post(url, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if int(data.get("return_code", -1)) != 0:
            raise RuntimeError(f"Kiwoom token error: {data}")
        self.config.token_cache_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return data

    def get_access_token(self, force_refresh: bool = False) -> str:
        if not force_refresh and self.config.token_cache_path.exists():
            try:
                cached = json.loads(self.config.token_cache_path.read_text(encoding="utf-8"))
                if _token_is_valid(cached, self.config.token_leeway_minutes):
                    return str(cached["token"])
            except Exception:
                pass
        data = self._issue_token()
        return str(data["token"])

    def _headers(self, *, force_refresh: bool = False) -> dict[str, str]:
        token = self.get_access_token(force_refresh=force_refresh)
        return {
            "Authorization": f"Bearer {token}",
            "api-id": "ka10007",
            "Content-Type": "application/json;charset=UTF-8",
        }

    def fetch_current_quote_raw(self, code: str, *, max_retries: int = 4) -> dict:
        url = f"{self.base_url}/api/dostk/mrkcond"
        body = {"stk_cd": str(code).strip().upper()}
        force_refresh = False
        last_error: Exception | None = None

        for attempt in range(max_retries):
            try:
                resp = requests.post(url, headers=self._headers(force_refresh=force_refresh), json=body, timeout=30)
                if resp.status_code == 401 and not force_refresh:
                    force_refresh = True
                    continue
                if resp.status_code == 429:
                    time.sleep(min(8.0, 1.5 * (attempt + 1)))
                    continue
                resp.raise_for_status()
                data = resp.json()
                if isinstance(data, dict) and data.get("return_code") not in (None, 0, "0"):
                    raise RuntimeError(f"Kiwoom quote error for {code}: {data}")
                return data
            except Exception as exc:
                last_error = exc
                if attempt >= max_retries - 1:
                    break
                time.sleep(min(8.0, 0.8 * (attempt + 1)))

        raise RuntimeError(f"Kiwoom quote request failed for {code}: {last_error}")


def _to_float(value: object, *, absolute: bool = False) -> Optional[float]:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if text == "":
        return None
    try:
        num = float(text)
    except ValueError:
        return None
    return abs(num) if absolute else num


def normalize_quote(raw: dict) -> dict[str, object]:
    code = str(raw.get("stk_cd", "")).replace(".0", "")
    date_raw = str(raw.get("date", "")).strip()
    time_raw = str(raw.get("tm", "")).strip().zfill(6) if raw.get("tm") else "000000"
    dt = pd.to_datetime(date_raw, format="%Y%m%d", errors="coerce")
    quote_time = pd.NaT
    if dt is not pd.NaT and pd.notna(dt):
        quote_time = pd.to_datetime(f"{date_raw}{time_raw}", format="%Y%m%d%H%M%S", errors="coerce")

    return {
        "date": None if pd.isna(dt) else str(dt.date()),
        "code": code.zfill(6) if code.isdigit() else code,
        "name": raw.get("stk_nm"),
        "close": _to_float(raw.get("cur_prc"), absolute=True),
        "open": _to_float(raw.get("open_pric"), absolute=True),
        "high": _to_float(raw.get("high_pric"), absolute=True),
        "low": _to_float(raw.get("low_pric"), absolute=True),
        "volume": _to_float(raw.get("trde_qty"), absolute=True),
        "trading_value": _to_float(raw.get("trde_prica"), absolute=True),
        "quote_time": None if pd.isna(quote_time) else quote_time.isoformat(),
        "change_abs": _to_float(raw.get("pred_rt"), absolute=False),
        "change_pct": _to_float(raw.get("flu_rt"), absolute=False),
        "best_ask": _to_float(raw.get("sel_1bid"), absolute=True),
        "best_bid": _to_float(raw.get("buy_1bid"), absolute=True),
        "market_phase": raw.get("290"),
        "source": "kiwoom_rest_ka10007",
    }


def fetch_current_quotes(
    codes: Iterable[str],
    *,
    use_mock: bool = False,
    api_root: Path | None = None,
    per_request_sleep_seconds: float = 0.50,
) -> pd.DataFrame:
    client = KiwoomRestClient(KiwoomRestConfig(api_root=Path(api_root) if api_root else DEFAULT_KIWOOM_API_ROOT), use_mock=use_mock)
    rows = []
    for code in codes:
        code = str(code).strip()
        if not code:
            continue
        try:
            raw = client.fetch_current_quote_raw(code)
            rows.append(normalize_quote(raw))
        except Exception:
            continue
        if per_request_sleep_seconds > 0:
            time.sleep(per_request_sleep_seconds)

    if not rows:
        return pd.DataFrame(
            columns=[
                "date",
                "code",
                "name",
                "close",
                "open",
                "high",
                "low",
                "volume",
                "trading_value",
                "quote_time",
                "change_abs",
                "change_pct",
                "best_ask",
                "best_bid",
                "market_phase",
                "source",
            ]
        )

    df = pd.DataFrame(rows)
    numeric_cols = ["close", "open", "high", "low", "volume", "trading_value", "change_abs", "change_pct", "best_ask", "best_bid"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.sort_values(["code"]).reset_index(drop=True)


def save_live_quotes(df: pd.DataFrame, output_path_value: Path | None = None) -> Path:
    output = Path(output_path_value or data_path("live_quotes.csv"))
    output.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output, index=False, encoding="utf-8-sig")
    return output

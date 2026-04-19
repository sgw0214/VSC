from __future__ import annotations

import argparse
import json
import math
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import parse_qsl, quote_plus, urlencode, urlparse, urlunparse
from xml.etree import ElementTree as ET

import numpy as np
import pandas as pd
import requests
from new_strategy.paths import data_path, strategy_output_path
from new_strategy.trend_file_contract import ensure_trend_lab_dirs, resolve_trend_file

try:
    from zoneinfo import ZoneInfo

    SEOUL_TZ = ZoneInfo("Asia/Seoul")
except Exception:  # pragma: no cover - Python 3.8 fallback
    SEOUL_TZ = timezone(timedelta(hours=9))
LANGS = ("ko", "en", "zh")
SOURCE_ROOT_GOOGLE_NEWS = "google_news_rss"
SOURCE_ROOT_BING_NEWS = "bing_news_rss"
SOURCE_ROOT_GDELT = "gdelt_doc_api"
SOURCE_ROOT_HN = "hackernews_algolia_api"
SOURCE_ROOT_SINA = "sina_news_rss"
SOURCE_ROOT_ARXIV = "arxiv_api"


def _env_int(name: str, default: int) -> int:
    text = str(os.getenv(name, str(default))).strip()
    try:
        return int(text)
    except Exception:
        return int(default)


# Contract policy:
# - Minimum independent source roots must be >= 3.
# - Target roots should be >= minimum (default 4).
MIN_INDEPENDENT_SOURCE_ROOTS = max(3, _env_int("NEW_STRATEGY_TREND_MIN_SOURCE_ROOTS", 3))
TARGET_INDEPENDENT_SOURCE_ROOTS = max(MIN_INDEPENDENT_SOURCE_ROOTS, _env_int("NEW_STRATEGY_TREND_TARGET_SOURCE_ROOTS", 4))
RSS_TEMPLATES = {
    "ko": "https://news.google.com/rss/search?q={query}{when_clause}&hl=ko&gl=KR&ceid=KR:ko",
    "en": "https://news.google.com/rss/search?q={query}{when_clause}&hl=en-US&gl=US&ceid=US:en",
    "zh": "https://news.google.com/rss/search?q={query}{when_clause}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
}
BING_RSS_TEMPLATES = {
    "ko": "https://www.bing.com/news/search?q={query}&setlang=ko&cc=KR&format=RSS",
    "en": "https://www.bing.com/news/search?q={query}&setlang=en-US&cc=US&format=RSS",
    "zh": "https://www.bing.com/news/search?q={query}&setlang=zh-CN&cc=CN&format=RSS",
}
BING_LANGS = ("ko", "en")
GDELT_ARTLIST_URL = (
    "https://api.gdeltproject.org/api/v2/doc/doc?"
    "query={query}&mode=ArtList&maxrecords={max_records}&format=json&sort=DateDesc&timespan={timespan}"
)
HACKERNEWS_SEARCH_URL = "https://hn.algolia.com/api/v1/search_by_date?query={query}&tags=story&hitsPerPage={hits}"
ARXIV_API_URL = (
    "https://export.arxiv.org/api/query?"
    "search_query=all:{query}&start=0&max_results={max_results}&sortBy=submittedDate&sortOrder=descending"
)
SINA_RSS_FEEDS = (
    "https://rss.sina.com.cn/news/china/focus15.xml",
    "https://rss.sina.com.cn/news/world/focus15.xml",
)
SCORE_WEIGHTS = {
    "burst_score": 20.0,
    "source_diversity_score": 20.0,
    "volume_score": 15.0,
    "persistence_score": 15.0,
    "cross_lang_consensus_score": 15.0,
    "freshness_score": 15.0,
}

# Noise contract for auto taxonomy registration:
# - Exclude generic stopwords/site tokens that pollute taxonomy quality.
# - Keep this list explicit and conservative.
NOISE_TOKEN_EXACT = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "this",
    "that",
    "will",
    "what",
    "why",
    "how",
    "are",
    "its",
    "new",
    "today",
    "daily",
    "news",
    "business",
    "market",
    "markets",
    "stock",
    "stocks",
    "price",
    "prices",
    "report",
    "global",
    "com",
    "net",
    "org",
    "www",
    "http",
    "https",
    "msn",
    "yahoo",
    "aol",
    "sohu",
    "daum",
    "naver",
    "新浪财经",
    "东方财富",
    "汽车之家",
    "연합뉴스",
    "네이트",
    "뉴스",
}
NOISE_TOKEN_PATTERN = re.compile(
    r"(?:^www\d*$)|(?:\.(?:com|net|org|cn|co|io)$)|(?:\d{4,})|(?:^[a-z]$)"
)


def _representativeness_tier(source_root_count: int) -> str:
    count = int(max(0, source_root_count))
    if count >= int(max(1, TARGET_INDEPENDENT_SOURCE_ROOTS)):
        return "high"
    if count >= int(max(1, MIN_INDEPENDENT_SOURCE_ROOTS)):
        return "medium"
    return "low"


@dataclass(frozen=True)
class TrendCollectConfig:
    window_hours: int = 24
    retention_days: int = 35
    score_window_days: int = 30
    max_items_per_query: int = 40
    request_timeout_seconds: float = 18.0
    request_sleep_seconds: float = 0.12
    run_at: datetime | None = None
    dry_run: bool = False


def _read_csv(path: Path, *, dtype: dict[str, str] | None = None) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, dtype=dtype, encoding="utf-8-sig", low_memory=False)


def _write_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")


def _normalize_url(url: str) -> str:
    text = str(url or "").strip()
    if not text:
        return ""
    try:
        p = urlparse(text)
    except Exception:
        return text
    query = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=False) if k in {"id"}]
    return urlunparse(
        p._replace(
            scheme=(p.scheme or "https").lower(),
            netloc=p.netloc.lower(),
            query=urlencode(query, doseq=True),
            fragment="",
        )
    )


def _infer_domain(url: str) -> str:
    text = str(url or "").strip()
    if not text:
        return ""
    try:
        return urlparse(text).netloc.lower()
    except Exception:
        return ""


def _normalize_source_root_series(series: pd.Series) -> pd.Series:
    # Legacy rows may contain NaN/None/null-like text after schema upgrade.
    # Treat all missing-like values as the default collection root.
    base = series.fillna("").astype(str).str.strip()
    lower = base.str.lower()
    missing_mask = lower.isin({"", "nan", "none", "null", "nat"})
    return pd.Series(np.where(missing_mask, SOURCE_ROOT_GOOGLE_NEWS, base), index=series.index, dtype=str)


def _parse_pub_dt(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        dt = parsedate_to_datetime(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _parse_gdelt_dt(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y%m%dT%H%M%SZ", "%Y%m%d%H%M%S"):
        try:
            dt = datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            continue
    return None


def _normalize_text_for_match(text: str) -> str:
    return str(text or "").strip().lower()


def _title_matches_query_alias(title: str, alias: str, canonical_keyword: str) -> bool:
    title_norm = _normalize_text_for_match(title)
    if not title_norm:
        return False
    alias_norm = _normalize_text_for_match(alias)
    canonical_norm = _normalize_text_for_match(str(canonical_keyword or "").replace("_", " "))
    for token in (alias_norm, canonical_norm):
        if len(token) >= 2 and token in title_norm:
            return True
    return False


def _node_text(node: ET.Element | None, name: str) -> str:
    if node is None:
        return ""
    child = node.find(name)
    if child is None or child.text is None:
        return ""
    return child.text.strip()


def _load_taxonomy() -> pd.DataFrame:
    path = resolve_trend_file("keyword_taxonomy")
    df = _read_csv(path, dtype=str).fillna("")
    if df.empty:
        raise RuntimeError(f"taxonomy missing or empty: {path}")
    req = {"canonical_keyword", "category_l1", "category_l2"}
    miss = req.difference(df.columns)
    if miss:
        raise RuntimeError(f"taxonomy missing columns: {sorted(miss)}")
    df["canonical_keyword"] = df["canonical_keyword"].astype(str).str.strip().str.lower()
    if "status" in df.columns:
        df = df[~df["status"].astype(str).str.lower().isin({"inactive", "deprecated", "disabled"})].copy()
    df["base_weight"] = pd.to_numeric(df.get("base_weight", 1.0), errors="coerce").fillna(1.0)
    return df.drop_duplicates(subset=["canonical_keyword"], keep="first").reset_index(drop=True)


def _load_aliases() -> pd.DataFrame:
    path = resolve_trend_file("keyword_aliases")
    df = _read_csv(path, dtype=str).fillna("")
    if df.empty:
        return pd.DataFrame(columns=["canonical_keyword", "alias", "lang", "priority", "status"])
    df["canonical_keyword"] = df["canonical_keyword"].astype(str).str.strip().str.lower()
    df["alias"] = df["alias"].astype(str).str.strip()
    df["lang"] = df["lang"].astype(str).str.strip().str.lower()
    df["priority"] = pd.to_numeric(df.get("priority"), errors="coerce").fillna(999).astype(int)
    if "status" in df.columns:
        df = df[df["status"].astype(str).str.lower().isin({"active", "validated", "promoted", ""})].copy()
    return df[(df["canonical_keyword"] != "") & (df["alias"] != "")].copy()


def _build_queries(taxonomy: pd.DataFrame, aliases: pd.DataFrame, *, lookback_days: int = 1) -> pd.DataFrame:
    safe_lookback = max(1, int(lookback_days))
    when_clause = f"+when:{safe_lookback}d"
    base = aliases.sort_values(["canonical_keyword", "lang", "priority", "alias"]).drop_duplicates(
        subset=["canonical_keyword", "lang"], keep="first"
    )
    amap = {(str(r["canonical_keyword"]), str(r["lang"])): str(r["alias"]) for r in base.to_dict("records")}
    rows: list[dict[str, str]] = []
    for keyword in taxonomy["canonical_keyword"].astype(str):
        for lang in LANGS:
            alias = amap.get((keyword, lang), keyword.replace("_", " "))
            rows.append(
                {
                    "canonical_keyword": keyword,
                    "lang": lang,
                    "alias": alias,
                    "source_root": SOURCE_ROOT_GOOGLE_NEWS,
                    "query_url": RSS_TEMPLATES.get(lang, RSS_TEMPLATES["en"]).format(query=quote_plus(alias), when_clause=when_clause),
                }
            )
            if lang in BING_LANGS:
                rows.append(
                    {
                        "canonical_keyword": keyword,
                        "lang": lang,
                        "alias": alias,
                        "source_root": SOURCE_ROOT_BING_NEWS,
                        "query_url": BING_RSS_TEMPLATES.get(lang, BING_RSS_TEMPLATES["en"]).format(query=quote_plus(alias)),
                    }
                )
        gdelt_alias = amap.get((keyword, "en"), keyword.replace("_", " "))
        gdelt_query = re.sub(r"\s+", " ", str(gdelt_alias or "").replace("_", " ").strip())
        if len(re.sub(r"[^A-Za-z0-9가-힣\u4e00-\u9fff]", "", gdelt_query)) >= 5:
            rows.append(
                {
                    "canonical_keyword": keyword,
                    "lang": "multi",
                    "alias": gdelt_alias,
                    "source_root": SOURCE_ROOT_GDELT,
                    "query_url": GDELT_ARTLIST_URL.format(
                        query=quote_plus(gdelt_query),
                        max_records=30,
                        timespan=f"{safe_lookback}day",
                    ),
                }
            )
        hn_alias = amap.get((keyword, "en"), keyword.replace("_", " "))
        hn_query = re.sub(r"\s+", " ", str(hn_alias or "").replace("_", " ").strip())
        if len(re.sub(r"[^A-Za-z0-9]", "", hn_query)) >= 2:
            rows.append(
                {
                    "canonical_keyword": keyword,
                    "lang": "en",
                    "alias": hn_alias,
                    "source_root": SOURCE_ROOT_HN,
                    "query_url": HACKERNEWS_SEARCH_URL.format(query=quote_plus(hn_query), hits=25),
                }
            )
        arxiv_alias = amap.get((keyword, "en"), keyword.replace("_", " "))
        arxiv_query = re.sub(r"\s+", " ", str(arxiv_alias or "").replace("_", " ").strip())
        if len(re.sub(r"[^A-Za-z0-9]", "", arxiv_query)) >= 2:
            rows.append(
                {
                    "canonical_keyword": keyword,
                    "lang": "en",
                    "alias": arxiv_alias,
                    "source_root": SOURCE_ROOT_ARXIV,
                    "query_url": ARXIV_API_URL.format(query=quote_plus(arxiv_query), max_results=20),
                }
            )
        sina_alias = amap.get((keyword, "zh"), amap.get((keyword, "ko"), keyword.replace("_", " ")))
        for feed_url in SINA_RSS_FEEDS:
            rows.append(
                {
                    "canonical_keyword": keyword,
                    "lang": "zh",
                    "alias": sina_alias,
                    "source_root": SOURCE_ROOT_SINA,
                    "query_url": feed_url,
                }
            )
    return pd.DataFrame(rows)


def _fetch_rss_items(session: requests.Session, rss_url: str, timeout: float) -> list[dict[str, str]]:
    resp = session.get(rss_url, timeout=timeout)
    resp.raise_for_status()
    try:
        root = ET.fromstring(resp.text)
    except Exception:
        return []
    out: list[dict[str, str]] = []
    for item in root.findall(".//item"):
        src = item.find("source")
        pub_dt = _parse_pub_dt(_node_text(item, "pubDate"))
        out.append(
            {
                "title": _node_text(item, "title"),
                "url": _node_text(item, "link"),
                "source_name": "" if src is None else (src.text or "").strip(),
                "source_url": "" if src is None else str(src.attrib.get("url") or "").strip(),
                "published_at": "" if pub_dt is None else pub_dt.isoformat(),
            }
        )
    return out


def _fetch_gdelt_items(session: requests.Session, url: str, timeout: float) -> list[dict[str, str]]:
    resp = session.get(url, timeout=timeout)
    if resp.status_code >= 500:
        resp.raise_for_status()
    if resp.status_code >= 400:
        return []
    if "keyword that was too short" in str(resp.text or "").lower():
        return []
    payload: dict[str, object] | None = None
    try:
        payload = resp.json()
    except Exception:
        return []
    if not isinstance(payload, dict):
        return []
    articles = payload.get("articles", [])
    if not isinstance(articles, list):
        return []
    out: list[dict[str, str]] = []
    for article in articles:
        if not isinstance(article, dict):
            continue
        url_text = str(article.get("url") or "").strip()
        if not url_text:
            continue
        pub_dt = _parse_gdelt_dt(str(article.get("seendate") or ""))
        if pub_dt is None:
            pub_fallback = pd.to_datetime(str(article.get("date") or article.get("publishedAt") or ""), errors="coerce", utc=True)
            if pd.notna(pub_fallback):
                pub_dt = pub_fallback.to_pydatetime()
        if pub_dt is None:
            continue
        domain = str(article.get("domain") or "").strip().lower() or _infer_domain(url_text)
        source_name = str(article.get("sourcecountry") or "").strip() or domain
        source_url = f"https://{domain}" if domain else ""
        out.append(
            {
                "title": str(article.get("title") or "").strip(),
                "url": url_text,
                "source_name": source_name,
                "source_url": source_url,
                "published_at": pub_dt.astimezone(timezone.utc).isoformat(),
            }
        )
    return out


def _fetch_hackernews_items(session: requests.Session, url: str, timeout: float) -> list[dict[str, str]]:
    resp = session.get(url, timeout=timeout)
    if resp.status_code >= 500:
        resp.raise_for_status()
    if resp.status_code >= 400:
        return []
    try:
        payload = resp.json()
    except Exception:
        return []
    if not isinstance(payload, dict):
        return []
    hits = payload.get("hits", [])
    if not isinstance(hits, list):
        return []
    out: list[dict[str, str]] = []
    for hit in hits:
        if not isinstance(hit, dict):
            continue
        title = str(hit.get("title") or hit.get("story_title") or "").strip()
        url_text = str(hit.get("url") or hit.get("story_url") or "").strip()
        if not url_text:
            continue
        pub = pd.to_datetime(str(hit.get("created_at") or ""), errors="coerce", utc=True)
        if pd.isna(pub):
            continue
        domain = _infer_domain(url_text)
        out.append(
            {
                "title": title,
                "url": url_text,
                "source_name": domain or "hackernews",
                "source_url": f"https://{domain}" if domain else "",
                "published_at": pub.to_pydatetime().astimezone(timezone.utc).isoformat(),
            }
        )
    return out


def _fetch_arxiv_items(session: requests.Session, url: str, timeout: float) -> list[dict[str, str]]:
    resp = session.get(url, timeout=timeout)
    if resp.status_code >= 500:
        resp.raise_for_status()
    if resp.status_code >= 400:
        return []
    try:
        root = ET.fromstring(resp.text)
    except Exception:
        return []
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    entries = root.findall("atom:entry", ns)
    out: list[dict[str, str]] = []
    for entry in entries:
        title = str(entry.findtext("atom:title", default="", namespaces=ns) or "").strip()
        published = str(entry.findtext("atom:published", default="", namespaces=ns) or "").strip()
        pub = pd.to_datetime(published, errors="coerce", utc=True)
        if pd.isna(pub):
            continue
        links = entry.findall("atom:link", ns)
        url_text = ""
        for link in links:
            href = str(link.attrib.get("href") or "").strip()
            rel = str(link.attrib.get("rel") or "").strip().lower()
            if not href:
                continue
            if rel == "alternate":
                url_text = href
                break
            if not url_text:
                url_text = href
        if not url_text:
            url_text = str(entry.findtext("atom:id", default="", namespaces=ns) or "").strip()
        if not url_text:
            continue
        out.append(
            {
                "title": title,
                "url": url_text,
                "source_name": "arxiv",
                "source_url": "https://arxiv.org",
                "published_at": pub.to_pydatetime().astimezone(timezone.utc).isoformat(),
            }
        )
    return out


def _collect_mentions(
    cfg: TrendCollectConfig,
    taxonomy: pd.DataFrame,
    aliases: pd.DataFrame,
    *,
    lookback_days: int | None = None,
) -> tuple[pd.DataFrame, list[str], dict[str, int]]:
    run_at = (cfg.run_at or datetime.now(SEOUL_TZ)).astimezone(SEOUL_TZ)
    win_end = run_at
    effective_days = max(1, int(lookback_days or max(1, math.ceil(int(cfg.window_hours) / 24))))
    win_start = run_at - timedelta(days=effective_days)
    win_start_utc = win_start.astimezone(timezone.utc)
    win_end_utc = win_end.astimezone(timezone.utc)
    queries = _build_queries(taxonomy, aliases, lookback_days=effective_days)
    session = requests.Session()
    rows: list[dict[str, str]] = []
    errors: list[str] = []
    counters = {"query_count": int(len(queries)), "request_success": 0, "request_error": 0}
    source_cache: dict[tuple[str, str], list[dict[str, str]]] = {}

    for idx, q in enumerate(queries.to_dict("records"), start=1):
        source_root = str(q.get("source_root") or SOURCE_ROOT_GOOGLE_NEWS)
        query_url = str(q.get("query_url") or "").strip()
        if not query_url:
            continue
        try:
            if source_root == SOURCE_ROOT_GDELT:
                items = _fetch_gdelt_items(session, query_url, timeout=cfg.request_timeout_seconds)
            elif source_root == SOURCE_ROOT_HN:
                items = _fetch_hackernews_items(session, query_url, timeout=cfg.request_timeout_seconds)
            elif source_root == SOURCE_ROOT_ARXIV:
                items = _fetch_arxiv_items(session, query_url, timeout=cfg.request_timeout_seconds)
            elif source_root == SOURCE_ROOT_SINA:
                cache_key = (source_root, query_url)
                if cache_key not in source_cache:
                    source_cache[cache_key] = _fetch_rss_items(session, query_url, timeout=cfg.request_timeout_seconds)
                items = source_cache[cache_key]
            else:
                items = _fetch_rss_items(session, query_url, timeout=cfg.request_timeout_seconds)
            counters["request_success"] += 1
        except Exception as exc:
            counters["request_error"] += 1
            errors.append(f"query_error:{source_root}:{q['canonical_keyword']}:{q['lang']}:{type(exc).__name__}")
            time.sleep(cfg.request_sleep_seconds)
            continue
        if cfg.max_items_per_query > 0:
            items = items[: int(cfg.max_items_per_query)]
        if source_root == SOURCE_ROOT_SINA:
            alias_text = str(q.get("alias") or "")
            canonical_keyword = str(q.get("canonical_keyword") or "")
            items = [it for it in items if _title_matches_query_alias(str(it.get("title") or ""), alias_text, canonical_keyword)]
        for item in items:
            pub_raw = str(item.get("published_at") or "")
            if not pub_raw:
                continue
            pub_dt = pd.to_datetime(pub_raw, errors="coerce", utc=True)
            if pd.isna(pub_dt):
                continue
            pub_py = pub_dt.to_pydatetime()
            if pub_py < win_start_utc or pub_py >= win_end_utc:
                continue
            url = str(item.get("url") or "").strip()
            pub_local_date = pub_py.astimezone(SEOUL_TZ).date().isoformat()
            rows.append(
                {
                    "as_of_date": pub_local_date,
                    "window_start": win_start_utc.isoformat(),
                    "window_end": win_end_utc.isoformat(),
                    "collected_at": run_at.astimezone(timezone.utc).isoformat(),
                    "canonical_keyword": str(q["canonical_keyword"]),
                    "query_alias": str(q["alias"]),
                    "lang": str(q["lang"]),
                    "source_name": str(item.get("source_name") or ""),
                    "source_domain": _infer_domain(str(item.get("source_url") or "")) or _infer_domain(url),
                    "source_root": source_root,
                    "title": str(item.get("title") or "").strip(),
                    "url": url,
                    "url_normalized": _normalize_url(url),
                    "published_at": pub_py.isoformat(),
                }
            )
        if idx < len(queries):
            time.sleep(cfg.request_sleep_seconds)

    cols = [
        "as_of_date",
        "window_start",
        "window_end",
        "collected_at",
        "canonical_keyword",
        "query_alias",
        "lang",
        "source_name",
        "source_domain",
        "source_root",
        "title",
        "url",
        "url_normalized",
        "published_at",
    ]
    mentions = pd.DataFrame(rows)
    if mentions.empty:
        mentions = pd.DataFrame(columns=cols)
    return mentions, errors, counters

def _save_mentions_rolling(mentions_new: pd.DataFrame, cfg: TrendCollectConfig) -> pd.DataFrame:
    path = resolve_trend_file("news_mentions_rolling")
    old = _read_csv(path, dtype=str).fillna("")
    all_rows = pd.concat([old, mentions_new], ignore_index=True)
    if all_rows.empty:
        if not cfg.dry_run:
            _write_csv(all_rows, path)
        return all_rows
    all_rows["published_at"] = pd.to_datetime(all_rows["published_at"], errors="coerce", utc=True)
    all_rows = all_rows.dropna(subset=["published_at"]).copy()
    all_rows["canonical_keyword"] = all_rows["canonical_keyword"].astype(str)
    all_rows["url_normalized"] = all_rows["url_normalized"].astype(str)
    if "source_root" not in all_rows.columns:
        all_rows["source_root"] = SOURCE_ROOT_GOOGLE_NEWS
    all_rows["source_root"] = _normalize_source_root_series(all_rows["source_root"])
    all_rows = all_rows.drop_duplicates(subset=["canonical_keyword", "url_normalized", "published_at"], keep="last")
    cutoff = (cfg.run_at or datetime.now(SEOUL_TZ)).astimezone(timezone.utc) - timedelta(days=int(cfg.retention_days))
    all_rows = all_rows[all_rows["published_at"] >= cutoff].copy()
    all_rows = all_rows.sort_values(["published_at", "canonical_keyword"], ascending=[False, True]).reset_index(drop=True)
    all_rows["published_at"] = all_rows["published_at"].dt.strftime("%Y-%m-%dT%H:%M:%S%z")
    if not cfg.dry_run:
        _write_csv(all_rows, path)
    return all_rows


def _daily_panel(mentions: pd.DataFrame, taxonomy: pd.DataFrame, cfg: TrendCollectConfig) -> pd.DataFrame:
    end_date = (cfg.run_at or datetime.now(SEOUL_TZ)).date()
    start_date = end_date - timedelta(days=int(cfg.retention_days) - 1)
    all_dates = pd.date_range(start_date, end_date, freq="D")
    base_idx = pd.MultiIndex.from_product([all_dates.date, taxonomy["canonical_keyword"].astype(str)], names=["as_of_date", "canonical_keyword"]).to_frame(index=False)
    if mentions.empty:
        out = base_idx
        out["mention_count"] = 0.0
        out["source_count"] = 0.0
        out["source_root_count"] = 0.0
        out["lang_count"] = 0.0
        return out

    work = mentions.copy()
    work["as_of_date"] = pd.to_datetime(work["as_of_date"], errors="coerce").dt.date
    if "source_root" not in work.columns:
        work["source_root"] = SOURCE_ROOT_GOOGLE_NEWS
    work["source_root"] = _normalize_source_root_series(work["source_root"])
    work = work.dropna(subset=["as_of_date"]).copy()
    agg = work.groupby(["as_of_date", "canonical_keyword"], as_index=False).agg(
        mention_count=("title", "size"),
        source_count=("source_domain", "nunique"),
        source_root_count=("source_root", "nunique"),
        lang_count=("lang", "nunique"),
    )
    out = base_idx.merge(agg, on=["as_of_date", "canonical_keyword"], how="left")
    for col in ["mention_count", "source_count", "source_root_count", "lang_count"]:
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0)
    return out


def _minmax(series: pd.Series) -> pd.Series:
    s = pd.to_numeric(series, errors="coerce").fillna(0.0)
    mn = float(s.min())
    mx = float(s.max())
    if not math.isfinite(mn) or not math.isfinite(mx) or mx <= mn:
        return pd.Series(np.zeros(len(s)), index=s.index)
    return (s - mn) / (mx - mn)


def _build_daily_scores(panel: pd.DataFrame, taxonomy: pd.DataFrame, cfg: TrendCollectConfig) -> pd.DataFrame:
    df = panel.merge(taxonomy[["canonical_keyword", "category_l1", "category_l2", "base_weight"]], on="canonical_keyword", how="left")
    df["base_weight"] = pd.to_numeric(df["base_weight"], errors="coerce").fillna(1.0)
    df["as_of_date"] = pd.to_datetime(df["as_of_date"], errors="coerce")
    df = df.dropna(subset=["as_of_date"]).sort_values(["canonical_keyword", "as_of_date"]).reset_index(drop=True)
    win = int(max(7, cfg.score_window_days))

    def _per_keyword(group: pd.DataFrame) -> pd.DataFrame:
        g = group.copy()
        vol = pd.to_numeric(g["mention_count"], errors="coerce").fillna(0.0)
        base_mean = vol.shift(1).rolling(win, min_periods=5).mean()
        base_std = vol.shift(1).rolling(win, min_periods=5).std(ddof=0)
        burst_z = pd.Series(np.zeros(len(g)), index=g.index, dtype=float)
        ok = base_std.notna() & (base_std > 0)
        burst_z.loc[ok] = ((vol.loc[ok] - base_mean.loc[ok]) / base_std.loc[ok]).clip(-6, 6)
        g["burst_z"] = burst_z.values
        g["persistence_score"] = (vol.gt(0).rolling(7, min_periods=1).sum() / 7.0).values
        vol3 = vol.rolling(3, min_periods=1).sum()
        vol30 = vol.rolling(win, min_periods=1).sum()
        fres = pd.Series(np.zeros(len(g)), index=g.index, dtype=float)
        has = vol30 > 0
        fres.loc[has] = (vol3.loc[has] / vol30.loc[has]).clip(0.0, 1.0)
        g["freshness_score"] = fres.values
        return g

    df = df.groupby("canonical_keyword", group_keys=False).apply(_per_keyword)
    burst_base = ((pd.to_numeric(df["burst_z"], errors="coerce").fillna(0.0) + 3.0) / 6.0).clip(0.0, 1.0)
    has_mentions = pd.to_numeric(df["mention_count"], errors="coerce").fillna(0.0) > 0
    df["burst_score"] = np.where(has_mentions, burst_base, 0.0)
    df["cross_lang_consensus_score"] = (pd.to_numeric(df["lang_count"], errors="coerce").fillna(0.0) / 3.0).clip(0.0, 1.0)
    df["source_root_diversity_score"] = (
        pd.to_numeric(df.get("source_root_count"), errors="coerce").fillna(0.0) / max(1.0, float(TARGET_INDEPENDENT_SOURCE_ROOTS))
    ).clip(0.0, 1.0)
    df["source_root_low_confidence"] = pd.to_numeric(df.get("source_root_count"), errors="coerce").fillna(0.0) < float(
        max(1, MIN_INDEPENDENT_SOURCE_ROOTS)
    )
    df["volume_score"] = df.groupby("as_of_date")["mention_count"].transform(_minmax)
    df["source_diversity_score"] = df.groupby("as_of_date")["source_count"].transform(_minmax)

    raw = (
        df["burst_score"] * SCORE_WEIGHTS["burst_score"]
        + df["source_diversity_score"] * SCORE_WEIGHTS["source_diversity_score"]
        + df["volume_score"] * SCORE_WEIGHTS["volume_score"]
        + df["persistence_score"] * SCORE_WEIGHTS["persistence_score"]
        + df["cross_lang_consensus_score"] * SCORE_WEIGHTS["cross_lang_consensus_score"]
        + df["freshness_score"] * SCORE_WEIGHTS["freshness_score"]
    ) / 100.0
    df["composite_raw_score"] = raw
    df["composite_weighted_score"] = (raw * df["base_weight"]).clip(lower=0.0)
    df["trend_score"] = (df.groupby("as_of_date")["composite_weighted_score"].transform(_minmax) * 100.0).round(4)
    df["rank_in_day"] = df.groupby("as_of_date")["trend_score"].rank(method="dense", ascending=False).astype(int)
    df["as_of_date"] = df["as_of_date"].dt.strftime("%Y-%m-%d")
    return df


def _build_snapshot(score_df: pd.DataFrame, mentions_rolling: pd.DataFrame, run_at: datetime, window_hours: int) -> dict[str, object]:
    as_of_date = run_at.date().isoformat()
    latest = score_df[score_df["as_of_date"] == as_of_date].copy().sort_values(["trend_score", "mention_count"], ascending=[False, False])
    top_overall = [
        {
            "keyword": str(r.get("canonical_keyword", "")),
            "trend_score": float(r.get("trend_score", 0.0)),
            "category_l1": str(r.get("category_l1", "")),
            "category_l2": str(r.get("category_l2", "")),
            "mentions": int(float(r.get("mention_count", 0.0))),
            "sources": int(float(r.get("source_count", 0.0))),
            "langs": int(float(r.get("lang_count", 0.0))),
        }
        for r in latest.head(30).to_dict("records")
    ]
    top_by_category: dict[str, list[dict[str, object]]] = {}
    for cat, grp in latest.groupby("category_l1"):
        top_by_category[str(cat)] = [
            {
                "keyword": str(r.get("canonical_keyword", "")),
                "trend_score": float(r.get("trend_score", 0.0)),
                "mentions": int(float(r.get("mention_count", 0.0))),
            }
            for r in grp.sort_values(["trend_score", "mention_count"], ascending=[False, False]).head(10).to_dict("records")
        ]

    today_mentions = mentions_rolling[mentions_rolling["as_of_date"].astype(str) == as_of_date].copy() if not mentions_rolling.empty else pd.DataFrame()
    if "source_root" not in today_mentions.columns:
        today_mentions["source_root"] = SOURCE_ROOT_GOOGLE_NEWS if not today_mentions.empty else pd.Series(dtype=str)
    if not today_mentions.empty:
        today_mentions["source_root"] = _normalize_source_root_series(today_mentions["source_root"])
    source_roots_today = sorted([str(x).strip() for x in today_mentions["source_root"].astype(str).tolist() if str(x).strip()])
    source_roots_today = sorted(list(dict.fromkeys(source_roots_today)))
    source_root_count_today = int(len(source_roots_today))
    representativeness = _representativeness_tier(source_root_count_today)
    return {
        "as_of_date": as_of_date,
        "generated_at": run_at.astimezone(timezone.utc).isoformat(),
        "collection_window": {
            "hours": int(window_hours),
            "start": (run_at - timedelta(hours=int(window_hours))).astimezone(timezone.utc).isoformat(),
            "end": run_at.astimezone(timezone.utc).isoformat(),
        },
        "weights": SCORE_WEIGHTS,
        "summary": {
            "mentions_today": int(len(today_mentions)),
            "keywords_with_mentions": int((latest["mention_count"] > 0).sum()) if not latest.empty else 0,
            "unique_sources_today": int(today_mentions["source_domain"].astype(str).nunique()) if not today_mentions.empty else 0,
            "independent_source_root_count_today": source_root_count_today,
            "independent_source_roots_today": source_roots_today,
            "representativeness": representativeness,
            "source_root_contract_ok": bool(source_root_count_today >= max(1, MIN_INDEPENDENT_SOURCE_ROOTS)),
            "min_source_roots_contract": int(max(1, MIN_INDEPENDENT_SOURCE_ROOTS)),
            "target_source_roots_contract": int(max(1, TARGET_INDEPENDENT_SOURCE_ROOTS)),
        },
        "top_overall": top_overall,
        "top_by_category": top_by_category,
    }


def _build_keyword_industry_links(score_df: pd.DataFrame, as_of_date: str) -> pd.DataFrame:
    seed = _read_csv(resolve_trend_file("keyword_industry_seed_map"), dtype=str).fillna("")
    if seed.empty:
        return seed
    seed["canonical_keyword"] = seed["canonical_keyword"].astype(str).str.lower()
    seed["relation_strength"] = pd.to_numeric(seed.get("relation_strength"), errors="coerce").fillna(0.0)
    seed["confidence"] = pd.to_numeric(seed.get("confidence"), errors="coerce").fillna(0.0)
    seed["sample_n"] = pd.to_numeric(seed.get("sample_n"), errors="coerce").fillna(0).astype(int)
    seed["lag_days"] = pd.to_numeric(seed.get("lag_days"), errors="coerce").fillna(1).astype(int)
    seed["relation_type"] = seed.get("relation_type", "seed")
    seed["last_validated_at"] = as_of_date
    seed["data_link_active"] = 0
    hist = score_df[["as_of_date", "canonical_keyword", "trend_score"]].copy()
    hist["as_of_date"] = pd.to_datetime(hist["as_of_date"], errors="coerce")
    hist["trend_score"] = pd.to_numeric(hist["trend_score"], errors="coerce")
    hist = hist.dropna(subset=["as_of_date", "trend_score"]).copy()
    if hist["as_of_date"].nunique() < 20:
        return seed.sort_values(["relation_strength", "confidence"], ascending=[False, False]).reset_index(drop=True)

    price_path = data_path("price_panel.csv")
    if not price_path.exists():
        return seed.sort_values(["relation_strength", "confidence"], ascending=[False, False]).reset_index(drop=True)

    try:
        price = pd.read_csv(price_path, usecols=["date", "industry", "close"], dtype={"industry": str}, low_memory=False)
    except Exception:
        return seed.sort_values(["relation_strength", "confidence"], ascending=[False, False]).reset_index(drop=True)
    price["date"] = pd.to_datetime(price["date"], errors="coerce")
    price["close"] = pd.to_numeric(price["close"], errors="coerce")
    price["industry"] = price["industry"].astype(str).str.strip()
    cutoff = pd.to_datetime(as_of_date) - pd.Timedelta(days=120)
    price = price[(price["date"] >= cutoff) & price["date"].notna() & price["close"].notna() & (price["industry"] != "")].copy()
    if price.empty:
        return seed.sort_values(["relation_strength", "confidence"], ascending=[False, False]).reset_index(drop=True)

    ind = price.groupby(["date", "industry"], as_index=False)["close"].mean().sort_values(["industry", "date"]).reset_index(drop=True)
    ind["ret_1d_fwd"] = ind.groupby("industry")["close"].pct_change().shift(-1)
    ind["ret_5d_fwd"] = ind.groupby("industry")["close"].pct_change(5).shift(-5)

    hist = hist.rename(columns={"as_of_date": "date"})
    data_rows: list[dict[str, object]] = []
    for keyword, kdf in hist.groupby("canonical_keyword"):
        for industry, idf in ind.groupby("industry"):
            joined = kdf.merge(idf[["date", "ret_1d_fwd", "ret_5d_fwd"]], on="date", how="inner")
            joined = joined.dropna(subset=["trend_score", "ret_1d_fwd", "ret_5d_fwd"]).copy()
            if len(joined) < 15:
                continue
            corr1 = joined["trend_score"].corr(joined["ret_1d_fwd"])
            corr5 = joined["trend_score"].corr(joined["ret_5d_fwd"])
            if pd.isna(corr1) and pd.isna(corr5):
                continue
            strength = float(np.nanmean([abs(corr1), abs(corr5)]))
            if strength < 0.45:
                continue
            confidence = float(min(0.99, strength * math.log1p(len(joined)) / 2.8))
            status = "candidate"
            if strength >= 0.65 and len(joined) >= 20:
                status = "promoted"
            elif strength >= 0.55:
                status = "validated"
            data_rows.append(
                {
                    "canonical_keyword": str(keyword),
                    "industry_name": str(industry),
                    "relation_type": "data",
                    "relation_strength": round(strength, 4),
                    "lag_days": 1,
                    "sample_n": int(len(joined)),
                    "confidence": round(confidence, 4),
                    "status": status,
                    "last_validated_at": as_of_date,
                    "note": "auto_data_link",
                    "data_link_active": 1,
                }
            )

    data_df = pd.DataFrame(data_rows)
    if data_df.empty:
        return seed.sort_values(["relation_strength", "confidence"], ascending=[False, False]).reset_index(drop=True)

    merged = pd.concat([seed, data_df], ignore_index=True)
    merged["relation_strength"] = pd.to_numeric(merged["relation_strength"], errors="coerce").fillna(0.0)
    merged["confidence"] = pd.to_numeric(merged["confidence"], errors="coerce").fillna(0.0)
    merged = merged.sort_values(
        ["canonical_keyword", "industry_name", "data_link_active", "confidence", "relation_strength"],
        ascending=[True, True, False, False, False],
    )
    merged = merged.drop_duplicates(subset=["canonical_keyword", "industry_name"], keep="first").reset_index(drop=True)
    return merged.sort_values(["relation_strength", "confidence"], ascending=[False, False]).reset_index(drop=True)

def _build_holding_exposure(links_df: pd.DataFrame, score_df: pd.DataFrame, as_of_date: str) -> pd.DataFrame:
    pos = _read_csv(strategy_output_path("telegram_bridge", "manual_portfolio_positions.csv"), dtype=str).fillna("")
    if pos.empty or "code" not in pos.columns:
        return pd.DataFrame(columns=["as_of_date", "code", "name", "industry", "quantity", "exposure_score", "top_keywords", "link_count"])
    pos["code"] = pos["code"].astype(str).str.zfill(6)
    pos["quantity"] = pd.to_numeric(pos.get("quantity"), errors="coerce").fillna(0.0)
    pos = pos[pos["quantity"] > 0].copy()
    if pos.empty:
        return pd.DataFrame()

    if "industry" not in pos.columns or pos["industry"].astype(str).str.strip().eq("").all():
        px = _read_csv(strategy_output_path("price_panel_latest_snapshot.csv"), dtype={"code": str}).fillna("")
        if not px.empty and "industry" in px.columns:
            px["code"] = px["code"].astype(str).str.zfill(6)
            px = px[["code", "name", "industry"]].drop_duplicates(subset=["code"], keep="last")
            pos = pos.merge(px, on="code", how="left", suffixes=("", "_px"))
            pos["industry"] = pos.get("industry", "").where(pos.get("industry", "").astype(str).str.strip() != "", pos.get("industry_px"))
            pos["name"] = pos.get("name", "").where(pos.get("name", "").astype(str).str.strip() != "", pos.get("name_px"))
    pos["industry"] = pos.get("industry", "").astype(str).str.strip()
    pos = pos[pos["industry"] != ""].copy()
    if pos.empty or links_df.empty:
        return pd.DataFrame()

    latest_scores = score_df[score_df["as_of_date"] == as_of_date][["canonical_keyword", "trend_score"]].copy()
    if latest_scores.empty:
        return pd.DataFrame()
    latest_scores["canonical_keyword"] = latest_scores["canonical_keyword"].astype(str).str.lower()
    score_map = latest_scores.set_index("canonical_keyword")["trend_score"].to_dict()

    links = links_df.copy()
    links["canonical_keyword"] = links["canonical_keyword"].astype(str).str.lower()
    links["industry_name"] = links["industry_name"].astype(str).str.strip()
    links["relation_strength"] = pd.to_numeric(links.get("relation_strength"), errors="coerce").fillna(0.0)
    links["keyword_trend_score"] = links["canonical_keyword"].map(score_map).fillna(0.0)
    links["exposure_contrib"] = links["relation_strength"] * links["keyword_trend_score"] / 100.0
    links = links[links["exposure_contrib"] > 0].copy()
    if links.empty:
        return pd.DataFrame()

    joined = pos.merge(links, left_on="industry", right_on="industry_name", how="left")
    joined = joined.dropna(subset=["canonical_keyword"]).copy()
    if joined.empty:
        return pd.DataFrame()

    rows: list[dict[str, object]] = []
    for code, grp in joined.groupby("code"):
        view = grp.sort_values(["exposure_contrib", "keyword_trend_score"], ascending=[False, False])
        top_keywords = view["canonical_keyword"].astype(str).drop_duplicates().head(5).tolist()
        rows.append(
            {
                "as_of_date": as_of_date,
                "code": code,
                "name": str(view.iloc[0].get("name") or ""),
                "industry": str(view.iloc[0].get("industry") or ""),
                "quantity": float(view.iloc[0].get("quantity") or 0.0),
                "exposure_score": float(view["exposure_contrib"].sum()),
                "top_keywords": ",".join(top_keywords),
                "link_count": int(len(view)),
            }
        )
    return pd.DataFrame(rows).sort_values("exposure_score", ascending=False).reset_index(drop=True)


def _infer_token_lang(token: str) -> str:
    if re.search(r"[\u4e00-\u9fff]", token):
        return "zh"
    if re.search(r"[가-힣]", token):
        return "ko"
    return "en"


def _normalize_candidate_keyword(token: str) -> str:
    text = str(token or "").strip().lower()
    if not text:
        return ""
    text = re.sub(r"\s+", "_", text)
    text = re.sub(r"[_]{2,}", "_", text).strip("_")
    return text


def _is_noise_token(token: str, lang: str) -> bool:
    t = _normalize_candidate_keyword(token)
    if not t:
        return True
    compact = t.replace("_", "")
    if len(compact) < 2:
        return True
    if len(compact) > 40:
        return True
    if t in NOISE_TOKEN_EXACT:
        return True
    if NOISE_TOKEN_PATTERN.search(t):
        return True
    if compact.isdigit():
        return True
    if lang == "en" and len(compact) <= 2:
        return True
    return False


def _safe_int(value: object, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return int(default)


def _extract_metric_from_review_note(note: str, key: str) -> int:
    text = str(note or "").strip().lower()
    if not text:
        return 0
    # Supports both:
    # - auto_queue_from_news_count_84
    # - auto_queue_from_news_count_84_source_5
    # - count=84,sources=5
    patterns = [
        rf"{re.escape(key)}[_=](\d+)",
        rf"{re.escape(key)}[^0-9]*(\d+)",
    ]
    for ptn in patterns:
        m = re.search(ptn, text)
        if m:
            return _safe_int(m.group(1), default=0)
    return 0


def _classify_auto_keyword(token: str) -> tuple[str, str]:
    t = str(token or "").lower()
    macro_hits = ("rate", "cpi", "inflation", "yield", "oil", "gas", "usd", "달러", "유가", "금리", "물가", "通胀", "油价")
    risk_hits = ("war", "geopolit", "conflict", "중동", "전쟁", "분쟁", "停火", "战争")
    policy_hits = ("tariff", "subsidy", "regulat", "관세", "정책", "政策")
    if any(k in t for k in macro_hits):
        return "MACRO", "AUTO_DISCOVERY"
    if any(k in t for k in risk_hits):
        return "RISK", "AUTO_DISCOVERY"
    if any(k in t for k in policy_hits):
        return "POLICY", "AUTO_DISCOVERY"
    return "THEME", "AUTO_DISCOVERY"


def _next_keyword_id(existing_ids: list[str]) -> int:
    nums: list[int] = []
    for kid in existing_ids:
        m = re.search(r"(\d+)$", str(kid or "").strip())
        if m:
            try:
                nums.append(int(m.group(1)))
            except Exception:
                continue
    return (max(nums) + 1) if nums else 1


def _auto_promote_unclassified_to_taxonomy(
    unclassified: pd.DataFrame,
    taxonomy: pd.DataFrame,
    aliases: pd.DataFrame,
    cfg: TrendCollectConfig,
) -> tuple[pd.DataFrame, pd.DataFrame, int]:
    enabled = str(os.getenv("NEW_STRATEGY_TREND_AUTO_PROMOTE", "1")).strip().lower() not in {"0", "false", "no", "off"}
    if not enabled or unclassified.empty:
        return unclassified, pd.DataFrame(columns=["observed_at", "action", "token", "status", "note"]), 0

    min_count = _safe_int(os.getenv("NEW_STRATEGY_TREND_AUTO_PROMOTE_MIN_COUNT", "20"), default=20)
    min_sources = _safe_int(os.getenv("NEW_STRATEGY_TREND_AUTO_PROMOTE_MIN_SOURCES", "3"), default=3)
    max_new = _safe_int(os.getenv("NEW_STRATEGY_TREND_AUTO_PROMOTE_MAX_NEW", "12"), default=12)
    now = (cfg.run_at or datetime.now(SEOUL_TZ)).astimezone(SEOUL_TZ)
    now_iso = now.isoformat(timespec="seconds")
    today = now.date().isoformat()

    work = unclassified.copy()
    for col in ["normalized_keyword", "raw_keyword", "lang", "status", "review_note"]:
        if col not in work.columns:
            work[col] = ""
    for col in ["mention_count", "source_count", "confidence"]:
        if col not in work.columns:
            work[col] = ""

    work["normalized_keyword"] = work["normalized_keyword"].astype(str).map(_normalize_candidate_keyword)
    work["lang"] = work["lang"].astype(str).str.strip().str.lower()
    work["status"] = work["status"].astype(str).str.strip().str.lower()
    work["mention_count"] = pd.to_numeric(work["mention_count"], errors="coerce")
    work["source_count"] = pd.to_numeric(work["source_count"], errors="coerce")
    fill_count_mask = work["mention_count"].isna()
    if fill_count_mask.any():
        work.loc[fill_count_mask, "mention_count"] = work.loc[fill_count_mask, "review_note"].map(
            lambda x: _extract_metric_from_review_note(str(x), "count")
        )
    fill_source_mask = work["source_count"].isna()
    if fill_source_mask.any():
        work.loc[fill_source_mask, "source_count"] = work.loc[fill_source_mask, "review_note"].map(
            lambda x: _extract_metric_from_review_note(str(x), "source")
        )

    known = set(taxonomy["canonical_keyword"].astype(str).str.lower().tolist())
    known.update(aliases["canonical_keyword"].astype(str).str.lower().tolist())
    known.update(aliases["alias"].astype(str).str.lower().tolist())

    cand = work[work["status"].isin({"unclassified", "queued", ""})].copy()
    cand = cand[cand["normalized_keyword"].astype(str) != ""].copy()
    cand["mention_count"] = cand["mention_count"].fillna(0.0)
    cand["source_count"] = cand["source_count"].fillna(0.0)
    cand = cand.sort_values(["mention_count", "source_count", "normalized_keyword"], ascending=[False, False, True]).reset_index()

    if cand.empty:
        return unclassified, pd.DataFrame(columns=["observed_at", "action", "token", "status", "note"]), 0

    taxonomy_path = resolve_trend_file("keyword_taxonomy")
    taxonomy_raw = _read_csv(taxonomy_path, dtype=str).fillna("")
    if taxonomy_raw.empty:
        return unclassified, pd.DataFrame(columns=["observed_at", "action", "token", "status", "note"]), 0

    alias_path = resolve_trend_file("keyword_aliases")
    alias_raw = _read_csv(alias_path, dtype=str).fillna("")
    if alias_raw.empty:
        alias_raw = pd.DataFrame(columns=["canonical_keyword", "alias", "lang", "alias_type", "priority", "status", "created_at", "updated_at", "note"])

    next_id = _next_keyword_id(taxonomy_raw.get("keyword_id", pd.Series(dtype=str)).astype(str).tolist())
    promoted_rows: list[dict[str, str]] = []
    promoted_alias_rows: list[dict[str, str]] = []
    logs: list[dict[str, str]] = []
    promoted_tokens: dict[str, tuple[str, str, float]] = {}

    for row in cand.to_dict("records"):
        token = _normalize_candidate_keyword(row.get("normalized_keyword") or row.get("raw_keyword"))
        if not token:
            continue
        lang = str(row.get("lang") or _infer_token_lang(token)).strip().lower()
        mention_count = max(0, _safe_int(row.get("mention_count"), default=0))
        source_count = max(0, _safe_int(row.get("source_count"), default=0))

        if token in known or token in promoted_tokens:
            continue
        if mention_count < min_count or source_count < min_sources:
            continue
        if _is_noise_token(token, lang):
            logs.append(
                {
                    "observed_at": now_iso,
                    "action": "rejected_noise_token",
                    "token": token,
                    "status": "rejected",
                    "note": f"count={mention_count},sources={source_count}",
                }
            )
            continue

        category_l1, category_l2 = _classify_auto_keyword(token)
        confidence = min(0.99, 0.4 + min(120, mention_count) * 0.003 + min(20, source_count) * 0.02)
        keyword_id = f"K{next_id:04d}"
        next_id += 1

        promoted_rows.append(
            {
                "keyword_id": keyword_id,
                "canonical_keyword": token,
                "category_l1": category_l1,
                "category_l2": category_l2,
                "polarity_default": "neutral",
                "geo_scope": "global",
                "horizon": "short",
                "base_weight": "0.85",
                "ambiguity_level": "high",
                "status": "candidate",
                "created_at": today,
                "updated_at": today,
                "note": f"auto_promoted count={mention_count},sources={source_count}",
            }
        )
        promoted_alias_rows.append(
            {
                "canonical_keyword": token,
                "alias": str(row.get("raw_keyword") or token),
                "lang": lang if lang in {"ko", "en", "zh"} else _infer_token_lang(token),
                "alias_type": "auto",
                "priority": "1",
                "status": "active",
                "created_at": today,
                "updated_at": today,
                "note": "auto_promoted_alias",
            }
        )
        promoted_tokens[token] = (category_l1, category_l2, confidence)
        known.add(token)
        logs.append(
            {
                "observed_at": now_iso,
                "action": "auto_promoted_taxonomy",
                "token": token,
                "status": "candidate",
                "note": f"count={mention_count},sources={source_count},confidence={confidence:.3f}",
            }
        )
        if len(promoted_rows) >= max_new:
            break

    if not promoted_rows:
        return unclassified, pd.DataFrame(logs), 0

    taxonomy_out = pd.concat([taxonomy_raw, pd.DataFrame(promoted_rows)], ignore_index=True)
    taxonomy_out = taxonomy_out.drop_duplicates(subset=["canonical_keyword"], keep="first").reset_index(drop=True)
    alias_out = pd.concat([alias_raw, pd.DataFrame(promoted_alias_rows)], ignore_index=True)
    alias_out = alias_out.drop_duplicates(subset=["canonical_keyword", "alias", "lang"], keep="first").reset_index(drop=True)

    # Mark promoted rows in unclassified queue for auditability.
    out_unclassified = work.copy()
    for token, (l1, l2, confidence) in promoted_tokens.items():
        mask = out_unclassified["normalized_keyword"].astype(str).map(_normalize_candidate_keyword) == token
        out_unclassified.loc[mask, "status"] = "auto_promoted"
        out_unclassified.loc[mask, "predicted_l1"] = l1
        out_unclassified.loc[mask, "predicted_l2"] = l2
        out_unclassified.loc[mask, "confidence"] = f"{confidence:.3f}"
        base_note = out_unclassified.loc[mask, "review_note"].astype(str).fillna("")
        out_unclassified.loc[mask, "review_note"] = np.where(
            base_note.str.strip() == "",
            "auto_promoted_to_taxonomy",
            base_note + " | auto_promoted_to_taxonomy",
        )

    if not cfg.dry_run:
        _write_csv(taxonomy_out, taxonomy_path)
        _write_csv(alias_out, alias_path)
        _write_csv(out_unclassified, resolve_trend_file("unclassified_keywords"))

    return out_unclassified, pd.DataFrame(logs), int(len(promoted_rows))


def _update_unclassified(mentions_today: pd.DataFrame, aliases: pd.DataFrame, taxonomy: pd.DataFrame, cfg: TrendCollectConfig) -> tuple[pd.DataFrame, pd.DataFrame]:
    path = resolve_trend_file("unclassified_keywords")
    prev = _read_csv(path, dtype=str).fillna("")
    if mentions_today.empty:
        return prev, pd.DataFrame(columns=["observed_at", "action", "token", "status", "note"])

    known = set(taxonomy["canonical_keyword"].astype(str).str.lower().tolist())
    known.update(aliases["alias"].astype(str).str.lower().tolist())
    known.update(aliases["canonical_keyword"].astype(str).str.lower().tolist())
    existing_tokens = set(prev.get("normalized_keyword", pd.Series(dtype=str)).astype(str).str.lower().tolist())

    pat = re.compile(r"[A-Za-z][A-Za-z0-9_+-]{2,}|[가-힣]{2,}|[\u4e00-\u9fff]{2,}")
    counts: dict[str, int] = {}
    source_counts: dict[str, set[str]] = {}
    lang_map: dict[str, str] = {}
    for row in mentions_today.to_dict("records"):
        title = str(row.get("title") or "")
        source_domain = str(row.get("source_domain") or "").strip().lower()
        for token in pat.findall(title):
            norm = _normalize_candidate_keyword(token)
            token_lang = _infer_token_lang(token)
            if not norm or norm in known:
                continue
            if _is_noise_token(norm, token_lang):
                continue
            counts[norm] = counts.get(norm, 0) + 1
            if norm not in source_counts:
                source_counts[norm] = set()
            if source_domain:
                source_counts[norm].add(source_domain)
            lang_map.setdefault(norm, token_lang)

    now_iso = (cfg.run_at or datetime.now(SEOUL_TZ)).isoformat(timespec="seconds")
    add_rows: list[dict[str, str]] = []
    logs: list[dict[str, str]] = []
    min_count = int(os.getenv("NEW_STRATEGY_TREND_UNCLASSIFIED_MIN_COUNT", "8"))
    min_sources = int(os.getenv("NEW_STRATEGY_TREND_UNCLASSIFIED_MIN_SOURCES", "2"))
    max_new = int(os.getenv("NEW_STRATEGY_TREND_UNCLASSIFIED_MAX_NEW", "80"))
    for token, count in sorted(counts.items(), key=lambda x: (-x[1], x[0])):
        src_cnt = int(len(source_counts.get(token, set())))
        if count < min_count or src_cnt < min_sources or token in existing_tokens:
            continue
        confidence = min(0.95, 0.25 + min(100, int(count)) * 0.004 + min(20, src_cnt) * 0.02)
        add_rows.append(
            {
                "observed_at": now_iso,
                "raw_keyword": token,
                "normalized_keyword": token,
                "source": "news",
                "lang": lang_map.get(token, _infer_token_lang(token)),
                "mention_count": str(int(count)),
                "source_count": str(int(src_cnt)),
                "predicted_l1": "",
                "predicted_l2": "",
                "confidence": f"{confidence:.3f}",
                "status": "unclassified",
                "review_note": f"auto_queue_from_news_count_{count}_source_{src_cnt}",
            }
        )
        logs.append(
            {
                "observed_at": now_iso,
                "action": "queued_unclassified",
                "token": token,
                "status": "unclassified",
                "note": f"count={count},sources={src_cnt}",
            }
        )
        if len(add_rows) >= max_new:
            break

    out = pd.concat([prev, pd.DataFrame(add_rows)], ignore_index=True)
    if not out.empty:
        out = out.drop_duplicates(subset=["normalized_keyword"], keep="first").reset_index(drop=True)
    if not cfg.dry_run:
        _write_csv(out, path)
    return out, pd.DataFrame(logs)


def _append_status(row: dict[str, object], cfg: TrendCollectConfig) -> pd.DataFrame:
    path = resolve_trend_file("collection_status")
    prev = _read_csv(path, dtype=str).fillna("")
    out = pd.concat([prev, pd.DataFrame([row])], ignore_index=True)
    out["run_at"] = pd.to_datetime(out["run_at"], errors="coerce")
    cutoff_ref = (cfg.run_at or datetime.now(SEOUL_TZ))
    if cutoff_ref.tzinfo is not None:
        cutoff_ref = cutoff_ref.replace(tzinfo=None)
    cutoff = cutoff_ref - timedelta(days=90)
    out = out[(out["run_at"].isna()) | (out["run_at"] >= cutoff)].copy()
    out = out.sort_values("run_at", ascending=False).reset_index(drop=True)
    out["run_at"] = out["run_at"].dt.strftime("%Y-%m-%dT%H:%M:%S")
    if not cfg.dry_run:
        _write_csv(out, path)
    return out


def run_trend_pipeline(cfg: TrendCollectConfig) -> dict[str, object]:
    ensure_trend_lab_dirs()
    started = datetime.now(SEOUL_TZ)
    run_at = (cfg.run_at or started).astimezone(SEOUL_TZ)

    taxonomy = _load_taxonomy()
    aliases = _load_aliases()
    mentions_new, errors, counters = _collect_mentions(cfg, taxonomy, aliases, lookback_days=max(1, math.ceil(int(cfg.window_hours) / 24)))
    mentions_rolling = _save_mentions_rolling(mentions_new, cfg)
    bootstrap_rows = 0
    bootstrap_trigger_days = min(int(cfg.score_window_days), 21)
    history_days = int(pd.to_datetime(mentions_rolling.get("as_of_date"), errors="coerce").dropna().dt.date.nunique()) if not mentions_rolling.empty else 0
    if history_days < bootstrap_trigger_days:
        boot_mentions, boot_errors, boot_counters = _collect_mentions(
            cfg,
            taxonomy,
            aliases,
            lookback_days=int(cfg.score_window_days),
        )
        if not boot_mentions.empty:
            bootstrap_rows = int(len(boot_mentions))
            mentions_rolling = _save_mentions_rolling(boot_mentions, cfg)
        errors.extend(boot_errors)
        counters["query_count"] += int(boot_counters.get("query_count", 0))
        counters["request_success"] += int(boot_counters.get("request_success", 0))
        counters["request_error"] += int(boot_counters.get("request_error", 0))

    panel = _daily_panel(mentions_rolling, taxonomy, cfg)
    score_df = _build_daily_scores(panel, taxonomy, cfg)
    as_of_date = run_at.date().isoformat()

    if not cfg.dry_run:
        _write_csv(score_df, resolve_trend_file("keyword_daily_scores"))

    links_df = _build_keyword_industry_links(score_df, as_of_date)
    if not cfg.dry_run:
        _write_csv(links_df, resolve_trend_file("keyword_industry_links"))

    exposure_df = _build_holding_exposure(links_df, score_df, as_of_date)
    if not cfg.dry_run:
        _write_csv(exposure_df, resolve_trend_file("holding_exposure"))

    snapshot = _build_snapshot(score_df, mentions_rolling, run_at=run_at, window_hours=cfg.window_hours)
    if not cfg.dry_run:
        resolve_trend_file("snapshot").write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")

    mentions_today = mentions_rolling[mentions_rolling["as_of_date"].astype(str) == as_of_date].copy() if not mentions_rolling.empty else pd.DataFrame()
    if mentions_today.empty:
        source_roots_today = []
    else:
        roots_series = (
            mentions_today["source_root"]
            if "source_root" in mentions_today.columns
            else pd.Series([SOURCE_ROOT_GOOGLE_NEWS] * len(mentions_today), index=mentions_today.index)
        )
        roots_series = _normalize_source_root_series(roots_series)
        source_roots_today = sorted(
            list(
                dict.fromkeys(
                    [str(x).strip() for x in roots_series.astype(str).tolist() if str(x).strip()]
                )
            )
        )
    source_root_count_today = int(len(source_roots_today))
    source_root_tier = _representativeness_tier(source_root_count_today)
    source_root_contract_ok = bool(source_root_count_today >= max(1, MIN_INDEPENDENT_SOURCE_ROOTS))
    unclassified, logs = _update_unclassified(mentions_today, aliases, taxonomy, cfg)
    unclassified, auto_logs, auto_promoted_total = _auto_promote_unclassified_to_taxonomy(unclassified, taxonomy, aliases, cfg)
    all_logs = pd.concat([logs, auto_logs], ignore_index=True)
    if not all_logs.empty:
        prev_logs = _read_csv(resolve_trend_file("classification_log"), dtype=str).fillna("")
        all_logs = pd.concat([prev_logs, all_logs], ignore_index=True).drop_duplicates(subset=["observed_at", "token", "action"], keep="last")
        if not cfg.dry_run:
            _write_csv(all_logs, resolve_trend_file("classification_log"))

    finished = datetime.now(SEOUL_TZ)
    status_row = {
        "run_at": finished.strftime("%Y-%m-%dT%H:%M:%S"),
        "as_of_date": as_of_date,
        "window_start": (run_at - timedelta(hours=int(cfg.window_hours))).isoformat(timespec="seconds"),
        "window_end": run_at.isoformat(timespec="seconds"),
        "status": "ok" if not errors else "partial",
        "query_count": counters.get("query_count", 0),
        "request_success": counters.get("request_success", 0),
        "request_error": counters.get("request_error", 0),
        "mentions_new_rows": int(len(mentions_new)),
        "mentions_rolling_rows": int(len(mentions_rolling)),
        "bootstrap_new_rows": int(bootstrap_rows),
        "keywords_covered_today": int((score_df[score_df["as_of_date"] == as_of_date]["mention_count"] > 0).sum()),
        "source_root_count_today": source_root_count_today,
        "source_roots_today": ",".join(source_roots_today),
        "representativeness": source_root_tier,
        "source_root_contract_ok": int(source_root_contract_ok),
        "min_source_roots_contract": int(max(1, MIN_INDEPENDENT_SOURCE_ROOTS)),
        "target_source_roots_contract": int(max(1, TARGET_INDEPENDENT_SOURCE_ROOTS)),
        "unclassified_total": int(len(unclassified)),
        "auto_promoted_total": int(auto_promoted_total),
        "error_count": int(len(errors)),
        "error_summary": "; ".join(errors[:8]),
        "duration_seconds": int((finished - started).total_seconds()),
    }
    _append_status(status_row, cfg)

    return {
        "status": status_row["status"],
        "as_of_date": as_of_date,
        "mentions_new_rows": int(len(mentions_new)),
        "mentions_rolling_rows": int(len(mentions_rolling)),
        "bootstrap_new_rows": int(bootstrap_rows),
        "keywords_covered_today": int(status_row["keywords_covered_today"]),
        "source_root_count_today": int(status_row["source_root_count_today"]),
        "representativeness": str(status_row["representativeness"]),
        "source_root_contract_ok": bool(int(status_row["source_root_contract_ok"])),
        "auto_promoted_total": int(status_row["auto_promoted_total"]),
        "error_count": int(len(errors)),
        "duration_seconds": int(status_row["duration_seconds"]),
        "paths": {
            "snapshot": str(resolve_trend_file("snapshot")),
            "daily_scores": str(resolve_trend_file("keyword_daily_scores")),
            "links": str(resolve_trend_file("keyword_industry_links")),
            "holding_exposure": str(resolve_trend_file("holding_exposure")),
            "mentions_rolling": str(resolve_trend_file("news_mentions_rolling")),
            "status": str(resolve_trend_file("collection_status")),
        },
    }


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run daily trend-lab collection and scoring pipeline.")
    p.add_argument("--window-hours", type=int, default=24)
    p.add_argument("--retention-days", type=int, default=35)
    p.add_argument("--score-window-days", type=int, default=30)
    p.add_argument("--max-items-per-query", type=int, default=40)
    p.add_argument("--request-timeout-seconds", type=float, default=18.0)
    p.add_argument("--request-sleep-seconds", type=float, default=0.12)
    p.add_argument("--run-at", default="")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--execute-once", action="store_true", help="compat flag for scheduler")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    run_at = None
    if str(args.run_at or "").strip():
        ts = pd.to_datetime(str(args.run_at), errors="coerce")
        if pd.isna(ts):
            raise SystemExit(f"invalid --run-at value: {args.run_at}")
        run_at = ts.to_pydatetime()
        run_at = run_at.replace(tzinfo=SEOUL_TZ) if run_at.tzinfo is None else run_at.astimezone(SEOUL_TZ)

    cfg = TrendCollectConfig(
        window_hours=int(args.window_hours),
        retention_days=int(args.retention_days),
        score_window_days=int(args.score_window_days),
        max_items_per_query=int(args.max_items_per_query),
        request_timeout_seconds=float(args.request_timeout_seconds),
        request_sleep_seconds=float(args.request_sleep_seconds),
        run_at=run_at,
        dry_run=bool(args.dry_run),
    )
    print(json.dumps(run_trend_pipeline(cfg), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

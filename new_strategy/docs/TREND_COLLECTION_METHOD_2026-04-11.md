# Trend Collection Method (2026-04-11)

## Schedule
- Run at `06:00` Asia/Seoul once per day.
- Collection window is previous `24h`: `[D-1 06:00, D 06:00)`.
- Retry interval: every `30m` until success (same day).

## Sources
- Google News RSS search by keyword alias (ko/en/zh).
- Bing News RSS search by keyword alias (ko/en/zh).
- GDELT Doc API (keyword, multi-language news index).
- Hacker News Algolia API (keyword-based tech/news stream).
- Sina RSS (중국 포털 뉴스 피드, 키워드 매칭 필터 적용).
- ArXiv API (논문/프리프린트 키워드 검색).
- Alias input: `trend_keyword_aliases.csv`.
- Canonical taxonomy input: `trend_keyword_taxonomy.csv`.

## Independent Source-Root Contract
- `source_root`: 수집 루트 식별자 (예: `google_news_rss`, `gdelt_api`, `reddit_api`).
- 당일 독립루트 수(`independent_source_root_count_today`)를 스냅샷/상태로그에 기록한다.
- 계약 최소값: `min_source_roots_contract` (기본 3, 3 미만 불가).
- 운영 목표값: `target_source_roots_contract` (기본 4, 최소값 이상).
- 대표성 등급:
  - `high`: 독립루트 수가 `target_source_roots_contract` 이상
  - `medium`: 독립루트 수가 `min_source_roots_contract` 이상
  - `low`: 그 외
- 계약 미충족 시 대시보드에 경고를 표시한다.

## Rolling Policy
- Raw mentions file: `trend_news_mentions_rolling.csv`.
- Retention: `35d` raw, score window `30d`.

## Score Components
- `burst_z` -> `burst_score`
- `source_diversity_score`
- `volume_score`
- `persistence_score`
- `cross_lang_consensus_score`
- `freshness_score` (30d context)

Weights:
- `20 : 20 : 15 : 15 : 15 : 15`

## Outputs
- `trend_keyword_daily_scores.csv`
- `trend_global_snapshot.json`
- `trend_keyword_industry_links.csv`
- `trend_holding_exposure.csv`
- `trend_collection_status.csv`

### Source-Root Fields
- `trend_global_snapshot.json > summary`
  - `independent_source_root_count_today`
  - `independent_source_roots_today`
  - `representativeness`
  - `source_root_contract_ok`
  - `min_source_roots_contract`
  - `target_source_roots_contract`
- `trend_collection_status.csv`
  - `source_root_count_today`
  - `source_roots_today`
  - `representativeness`
  - `source_root_contract_ok`
  - `min_source_roots_contract`
  - `target_source_roots_contract`

## Failure Policy
- No silent fallback.
- Every run appends `trend_collection_status.csv` with status/error summary.

## Related UI Contract
- Trend dashboard chart rendering contract:
  - `new_strategy/docs/TREND_CHART_CONTRACT_2026-04-12.md`

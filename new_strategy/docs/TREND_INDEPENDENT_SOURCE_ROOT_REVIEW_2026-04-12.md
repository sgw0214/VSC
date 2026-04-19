# Trend Independent Source-Root Review (2026-04-12)

## 목적
- 글로벌 데일리 트렌드의 대표성이 충분한지, 수집 루트 독립성 관점에서 점검한다.
- 핵심 기준은 `source_root`(수집 채널 루트) 수와 품질 계약이다.

## 현재 점검 결과 (KST 2026-04-12 실행 기준)
- 실행 엔트리: `python -m new_strategy.run_trend_pipeline --execute-once`
- 결과:
  - `independent_source_root_count_today = 1`
  - `independent_source_roots_today = ["google_news_rss"]`
  - `representativeness = low`
  - `source_root_contract_ok = false` (계약 최소 3 미달)

## 원인
- 현재 수집 파이프라인의 실수집 루트가 `google_news_rss` 단일 루트다.
- 기존 데이터 스키마 이행 과정에서 `NaN`이 루트로 잘못 집계될 수 있었고(가짜 2루트), 이번 수정으로 정규화했다.

## 이번 수정 반영
- `run_trend_pipeline.py`
  - `source_root` 결측/NaN/none/null 정규화 추가 (`_normalize_source_root_series`).
  - 스냅샷/상태로그에 독립루트 계약 필드 저장:
    - `source_root_count_today`, `source_roots_today`
    - `representativeness`
    - `source_root_contract_ok`
    - `min_source_roots_contract`, `target_source_roots_contract`
- `streamlit_app.py`
  - 글로벌 트렌드 화면에 독립루트 KPI 추가.
  - 계약 미충족 시 경고 표시.
  - 수집 상태 표에 독립루트/계약충족/대표성 컬럼 표시.

## 운영 판단
- 현재는 점수가 정상 계산되더라도, “글로벌 대표성” 해석에는 제한이 있다.
- 해석 규칙:
  - `source_root_contract_ok=false`면 참고용(탐색)으로만 사용.
  - 투자 의사결정 핵심 근거로 승격하지 않는다.

## 다음 확장 우선순위 (독립루트 확보)
- 1순위: 뉴스 집계 API 루트 1개 추가 (Google RSS와 다른 공급자)
- 2순위: 소셜/포럼 루트 1개 추가 (뉴스와 독립된 신호 축)
- 3순위: 공식 보도자료/정책 공지 루트 1개 추가 (정책 이벤트 축)

목표: 최소 3루트(`min_source_roots_contract=3`) 계약 충족 후, 4루트(`target_source_roots_contract=4`)에서 대표성 `high` 진입.

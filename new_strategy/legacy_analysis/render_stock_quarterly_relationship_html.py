from io import StringIO
from pathlib import Path
import argparse

import matplotlib.pyplot as plt
from matplotlib import font_manager
import pandas as pd

from new_strategy.paths import data_path, output_path

KO_TO_EN = {
    "분기매출액": "revenue_q",
    "분기영업이익": "op_income_q",
    "분기당기순이익": "net_income_q",
    "분기영업이익률": "op_margin_q",
    "분기매출액YoY증감액": "revenue_q_yoy",
    "분기영업이익YoY증감액": "op_income_q_yoy",
    "분기당기순이익YoY증감액": "net_income_q_yoy",
    "분기매출액QoQ증감액": "revenue_q_qoq",
    "분기영업이익QoQ증감액": "op_income_q_qoq",
    "분기당기순이익QoQ증감액": "net_income_q_qoq",
    "분기순이익률": "net_margin_q",
    "분기순이익률QoQ변화": "net_margin_q_qoq",
    "분기영업이익률QoQ변화": "op_margin_q_qoq",
    "영업이익대비매출QoQ격차": "op_income_vs_revenue_qoq_gap",
    "당기순이익대비매출QoQ격차": "net_income_vs_revenue_qoq_gap",
    "영업이익QoQ가속도": "op_income_qoq_accel",
    "당기순이익QoQ가속도": "net_income_qoq_accel",
    "최근4분기매출합": "revenue_t4_sum",
    "최근4분기영업이익합": "op_income_t4_sum",
    "최근4분기당기순이익합": "net_income_t4_sum",
    "최근4분기영업이익변동성": "op_income_t4_std",
    "최근4분기당기순이익변동성": "net_income_t4_std",
    "영업이익흑자전환": "op_turnaround_flag",
    "당기순이익흑자전환": "net_turnaround_flag",
    "영업이익2분기연속흑자": "op_2q_positive_flag",
    "당기순이익2분기연속흑자": "net_2q_positive_flag",
    "흑자전환여부": "any_turnaround_flag",
    "2분기연속흑자여부": "any_2q_positive_flag",
    "분기매출액YoY증가율": "revenue_q_yoy_pct",
    "분기영업이익YoY증가율": "op_income_q_yoy_pct",
    "분기당기순이익YoY증가율": "net_income_q_yoy_pct",
    "분기매출액QoQ증가율": "revenue_q_qoq_pct",
    "분기영업이익QoQ증가율": "op_income_q_qoq_pct",
    "분기당기순이익QoQ증가율": "net_income_q_qoq_pct",
    "분기주가수익률": "period_ret",
    "공시후30일수익률": "post_filing_30d_ret",
    "공시후20일수익률": "post_filing_20d_ret",
    "공시후60일수익률": "post_filing_60d_ret",
    "공시후90일수익률": "post_filing_90d_ret",
    "분기KOSPI수익률": "period_kospi_ret",
    "분기평균VIX": "period_avg_vix",
    "분기평균USDKRW": "period_avg_usdkrw",
    "분기평균미국10년금리": "period_avg_us10y",
    "분기평균국고10년금리": "period_avg_kr10y",
    "분기평균금가격": "period_avg_gold_kr_close",
    "분기평균리스크카운트": "period_avg_risk_count",
    "분기평균노출비중": "period_avg_exposure",
}


def configure_korean_font() -> None:
    candidates = [
        "Malgun Gothic",
        "NanumGothic",
        "AppleGothic",
        "Noto Sans CJK KR",
        "DejaVu Sans",
    ]
    available = {f.name for f in font_manager.fontManager.ttflist}
    for name in candidates:
        if name in available:
            plt.rcParams["font.family"] = name
            break
    plt.rcParams["axes.unicode_minus"] = False


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Render quarterly relationship chart for one stock.")
    p.add_argument("--code", required=True, help="6-digit stock code")
    p.add_argument("--x-col", default="quarter_label")
    p.add_argument("--left-col", default="net_income_q_yoy_pct")
    p.add_argument("--right-col", default="post_filing_60d_ret")
    p.add_argument("--input", default=str(data_path("quarterly_stock_panel.csv")))
    p.add_argument("--output", default="")
    p.add_argument("--auto-best", action="store_true", help="Use 최고상관변수/최고상관대상 from stock summary")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    configure_korean_font()
    code = str(args.code).zfill(6)
    input_path = Path(args.input)
    left_col = args.left_col
    right_col = args.right_col

    if args.auto_best:
        summary = pd.read_csv(output_path("stock_quarterly_relationship_summary.csv"), dtype=str, low_memory=False)
        row = summary[summary["종목코드"].astype(str).str.zfill(6) == code]
        if row.empty:
            raise SystemExit(f"no summary rows for code={code}")
        left_col = KO_TO_EN.get(row.iloc[0]["최고상관변수"], row.iloc[0]["최고상관변수"])
        right_col = KO_TO_EN.get(row.iloc[0]["최고상관대상"], row.iloc[0]["최고상관대상"])

    if args.output:
        out_path = Path(args.output)
    else:
        out_path = output_path(f"{code}_{left_col}_vs_{right_col}.html")

    df = pd.read_csv(input_path, dtype={"code": str}, low_memory=False)
    s = df[df["code"].astype(str).str.zfill(6) == code].copy()
    if s.empty:
        raise SystemExit(f"no rows for code={code}")

    s["fiscal_year"] = pd.to_numeric(s["fiscal_year"], errors="coerce")
    s["reprt_code"] = s["reprt_code"].astype(str)
    q_order = {"11013": 1, "11012": 2, "11014": 3, "11011": 4}
    s["quarter_order"] = s["reprt_code"].map(q_order).fillna(9)
    s = s.sort_values(["fiscal_year", "quarter_order"]).reset_index(drop=True)

    for col in [left_col, right_col]:
        s[col] = pd.to_numeric(s[col], errors="coerce")

    s = s[s[left_col].notna() | s[right_col].notna()].copy()
    x = s[args.x_col].astype(str)
    x_pos = list(range(len(s)))
    left = s[left_col]
    right = s[right_col] * 100.0
    name = s["name"].iloc[0]

    fig, ax1 = plt.subplots(figsize=(16, 8))
    ax2 = ax1.twinx()

    ax1.bar(x_pos, left, color="#d98c2b", alpha=0.75, width=0.7, label=left_col)
    ax2.plot(x_pos, right, color="#1f5c99", linewidth=2.2, marker="o", markersize=4, label=right_col)

    ax1.set_title(f"{name}({code}) quarterly relationship", fontsize=14)
    ax1.set_xlabel("Quarter")
    ax1.set_ylabel(f"{left_col}")
    ax2.set_ylabel(f"{right_col} (%)")
    ax1.grid(True, axis="y", alpha=0.25)
    tick_idx = list(range(0, len(x_pos), 2))
    if tick_idx[-1] != len(x) - 1:
        tick_idx.append(len(x) - 1)
    ax1.set_xticks(tick_idx)
    ax1.set_xticklabels([x.iloc[i] for i in tick_idx], rotation=90, fontsize=9, ha="center")
    plt.subplots_adjust(bottom=0.28, left=0.08, right=0.92, top=0.9)

    handles1, labels1 = ax1.get_legend_handles_labels()
    handles2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(handles1 + handles2, labels1 + labels2, loc="upper left", frameon=False)

    svg = StringIO()
    fig.savefig(svg, format="svg", bbox_inches="tight")
    plt.close(fig)

    latest = s.iloc[-1]
    html = f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{name} {code} quarterly relationship</title>
  <style>
    :root {{
      --bg: #f6f3ed;
      --card: #fffdf9;
      --ink: #1f2b36;
      --muted: #6e7a86;
      --line: #ddd4c6;
      --bar: #d98c2b;
      --linec: #1f5c99;
    }}
    body {{
      margin: 0;
      background: linear-gradient(180deg, #f8f4ec 0%, var(--bg) 100%);
      color: var(--ink);
      font-family: "Segoe UI", "Malgun Gothic", sans-serif;
    }}
    .wrap {{
      max-width: 1280px;
      margin: 0 auto;
      padding: 28px 18px 36px;
    }}
    .card {{
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 22px;
      box-shadow: 0 18px 40px rgba(31, 43, 54, 0.08);
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: 28px;
    }}
    p {{
      margin: 0 0 18px;
      color: var(--muted);
    }}
    .meta {{
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      margin-bottom: 18px;
      font-size: 14px;
    }}
    .pill {{
      padding: 8px 12px;
      border-radius: 999px;
      background: #f5efe4;
      border: 1px solid #ead8b8;
    }}
    .chart svg {{
      width: 100%;
      height: auto;
      display: block;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      margin-top: 18px;
      font-size: 13px;
    }}
    th, td {{
      border-bottom: 1px solid var(--line);
      padding: 8px 6px;
      text-align: right;
    }}
    th:first-child, td:first-child {{
      text-align: left;
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <h1>{name} ({code})</h1>
      <p>막대: {left_col}, 선: {right_col}</p>
      <div class="meta">
        <div class="pill">구간: {s.iloc[0][args.x_col]} ~ {latest[args.x_col]}</div>
        <div class="pill">최근 {left_col}: {latest[left_col]:.4f}</div>
        <div class="pill">최근 {right_col}: {latest[right_col]:.4f}</div>
        <div class="pill">관측치: {len(s)}</div>
      </div>
      <div class="chart">{svg.getvalue()}</div>
      <table>
        <thead>
          <tr>
            <th>분기</th>
            <th>{left_col}</th>
            <th>{right_col}</th>
          </tr>
        </thead>
        <tbody>
          {''.join(f"<tr><td>{row[args.x_col]}</td><td>{'' if pd.isna(row[left_col]) else f'{row[left_col]:.4f}'}</td><td>{'' if pd.isna(row[right_col]) else f'{row[right_col]:.4f}'}</td></tr>" for _, row in s.iterrows())}
        </tbody>
      </table>
    </div>
  </div>
</body>
</html>
"""

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    print(out_path)


if __name__ == "__main__":
    main()

from io import StringIO
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from new_strategy.paths import data_path, output_path

DATA_PATH = data_path("fundamental_quarterly_multi.csv")
OUT_PATH = output_path("samsung_005930_quarterly_revenue.html")

ORDER = {"11013": 1, "11012": 2, "11014": 3, "11011": 4}
LABEL = {"11013": "Q1", "11012": "Q2", "11014": "Q3", "11011": "Q4"}


def main() -> None:
    df = pd.read_csv(DATA_PATH, low_memory=False)
    s = df[df["종목코드"].astype(str).str.zfill(6) == "005930"].copy()
    s["보고서코드"] = s["보고서코드"].astype(str).str.extract(r"(\d{5})", expand=False)
    s = s[s["보고서코드"].isin(ORDER)].copy()
    s["q_order"] = s["보고서코드"].map(ORDER)
    s["quarter_label"] = s["사업연도"].astype(int).astype(str) + "-" + s["보고서코드"].map(LABEL)
    s = s.sort_values(["사업연도", "q_order"])
    s = s[s["분기매출액"].notna()].copy()
    s["revenue_trn"] = s["분기매출액"] / 1e12

    fig, ax = plt.subplots(figsize=(14, 6))
    ax.plot(s["quarter_label"], s["revenue_trn"], color="#1f6aa5", linewidth=2.2)
    ax.scatter(s["quarter_label"], s["revenue_trn"], color="#1f6aa5", s=18)
    ax.set_title("Samsung Electronics Quarterly Revenue", fontsize=14)
    ax.set_ylabel("KRW Trillion")
    ax.set_xlabel("Quarter")
    ax.grid(True, axis="y", alpha=0.3)
    plt.xticks(rotation=70, fontsize=8)
    plt.tight_layout()

    svg = StringIO()
    fig.savefig(svg, format="svg", bbox_inches="tight")
    plt.close(fig)

    latest = s.iloc[-1]
    html = f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Samsung 005930 Quarterly Revenue</title>
  <style>
    :root {{
      --bg: #f4efe6;
      --card: #fffdf8;
      --ink: #1d2a36;
      --muted: #6c7782;
      --line: #d8cfc1;
      --accent: #1f6aa5;
    }}
    body {{
      margin: 0;
      font-family: "Segoe UI", "Malgun Gothic", sans-serif;
      background:
        radial-gradient(circle at top left, #efe4d0 0, transparent 28%),
        linear-gradient(180deg, #f7f1e8 0%, var(--bg) 100%);
      color: var(--ink);
    }}
    .wrap {{
      max-width: 1200px;
      margin: 0 auto;
      padding: 32px 20px 40px;
    }}
    .card {{
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 20px;
      padding: 24px;
      box-shadow: 0 20px 50px rgba(29, 42, 54, 0.08);
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: 30px;
      line-height: 1.1;
    }}
    p {{
      margin: 0 0 18px;
      color: var(--muted);
    }}
    .meta {{
      display: flex;
      gap: 16px;
      flex-wrap: wrap;
      margin-bottom: 18px;
      font-size: 14px;
    }}
    .pill {{
      padding: 8px 12px;
      border-radius: 999px;
      background: #f2f6fa;
      color: var(--accent);
      border: 1px solid #d5e2ee;
    }}
    .chart {{
      overflow-x: auto;
    }}
    .chart svg {{
      width: 100%;
      height: auto;
      display: block;
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <h1>삼성전자 분기매출 추이</h1>
      <p>종목코드 005930, 기준 컬럼은 <code>분기매출액</code>입니다.</p>
      <div class="meta">
        <div class="pill">구간: {s.iloc[0]["quarter_label"]} ~ {latest["quarter_label"]}</div>
        <div class="pill">최근 분기 매출: {latest["revenue_trn"]:.1f}조원</div>
        <div class="pill">총 관측치: {len(s)}개</div>
      </div>
      <div class="chart">{svg.getvalue()}</div>
    </div>
  </div>
</body>
</html>
"""
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(html, encoding="utf-8")
    print(OUT_PATH)


if __name__ == "__main__":
    main()

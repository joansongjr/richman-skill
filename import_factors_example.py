#!/usr/bin/env python3
"""示例脚本：从本地 CSV 导入估值/因子数据到 fundamentals 表。

用途：
- 你可以从 FactSet / Wind / 券商终端导出一个包含 PE、PB、EPS 增速、评级等字段的 CSV，
  放在 data/factors/example_factors.csv。
- 本脚本读取该 CSV，并按 code 匹配 stocks 表中的标的，将数据写入 fundamentals 表。

注意：
- 本脚本不直接连接任何第三方 API，只使用你本地已有的导出文件。
- 示例 CSV 格式见 data/factors/example_factors.csv。
"""

import csv
import sqlite3
import pathlib
from datetime import date

ROOT = pathlib.Path(__file__).resolve().parent
DB_PATH = ROOT / "data" / "topics.db"
FACTORS_CSV = ROOT / "data" / "factors" / "example_factors.csv"


def import_factors():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # 建立 code -> stock_id 映射
    cur.execute("SELECT id, code FROM stocks")
    code_to_id = {code: stock_id for stock_id, code in cur.fetchall()}

    if not FACTORS_CSV.exists():
        print(f"[warn] 因子 CSV 文件不存在: {FACTORS_CSV}")
        conn.close()
        return

    updated = 0
    today = date.today().isoformat()

    with FACTORS_CSV.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            code = row.get("code")
            if code not in code_to_id:
                print(f"[skip] 未在 stocks 表中找到代码: {code}")
                continue
            stock_id = code_to_id[code]

            pe_12m_fwd = row.get("pe_12m_fwd") or None
            pb = row.get("pb") or None
            eps_growth_1y = row.get("eps_growth_1y") or None
            eps_growth_3y = row.get("eps_growth_3y") or None
            broker_rating = row.get("broker_rating") or None

            cur.execute(
                """
                INSERT INTO fundamentals (
                  stock_id, pe_12m_fwd, pb, eps_growth_1y, eps_growth_3y, broker_rating, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(stock_id) DO UPDATE SET
                  pe_12m_fwd=excluded.pe_12m_fwd,
                  pb=excluded.pb,
                  eps_growth_1y=excluded.eps_growth_1y,
                  eps_growth_3y=excluded.eps_growth_3y,
                  broker_rating=excluded.broker_rating,
                  updated_at=excluded.updated_at
                """,
                (
                    stock_id,
                    float(pe_12m_fwd) if pe_12m_fwd else None,
                    float(pb) if pb else None,
                    float(eps_growth_1y) if eps_growth_1y else None,
                    float(eps_growth_3y) if eps_growth_3y else None,
                    broker_rating,
                    today,
                ),
            )
            updated += 1

    conn.commit()
    conn.close()
    print(f"[ok] 已更新 fundamentals 记录 {updated} 条。")


if __name__ == "__main__":
    import_factors()

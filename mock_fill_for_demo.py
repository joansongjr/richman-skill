#!/usr/bin/env python3
"""为 Richman 日报生成一份演示用的 topic_heat 和 signals 数据。

仅用于本地 demo，不构成任何投资建议。
"""

import sqlite3
import pathlib
from datetime import date

DB_PATH = pathlib.Path(__file__).resolve().parents[0] / "data" / "topics.db"


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    today = date.today().isoformat()

    # 1. 填充 topic_heat：给两个题材各塞一条今日记录
    cur.execute("SELECT id, name FROM topics")
    topics = cur.fetchall()
    for topic_id, name in topics:
        cur.execute(
            """
            INSERT OR REPLACE INTO topic_heat
            (topic_id, date, posts_T1, posts_T2, replies_T1, replies_T2, score)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (topic_id, today, 100, 50.0, 300, 150.0, 1.0 if topic_id == 1 else 0.8),
        )

    # 2. 清空旧 signals，并为每只股票插入一条演示信号
    cur.execute("DELETE FROM signals")
    cur.execute("SELECT id, code, name FROM stocks")
    stocks = cur.fetchall()
    for stock_id, code, name in stocks:
        details = f"演示信号：假设 {name} ({code}) 今天突破前高并放量。"
        cur.execute(
            "INSERT INTO signals (stock_id, signal_type, signal_date, details) VALUES (?, ?, ?, ?)",
            (stock_id, "breakout_demo", today, details),
        )

    conn.commit()
    conn.close()
    print(f"已为 {today} 生成演示用 topic_heat 和 signals 数据。")


if __name__ == "__main__":
    main()

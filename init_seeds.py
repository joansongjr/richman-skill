#!/usr/bin/env python3
"""初始化 Richman Skill 的示例题材和标的池。

说明：
- 这里只插入少量“样本股”，用于验证流程，不构成任何投资建议。
- 后续你可以根据自己真实关注的赛道和标的，随时修改/扩展。
"""

import sqlite3
import pathlib
from datetime import datetime

ROOT = pathlib.Path(__file__).resolve().parent
DB_PATH = ROOT / "data" / "topics.db"
SCHEMA_PATH = ROOT / "schema.sql"


def init_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.commit()
    return conn


def upsert_topic(conn: sqlite3.Connection, name: str, description: str = "") -> int:
    cur = conn.cursor()
    cur.execute("SELECT id FROM topics WHERE name = ?", (name,))
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute(
        "INSERT INTO topics (name, description, created_at) VALUES (?, ?, ?)",
        (name, description, datetime.utcnow().isoformat()),
    )
    conn.commit()
    return cur.lastrowid


def upsert_stock(conn: sqlite3.Connection, topic_id: int, code: str, market: str, name: str):
    cur = conn.cursor()
    # 尝试按 code+market 查找是否已存在
    cur.execute("SELECT id FROM stocks WHERE code = ? AND market = ?", (code, market))
    row = cur.fetchone()
    if row:
        stock_id = row[0]
        # 更新 topic_id/name，保持同步
        cur.execute(
            "UPDATE stocks SET topic_id = ?, name = ? WHERE id = ?",
            (topic_id, name, stock_id),
        )
    else:
        cur.execute(
            "INSERT INTO stocks (topic_id, code, market, name) VALUES (?, ?, ?, ?)",
            (topic_id, code, market, name),
        )
    conn.commit()


def main():
    conn = init_db()

    # 示例题材——仅用于演示
    topic_cpo = upsert_topic(conn, "CPO/光模块", "光模块 / 硅光 / 数据中心高速光互联赛道")
    topic_lpo = upsert_topic(conn, "LPO/高速互联", "高速网络设备 / AI I/O / 数据中心交换机等")

    # 示例标的——不构成投资建议
    # 市场代码简化为 CN，后续接行情时再细分 SH/SZ 等
    sample_stocks = [
        # CPO / 光模块
        (topic_cpo, "300308.SZ", "CN", "中际旭创"),
        (topic_cpo, "300502.SZ", "CN", "新易盛"),
        (topic_cpo, "300394.SZ", "CN", "天孚通信"),
        # LPO / 高速互联
        (topic_lpo, "000938.SZ", "CN", "紫光股份"),
        (topic_lpo, "603019.SH", "CN", "中科曙光"),
    ]

    for topic_id, code, market, name in sample_stocks:
        upsert_stock(conn, topic_id, code, market, name)

    # 打印结果确认
    cur = conn.cursor()
    print("[topics]")
    for row in cur.execute("SELECT id, name FROM topics"):
        print("  ", row)

    print("\n[stocks]")
    for row in cur.execute("SELECT code, market, name FROM stocks"):
        print("  ", row)

    conn.close()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""入口脚本：依次调用各网站的抓取函数，把帖子写入 SQLite。

目前只放骨架和 TODO，具体实现可以在后续逐步补全。
"""

import sqlite3
import pathlib
from datetime import datetime, timedelta

DB_PATH = pathlib.Path(__file__).resolve().parents[1] / "data" / "topics.db"
SCHEMA_PATH = pathlib.Path(__file__).resolve().parents[1] / "schema.sql"


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.commit()
    return conn


def fetch_from_xueqiu(conn: sqlite3.Connection, since: datetime):
    """TODO: 雪球抓取逻辑占位。

    思路：使用 requests + 合理的 headers/cookies 抓取公开的热门话题/帖子列表，
    解析标题/时间/回复数/浏览数，并根据 keywords 识别 topic_raw / stock_code。
    """
    print("[TODO] fetch_from_xueqiu: not implemented yet")


def fetch_from_guba(conn: sqlite3.Connection, since: datetime):
    """TODO: 东方财富股吧抓取逻辑占位。"""
    print("[TODO] fetch_from_guba: not implemented yet")


def fetch_from_10jqka(conn: sqlite3.Connection, since: datetime):
    """TODO: 同花顺热门概念/新闻抓取逻辑占位。"""
    print("[TODO] fetch_from_10jqka: not implemented yet")


def main():
    conn = init_db()
    since = datetime.utcnow() - timedelta(days=7)
    print(f"DB: {DB_PATH}")
    print(f"抓取时间范围: >= {since.isoformat()} (UTC)")

    fetch_from_xueqiu(conn, since)
    fetch_from_guba(conn, since)
    fetch_from_10jqka(conn, since)

    conn.close()


if __name__ == "__main__":
    main()

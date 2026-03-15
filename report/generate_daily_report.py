#!/usr/bin/env python3
"""生成每日赛道+K线选股报告的骨架脚本。

步骤：
1. 从 topic_heat 中选出当日 Top N 题材。
2. 对每个题材，从 stocks + signals 里选出有最新信号的标的。
3. 生成 Markdown 报告，保存到 reports/daily-YYYY-MM-DD.md。
4. 后续可由上层 Agent 调用 LLM（Kimi 等）润色推荐理由。
"""

import sqlite3
import pathlib
from datetime import date

DB_PATH = pathlib.Path(__file__).resolve().parents[1] / "data" / "topics.db"
REPORT_DIR = pathlib.Path(__file__).resolve().parents[1] / "reports"


def get_stock_id(conn: sqlite3.Connection, code: str, market: str) -> int:
    """根据 code 和 market 获取 stock_id。"""
    cur = conn.cursor()
    cur.execute("SELECT id FROM stocks WHERE code = ? AND market = ?", (code, market))
    row = cur.fetchone()
    return row[0] if row else 0


def load_top_topics(conn: sqlite3.Connection, today: str, top_n: int = 5):
    cur = conn.cursor()
    cur.execute(
        """
        SELECT t.id, t.name, h.score, h.posts_T1, h.replies_T1
        FROM topic_heat h
        JOIN topics t ON h.topic_id = t.id
        WHERE h.date = ?
        ORDER BY h.score DESC
        LIMIT ?
        """,
        (today, top_n),
    )
    return cur.fetchall()


def load_signals_for_topic(conn: sqlite3.Connection, topic_id: int):
    cur = conn.cursor()
    cur.execute(
        """
        SELECT s.signal_type, s.signal_date, s.details, st.code, st.market, st.name
        FROM signals s
        JOIN stocks st ON s.stock_id = st.id
        WHERE st.topic_id = ?
        ORDER BY s.signal_date DESC
        """,
        (topic_id,),
    )
    rows = cur.fetchall()
    by_stock = {}
    for signal_type, signal_date, details, code, market, name in rows:
        key = (code, market, name)
        by_stock.setdefault(key, []).append((signal_type, signal_date, details))
    return by_stock


def load_fundamentals(conn: sqlite3.Connection):
    """加载 fundamentals 表，返回 (code, market, name) -> 估值/成长 dict。"""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT s.code, s.market, s.name,
               f.pe_12m_fwd, f.pb, f.eps_growth_1y, f.eps_growth_3y, f.broker_rating
        FROM stocks s
        LEFT JOIN fundamentals f ON s.id = f.stock_id
        """
    )
    funda_map = {}
    for code, market, name, pe, pb, g1, g3, rating in cur.fetchall():
        funda_map[(code, market, name)] = {
            "pe": pe,
            "pb": pb,
            "g1": g1,
            "g3": g3,
            "rating": rating,
        }
    return funda_map


def generate_report():
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()

    conn = sqlite3.connect(DB_PATH)

    topics = load_top_topics(conn, today)
    if not topics:
        print(f"[warn] topic_heat 中没有 {today} 的记录，先跑热度统计脚本再生成报告。")
        return

    funda_map = load_fundamentals(conn)

    md_lines = []
    md_lines.append(f"# 科技/题材选股日报 · {today}\n")
    md_lines.append("\n")

    for idx, (topic_id, name, score, posts_T1, replies_T1) in enumerate(topics, start=1):
        md_lines.append(f"## {idx}. 题材：{name} (score={score:.2f}, 帖子={posts_T1}, 回复={replies_T1})\n")
        md_lines.append("\n")

        by_stock = load_signals_for_topic(conn, topic_id)
        
        # 获取该题材下所有个股（即使没有信号也展示）
        cur = conn.cursor()
        all_stocks = cur.execute(
            "SELECT code, market, name FROM stocks WHERE topic_id = ?", (topic_id,)
        ).fetchall()
        
        if not all_stocks:
            md_lines.append("- 该题材下暂无标的。\n\n")
            continue

        for code, market, stock_name in all_stocks:
            signals = by_stock.get((code, market, stock_name), [])
            md_lines.append(f"### 标的：{stock_name}（{code}.{market}）\n")

            # 1. 题材逻辑 & 行业位置 & 券商观点
            md_lines.append("**1. 题材逻辑 & 行业位置 & 券商观点（概要）：**\n")
            # 尝试从 insights 表获取
            stock_insight = cur.execute(
                "SELECT insight FROM insights WHERE entity_type='stock' AND entity_id=?",
                (get_stock_id(conn, code, market),)
            ).fetchone()
            if stock_insight and stock_insight[0]:
                md_lines.append(f"> {stock_insight[0]}\n\n")
            else:
                md_lines.append(
                    "> 暂无分析（运行 `python report/generate_insights.py` 生成）\n\n"
                )

            # 2. 当前技术信号
            md_lines.append("**2. 当前技术信号：**\n")
            if signals:
                for sig_type, sig_date, details in signals[:3]:
                    md_lines.append(f"- {sig_date} · {sig_type} · {details}\n")
            else:
                md_lines.append("- 暂无触发信号\n")
            md_lines.append("\n")

            # 3. 估值 & 增长概览
            f = funda_map.get((code, market, stock_name))
            if f and any(v is not None for v in f.values()):
                md_lines.append("**3. 估值 & 增长概览：**\n")
                parts = []
                if f["pe"] is not None:
                    parts.append(f"12M PE ~ {f['pe']:.1f}x")
                if f["pb"] is not None:
                    parts.append(f"PB ~ {f['pb']:.1f}x")
                if f["g1"] is not None:
                    parts.append(f"EPS 1Y 增速 ~ {f['g1']:.1f}%")
                if f["g3"] is not None:
                    parts.append(f"EPS 3Y 增速 ~ {f['g3']:.1f}%")
                if f["rating"]:
                    parts.append(f"一致评级：{f['rating']}")
                if parts:
                    md_lines.append("- " + "，".join(parts) + "\n\n")

    conn.close()

    report_path = REPORT_DIR / f"daily-{today}.md"
    report_path.write_text("".join(md_lines), encoding="utf-8")
    print(f"已生成报告: {report_path}")


if __name__ == "__main__":
    generate_report()

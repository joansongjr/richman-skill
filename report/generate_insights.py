#!/usr/bin/env python3
"""用 LLM 生成题材逻辑和个股推荐理由。

调用 MiniMax / Kimi / OpenAI 等 API 生成：
1. 题材逻辑（赛道为何火、核心驱动因素）
2. 公司在产业链中的位置
3. 券商观点摘要
"""

import os
import json
import sqlite3
import pathlib
import requests

ROOT = pathlib.Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "topics.db"

# 优先使用 MiniMax（便宜），备选 Kimi
MINIMAX_API_KEY = os.environ.get("MINIMAX_API_KEY", "")
KIMI_API_KEY = os.environ.get("KIMI_API_KEY", "")


def call_llm(prompt: str, max_tokens: int = 500) -> str:
    """调用 LLM API 生成文本。优先本地 Ollama，备选云端 API。"""
    
    # 1. 优先尝试本地 Ollama（qwen3:8b）
    try:
        r = requests.post(
            "http://127.0.0.1:11434/api/generate",
            json={
                "model": "qwen3:8b",
                "prompt": prompt + " /no_think",
                "stream": False,
                "options": {"num_predict": max_tokens},
            },
            timeout=90,
        )
        if r.status_code == 200:
            data = r.json()
            text = data.get("response", "").strip()
            # qwen3 可能把内容放在 thinking 字段
            if not text and data.get("thinking"):
                # 从 thinking 中提取结论部分
                thinking = data.get("thinking", "")
                # 找到最后的总结/结论
                import re
                # 尝试提取"综上"或"总结"后的内容
                match = re.search(r'(综上|总结|因此|所以|综合来看)[：:，,]?\s*(.+)', thinking, re.DOTALL)
                if match:
                    text = match.group(2).strip()[:500]
                else:
                    # 取最后 200 字符作为结论
                    text = thinking[-300:].strip()
            if text:
                return text
    except Exception as e:
        print(f"[warn] Ollama 调用失败: {e}")

    # 2. 尝试 MiniMax
    if MINIMAX_API_KEY:
        try:
            r = requests.post(
                "https://api.minimax.io/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {MINIMAX_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "MiniMax-M2.5",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                },
                timeout=30,
            )
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            print(f"[warn] MiniMax 调用失败: {e}")

    # 3. 尝试 Kimi
    if KIMI_API_KEY:
        try:
            r = requests.post(
                "https://api.moonshot.cn/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {KIMI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "moonshot-v1-8k",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                },
                timeout=30,
            )
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            print(f"[warn] Kimi 调用失败: {e}")

    return ""


def generate_topic_insight(topic_name: str) -> str:
    """生成题材逻辑概述。"""
    prompt = f"""你是一位资深的 A 股 TMT 行业分析师。请用 2-3 句话简要说明"{topic_name}"这个题材/赛道：
1. 当前为什么受市场关注（核心驱动因素）
2. 产业链的关键环节

要求：简洁专业，不要用营销语言，不要推荐买入。"""

    return call_llm(prompt, max_tokens=200)


def generate_stock_insight(stock_name: str, stock_code: str, topic_name: str) -> str:
    """生成个股推荐理由。"""
    prompt = f"""你是一位资深的 A 股 TMT 行业分析师。请用 3-4 句话简要说明 {stock_name}({stock_code}) 在"{topic_name}"赛道中的位置：
1. 公司主营业务和在产业链中的位置
2. 相对竞争对手的优势或差异化
3. 市场/券商的主流观点（如有）

要求：简洁客观，不要推荐买入，不要给目标价。"""

    return call_llm(prompt, max_tokens=300)


def update_insights_in_db():
    """为 DB 中的题材和个股生成 insights，存入新表。"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # 创建 insights 表（如果不存在）
    cur.execute("""
        CREATE TABLE IF NOT EXISTS insights (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type TEXT NOT NULL,  -- 'topic' or 'stock'
            entity_id INTEGER NOT NULL,
            insight TEXT,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(entity_type, entity_id)
        )
    """)

    # 生成题材 insights
    print("生成题材 insights...")
    for row in cur.execute("SELECT id, name FROM topics").fetchall():
        topic_id, topic_name = row
        # 检查是否已有
        existing = cur.execute(
            "SELECT insight FROM insights WHERE entity_type='topic' AND entity_id=?",
            (topic_id,)
        ).fetchone()
        if existing and existing[0]:
            print(f"  [skip] {topic_name} 已有 insight")
            continue

        print(f"  [gen] {topic_name}...")
        insight = generate_topic_insight(topic_name)
        if insight:
            cur.execute(
                """INSERT OR REPLACE INTO insights (entity_type, entity_id, insight, updated_at)
                   VALUES ('topic', ?, ?, CURRENT_TIMESTAMP)""",
                (topic_id, insight)
            )
            print(f"    ✅ {insight[:50]}...")
        else:
            print(f"    ❌ 生成失败")

    # 生成个股 insights
    print("\n生成个股 insights...")
    stocks = cur.execute("""
        SELECT s.id, s.code, s.name, t.name as topic_name
        FROM stocks s
        JOIN topics t ON s.topic_id = t.id
    """).fetchall()

    for stock_id, code, name, topic_name in stocks:
        existing = cur.execute(
            "SELECT insight FROM insights WHERE entity_type='stock' AND entity_id=?",
            (stock_id,)
        ).fetchone()
        if existing and existing[0]:
            print(f"  [skip] {name} 已有 insight")
            continue

        print(f"  [gen] {name} ({code})...")
        insight = generate_stock_insight(name, code, topic_name)
        if insight:
            cur.execute(
                """INSERT OR REPLACE INTO insights (entity_type, entity_id, insight, updated_at)
                   VALUES ('stock', ?, ?, CURRENT_TIMESTAMP)""",
                (stock_id, insight)
            )
            print(f"    ✅ {insight[:50]}...")
        else:
            print(f"    ❌ 生成失败")

    conn.commit()
    conn.close()
    print("\n✅ Insights 生成完成")


if __name__ == "__main__":
    update_insights_in_db()

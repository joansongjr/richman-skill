#!/usr/bin/env python3
"""题材热度模块：从同花顺概念板块获取热度数据，写入 topic_heat 表。

策略：
1. 从 topics 表读取我们关注的题材及其别名
2. 用 AKShare 拉取同花顺全部概念板块当日数据（涨跌幅、涨/跌家数、换手率等）
3. 匹配关注题材，计算热度得分
4. 写入 topic_heat 表供日报使用

热度得分算法：
- 涨跌幅权重 40%（涨幅大=资金关注度高）
- 涨家数占比权重 30%（板块内上涨个股比例）
- 换手率权重 30%（活跃度）
- 归一化到 0~1 区间
"""

import sqlite3
import pathlib
import os
from datetime import date

ROOT = pathlib.Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "topics.db"


def get_topic_aliases(conn):
    """获取所有题材及其别名，用于和同花顺板块名匹配。"""
    cur = conn.cursor()
    result = {}  # topic_id -> {name, aliases: []}

    for row in cur.execute("SELECT id, name FROM topics"):
        tid, name = row
        result[tid] = {"name": name, "aliases": [name]}

    for row in cur.execute("SELECT topic_id, alias FROM topic_aliases"):
        tid, alias = row
        if tid in result:
            result[tid]["aliases"].append(alias)

    # 额外从 topics.example.yaml 加载别名（如果 topic_aliases 表为空）
    yaml_path = ROOT / "config" / "topics.example.yaml"
    if yaml_path.exists():
        import yaml
        with open(yaml_path, "r", encoding="utf-8") as f:
            topics_yaml = yaml.safe_load(f) or []
        for item in topics_yaml:
            yname = item.get("name", "")
            yaliases = item.get("aliases", [])
            # 匹配已有 topic
            for tid, info in result.items():
                if info["name"] == yname:
                    for a in yaliases:
                        if a not in info["aliases"]:
                            info["aliases"].append(a)

    return result


def match_board_to_topic(board_name, topic_map):
    """尝试将同花顺板块名匹配到我们的题材。返回 topic_id 或 None。"""
    board_lower = board_name.lower()
    for tid, info in topic_map.items():
        for alias in info["aliases"]:
            alias_lower = alias.lower()
            # 精确包含匹配
            if alias_lower in board_lower or board_lower in alias_lower:
                return tid
    return None


def fetch_and_compute_heat():
    """拉取概念板块数据，计算热度，写入 DB。"""
    os.environ.setdefault("no_proxy", "*")

    conn = sqlite3.connect(DB_PATH)
    topic_map = get_topic_aliases(conn)

    if not topic_map:
        print("[warn] topics 表为空，先运行 init_seeds.py")
        conn.close()
        return

    print(f"关注的题材：{[v['name'] for v in topic_map.values()]}")

    # 拉取同花顺全部概念板块
    import akshare as ak
    import requests

    # Monkey-patch to bypass proxy
    orig_init = requests.Session.__init__
    def patched_init(self, *a, **kw):
        orig_init(self, *a, **kw)
        self.trust_env = False
    requests.Session.__init__ = patched_init

    print("正在拉取同花顺概念板块列表...")
    try:
        boards_df = ak.stock_board_concept_name_ths()
    except Exception as e:
        print(f"[error] 拉取概念板块失败: {e}")
        # Fallback: 使用 Sina 板块数据
        print("尝试 Fallback...")
        _fallback_compute_heat(conn, topic_map)
        conn.close()
        return

    print(f"共 {len(boards_df)} 个概念板块，开始匹配...")

    today = date.today().isoformat()
    matched = 0

    for _, row in boards_df.iterrows():
        board_name = str(row.get("name", ""))
        tid = match_board_to_topic(board_name, topic_map)
        if tid is None:
            continue

        matched += 1
        topic_name = topic_map[tid]["name"]

        # 从板块数据中提取指标
        # 同花顺板块列表的列名可能不同，尝试多个
        change_pct = _safe_float(row, ["涨跌幅", "涨跌幅(%)", "change_pct"], 0)
        up_count = _safe_float(row, ["上涨家数", "涨家数", "up_count"], 0)
        down_count = _safe_float(row, ["下跌家数", "跌家数", "down_count"], 0)
        total_count = up_count + down_count if (up_count + down_count) > 0 else 1

        # 计算热度得分
        # 涨幅分（归一化到 0~1，假设 -5%~+5% 的范围）
        change_score = max(0, min(1, (change_pct + 5) / 10))
        # 涨家数占比
        up_ratio = up_count / total_count
        # 简单综合得分
        score = round(change_score * 0.5 + up_ratio * 0.5, 4)

        print(f"  ✅ {board_name} → {topic_name}: 涨跌幅={change_pct:.2f}%, 涨家占比={up_ratio:.1%}, 得分={score:.4f}")

        # 写入 topic_heat（posts_T1/T2 和 replies 暂时用板块统计数据填充）
        cur = conn.cursor()
        cur.execute(
            """INSERT OR REPLACE INTO topic_heat
               (topic_id, date, posts_T1, posts_T2, replies_T1, replies_T2, score)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (tid, today, int(up_count), float(total_count), int(down_count), 0.0, score),
        )

    conn.commit()
    conn.close()

    print(f"\n匹配到 {matched} 个板块，热度数据已写入 topic_heat (日期={today})")


def _safe_float(row, col_names, default=0.0):
    """安全获取 DataFrame 行中的浮点值。"""
    for col in col_names:
        if col in row.index:
            try:
                return float(row[col])
            except (ValueError, TypeError):
                continue
    return default


def _fallback_compute_heat(conn, topic_map):
    """Fallback：使用 Sina 实时行情估算板块热度。

    当同花顺接口不可用时，用个股涨跌幅平均值作为板块热度。
    """
    import requests
    import json

    session = requests.Session()
    session.trust_env = False

    today = date.today().isoformat()
    cur = conn.cursor()

    for tid, info in topic_map.items():
        # 获取该题材下所有个股
        cur.execute("SELECT code, market, name FROM stocks WHERE topic_id = ?", (tid,))
        stocks = cur.fetchall()
        if not stocks:
            continue

        changes = []
        up_count = 0
        for code, market, name in stocks:
            if market != "CN":
                continue
            num = code.split(".")[0]
            suffix = code.split(".")[-1].lower()
            sina_sym = f"{'sz' if suffix == 'sz' else 'sh'}{num}"
            try:
                r = session.get(
                    f"https://hq.sinajs.cn/list={sina_sym}",
                    headers={"Referer": "https://finance.sina.com.cn"},
                    timeout=10,
                )
                parts = r.text.split(",")
                if len(parts) > 3:
                    prev_close = float(parts[2])
                    cur_price = float(parts[3])
                    if prev_close > 0:
                        chg = (cur_price / prev_close - 1) * 100
                        changes.append(chg)
                        if chg > 0:
                            up_count += 1
            except Exception:
                pass

        if not changes:
            continue

        avg_change = sum(changes) / len(changes)
        up_ratio = up_count / len(changes) if changes else 0
        change_score = max(0, min(1, (avg_change + 5) / 10))
        score = round(change_score * 0.5 + up_ratio * 0.5, 4)

        print(f"  [fallback] {info['name']}: 平均涨幅={avg_change:.2f}%, 涨家占比={up_ratio:.1%}, 得分={score:.4f}")

        cur.execute(
            """INSERT OR REPLACE INTO topic_heat
               (topic_id, date, posts_T1, posts_T2, replies_T1, replies_T2, score)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (tid, today, up_count, float(len(changes)), len(changes) - up_count, 0.0, score),
        )

    conn.commit()
    print(f"\n[fallback] 热度数据已写入 topic_heat (日期={today})")


if __name__ == "__main__":
    fetch_and_compute_heat()

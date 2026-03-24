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
    topic_sodium = upsert_topic(
        conn,
        "钠电池/钠离子电池",
        "钠离子电池产业链：电芯制造、正极材料、负极材料（硬碳）、电解液等，"
        "2026年为规模化商用关键转折点",
    )

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
        # 钠电池 / 钠离子电池 —— 电芯制造
        (topic_sodium, "300750.SZ", "CN", "宁德时代"),    # 龙头，二代钠电池已发布，2026年规模化部署
        (topic_sodium, "002594.SZ", "CN", "比亚迪"),      # 首座钠电池工厂2024年动工
        (topic_sodium, "002866.SZ", "CN", "传艺科技"),    # 规划10GWh钠电池产能，中试线已投产
        (topic_sodium, "600152.SH", "CN", "维科技术"),    # 2023年量产，储能钠电出货领先
        # 钠电池 —— 正极材料
        (topic_sodium, "003027.SZ", "CN", "同兴环保"),    # 钠电正极材料（聚阴离子路线），已送样30+客户
        (topic_sodium, "688005.SH", "CN", "容百科技"),    # 层状氧化物正极材料龙头
        (topic_sodium, "300073.SZ", "CN", "当升科技"),    # 正极材料，布局钠电正极
        (topic_sodium, "688707.SH", "CN", "振华新材"),    # 层状氧化物正极
        # 钠电池 —— 负极材料（硬碳）
        (topic_sodium, "835185.BJ", "CN", "贝特瑞"),     # 负极材料龙头，布局硬碳负极
        (topic_sodium, "300890.SZ", "CN", "翔丰华"),     # 负极材料，硬碳研发
        (topic_sodium, "600884.SH", "CN", "杉杉股份"),    # 负极材料供应商
        # 钠电池 —— 电解液 & 其他
        (topic_sodium, "002709.SZ", "CN", "天赐材料"),    # 电解液龙头
        (topic_sodium, "002407.SZ", "CN", "多氟多"),     # 电解液（六氟磷酸钠）
        (topic_sodium, "600348.SH", "CN", "华阳股份"),    # 投资中科海钠，布局钠电全产业链
        (topic_sodium, "300438.SZ", "CN", "鹏辉能源"),    # 电芯制造，聚阴离子+层状氧化物双路线
        # 钠电池 —— 正极材料（补充）
        (topic_sodium, "300758.SZ", "CN", "七彩化学"),    # 普鲁士蓝/白正极材料
        # 钠电池 —— 负极材料（补充）
        (topic_sodium, "603659.SH", "CN", "璞泰来"),     # 石墨负极龙头，拓展硬碳
        (topic_sodium, "300174.SZ", "CN", "元力股份"),    # 生物基硬碳负极，第二增长曲线
        # 钠电池 —— 电解液（补充）
        (topic_sodium, "300037.SZ", "CN", "新宙邦"),     # 吨级NaPF6量产交付
        # 钠电池 —— 铝箔集流体（结构性受益：钠电池正负极均用铝箔，需求翻倍）
        (topic_sodium, "603876.SH", "CN", "鼎胜新材"),    # 电池级铝箔龙头，钠电池铝箔用量翻倍
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

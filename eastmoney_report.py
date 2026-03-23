#!/usr/bin/env python3
"""
东方财富研报采集工具

功能：
- 从东方财富(data.eastmoney.com)公开 API 采集研报列表
- 按券商、行业、日期范围过滤
- SQLite 本地去重，避免重复推送
- 企业微信群机器人 Webhook 推送
- 支持命令行交互式搜索

数据源：东方财富研报中心（公开 JSON API，无需登录）
"""

import hashlib
import json
import logging
import sqlite3
import sys
import time
from datetime import datetime, timedelta
from typing import Optional

import requests

# ============================================================
# 配置区
# ============================================================
CONFIG = {
    # --- 券商过滤 ---
    # 只推送这些券商的研报，留空则不过滤
    "broker_whitelist": [
        "兴业证券",
        "中信证券",
        "海通证券",
        "国泰君安",
        "华泰证券",
    ],

    # --- 行业过滤（可选） ---
    # 只推送标题中包含这些关键词的研报，留空则不过滤
    "industry_keywords": [],

    # --- 日期范围 ---
    # 默认采集最近 N 天的研报
    "days_back": 7,

    # --- 研报类型 ---
    # 0: 全部, 1: 行业研报, 2: 个股研报, 3: 策略研报, 4: 宏观研报
    "report_type": 0,

    # --- 每页条数 & 最大页数 ---
    "page_size": 50,
    "max_pages": 5,

    # --- 企业微信群机器人 Webhook ---
    "wechat_webhook_url": "",

    # --- 推送策略 ---
    "merge_threshold": 5,

    # --- 去重数据库 ---
    "db_path": "eastmoney_pushed.db",
    "cleanup_days": 30,

    # --- 请求控制 ---
    "request_interval": 1,
    "request_timeout": 15,
    "user_agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}

# 常用券商的 orgCode 映射（东方财富内部编码）
# 通过浏览器抓包 https://data.eastmoney.com/report/ 获取
BROKER_ORG_CODES = {
    "兴业证券": "80000031",
    "中信证券": "80000169",
    "海通证券": "80000155",
    "国泰君安": "80000065",
    "华泰证券": "80000195",
    "招商证券": "80000118",
    "广发证券": "80000152",
    "中金公司": "80000153",
    "申万宏源": "80000166",
    "天风证券": "80000076",
    "光大证券": "80000159",
    "东方证券": "80000154",
    "国信证券": "80000124",
    "浙商证券": "80000113",
    "民生证券": "80000038",
    "平安证券": "80000009",
    "中泰证券": "80000157",
    "开源证券": "80000078",
    "信达证券": "80000149",
    "长江证券": "80000158",
}

# ============================================================
# 日志配置
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ============================================================
# 数据库操作（复用 hibor_report_push.py 的逻辑）
# ============================================================
def init_db(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pushed_reports (
            report_id TEXT PRIMARY KEY,
            title TEXT,
            broker TEXT,
            pushed_at TEXT
        )
    """)
    conn.commit()
    return conn


def is_pushed(conn: sqlite3.Connection, report_id: str) -> bool:
    cur = conn.execute(
        "SELECT 1 FROM pushed_reports WHERE report_id = ?", (report_id,)
    )
    return cur.fetchone() is not None


def mark_pushed(conn: sqlite3.Connection, report_id: str, title: str, broker: str):
    conn.execute(
        "INSERT OR IGNORE INTO pushed_reports (report_id, title, broker, pushed_at) VALUES (?, ?, ?, ?)",
        (report_id, title, broker, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
    )
    conn.commit()


def cleanup_old_records(conn: sqlite3.Connection, days: int):
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    cur = conn.execute("DELETE FROM pushed_reports WHERE pushed_at < ?", (cutoff,))
    if cur.rowcount > 0:
        conn.commit()
        logger.info("清理了 %d 条 %d 天前的去重记录", cur.rowcount, days)


# ============================================================
# 东方财富研报 API
# ============================================================
API_BASE = "https://reportapi.eastmoney.com/report/list"
REPORT_DETAIL_URL = "https://data.eastmoney.com/report/zw/industry.jshtml?infocode={}"


def build_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": CONFIG["user_agent"],
        "Referer": "https://data.eastmoney.com/",
        "Accept": "application/json, text/plain, */*",
    })
    return session


def fetch_reports_by_broker(
    session: requests.Session,
    broker_name: str,
    begin_date: str,
    end_date: str,
    report_type: int = 0,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    """
    调用东方财富研报 API 获取指定券商的研报列表。

    参数:
        broker_name: 券商名称，如 "兴业证券"
        begin_date: 开始日期 YYYY-MM-DD
        end_date: 结束日期 YYYY-MM-DD
        report_type: 0全部 1行业 2个股 3策略 4宏观
        page: 页码
        page_size: 每页条数

    返回: API 原始 JSON
    """
    org_code = BROKER_ORG_CODES.get(broker_name, "")
    if not org_code:
        logger.warning("未找到券商 [%s] 的 orgCode，将按名称模糊匹配", broker_name)

    params = {
        "industryCode": "*",
        "pageSize": page_size,
        "industry": "*",
        "rating": "*",
        "ratingChange": "*",
        "beginTime": begin_date,
        "endTime": end_date,
        "pageNo": page,
        "fields": "",
        "qType": report_type,
        "orgCode": org_code or "*",
        "code": "*",
        "author": "*",
        "encodeUrl": "*",
        "p": page,
        "pageNum": page,
    }

    resp = session.get(API_BASE, params=params, timeout=CONFIG["request_timeout"])
    resp.raise_for_status()
    return resp.json()


def fetch_all_reports(
    session: requests.Session,
    broker_name: Optional[str] = None,
    days_back: Optional[int] = None,
    report_type: Optional[int] = None,
) -> list[dict]:
    """
    采集研报，自动翻页。

    返回标准化的研报列表 [{title, url, broker, date, industry, author, abstract, report_id}, ...]
    """
    days = days_back or CONFIG["days_back"]
    rtype = report_type if report_type is not None else CONFIG["report_type"]
    end_date = datetime.now().strftime("%Y-%m-%d")
    begin_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    all_reports = []
    brokers_to_fetch = [broker_name] if broker_name else (CONFIG["broker_whitelist"] or [None])

    for broker in brokers_to_fetch:
        broker_label = broker or "全部券商"
        logger.info("采集 [%s] %s ~ %s 的研报...", broker_label, begin_date, end_date)

        for page in range(1, CONFIG["max_pages"] + 1):
            try:
                data = fetch_reports_by_broker(
                    session,
                    broker or "",
                    begin_date,
                    end_date,
                    report_type=rtype,
                    page=page,
                    page_size=CONFIG["page_size"],
                )
            except requests.RequestException as e:
                logger.error("  第 %d 页请求失败: %s", page, e)
                break

            items = data.get("data") or []
            hits = data.get("hits", 0)
            logger.info("  第 %d 页: %d 条 (总计 %d 条)", page, len(items), hits)

            for item in items:
                info_code = item.get("infoCode", "")
                title = item.get("title", "")
                org_name = item.get("orgSName", "")
                publish_date = (item.get("publishDate") or "")[:10]
                industry = item.get("industryName", "")
                author = item.get("researcher", "")
                abstract = item.get("abstract", "") or ""

                report_id = hashlib.md5(
                    f"{info_code}|{title}".encode()
                ).hexdigest()

                url = REPORT_DETAIL_URL.format(info_code)

                all_reports.append({
                    "title": title,
                    "url": url,
                    "broker": org_name,
                    "date": publish_date,
                    "industry": industry,
                    "author": author,
                    "abstract": abstract,
                    "info_code": info_code,
                    "report_id": report_id,
                })

            # 没有更多数据了
            if len(items) < CONFIG["page_size"]:
                break

            time.sleep(CONFIG["request_interval"])

        time.sleep(CONFIG["request_interval"])

    # 按 report_id 去重
    seen = set()
    unique = []
    for r in all_reports:
        if r["report_id"] not in seen:
            seen.add(r["report_id"])
            unique.append(r)

    logger.info("共采集到 %d 条不重复研报", len(unique))
    return unique


# ============================================================
# 过滤
# ============================================================
def filter_reports(reports: list[dict]) -> list[dict]:
    filtered = reports

    # 券商过滤（API 层面已经按券商过滤，这里做二次校验）
    broker_list = CONFIG["broker_whitelist"]
    if broker_list:
        filtered = [r for r in filtered if r["broker"] in broker_list]

    # 行业关键词过滤
    keywords = CONFIG["industry_keywords"]
    if keywords:
        filtered = [
            r for r in filtered
            if any(kw in r["title"] or kw in r.get("industry", "") for kw in keywords)
        ]
        logger.info("行业过滤后剩余 %d 条", len(filtered))

    return filtered


# ============================================================
# 企业微信推送
# ============================================================
def send_wechat_markdown(webhook_url: str, content: str):
    payload = {
        "msgtype": "markdown",
        "markdown": {"content": content},
    }
    try:
        resp = requests.post(webhook_url, json=payload, timeout=10)
        result = resp.json()
        if result.get("errcode") == 0:
            logger.info("企业微信推送成功")
        else:
            logger.error("企业微信推送失败: %s", result)
    except requests.RequestException as e:
        logger.error("企业微信推送异常: %s", e)


def push_reports(reports: list[dict]):
    webhook_url = CONFIG["wechat_webhook_url"]

    if not webhook_url:
        logger.info("未配置企业微信 Webhook，仅打印结果")
        print_reports(reports)
        return

    if len(reports) <= CONFIG["merge_threshold"]:
        for r in reports:
            content = f"**{r['broker']}** | {r['date']}\n[{r['title']}]({r['url']})"
            if r.get("author"):
                content += f"\n> 作者: {r['author']}"
            send_wechat_markdown(webhook_url, content)
            time.sleep(1)
    else:
        # 合并推送：按券商分组
        grouped: dict[str, list[dict]] = {}
        for r in reports:
            grouped.setdefault(r["broker"], []).append(r)

        lines = [f"**研报汇总（共 {len(reports)} 篇）**", ""]
        for broker, broker_reports in grouped.items():
            lines.append(f"**{broker}**（{len(broker_reports)} 篇）")
            for r in broker_reports:
                lines.append(f"- [{r['title']}]({r['url']}) {r['date']}")
            lines.append("")

        send_wechat_markdown(webhook_url, "\n".join(lines))


# ============================================================
# 终端输出
# ============================================================
def print_reports(reports: list[dict]):
    """在终端打印研报列表。"""
    if not reports:
        print("\n没有找到符合条件的研报。")
        return

    # 按券商分组
    grouped: dict[str, list[dict]] = {}
    for r in reports:
        grouped.setdefault(r["broker"], []).append(r)

    total = len(reports)
    print(f"\n{'='*60}")
    print(f"  共 {total} 篇研报")
    print(f"{'='*60}")

    for broker, broker_reports in grouped.items():
        print(f"\n▎{broker}（{len(broker_reports)} 篇）")
        print(f"  {'─'*50}")
        for i, r in enumerate(broker_reports, 1):
            print(f"  {i}. [{r['date']}] {r['title']}")
            if r.get("author"):
                print(f"     作者: {r['author']}")
            if r.get("industry"):
                print(f"     行业: {r['industry']}")
            if r.get("abstract"):
                # 摘要截取前 80 字符
                abstract = r["abstract"][:80]
                if len(r["abstract"]) > 80:
                    abstract += "..."
                print(f"     摘要: {abstract}")
            print(f"     链接: {r['url']}")

    print(f"\n{'='*60}")


# ============================================================
# 命令行入口
# ============================================================
def cli_search():
    """命令行搜索模式。"""
    import argparse

    parser = argparse.ArgumentParser(description="东方财富研报搜索工具")
    parser.add_argument(
        "-b", "--broker",
        help="券商名称，如 '兴业证券'（可指定多个，逗号分隔）",
    )
    parser.add_argument(
        "-d", "--days", type=int, default=7,
        help="搜索最近 N 天的研报（默认 7）",
    )
    parser.add_argument(
        "-t", "--type", type=int, default=0, dest="report_type",
        help="研报类型: 0全部 1行业 2个股 3策略 4宏观（默认 0）",
    )
    parser.add_argument(
        "-k", "--keyword",
        help="标题/行业关键词过滤（可指定多个，逗号分隔）",
    )
    parser.add_argument(
        "--push", action="store_true",
        help="推送到企业微信（需配置 webhook）",
    )
    parser.add_argument(
        "--json", action="store_true", dest="output_json",
        help="输出 JSON 格式",
    )

    args = parser.parse_args()

    # 更新配置
    if args.broker:
        CONFIG["broker_whitelist"] = [b.strip() for b in args.broker.split(",")]
    if args.keyword:
        CONFIG["industry_keywords"] = [k.strip() for k in args.keyword.split(",")]
    CONFIG["days_back"] = args.days
    CONFIG["report_type"] = args.report_type

    # 采集
    session = build_session()
    reports = []

    brokers = CONFIG["broker_whitelist"]
    if brokers:
        for broker in brokers:
            reports.extend(
                fetch_all_reports(session, broker_name=broker, days_back=args.days, report_type=args.report_type)
            )
    else:
        reports = fetch_all_reports(session, days_back=args.days, report_type=args.report_type)

    # 过滤
    reports = filter_reports(reports)

    # 按日期倒序
    reports.sort(key=lambda r: r["date"], reverse=True)

    # 输出
    if args.output_json:
        print(json.dumps(reports, ensure_ascii=False, indent=2))
    else:
        print_reports(reports)

    # 推送
    if args.push:
        conn = init_db(CONFIG["db_path"])
        cleanup_old_records(conn, CONFIG["cleanup_days"])
        new_reports = [r for r in reports if not is_pushed(conn, r["report_id"])]
        logger.info("去重后待推送 %d 条", len(new_reports))
        if new_reports:
            push_reports(new_reports)
            for r in new_reports:
                mark_pushed(conn, r["report_id"], r["title"], r["broker"])
        conn.close()

    return reports


# ============================================================
# 主流程（定时任务模式）
# ============================================================
def main():
    logger.info("=" * 50)
    logger.info("东方财富研报采集推送 - 开始运行")
    logger.info("=" * 50)

    conn = init_db(CONFIG["db_path"])
    cleanup_old_records(conn, CONFIG["cleanup_days"])

    session = build_session()

    # 按白名单中的每个券商分别采集
    all_reports = []
    for broker in CONFIG["broker_whitelist"]:
        all_reports.extend(fetch_all_reports(session, broker_name=broker))

    # 过滤
    all_reports = filter_reports(all_reports)

    # 去重
    new_reports = [r for r in all_reports if not is_pushed(conn, r["report_id"])]
    logger.info("去重后待推送 %d 条（共 %d 条命中过滤条件）", len(new_reports), len(all_reports))

    if not new_reports:
        logger.info("没有新研报需要推送")
        conn.close()
        return

    # 按日期倒序
    new_reports.sort(key=lambda r: r["date"], reverse=True)

    # 推送
    push_reports(new_reports)

    # 标记
    for r in new_reports:
        mark_pushed(conn, r["report_id"], r["title"], r["broker"])

    logger.info("本次推送完成，共推送 %d 条研报", len(new_reports))
    conn.close()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        cli_search()
    else:
        main()

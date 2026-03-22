#!/usr/bin/env python3
"""
慧博投研资讯研报采集 & 企业微信群机器人推送工具

功能：
- 从慧博投研资讯(hibor.com.cn)采集研报列表
- 按券商名单过滤
- 可选按行业、日期过滤
- SQLite 本地去重，避免重复推送
- 企业微信群机器人 Webhook 推送（Markdown 格式）
- 自动清理过期去重记录
"""

import hashlib
import logging
import re
import sqlite3
import time
from datetime import datetime, timedelta
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

# ============================================================
# 配置区 - 所有配置集中在此，方便修改
# ============================================================
CONFIG = {
    # --- 慧博登录配置 ---
    # 方式一：账号密码登录
    "hibor_username": "",
    "hibor_password": "",
    # 方式二：手动粘贴浏览器 Cookie（优先使用，非空时跳过账号密码登录）
    "hibor_cookie": "",

    # --- 采集页面配置 ---
    # 慧博研报分类页面 URL（服务端直出 HTML）
    # 常见分类：
    #   行业分析: /microns_2.html
    #   公司调研: /microns_3.html
    #   投资策略: /microns_4.html
    #   宏观研究: /microns_1.html
    "report_pages": [
        "https://www.hibor.com.cn/microns_2.html",  # 行业分析
        "https://www.hibor.com.cn/microns_3.html",  # 公司调研
        "https://www.hibor.com.cn/microns_4.html",  # 投资策略
    ],

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

    # --- 日期过滤 ---
    # True: 只推送当天的研报; False: 推送列表页所有研报
    "today_only": True,

    # --- 企业微信群机器人 Webhook ---
    "wechat_webhook_url": "",

    # --- 推送策略 ---
    # 单次推送超过此数量时，合并为一条消息按券商分组展示
    "merge_threshold": 5,

    # --- 去重数据库 ---
    "db_path": "hibor_pushed.db",
    # 自动清理多少天前的记录
    "cleanup_days": 30,

    # --- 采集控制 ---
    # 请求间隔（秒），避免被封
    "request_interval": 2,
    # 请求超时（秒）
    "request_timeout": 15,
    # User-Agent
    "user_agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
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
# 数据库操作
# ============================================================
def init_db(db_path: str) -> sqlite3.Connection:
    """初始化 SQLite 数据库，创建去重表。"""
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
    """检查研报是否已推送。"""
    cur = conn.execute(
        "SELECT 1 FROM pushed_reports WHERE report_id = ?", (report_id,)
    )
    return cur.fetchone() is not None


def mark_pushed(conn: sqlite3.Connection, report_id: str, title: str, broker: str):
    """标记研报已推送。"""
    conn.execute(
        "INSERT OR IGNORE INTO pushed_reports (report_id, title, broker, pushed_at) VALUES (?, ?, ?, ?)",
        (report_id, title, broker, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
    )
    conn.commit()


def cleanup_old_records(conn: sqlite3.Connection, days: int):
    """清理指定天数前的去重记录。"""
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    cur = conn.execute("DELETE FROM pushed_reports WHERE pushed_at < ?", (cutoff,))
    if cur.rowcount > 0:
        conn.commit()
        logger.info("清理了 %d 条 %d 天前的去重记录", cur.rowcount, days)


# ============================================================
# 慧博登录 & 采集
# ============================================================
def create_session() -> requests.Session:
    """创建带登录态的 requests Session。"""
    session = requests.Session()
    session.headers.update({
        "User-Agent": CONFIG["user_agent"],
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    })

    # 方式一：手动 Cookie（优先）
    if CONFIG["hibor_cookie"].strip():
        logger.info("使用手动 Cookie 登录")
        session.headers["Cookie"] = CONFIG["hibor_cookie"].strip()
        return session

    # 方式二：账号密码登录
    username = CONFIG["hibor_username"].strip()
    password = CONFIG["hibor_password"].strip()
    if username and password:
        logger.info("使用账号密码登录慧博...")
        login_url = "https://www.hibor.com.cn/login.html"
        try:
            login_data = {
                "username": username,
                "password": password,
            }
            resp = session.post(
                login_url,
                data=login_data,
                timeout=CONFIG["request_timeout"],
            )
            if resp.status_code == 200:
                logger.info("登录请求完成，状态码: %d", resp.status_code)
            else:
                logger.warning("登录返回非 200 状态码: %d", resp.status_code)
        except requests.RequestException as e:
            logger.error("登录失败: %s", e)
    else:
        logger.warning("未配置登录凭据，将以游客身份采集（可能内容受限）")

    return session


def extract_broker_from_title(title: str) -> str:
    """
    从研报标题中提取券商名称。
    慧博标题格式: "券商名-报告标题-编号"
    例: "兴业证券-电子行业周报：半导体景气回升-260322"
    """
    match = re.match(r"^([^-\s]+(?:证券|基金|期货|资管|研究所|研究院|资本))", title)
    if match:
        return match.group(1)
    # 备选：取第一个短横线前的内容
    parts = title.split("-", 1)
    if len(parts) > 1 and len(parts[0].strip()) <= 10:
        return parts[0].strip()
    return ""


def parse_report_list(html: str, page_url: str) -> list[dict]:
    """
    解析慧博研报列表页 HTML，提取研报信息。
    返回 [{title, url, broker, date, report_id}, ...]
    """
    soup = BeautifulSoup(html, "html.parser")
    reports = []

    # 慧博列表页通常的结构：包含研报链接的列表元素
    # 尝试多种常见选择器
    link_candidates = []

    # 尝试查找研报列表中的链接
    for selector in [
        "div.report-list a",
        "ul.report-list li a",
        "div.list-content a",
        "table.report-table td a",
        "div.main-content a",
        "div.content a",
        "ul li a",
    ]:
        found = soup.select(selector)
        if found:
            link_candidates = found
            break

    # 如果特定选择器都没匹配到，取页面中所有指向研报详情的链接
    if not link_candidates:
        link_candidates = soup.find_all("a", href=True)

    for a_tag in link_candidates:
        href = a_tag.get("href", "")
        title = a_tag.get_text(strip=True)

        # 过滤：只保留看起来像研报详情的链接
        if not title or len(title) < 5:
            continue
        # 慧博研报详情页 URL 通常包含 /doc 或数字 ID
        if not re.search(r"(doc|report|detail|\d{5,})", href, re.IGNORECASE):
            continue

        full_url = urljoin(page_url, href)
        broker = extract_broker_from_title(title)

        # 尝试从标题中提取日期（格式如 260322 表示 2026-03-22）
        date_match = re.search(r"-(\d{6})$", title)
        report_date = ""
        if date_match:
            raw_date = date_match.group(1)
            try:
                # 格式: YYMMDD
                report_date = datetime.strptime(raw_date, "%y%m%d").strftime("%Y-%m-%d")
            except ValueError:
                pass

        # 如果标题中没有日期，尝试从附近元素提取
        if not report_date:
            parent = a_tag.parent
            if parent:
                date_text = parent.get_text()
                date_match2 = re.search(r"(\d{4}-\d{2}-\d{2})", date_text)
                if date_match2:
                    report_date = date_match2.group(1)

        # 生成唯一 ID
        report_id = hashlib.md5(f"{title}|{full_url}".encode()).hexdigest()

        reports.append({
            "title": title,
            "url": full_url,
            "broker": broker,
            "date": report_date,
            "report_id": report_id,
        })

    return reports


def fetch_reports(session: requests.Session) -> list[dict]:
    """采集所有配置页面的研报列表。"""
    all_reports = []

    for page_url in CONFIG["report_pages"]:
        logger.info("采集页面: %s", page_url)
        try:
            resp = session.get(page_url, timeout=CONFIG["request_timeout"])
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding or "utf-8"

            reports = parse_report_list(resp.text, page_url)
            logger.info("  解析到 %d 条研报", len(reports))
            all_reports.extend(reports)

        except requests.RequestException as e:
            logger.error("  采集失败: %s", e)

        time.sleep(CONFIG["request_interval"])

    # 按 report_id 去重（不同页面可能有重复）
    seen = set()
    unique_reports = []
    for r in all_reports:
        if r["report_id"] not in seen:
            seen.add(r["report_id"])
            unique_reports.append(r)

    logger.info("共采集到 %d 条不重复研报", len(unique_reports))
    return unique_reports


# ============================================================
# 过滤
# ============================================================
def filter_reports(reports: list[dict]) -> list[dict]:
    """按配置的券商名单、行业关键词、日期进行过滤。"""
    filtered = reports

    # 券商过滤
    broker_list = CONFIG["broker_whitelist"]
    if broker_list:
        filtered = [r for r in filtered if r["broker"] in broker_list]
        logger.info("券商过滤后剩余 %d 条", len(filtered))

    # 行业关键词过滤
    keywords = CONFIG["industry_keywords"]
    if keywords:
        filtered = [
            r for r in filtered
            if any(kw in r["title"] for kw in keywords)
        ]
        logger.info("行业过滤后剩余 %d 条", len(filtered))

    # 日期过滤
    if CONFIG["today_only"]:
        today = datetime.now().strftime("%Y-%m-%d")
        filtered = [r for r in filtered if r["date"] == today]
        logger.info("日期过滤（仅今天 %s）后剩余 %d 条", today, len(filtered))

    return filtered


# ============================================================
# 企业微信推送
# ============================================================
def send_wechat_markdown(webhook_url: str, content: str):
    """通过企业微信群机器人 Webhook 发送 Markdown 消息。"""
    payload = {
        "msgtype": "markdown",
        "markdown": {
            "content": content,
        },
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


def format_single_report(report: dict) -> str:
    """格式化单条研报为 Markdown。"""
    lines = []
    lines.append(f"**{report['broker']}**")
    lines.append(f"[{report['title']}]({report['url']})")
    if report["date"]:
        lines.append(f"> 日期: {report['date']}")
    return "\n".join(lines)


def push_reports(reports: list[dict]):
    """推送研报到企业微信群。"""
    webhook_url = CONFIG["wechat_webhook_url"]
    if not webhook_url:
        logger.warning("未配置企业微信 Webhook URL，跳过推送")
        for r in reports:
            logger.info("  [%s] %s | %s", r["broker"], r["title"], r["url"])
        return

    if len(reports) <= CONFIG["merge_threshold"]:
        # 逐条推送
        for r in reports:
            content = format_single_report(r)
            send_wechat_markdown(webhook_url, content)
            time.sleep(1)  # 避免发送过快
    else:
        # 合并推送：按券商分组
        grouped: dict[str, list[dict]] = {}
        for r in reports:
            grouped.setdefault(r["broker"], []).append(r)

        lines = [f"**今日研报汇总（共 {len(reports)} 篇）**", ""]
        for broker, broker_reports in grouped.items():
            lines.append(f"**{broker}**（{len(broker_reports)} 篇）")
            for r in broker_reports:
                lines.append(f"- [{r['title']}]({r['url']})")
            lines.append("")

        content = "\n".join(lines)
        send_wechat_markdown(webhook_url, content)


# ============================================================
# 主流程
# ============================================================
def main():
    logger.info("=" * 50)
    logger.info("慧博研报采集推送 - 开始运行")
    logger.info("=" * 50)

    # 初始化数据库
    conn = init_db(CONFIG["db_path"])

    # 清理过期记录
    cleanup_old_records(conn, CONFIG["cleanup_days"])

    # 创建会话并登录
    session = create_session()

    # 采集研报
    reports = fetch_reports(session)

    # 过滤
    reports = filter_reports(reports)

    # 去重：排除已推送的
    new_reports = [r for r in reports if not is_pushed(conn, r["report_id"])]
    logger.info("去重后待推送 %d 条（共 %d 条命中过滤条件）", len(new_reports), len(reports))

    if not new_reports:
        logger.info("没有新研报需要推送")
        conn.close()
        return

    # 推送
    push_reports(new_reports)

    # 标记已推送
    for r in new_reports:
        mark_pushed(conn, r["report_id"], r["title"], r["broker"])

    logger.info("本次推送完成，共推送 %d 条研报", len(new_reports))
    conn.close()


if __name__ == "__main__":
    main()

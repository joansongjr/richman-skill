#!/usr/bin/env python3
"""根据行情数据扫描技术形态信号（A 股）。

支持三种形态：
- breakout: 突破前高 + 放量
- first_limit_up: 首板涨停启动
- bottom_reversal: 底部放量反转

数据源：AKShare（A 股日 K 线，前复权）。
"""

import sqlite3
import pathlib
from datetime import date, timedelta

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "topics.db"
PATTERNS_PATH = ROOT / "signals" / "patterns.example.yaml"


def load_patterns():
    with open(PATTERNS_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_connection():
    return sqlite3.connect(DB_PATH)


def fetch_cn_kline(symbol: str, start: str, end: str):
    """使用 Sina 财经接口获取 A 股日 K 线。

    symbol 形如 "300308.SZ" 或 "603019.SH"。
    Sina 接口不需要认证，返回最近 N 条日 K 数据。
    """
    import requests
    import json
    import pandas as pd

    code = symbol.split(".")[0]
    suffix = symbol.split(".")[-1].lower()
    # Sina 格式：sz300502 / sh603019
    if suffix in ("sz", "szse"):
        sina_symbol = f"sz{code}"
    else:
        sina_symbol = f"sh{code}"

    session = requests.Session()
    session.trust_env = False  # 绕过系统代理

    r = session.get(
        "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData",
        params={"symbol": sina_symbol, "scale": "240", "ma": "no", "datalen": "120"},
        headers={"Referer": "https://finance.sina.com.cn"},
        timeout=15,
    )
    r.raise_for_status()
    data = json.loads(r.text)

    if not data:
        raise ValueError(f"Sina 返回空数据: {sina_symbol}")

    df = pd.DataFrame(data)
    df = df.rename(columns={"day": "date"})
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = df[col].astype(float)
    df["turnover"] = 0.0  # Sina K线接口不含换手率

    # 按日期过滤
    df = df[(df["date"] >= start) & (df["date"] <= end)]
    df = df.reset_index(drop=True)
    return df[["date", "open", "high", "low", "close", "volume", "turnover"]]


# ─── 形态检测函数 ────────────────────────────────────────────────

def detect_breakout(df, lookback_days: int, price_threshold_pct: float, volume_multiplier: float):
    """突破前高 + 放量。"""
    if len(df) < lookback_days + 1:
        return False, "样本数据不足"

    today_row = df.iloc[-1]
    hist = df.iloc[-(lookback_days + 1): -1]

    prev_high = hist["high"].max()
    avg_vol = hist["volume"].mean()
    today_close = float(today_row["close"])
    today_vol = float(today_row["volume"])

    if prev_high <= 0 or avg_vol <= 0:
        return False, "历史高点或均量异常"

    price_up_pct = (today_close / prev_high - 1) * 100
    vol_ratio = today_vol / avg_vol

    if price_up_pct >= price_threshold_pct and vol_ratio >= volume_multiplier:
        details = (
            f"突破最近{lookback_days}日高点{prev_high:.2f}，"
            f"收盘{today_close:.2f}(+{price_up_pct:.1f}%)，"
            f"量能{vol_ratio:.1f}倍"
        )
        return True, details

    return False, f"未触发breakout：涨幅{price_up_pct:.1f}%、量能{vol_ratio:.1f}x"


def detect_first_limit_up(df, lookback_days: int, limit_up_pct: float, min_turnover: float):
    """首板涨停启动：最近N日内没有涨停，今天涨停。"""
    if len(df) < lookback_days + 1:
        return False, "样本数据不足"

    today_row = df.iloc[-1]
    hist = df.iloc[-(lookback_days + 1): -1]

    today_open = float(today_row["open"])
    today_close = float(today_row["close"])
    today_turnover = float(today_row["turnover"])

    # 计算今日涨幅（相对前一日收盘）
    prev_close = float(hist.iloc[-1]["close"])
    if prev_close <= 0:
        return False, "前日收盘价异常"

    change_pct = (today_close / prev_close - 1) * 100

    # 检查是否涨停
    if change_pct < limit_up_pct:
        return False, f"未涨停：涨幅{change_pct:.1f}%"

    # 检查换手率（如果有数据）
    if today_turnover > 0 and today_turnover < min_turnover:
        return False, f"换手率{today_turnover:.1f}%不足{min_turnover}%"

    # 检查最近N日内是否已有涨停（排除连板，只找首板）
    for i in range(1, len(hist)):
        row = hist.iloc[-i]
        prev = hist.iloc[-i - 1] if i < len(hist) else None
        if prev is not None:
            prev_c = float(prev["close"])
            cur_c = float(row["close"])
            if prev_c > 0:
                pct = (cur_c / prev_c - 1) * 100
                if pct >= limit_up_pct:
                    return False, f"近{lookback_days}日内已有涨停，非首板"

    details = (
        f"首板涨停！涨幅{change_pct:.1f}%，"
        f"换手率{today_turnover:.1f}%，"
        f"近{lookback_days}日内无涨停记录"
    )
    return True, details


def detect_bottom_reversal(df, lookback_days: int, low_pct_threshold: float, volume_multiplier: float):
    """底部放量反转：股价处于N日低位区域，当日放量上涨。"""
    if len(df) < lookback_days + 1:
        return False, "样本数据不足"

    today_row = df.iloc[-1]
    hist = df.iloc[-(lookback_days + 1): -1]

    period_high = hist["high"].max()
    period_low = hist["low"].min()
    avg_vol = hist["volume"].mean()

    today_close = float(today_row["close"])
    today_open = float(today_row["open"])
    today_vol = float(today_row["volume"])
    prev_close = float(hist.iloc[-1]["close"])

    if period_high <= 0 or avg_vol <= 0 or period_high == period_low:
        return False, "数据异常"

    # 当前位置在 N 日区间的百分位
    position_pct = (today_close - period_low) / (period_high - period_low) * 100

    # 相对 N 日最高点的折价
    discount_pct = (1 - today_close / period_high) * 100

    # 今日涨幅
    change_pct = (today_close / prev_close - 1) * 100 if prev_close > 0 else 0

    # 量能倍数
    vol_ratio = today_vol / avg_vol if avg_vol > 0 else 0

    # 条件：处于低位（折价超阈值） + 放量 + 今日阳线上涨
    if (discount_pct >= low_pct_threshold
            and vol_ratio >= volume_multiplier
            and today_close > today_open
            and change_pct > 0):
        details = (
            f"底部反转！相对{lookback_days}日高点折价{discount_pct:.1f}%，"
            f"今日涨{change_pct:.1f}%，"
            f"量能{vol_ratio:.1f}倍"
        )
        return True, details

    return False, (
        f"未触发bottom_reversal：折价{discount_pct:.1f}%、"
        f"涨幅{change_pct:.1f}%、量能{vol_ratio:.1f}x"
    )


# ─── 主扫描逻辑 ──────────────────────────────────────────────────

def scan_signals():
    patterns = load_patterns()

    # 各形态参数
    bo_cfg = patterns.get("breakout", {})
    flu_cfg = patterns.get("first_limit_up", {})
    br_cfg = patterns.get("bottom_reversal", {})

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT id, code, market, name FROM stocks")
    stocks = cur.fetchall()

    # 需要足够长的历史数据
    max_lookback = max(
        int(bo_cfg.get("lookback_days", 20)),
        int(flu_cfg.get("lookback_days", 10)),
        int(br_cfg.get("lookback_days", 60)),
    )

    today = date.today()
    start = (today - timedelta(days=max_lookback + 60)).isoformat()
    end = today.isoformat()

    print(f"共 {len(stocks)} 只标的，扫描 breakout / first_limit_up / bottom_reversal 三种形态")
    print(f"数据范围：{start} ~ {end}\n")

    inserted = 0

    for stock_id, code, market, name in stocks:
        if market != "CN":
            print(f"[skip] {code} {name} 市场={market} 暂未实现")
            continue

        print(f"[scan] {code} {name}")
        try:
            df = fetch_cn_kline(code, start, end)
        except Exception as e:
            print(f"  ❌ 获取行情失败: {e}")
            continue

        if len(df) == 0:
            print(f"  ❌ 无行情数据")
            continue

        signal_date = df.iloc[-1]["date"]

        # --- breakout ---
        is_sig, details = detect_breakout(
            df,
            lookback_days=int(bo_cfg.get("lookback_days", 20)),
            price_threshold_pct=float(bo_cfg.get("price_threshold_pct", 1.0)),
            volume_multiplier=float(bo_cfg.get("volume_multiplier", 1.5)),
        )
        if is_sig:
            print(f"  ✅ breakout: {details}")
            cur.execute(
                "INSERT INTO signals (stock_id, signal_type, signal_date, details) VALUES (?, ?, ?, ?)",
                (stock_id, "breakout", signal_date, details),
            )
            inserted += 1
        else:
            print(f"  · breakout: {details}")

        # --- first_limit_up ---
        is_sig, details = detect_first_limit_up(
            df,
            lookback_days=int(flu_cfg.get("lookback_days", 10)),
            limit_up_pct=float(flu_cfg.get("limit_up_pct", 9.5)),
            min_turnover=float(flu_cfg.get("min_turnover", 3.0)),
        )
        if is_sig:
            print(f"  ✅ first_limit_up: {details}")
            cur.execute(
                "INSERT INTO signals (stock_id, signal_type, signal_date, details) VALUES (?, ?, ?, ?)",
                (stock_id, "first_limit_up", signal_date, details),
            )
            inserted += 1
        else:
            print(f"  · first_limit_up: {details}")

        # --- bottom_reversal ---
        is_sig, details = detect_bottom_reversal(
            df,
            lookback_days=int(br_cfg.get("lookback_days", 60)),
            low_pct_threshold=float(br_cfg.get("low_pct_threshold", 20.0)),
            volume_multiplier=float(br_cfg.get("volume_multiplier", 2.0)),
        )
        if is_sig:
            print(f"  ✅ bottom_reversal: {details}")
            cur.execute(
                "INSERT INTO signals (stock_id, signal_type, signal_date, details) VALUES (?, ?, ?, ?)",
                (stock_id, "bottom_reversal", signal_date, details),
            )
            inserted += 1
        else:
            print(f"  · bottom_reversal: {details}")

        print()

    conn.commit()
    conn.close()

    print(f"扫描完成，新增信号 {inserted} 条。")


if __name__ == "__main__":
    scan_signals()

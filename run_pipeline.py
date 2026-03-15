#!/usr/bin/env python3
"""Richman Skill 一键执行管道：

1. 初始化种子数据（幂等）
2. 扫描 K 线技术信号
3. 生成日报 Markdown

用法：
    python run_pipeline.py              # 完整流程
    python run_pipeline.py --scan-only  # 只扫描信号
    python run_pipeline.py --report-only # 只生成报告
"""

import sys
import os
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent

# 将项目根目录加入 path
sys.path.insert(0, str(ROOT))


def run_init():
    print("=" * 50)
    print("Step 1: 初始化种子数据")
    print("=" * 50)
    from init_seeds import main as init_main
    init_main()
    print()


def run_heat():
    print("=" * 50)
    print("Step 2: 拉取题材热度")
    print("=" * 50)
    from fetch.fetch_heat import fetch_and_compute_heat
    fetch_and_compute_heat()
    print()


def run_scan():
    print("=" * 50)
    print("Step 3: 扫描 K 线技术信号")
    print("=" * 50)
    from signals.scan_signals import scan_signals
    scan_signals()
    print()


def run_report():
    print("=" * 50)
    print("Step 4: 生成日报")
    print("=" * 50)
    from report.generate_daily_report import generate_report
    generate_report()
    print()


def main():
    args = sys.argv[1:]

    if "--scan-only" in args:
        run_scan()
    elif "--report-only" in args:
        run_report()
    else:
        run_init()
        run_heat()
        run_scan()
        run_report()

    print("✅ Pipeline 完成")


if __name__ == "__main__":
    main()

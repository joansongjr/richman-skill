# richman-skill

"Richman Skill"：赛道 + 情绪 + K 线 技术形态选股工具（Skill 雏形）。

## 目录结构

- `schema.sql` — SQLite 数据库结构（topic_posts、topics、stocks、signals 等）
- `config/topics.yaml` — 题材归一化映射表（统一名称 + 别名列表）
- `data/` — SQLite 数据库文件、临时抓取结果
- `fetch/` — 各站点抓取脚本（雪球、股吧、同花顺等）
- `signals/` — K 线形态识别逻辑
- `report/` — 报告生成脚本（Markdown/JSON）

## 使用流程（初版）

1. 运行 `python fetch/fetch_all.py` 抓取最近 7 天帖子/话题数据。
2. 运行 `python signals/scan_signals.py` 更新每个题材下标的的技术信号。
3. 运行 `python report/generate_daily_report.py` 生成当日选股报告：
   - 输出到 `reports/daily-YYYY-MM-DD.md`。

后续可以封装成 OpenClaw Skill 或 cron 任务。

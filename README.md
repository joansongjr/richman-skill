# richman-skill

"Richman Skill"：面向专业投资人的 **赛道题材 + 情绪热度 + K 线技术形态选股助手**。

> 核心思路：从热门题材/赛道中出发，用舆情热度筛方向，用技术形态筛买点，最后生成结构化的选股理由和每日早晚报。

## 功能模块

1. **题材热度模块**（计划中）  
   - 从雪球 / 东方财富股吧 / 同花顺等公开网页/接口抓取帖子数据。  
   - 统计不同题材在最近 24 小时 vs 过去 3–7 天的发帖数、回复数增速。  
   - 计算综合热度得分，选出当下最热的 3–5 个题材/赛道。

2. **K 线技术形态模块**（开发中）  
   - 基于免费行情源（优先 A 股，后续扩展港股/美股），获取标的的日 K 线数据。  
   - 使用可配置规则（YAML）识别经典形态：  
     - 突破前高 + 放量（breakout）  
     - 第一个涨停启动（first_limit_up，A 股）  
     - 底部放量反转（bottom_reversal）等。  
   - 将识别到的技术信号写入 SQLite 数据库，供报告和上层 Agent 使用。

3. **推荐理由模块**（计划中）  
   - 结合：  
     - 题材逻辑（赛道为何火、核心驱动因素）  
     - 公司在产业链中的位置与竞争格局  
     - 市场观点 & 券商研报摘要  
   - 由 LLM（如 Kimi / MiniMax）生成结构化的推荐理由文本，包括：  
     - 题材 & 赛道逻辑  
     - 公司位置与优势  
     - 当前技术信号的含义  
     - 风险提示（估值、预期一致性、政策风险等）。

4. **定时推送模块：Richman 早晚报**（计划中）  
   - 早上 **07:50**：生成并推送一份“开盘前选股摘要”，侧重：  
     - 当下最热题材 Top N  
     - 每个题材下技术形态有信号的重点标的  
   - 晚上 **21:30**：生成并推送一份“收盘后复盘摘要”，侧重：  
     - 早盘信号标的当天实际走势  
     - 题材热度变化与市场情绪回顾  
   - 推送渠道（示例）：  
     - Telegram / 飞书（通过 OpenClaw 的 `message` / Feishu 插件）  
   - 后续可扩展邮件 / 其他渠道。

> 当前仓库处于 **MVP 阶段**：先实现本地 SQLite + 行情 + K 线形态扫描 + Markdown 报告，之后再逐步接入题材抓取和自动推送。

## 目录结构（当前）

- `schema.sql` — SQLite 数据库结构（topic_posts, topics, stocks, signals, topic_heat 等）  
- `config/`  
  - `topics.example.yaml` — 题材归一化映射示例（统一名称 + 别名列表）  
- `fetch/`  
  - `fetch_all.py` — 各站点抓取入口脚本（目前为骨架，待补充具体逻辑）  
- `signals/`  
  - `scan_signals.py` — 扫描标的的 K 线技术信号（当前为骨架，将接入行情和模式识别）  
  - `patterns.example.yaml` — 技术形态规则示例（breakout / first_limit_up / bottom_reversal 等）  
- `report/`  
  - `generate_daily_report.py` — 生成每日选股 Markdown 报告的脚本。  
- `README_FOR_OPENCLAW.md` — 初始设计笔记，可后续合并进正式 README。

后续还会新增：

- `init_seeds.py` — 初始化题材和标的池（插入 CPO/光模块等赛道的代表性股票）。  
- `cron/` — 示例定时任务脚本（早 7:50 / 晚 21:30 自动跑报告并通过 OpenClaw 推送）。

## 使用说明（本地开发阶段）

> 以下为规划中的使用流程，随着代码完善会逐步补全。

1. 克隆仓库并进入目录：

```bash
git clone https://github.com/<your-account>/richman-skill.git
cd richman-skill
```

2. 创建 Python 虚拟环境并安装依赖（示例）：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt  # 后续会补充依赖列表
```

3. 初始化数据库（自动执行 `schema.sql`）：

```bash
python fetch/fetch_all.py  # 当前会创建 data/topics.db 并打印 TODO
```

4. 运行技术信号扫描和日报生成：

```bash
python signals/scan_signals.py          # 根据行情+形态规则更新 signals 表
python report/generate_daily_report.py  # 生成 reports/daily-YYYY-MM-DD.md
```

未来会通过 OpenClaw Skill 的方式接入到 Agent，支持自然语言调用和自动推送。

## 免责声明

本项目仅用于技术研究与教学演示，不构成任何投资建议。  
使用者需自行承担基于本工具输出进行交易的风险。

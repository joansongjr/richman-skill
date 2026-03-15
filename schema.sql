-- SQLite schema for thematic-kline-stockpicker

PRAGMA foreign_keys = ON;

-- 原始帖子数据（雪球 / 股吧 / 同花顺 / 其他）
CREATE TABLE IF NOT EXISTS topic_posts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source TEXT NOT NULL,           -- xueqiu / guba / 10jqka / weibo / ...
  topic_raw TEXT NOT NULL,        -- 原始题材/关键词
  topic_norm TEXT,                -- 归一化题材名（由 topics 表提供）
  stock_code TEXT,                -- 关联个股（可为空）
  title TEXT NOT NULL,
  replies INTEGER DEFAULT 0,
  views INTEGER DEFAULT 0,
  likes INTEGER DEFAULT 0,
  created_at DATETIME NOT NULL
);

-- 归一化题材表
CREATE TABLE IF NOT EXISTS topics (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,      -- 统一题材名，例如 "CPO/光模块"
  description TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 题材别名映射（用来把不同平台的名字归一化）
CREATE TABLE IF NOT EXISTS topic_aliases (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  topic_id INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
  alias TEXT NOT NULL
);

-- 标的池：题材 - 股票 对应关系
CREATE TABLE IF NOT EXISTS stocks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  topic_id INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
  code TEXT NOT NULL,             -- 例如 300502.SZ / AAPL / 0700.HK
  market TEXT NOT NULL,           -- CN / HK / US 等
  name TEXT NOT NULL,
  UNIQUE(code, market)
);

-- 技术信号表（由 K 线形态扫描脚本写入）
CREATE TABLE IF NOT EXISTS signals (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  stock_id INTEGER NOT NULL REFERENCES stocks(id) ON DELETE CASCADE,
  signal_type TEXT NOT NULL,      -- breakout / first_limit_up / bottom_reversal 等
  signal_date DATE NOT NULL,
  details TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 每日题材热度统计表
CREATE TABLE IF NOT EXISTS topic_heat (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  topic_id INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
  date DATE NOT NULL,
  posts_T1 INTEGER NOT NULL,      -- 当日发帖数
  posts_T2 REAL NOT NULL,         -- 过去 3-7 天日均发帖数
  replies_T1 INTEGER NOT NULL,
  replies_T2 REAL NOT NULL,
  score REAL NOT NULL,
  UNIQUE(topic_id, date)
);

-- 基本面 / 估值因子表（来自 FactSet / Wind / 其他本地 CSV 导入）
CREATE TABLE IF NOT EXISTS fundamentals (
  stock_id INTEGER PRIMARY KEY REFERENCES stocks(id) ON DELETE CASCADE,
  pe_12m_fwd REAL,         -- 未来12个月预期PE
  pb REAL,                 -- 市净率
  eps_growth_1y REAL,      -- EPS 1年预期增速(%)
  eps_growth_3y REAL,      -- EPS 3年预期增速(%)
  broker_rating TEXT,      -- 一致评级（如 Buy/Overweight/Neutral）
  updated_at DATE          -- 数据更新时间
);

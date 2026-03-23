# CLAUDE.md

## 项目背景

我是一个基金经理，每天需要看关注的券商研报。研报来源分散（券商平台、邮件、微信），所以做了这个工具把研报聚合起来，自动推送到企业微信群。

当前数据源：
- 慧博投研资讯（hibor.com.cn），有免费账号
- 东方财富研报中心（data.eastmoney.com），公开 JSON API，无需登录

## 项目结构

本项目是 richman-skill 的一部分（投资选股助手），研报推送是其中一个模块：

- `eastmoney_report.py` — 东方财富研报采集：公开 API → 券商过滤 → SQLite 去重 → 企业微信推送 + CLI 搜索
- `hibor_report_push.py` — 慧博研报采集：登录采集 → 券商过滤 → SQLite 去重 → 企业微信推送
- `README_HIBOR.md` — 研报推送模块的使用说明
- `requirements.txt` — Python 依赖（requests + beautifulsoup4）

## 技术栈

- Python，依赖尽量少
- requests + BeautifulSoup4 解析服务端直出 HTML
- SQLite 本地去重
- 企业微信群机器人 Webhook 推送

## 开发偏好

- 用中文沟通
- 所有配置集中在文件顶部的 CONFIG 字典
- 代码简洁，不过度工程化
- 完成后 commit 并 push 到 GitHub

## 当前进度

- [x] 慧博研报采集（登录、HTML 解析、券商提取）
- [x] 券商/行业/日期过滤
- [x] SQLite 去重 + 自动清理
- [x] 企业微信推送（单条/合并两种模式）
- [x] 东方财富研报数据源（公开 API，无需登录，支持 CLI 搜索）
- [ ] 实际测试慧博页面结构，调整 CSS 选择器
- [ ] 接入更多研报来源（邮件、其他平台）
- [ ] 研报内容摘要（LLM 生成）

## 会话约定

每次会话结束前：
1. 把重要的决策和进展更新到本文件的「当前进度」和「开发日志」
2. commit 并 push 到 GitHub
3. 这样新会话自动读取本文件即可恢复上下文，不需要重复解释

## 开发日志

### 2026-03-23
- 初始版本完成：慧博采集 + 券商过滤 + SQLite 去重 + 企业微信推送
- 创建 README_HIBOR.md 使用说明
- 创建 CLAUDE.md 用于跨会话上下文保持
- 新增东方财富研报数据源 `eastmoney_report.py`
  - 使用东方财富公开 JSON API（reportapi.eastmoney.com），无需登录
  - 支持按券商、日期范围、研报类型、关键词过滤
  - 内置 20 家主流券商的 orgCode 映射
  - CLI 模式：`python eastmoney_report.py -b 兴业证券 -d 7`
  - 定时任务模式：直接运行 `python eastmoney_report.py`
  - 复用企微推送 + SQLite 去重逻辑

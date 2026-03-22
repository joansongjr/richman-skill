# 慧博研报采集 & 企业微信推送工具

从 [慧博投研资讯](https://www.hibor.com.cn) 采集券商研报，按关注券商过滤后，自动推送到企业微信群。

## 功能

- 登录慧博（支持账号密码 / 手动粘贴 Cookie）
- 采集多个研报分类页面（行业分析、公司调研、投资策略等）
- 从标题自动提取券商名称并按白名单过滤
- 可选行业关键词过滤、仅推当天研报
- SQLite 本地去重，避免重复推送
- 企业微信群机器人 Webhook 推送（Markdown 格式）
- 超过 5 篇自动合并为按券商分组的汇总消息
- 自动清理 30 天前的去重记录

## 安装

```bash
cd richman-skill
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 配置

编辑 `hibor_report_push.py` 顶部的 `CONFIG` 字典：

### 1. 慧博登录

**方式一：账号密码**
```python
"hibor_username": "your_username",
"hibor_password": "your_password",
```

**方式二：浏览器 Cookie（优先）**

1. 浏览器登录 hibor.com.cn
2. F12 → Network → 任意请求 → 复制 Cookie 头的值
3. 粘贴到配置中：
```python
"hibor_cookie": "your_cookie_string_here",
```

### 2. 企业微信群机器人

1. 在企业微信群中点击右上角 → 群机器人 → 添加机器人
2. 记录 Webhook URL（格式：`https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx`）
3. 填入配置：
```python
"wechat_webhook_url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY",
```

### 3. 券商白名单

```python
"broker_whitelist": [
    "兴业证券",
    "中信证券",
    "海通证券",
    "国泰君安",
    "华泰证券",
],
```

### 4. 行业过滤（可选）

```python
"industry_keywords": ["电子", "半导体", "新能源"],
```

### 5. 日期过滤

```python
"today_only": True,   # True: 只推当天; False: 推列表页所有
```

## 运行

```bash
python hibor_report_push.py
```

## 定时执行（cron）

编辑 crontab：
```bash
crontab -e
```

添加以下内容（每天 8:00、12:00、18:00 各跑一次）：
```cron
0 8 * * * cd /path/to/richman-skill && /path/to/.venv/bin/python hibor_report_push.py >> hibor.log 2>&1
0 12 * * * cd /path/to/richman-skill && /path/to/.venv/bin/python hibor_report_push.py >> hibor.log 2>&1
0 18 * * * cd /path/to/richman-skill && /path/to/.venv/bin/python hibor_report_push.py >> hibor.log 2>&1
```

请将 `/path/to/` 替换为实际路径。

## 推送效果

**单篇推送（≤5 篇时）：**
> **兴业证券**
> [兴业证券-电子行业周报：半导体景气回升-260322](https://www.hibor.com.cn/...)
> > 日期: 2026-03-22

**合并推送（>5 篇时）：**
> **今日研报汇总（共 12 篇）**
>
> **兴业证券**（3 篇）
> - [报告标题1](url)
> - [报告标题2](url)
>
> **中信证券**（2 篇）
> - [报告标题3](url)

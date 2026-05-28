# Cronos 后端

基于 FastAPI 构建的智能 RSS 阅读系统后端，提供 RSS 订阅管理、文章采集、AI 流式摘要、用户认证等功能。

## 环境要求

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)（包管理工具）

## 快速开始

### 1. 安装依赖

```bash
uv sync
```

> 首次克隆项目后还需安装 Playwright 浏览器：
> ```bash
> uv run playwright install chromium
> ```

### 2. 启动服务

```bash
uv run python run.py
```

服务默认监听 `http://localhost:8000`，启动后自动完成数据库初始化。

### 3. 查看 API 文档

启动后访问 `http://localhost:8000/docs` 查看自动生成的 Swagger 文档。

---

## 依赖管理

项目使用 `uv` 管理依赖，所有依赖声明在 `pyproject.toml` 中。

| 操作 | 命令 |
|------|------|
| 安装所有依赖 | `uv sync` |
| 添加新依赖 | `uv add <package>` |
| 移除依赖 | `uv remove <package>` |
| 运行脚本 | `uv run python <script.py>` |

---

## 项目结构

```
crono-backend/
├── app.py              # FastAPI 应用工厂，路由注册与生命周期管理
├── run.py              # 启动入口（uvicorn）
├── pyproject.toml      # 项目元数据与依赖声明
├── cronos.db           # SQLite 数据库文件（运行后自动生成）
│
├── models/             # Pydantic 数据模型
│   ├── user.py         # 用户注册/登录/响应模型
│   ├── config.py       # 系统配置模型
│   ├── rss/            # RSS 相关模型（Feed、Article）
│   └── llm/            # LLM 配置与请求模型
│
├── routes/             # API 路由层
│   ├── auth.py         # 用户认证（注册、登录、/me）
│   ├── config.py       # 系统配置 CRUD
│   ├── rss/            # RSS 订阅源、文章、状态、更新器路由
│   └── llm/            # LLM 配置、聊天、摘要路由
│
├── services/           # 业务逻辑层
│   ├── auth.py         # JWT 签发/验证、密码哈希、认证依赖
│   ├── database.py     # SQLite 连接管理与数据库初始化
│   ├── playwright.py   # Playwright 动态抓取 + 正文提取
│   ├── config.py       # 配置读写服务
│   ├── rss/            # RSS 更新调度、文章入库、状态管理
│   └── llm/            # LLM 调用与流式摘要服务
│
└── sql/                # 数据库建表脚本（启动时自动执行）
    ├── users.sql        # 用户表
    ├── rss_feeds.sql    # 订阅源表
    ├── articles.sql     # 文章表
    ├── article_states.sql # 文章状态表
    ├── config.sql       # 系统配置表
    └── llm_config.sql   # LLM 配置表
```

---

## API 概览

### 认证 `/auth`

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/auth/register` | 注册新用户，返回 JWT Token |
| POST | `/auth/login` | 登录，返回 JWT Token |
| GET  | `/auth/me` | 获取当前登录用户信息 |

### RSS `/rss`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET/POST/PATCH/DELETE | `/rss/feed/` | 订阅源管理 |
| GET | `/rss/article/latest` | 获取最新文章 |
| GET | `/rss/article/{feed_id}` | 按订阅源获取文章 |
| POST | `/rss/article/state/mark-as-read/{id}` | 标记已读 |
| GET/POST/DELETE | `/rss/updater/` | 更新器控制（启动/停止/立即刷新） |

### LLM `/llm`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/llm/ai_summary/stream` | 流式生成文章摘要 |
| POST | `/llm/stream_chat` | 流式通用对话 |
| GET/POST/PATCH/DELETE | `/llm/llm_config` | LLM 配置管理 |

### 配置 `/config`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/config/` | 获取所有配置项 |
| PATCH | `/config/` | 批量更新配置项 |

---

## 数据库

项目使用 SQLite，数据库文件为 `cronos.db`，首次启动时自动根据 `sql/` 目录下的脚本建表并写入默认配置。无需手动初始化。

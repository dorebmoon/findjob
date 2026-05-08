# FindJob - 求职信息聚合平台

一站式管理各大求职网站的账号和消息，告别在多个平台间来回切换的烦恼。

## ✨ 功能特性

- 🔗 **六大平台聚合** — 支持 Boss直聘、智联招聘、前程无忧、58同城、鱼泡直聘、猎聘
- 🔐 **多种登录方式** — 密码自动登录 + 手机验证码登录（手动浏览器操作）
- 📬 **消息中心** — 聚合查看所有平台的最新推送消息
- 🔒 **安全加密** — 账号密码 Fernet 对称加密存储，保护隐私
- 🎯 **分类筛选** — 按平台筛选查看消息
- 📊 **数据统计** — 总消息数、未读数、平台连接状态一目了然
- 🎨 **6种主题风格** — 深邃夜空、明亮日光、深海蓝、星空紫、森林绿、暖阳橙
- 💾 **持久化浏览器** — 登录状态自动保存，关闭后再次打开无需重新登录

## 🚀 快速开始

### 环境要求

- Python 3.9+
- macOS / Linux / Windows

### 安装依赖

```bash
pip install -r requirements.txt
playwright install chromium
```

### 启动服务

```bash
python app.py
```

服务将在 http://localhost:5001 启动。

### 使用步骤

1. 打开浏览器访问 http://localhost:5001
2. 注册并登录 FindJob 账号
3. 在「平台管理」页面配置各求职平台的账号密码（可选）
4. 点击「验证码」按钮，系统会打开 Chromium 浏览器进入平台登录页
5. 在浏览器中手动完成验证码登录（输入手机号 → 发送验证码 → 完成验证 → 登录）
6. 登录成功后，系统自动检测并保存登录状态
7. 切换到「消息中心」查看聚合消息
8. 点击「加载演示数据」可预览消息面板效果

## 📁 项目结构

```
findjob/
├── app.py                    # Flask 主应用（路由、API、业务逻辑）
├── config.py                 # 配置文件（平台信息、数据库、加密密钥）
├── models.py                 # 数据模型（User、PlatformCredential、Message）+ 加密工具
├── cleanup.py                # 临时文件清理工具
├── requirements.txt          # Python 依赖
├── .env                      # 环境变量（SECRET_KEY、ENCRYPTION_KEY）
├── .gitignore                # Git 忽略规则
├── README.md                 # 项目说明
│
├── scrapers/                 # 平台爬虫模块
│   ├── __init__.py           # 爬虫注册表
│   ├── base.py               # 基础爬虫类（浏览器管理、Cookie检测、持久化配置）
│   ├── boss.py               # Boss直聘爬虫
│   ├── zhilian.py            # 智联招聘爬虫
│   ├── qiancheng.py          # 前程无忧爬虫
│   ├── tongcheng.py          # 58同城爬虫
│   ├── yupao.py              # 鱼泡直聘爬虫
│   └── liepin.py             # 猎聘爬虫
│
├── templates/                # Jinja2 HTML 模板
│   ├── base.html             # 基础模板（CSS变量、动画、通用组件）
│   ├── login.html            # 登录页
│   ├── register.html         # 注册页
│   └── dashboard.html        # 主控制面板（平台管理、消息中心、主题切换）
│
├── instance/                 # SQLite 数据库（自动创建）
│   └── findjob.db
│
└── browser_profiles/         # 浏览器持久化配置（自动创建）
    ├── boss/                 # Boss直聘浏览器 Profile
    ├── zhilian/              # 智联招聘浏览器 Profile
    ├── qiancheng/            # 前程无忧浏览器 Profile
    ├── tongcheng/            # 58同城浏览器 Profile
    ├── yupao/                # 鱼泡直聘浏览器 Profile
    └── liepin/               # 猎聘浏览器 Profile
```

## 🔐 登录方式

### 方式一：密码登录

自动填写账号密码并提交，适合无验证码拦截的平台。

- 前提：需要先在「配置账号」中保存账号密码
- 流程：点击「密码登录」→ 系统自动操作浏览器填写并提交

### 方式二：验证码登录（推荐）

通过 Playwright 打开真实浏览器，用户手动完成登录操作，系统后台自动检测登录状态。

- 流程：
  1. 点击「验证码」按钮
  2. 系统打开 Chromium 浏览器进入平台登录页
  3. 用户手动操作：选择验证码登录 → 输入手机号 → 发送验证码 → 完成滑块/图形验证 → 输入验证码 → 登录
  4. 后台每2秒通过 Cookie 检测登录状态
  5. 登录成功自动保存，关闭浏览器
- 如果自动检测失败，可点击「我已完成登录」手动确认

### 检测原理

每个平台有专属的 Cookie 检测规则：

| 平台 | 检测的登录 Cookie |
|------|-------------------|
| Boss直聘 | `wt2`, `bst`, `t`, `__zp_stoken__`, `wt2_geek` |
| 智联招聘 | `xltoken`, `xap`, `zhaopin_token`, `ZP-LOGIN-TOKEN` |
| 前程无忧 | `51job_login`, `guide_51job`, `usercookie`, `tgc` |
| 58同城 | `58coessionid`, `PPU`, `58tj_uuid`, `isp58` |
| 鱼泡直聘 | `yupao_token`, `yp_session`, `user_token`, `PHPSESSID` |
| 猎聘 | `ltoken`, `lt_auth`, `in_user`, `user_trace_token` |

## 🎨 主题风格

点击顶栏的「主题」按钮可切换6种风格：

| 主题 | 说明 |
|------|------|
| 🌙 深邃夜空 | 默认暗色主题 |
| ☀️ 明亮日光 | 浅色主题，适合白天使用 |
| 🌊 深海蓝 | 青绿色调暗色主题 |
| 💜 星空紫 | 紫色暗色主题 |
| 🌲 森林绿 | 绿色暗色主题 |
| 🔥 暖阳橙 | 暖色调暗色主题 |

主题选择保存在浏览器 localStorage 中，刷新后自动恢复。

## 🛠 技术栈

| 层级 | 技术 |
|------|------|
| 后端框架 | Flask + SQLAlchemy + Flask-Login |
| 前端 | 原生 HTML/CSS/JS（无框架依赖）+ Remix Icon |
| 浏览器自动化 | Playwright (Chromium) |
| 加密 | Fernet 对称加密 (cryptography) |
| 数据库 | SQLite |
| 定时任务 | APScheduler |

## 🧹 临时文件清理

项目运行过程中会生成以下临时文件：

| 文件/目录 | 说明 | 清除影响 |
|-----------|------|----------|
| `browser_profiles/` | 浏览器持久化配置 | 需重新登录所有平台 |
| `instance/findjob.db` | SQLite 数据库 | 用户数据全部丢失 |
| `__pycache__/` | Python 字节码缓存 | 无影响，自动重建 |
| `nohup.out` | 后台运行日志 | 无影响 |

使用清理工具：

```bash
python cleanup.py              # 交互式清理
python cleanup.py --dry-run    # 预览模式（不实际删除）
python cleanup.py --all        # 清理所有临时文件
python cleanup.py --browser    # 仅清理浏览器配置
python cleanup.py --cache      # 仅清理 Python 缓存
```

## ⚠️ 注意事项

- 首次登录时会弹出 Chromium 浏览器窗口，部分平台需要手动完成验证码
- 使用**持久化浏览器配置**，登录一次后浏览器关闭再次打开仍保持登录状态
- 账号密码使用 Fernet (AES) 加密存储在本地 SQLite 数据库中
- 建议在 `.env` 文件中修改默认的 `SECRET_KEY` 和 `ENCRYPTION_KEY`
- 请确保遵守各平台的使用条款，合理使用本工具

## 📄 API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/credentials` | 保存平台账号密码 |
| DELETE | `/api/credentials/<platform>` | 删除平台凭证 |
| GET | `/api/credentials/status` | 获取所有平台登录状态 |
| POST | `/api/login/<platform>` | 密码登录指定平台 |
| POST | `/api/login-all` | 一键登录全部平台 |
| POST | `/api/manual-login/<platform>` | 打开浏览器手动登录 |
| GET | `/api/manual-login/<platform>/status` | 轮询手动登录状态 |
| POST | `/api/manual-login/<platform>/confirm` | 手动确认登录完成 |
| GET | `/api/messages` | 获取消息列表（支持 `?platform=` 筛选） |
| POST | `/api/messages/refresh` | 刷新所有平台消息 |
| POST | `/api/messages/<id>/read` | 标记消息已读 |
| GET | `/api/messages/stats` | 获取消息统计数据 |
| POST | `/api/demo-data` | 加载演示数据 |
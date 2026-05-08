# FindJob - 求职信息聚合平台

一站式管理各大求职网站的账号和消息，告别在多个平台间来回切换的烦恼。

## ✨ 功能特性

- 🔗 **六大平台聚合** — 支持 Boss直聘、智联招聘、前程无忧、58同城、鱼泡直聘、猎聘
- 🔐 **一键登录** — 同时登录所有求职平台账号
- 📬 **消息中心** — 聚合查看所有平台的最新推送消息
- 🔒 **安全加密** — 账号密码 AES 加密存储，保护隐私
- 🎯 **分类筛选** — 按平台筛选查看消息
- 📊 **数据统计** — 总消息数、未读数、平台连接状态一目了然
- 🌙 **暗色主题** — 现代化的暗色 UI 设计

## 🚀 快速开始

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

1. 注册并登录 FindJob 账号
2. 在「平台管理」页面配置各求职平台的账号密码
3. 点击「一键登录全部」或单个平台的「登录」按钮
4. 在弹出的浏览器窗口中完成必要的验证（如验证码）
5. 登录成功后，切换到「消息中心」查看聚合消息
6. 点击「刷新消息」获取最新推送

## 📁 项目结构

```
findjob/
├── app.py              # Flask 主应用
├── config.py           # 配置文件
├── models.py           # 数据模型 & 加密工具
├── requirements.txt    # Python 依赖
├── .env                # 环境变量
├── scrapers/           # 平台爬虫模块
│   ├── __init__.py
│   ├── base.py         # 基础爬虫类
│   ├── boss.py         # Boss直聘
│   ├── zhilian.py      # 智联招聘
│   ├── qiancheng.py    # 前程无忧
│   ├── tongcheng.py    # 58同城
│   ├── yupao.py        # 鱼泡直聘
│   └── liepin.py       # 猎聘
└── templates/          # HTML 模板
    ├── base.html       # 基础模板
    ├── login.html      # 登录页
    ├── register.html   # 注册页
    └── dashboard.html  # 主控制面板
```

## 🛠 技术栈

- **后端**: Flask + SQLAlchemy + APScheduler
- **前端**: 原生 HTML/CSS/JS (无框架依赖)
- **自动化**: Playwright (浏览器自动化)
- **加密**: Fernet (对称加密)
- **数据库**: SQLite

## ⚠️ 注意事项

- 首次登录时会弹出 Chromium 浏览器窗口，部分平台可能需要手动完成验证码
- 请确保遵守各平台的使用条款
- 账号密码使用 AES 加密存储在本地 SQLite 数据库中
- 建议在 `.env` 文件中修改默认的加密密钥
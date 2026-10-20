# 织忆·认知花园 (Cognitive Garden)

> 认知辅助工具：通过日常叙事记录构建个人记忆网络，纵向追踪叙事特征变化，为老人与家属提供趋势参考。

**定位声明**：本项目是叙事记录与趋势观察工具，不是医疗设备，不构成认知衰退的筛查、诊断或医疗决策依据。健康度分数为未经验证的研究性指标，仅供纵向自我参考。涉及认知健康疑虑时请咨询专业医疗机构。

---

## 项目概述

**织忆·认知花园**是一款面向老年用户及其家属的认知健康辅助工具。用户通过语音或文字记录日常叙事，系统自动构建可视化的记忆网络图谱，并通过多维度分析评估认知健康状态。

### 核心功能

- **叙事织网**：语音输入日常叙事，自动提取实体（人物、地点、事件、物品）构建记忆网络
- **认知评估**：MMSE / AD8 认知量表评估，支持定期复评
- **记忆衰退分析**：以个人历史为基线，对比近期与历史叙事，检测实体遗忘、叙事简化、重复叙述、指代失败（"那个谁"类专名提取困难）、填充词密度上升等信号
- **多角色视图**：老人端、家属端、医生端三种视角
- **数据持久化**：本地 localStorage + 后端 SQLite 同步
- **离线支持**：PWA 支持，断网可用

### 方法学定位与依据

信号检测的文献锚点（详见代码注释）：

- MMSE（Folstein et al., 1975）、MoCA（Nasreddine et al., 2005）、AD8（Galvin et al., 2005）为标准认知筛查量表，本项目集成其条目用于自评记录
- 叙事/言语特征与认知衰退的关联：代词使用增多、言语重复、信息内容下降、找词停顿等是 MCI/AD 言语研究的可复现发现（Fraser, Meltzer & Rudzicz, 2016, *Journal of Alzheimer's Disease*；Winterlight Labs 公开 Science 页面汇总）
- **个人基线偏离优先于群体阈值**：一次测量无法区分正常波动与衰退，同一个人相隔数月的纵向对比才是有效信号（纵向个体内对照路线）
- 健康度公式的具体权重（0.35/0.35/0.30 等）目前**无临床数据支撑**，是待验证的启发式参数，仓库路线图（cognitive-garden-roadmap.md）包含临床验证计划

---

## 技术栈

### 前端
- **Vite** + 原生 ES6 模块（无框架，极致轻量）
- **SVG** 力导向布局可视化
- **Web Speech API** / MediaRecorder 语音输入
- **Service Worker** PWA 离线支持

### 后端
- **FastAPI** + **SQLAlchemy** + **SQLite**
- **bcrypt** 密码哈希 + **PyJWT** 认证
- **AES-256-GCM** 业务数据加密
- **jieba** 中文分词 + 自定义词典
- **alembic** 数据库迁移

### 桌面
- **Tauri** + **Rust** 封装（WebView2）

---

## 快速开始

### 环境要求
- Python 3.11+
- Node.js 20+
- Rust 1.70+ (仅桌面构建)

### 启动后端
```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
python run.py
# 后端运行在 http://127.0.0.1:8004
```

### 启动前端（开发）
```bash
cd frontend
npm install
npm run dev
# 前端运行在 http://localhost:5173
```

### 构建前端
```bash
cd frontend
npm run build
# 构建输出到 ../dist
```

### 启动桌面应用
```bash
cd src-tauri
cargo build --release
# 可执行文件在 target/release/cognitive-garden.exe
```

---

## 项目结构

```
├── frontend/          # 前端源码
│   ├── src/
│   │   ├── main.js              # 入口
│   │   ├── state.js             # 全局状态
│   │   ├── api/                 # 后端 API 客户端
│   │   ├── graph/               # 节点/边操作、健康度、布局
│   │   ├── ui/                  # 渲染、交互、面板
│   │   ├── nlp/                 # 文本解析、实体提取
│   │   ├── audio/               # 录音器
│   │   └── tests/               # 前端测试
│   ├── package.json
│   └── vite.config.js
│
├── backend/           # 后端源码
│   ├── app/
│   │   ├── main.py              # FastAPI 入口
│   │   ├── models.py            # 数据库模型
│   │   ├── schemas.py           # Pydantic 校验
│   │   ├── database.py          # 数据库连接
│   │   ├── config.py            # 配置管理
│   │   ├── routers/             # API 路由
│   │   │   ├── auth.py          # 注册/登录/恢复
│   │   │   ├── session.py       # 会话记录
│   │   │   ├── graph.py         # 图谱导出
│   │   │   ├── baseline.py      # 基线设置
│   │   │   ├── stt.py           # 语音转文字
│   │   │   ├── state_sync.py    # 状态同步
│   │   │   ├── backup.py        # 备份恢复
│   │   │   ├── scale.py         # 认知量表
│   │   │   ├── lexicon.py       # 自定义词典
│   │   │   ├── decline.py       # 记忆衰退分析
│   │   │   └── notification.py  # 通知系统
│   │   └── services/            # 业务服务
│   │       ├── crypto.py        # 加密工具
│   │       ├── key_manager.py   # 密钥缓存
│   │       ├── scales.py        # 量表定义
│   │       ├── decline.py       # 衰退分析算法
│   │       └── nlp.py           # NLP 管线
│   ├── alembic/                 # 数据库迁移
│   ├── tests/                   # 后端测试
│   ├── run.py                   # 启动脚本
│   └── requirements.txt
│
├── src-tauri/         # Tauri 桌面应用
│   ├── src/main.rs              # Rust 启动器
│   ├── Cargo.toml
│   └── tauri.conf.json
│
├── dist/              # 前端构建输出
└── release/           # 桌面分发包
```

---

## API 文档

启动后端后访问：
- 开发环境：`http://127.0.0.1:8004/docs` (Swagger UI)
- 生产环境：API 文档关闭

### 核心端点

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | `/auth/register` | 注册（含加密主密钥生成） |
| POST | `/auth/login` | 登录 |
| POST | `/auth/recovery` | 恢复码重置密码 |
| POST | `/session/` | 创建会话 |
| GET | `/session/trend/health` | 健康趋势 |
| GET | `/graph/latest` | 最新图谱 |
| GET | `/graph/export/json` | 导出 JSON |
| POST | `/scale/{id}/submit` | 提交量表 |
| GET | `/decline/analysis` | 衰退分析 |
| GET | `/notification/` | 通知列表 |
| POST | `/backup/export` | 导出备份 |
| POST | `/backup/import` | 导入恢复 |

---

## 测试

### 后端测试
```bash
cd backend
pytest -v --cov=app --cov-report=term-missing
```

### 前端测试
```bash
cd frontend
npx vitest run
```

### E2E 测试
```bash
npx playwright test
```

---

## 部署

### 桌面应用分发
1. 构建前端：`cd frontend && npm run build`
2. 构建后端：`cd backend && pyinstaller backend.spec`
3. 构建 Tauri：`cd src-tauri && cargo build --release`
4. 将 `cognitive-garden.exe`、`backend/`、`dist/` 放入 `release/` 目录

### 环境变量
| 变量 | 说明 | 默认值 |
|------|------|--------|
| `CG_JWT_SECRET` | JWT 密钥 | 自动生成并持久化 |
| `CG_PORT` | 后端端口 | 8004 |
| `CG_AUTO_MIGRATE` | 自动迁移 | 1 |
| `CG_DEBUG` | 调试模式 | 0 |

---

## 安全

- 业务数据（叙事文本、量表答案）使用 **AES-256-GCM** 加密
- 主密钥架构：随机主密钥加密数据，KEK（密码派生）仅用于包装主密钥
- 修改密码无需重加密所有历史数据
- JWT 密钥持久化存储，文件权限限制为 `0o600`
- 限流保护：敏感操作有速率限制
- KMS 提供 file（单机默认）/ env / aws 三种 provider：file 模式密钥持久化到用户目录（0o600），重启后数据仍可解密
- 语音留言（v2，2026-10 重构）：每条消息独立随机内容密钥加密，各用户用**自己的**主密钥包装/解包自己的密钥副本。如实定性为**服务端中转加密**（服务端有能力恢复明文），不是端到端加密；升级路径为 X25519 ECDH 密钥协商（见 e2ee.py 模块文档）

---

## 许可证

MIT License（见 [LICENSE](LICENSE)）

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

### 容器化部署（生产）

```bash
# 1. 构建前端（产物挂载给 nginx）
cd frontend && npm ci && npm run build && cd ..

# 2. 准备密钥：缺失时 compose 会拒绝启动
cp .env.example .env
# 必填：CG_PG_PASSWORD / CG_REDIS_PASSWORD / CG_JWT_SECRET / CG_KMS_MASTER_KEY
# 生成 JWT 密钥：openssl rand -hex 32
# 生成 KMS 主密钥：python -c "import secrets,base64; print(base64.b64encode(secrets.token_bytes(32)).decode())"

# 3. 启动（含反代）
docker compose --profile with-nginx up -d
# 可选监控：--profile with-nginx --profile with-monitoring
```

**首次启动检查**

| 检查项 | 命令 | 期望 |
|---|---|---|
| 后端就绪 | `curl -fsS http://127.0.0.1/health` | `status: ok` |
| 反代安全头 | `curl -sI http://127.0.0.1/ \| grep -i x-content-type` | `nosniff` |
| 指标不外泄 | `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1/metrics` | `404` |
| 上传目录不外泄 | `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1/uploads/x` | `404` |
| SSE 鉴权 | `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1/events` | `401` |
| 迁移版本 | `docker compose exec backend alembic current` | 与 `alembic heads` 一致 |

**网络暴露面**：仅 nginx 的 80 端口对外；backend 绑定 `127.0.0.1:8004` 供本机调试，
PostgreSQL / Redis 只在容器网络内可达（不映射宿主机端口）。

### 管理员与医生账号

自助注册只接受 `elderly` / `family` 角色——`admin` / `doctor` 具备跨用户数据与密钥
导出权限，开放自助注册等于放弃权限边界。开通方式（运维在库中提升）：

```bash
docker compose exec postgres psql -U cg_user -d cognitive_garden \
  -c "UPDATE users SET role='admin' WHERE username='<用户名>';"
```

提升后该用户无需重新登录（每次请求按库中角色校验），但建议重新登录以刷新前端菜单。

### 环境变量

变量名同时接受 `CG_` 前缀与裸字段名两种写法（兼容历史部署）。

| 变量 | 说明 | 必填 |
|------|------|------|
| `CG_PG_PASSWORD` | PostgreSQL 密码 | 容器部署必填 |
| `CG_REDIS_PASSWORD` | Redis 密码（Redis 以 `--requirepass` 启动） | 容器部署必填 |
| `CG_JWT_SECRET` | JWT 签名密钥；更换会使全部已签发 token 失效 | 容器部署必填 |
| `CG_KMS_PROVIDER` | `file`（单机默认）/ `env` / `aws` | 否 |
| `CG_KMS_MASTER_KEY` | env 模式的 base64(32B) 主密钥 | env 模式必填 |
| `CG_CORS_ORIGINS` | 跨域前端域名，逗号分隔；同源反代部署可留空 | 否 |
| `CG_TRUST_PROXY` | 前置反代可信时按 `X-Real-IP`/XFF 末跳取客户端 IP | 反代部署建议 `1` |
| `CG_METRICS_TOKEN` | 设置后 `/metrics` 需 `Authorization: Bearer` | 否 |
| `CG_SERVE_UPLOADS` | 是否把语音密文目录作为静态资源暴露（默认 `0`） | 否 |
| `CG_DATA_DIR` | 数据盘检查路径（健康检查用） | 否 |
| `CG_AUTO_MIGRATE` | 启动时自动执行 alembic 迁移 | 否（默认 1） |
| `CG_ALLOW_CREATE_ALL` | 迁移失败时降级 `create_all`（仅开发） | 否（默认 0） |
| `CG_DEBUG` | 调试模式（开放 `/docs`、CORS 开发来源） | 否 |
| `CG_PORT` / `CG_HOST` | 监听端口/地址 | 否 |
| `ALERT_OUTBOUND_MIN_SEVERITY` | 出站告警门槛（info/warning/danger） | 否 |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASSWORD` / `SMTP_FROM` / `SMTP_USE_SSL` | 告警邮件通道（G1），留空关闭 | 否 |
| `ALERT_WEBHOOK_URL` | 企业微信群机器人 webhook（G1） | 否 |

**迁移语义**：生产环境迁移失败即终止启动（不会带着不一致的 schema 对外服务）；
PostgreSQL 下多副本同时启动时通过 advisory lock 串行化迁移，只有一个实例执行。

### 密钥备份（必做）
file KMS 的 wrap key 与数据同机存放，密钥丢失 = 全部加密内容永久不可解。
首次部署后立即以管理员身份 `GET /api/v1/backup/kms-wrap-key` 导出备份，
灾后用 `POST /api/v1/backup/kms-wrap-key` 恢复（校验 → 落盘 → 热替换，
无需重启）；`GET /api/v1/backup/kms-status` 自检当前 provider 的恢复路径。
env/aws provider 的密钥由对应密钥管理体系备份。

### 数据库备份与恢复（S2）
`pg-backup` 服务随主栈启动：每 24h 一次 `pg_dump -Fc` 到 `cg_pg_backups`
卷，滚动保留 14 天。恢复：

```bash
docker exec -i cg-pg-backup pg_restore -h postgres -U cg_user \
  -d cognitive_garden --clean /backups/<文件名>.dump
```

备份卷与数据同机——异地容灾请另行把 `cg_pg_backups` 卷同步到对象存储。

### 监控与告警（S1）
`docker compose --profile with-monitoring up -d` 启动 Prometheus（:9090），
规则见 `monitoring/alert_rules.yml`：5xx 率 >5%、ASR 失败率 >30%、
漏录提醒 job 超 25h 未执行。若设置了 `CG_METRICS_TOKEN`，需在
`monitoring/prometheus.yml` 中填入同一令牌（文件内已留注释位置）。

### 账号注销（G4）
登录用户在左侧「账户与安全」面板点「注销账号」，密码确认后级联删除
全部业务数据；分析事件与审计日志匿名化/去关联化保留（合规要求）。

### 回滚

应用回滚：`docker compose down && git checkout <上一个稳定 tag> && docker compose --profile with-nginx up -d --build`。
数据库回滚需先确认迁移可逆（`alembic downgrade -1`）；本仓库迁移以新增列/表为主，
破坏性变更需先恢复 pg 备份再切回旧镜像。**镜像回滚不会自动回滚 schema**，
因此升级前务必确认最近一次 `pg-backup` 成功。

---

## 安全

- 业务数据（叙事文本、量表答案）使用 **AES-256-GCM** 加密
- 主密钥架构：随机主密钥加密数据，KEK（密码派生）仅用于包装主密钥
- 修改密码无需重加密所有历史数据
- JWT 密钥持久化存储，文件权限限制为 `0o600`；容器部署经环境变量注入
- 密码校验：bcrypt，UTF-8 上限 72 字节（bcrypt 5.0 起超长输入直接拒绝），超限返回可读校验错误
- 登录防爆破：IP 维度限流（5 次 / 5 分钟）+ 账号维度锁定（5 次失败锁 15 分钟，跨 IP 有效）；账号不存在时执行等价 bcrypt 计算，避免响应时间枚举账号
- 限流客户端 IP：默认只认 TCP 对端地址；仅在 `CG_TRUST_PROXY=1` 时采信反代写入的 `X-Real-IP` / XFF 末跳
- 可观测端点：`/metrics` 需 Bearer 令牌或私网来源；`/events` 强制校验 access token（query 传递）+ 15s 心跳
- 语音留言密文目录默认不作为静态资源暴露（`CG_SERVE_UPLOADS=0`）
- 错误响应不返回服务器路径与堆栈，返回 `request_id` 供日志关联
- 上传体积上限：STT 音频默认 10MB、备份导入默认 10MB（解压后 10 倍上限防压缩炸弹）
- 容器以非 root 用户运行（entrypoint 修正卷属主后 `gosu` 降权），镜像内不含 `.env` 与测试数据
- KMS 提供 file（单机默认）/ env / aws 三种 provider：file 模式密钥持久化到用户目录（0o600），重启后数据仍可解密；wrap key 支持导出备份与灾后恢复（见上方"密钥备份"）
- 语音留言（v2，2026-10 重构）：每条消息独立随机内容密钥加密，各用户用**自己的**主密钥包装/解包自己的密钥副本。如实定性为**服务端中转加密**（服务端有能力恢复明文），不是端到端加密；升级路径为 X25519 ECDH 密钥协商（见 e2ee.py 模块文档）

---

## 许可证

MIT License（见 [LICENSE](LICENSE)）

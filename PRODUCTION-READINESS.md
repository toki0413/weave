# 织忆 · 生产交付说明

基线：`master` @ `d97c061`（2026-11-11）
结论：功能、安全、可观测与部署编排达到试点部署条件。剩余风险集中在两项外部依赖（ASR 生产密钥、真实试点数据）和若干需要在部署环境完成的动作，逐条列在第四节。

本文只记录能够用命令复核的事实。测试数字取自本基线的本地与 CI 运行，未包含推断值。

---

## 一、已修复问题

### 交付阻断

| 问题 | 改前 | 改后 | 落点 | 核验 |
|---|---|---|---|---|
| 带反代的部署无法启动 | `docker-compose` 挂载 `./nginx.conf`，仓库中不存在该文件 | 补齐反代配置：SPA 回退、SSE 免缓冲、安全响应头与 CSP、上传上限、`/metrics` 与 `/uploads` 公网拒绝 | `nginx.conf` | `test_deploy_config.py` 断言文件存在且被挂载、SSE 关闭缓冲、安全头齐全 |
| 任何人都能注册成管理员 | `/auth/register` 直接采用客户端传入的 `role` | 自助注册仅接受 `elderly` / `family`；`admin` / `doctor` 由运维在库中开通 | `routers/auth.py` | 注册 `admin` / `doctor` / `ADMIN` 均返回 400 |
| 任意登录用户可下载全站日志 | `/backup/logs` 只校验登录态 | 改为 admin-only，并加 5 次/5 分钟限流 | `routers/backup.py` | 普通用户 403，管理员 200/404 |
| 中文密码注册直接 500 | bcrypt 锁 5.0.0，对 >72 字节密码抛 `ValueError`，而 schema 允许 128 字符 | 校验改为 UTF-8 字节上限（422 + 可读提示）；校验侧截断至 72 字节，兼容 4.x 静默截断生成的历史哈希 | `schemas.py`、`routers/auth.py` | 80 字节密码返回 422；200 字符密码登录返回 401 而非 500 |
| 迁移失败仍对外服务 | alembic 失败静默降级 `create_all`，实例带着与迁移历史不一致的 schema 上线 | 生产 fail-fast；降级需显式 `CG_ALLOW_CREATE_ALL=1`；PostgreSQL 迁移加 advisory lock，多副本启动串行化 | `app/main.py` | `test_deploy_config.py` + 全量迁移测试 |
| CI 依赖安装失败 | sphinx 9.2.0 声明 `requires-python >=3.13`，CI 跑 3.12 | 固定在 9.1.1（支持 3.12 的最后一个补丁版），并在文件内注明升级条件 | `requirements-dev.txt` | 在真实 3.12.13 环境完成安装并跑通全量测试 |
| 第 8 条会话必 500 | `create_session` 在 `history_count >= 7` 时调用 `build_personal_baseline`，该函数从未导入 → `NameError` 转成 500。试点按每天 3 条，第 3 天触发；全量测试从未创建过 8 条会话，因此一直全绿 | 补导入；新增 3 条回归用例（第 8 条、第 12 条、基线落库）；CI 增加 pyflakes 未定义名门禁 | `routers/session.py`、`tests/test_session_baseline_rebuild.py`、`ci.yml` | 修复前第 8 条复现 `NameError`，修复后 354 通过 |
| 量表提交不广播事件 | `scale.py` 调用 `broadcast_event` 但未导入，`NameError` 被外层 `try/except` 吞掉：接口 200，家属端从未收到 `new_scale` | 补导入；新增用例直接监听事件队列断言消息内容 | `routers/scale.py`、`tests/test_scale.py` | 新增用例断言 `new_scale` 与 `elderly_id` 出现 |

### 安全与暴露面

| 问题 | 改前 | 改后 | 落点 |
|---|---|---|---|
| 实时事件流无鉴权 | `/events` 不校验任何凭证，可订阅跨用户事件 | 校验 access token（签名、类型、黑名单、用户存在），加 15s 心跳；前端同步携带 token | `app/main.py`、`services/websocket.js` |
| 指标端点公开 | `/metrics` 无任何限制 | 配置 `CG_METRICS_TOKEN` 时按 Bearer 校验；未配置时仅接受环回/私网来源，其余 404 | `app/main.py` |
| 错误响应泄露服务器路径 | 500 响应返回日志文件绝对路径 | 只返回 `request_id`（同时写入日志与响应头），不暴露路径与堆栈 | `app/main.py` |
| 语音密文目录静态暴露 | `/uploads` 无条件挂载为静态资源 | 默认不挂载；需 `CG_SERVE_UPLOADS=1` 显式开启，反代侧同步拒绝 | `app/main.py`、`nginx.conf` |
| 数据库与缓存暴露公网 | compose 映射 `5432`、`6379` | 移除端口映射，仅在容器网络内可达 | `docker-compose.yml` |
| 凭据硬编码 | PG 密码写死在 compose 与 healthcheck | 改为环境变量必填（`${VAR:?}`），缺失时 compose 拒绝启动 | `docker-compose.yml` |
| 镜像以 root 运行且包含密钥 | 无 `USER`，`COPY . .` 会把 `.env`、`uploads`、`tests` 带进镜像 | 非 root 运行（entrypoint 修正卷属主后 `gosu` 降权）；`.dockerignore` 排除密钥与数据；生产镜像不再安装测试工具 | `Dockerfile`、`.dockerignore`、`requirements-dev.txt` |
| 限流可被伪造头绕过 | 无条件采信 `X-Forwarded-For` 首项 | 默认只认 TCP 对端；`CG_TRUST_PROXY=1` 时优先 `X-Real-IP`，其次取 XFF 末跳 | `rate_limit.py` |
| Redis 滑动窗口计数偏小 | member 用时间戳字符串，同毫秒并发互相覆盖 | member 加随机后缀，计数准确 | `rate_limit.py` |
| 登录可爆破、可枚举账号 | 仅 IP 限流；账号不存在时跳过 bcrypt 校验 | 增加账号级锁定（5 次失败锁 15 分钟，跨 IP 有效）与计时均衡；审计记录改为标识散列 | `routers/auth.py` |
| 配置前缀未生效 | CI 一直设置 `CG_KMS_*`，但 settings 字段不认该前缀，实际读不到 | 关键字段加 `AliasChoices`，`CG_` 前缀与裸字段名都识别 | `config.py` |

### 稳定性与可维护性

| 问题 | 改前 | 改后 | 落点 |
|---|---|---|---|
| 生产 Redis 静默降级 | `retry_on_timeout` 在 redis-py 6+ 已移除，传入即抛错并被吞掉，限流/黑名单/跨副本 SSE 全部退回内存模式 | 移除该参数，补 `socket_keepalive` 与 `health_check_interval` | `redis_client.py` |
| SSE 订阅断流 | 订阅线程用带 `socket_timeout` 的连接，空闲超时即退出且不重连 | 独立连接（无 socket_timeout）+ 5 秒重连循环 | `redis_client.py`、`services/events.py` |
| 连接数指标泄漏 | 中间件在 `call_next` 抛异常时不归还 Gauge | 改为 `try/finally`，异常路径同样观测与归还 | `app/main.py` |
| 指标标签基数爆炸 | 用实际路径做 label，`/sessions/{id}` 每用户一个标签；挂载子应用全部落到 `unmatched` | 主应用取路由模板；子应用拼 `root_path`；取不到时按 UUID/数字/超长段归一化 | `app/main.py` |
| 上传可打满内存 | STT 与备份导入均整块 `read()` 后再判断大小 | 限量读取（上限 +1 字节）；gzip 解压改为分块并设解压上限，防压缩炸弹 | `routers/stt.py`、`routers/backup.py` |
| 安全检查形同虚设 | CI 的 bandit 与 npm audit 都带 `\|\| true` | 改为中危及以上阻断构建；新增断言防止回退 | `.github/workflows/ci.yml` |

### 视觉与品牌

| 项 | 改前 | 改后 |
|---|---|---|
| 设计令牌 | 仅颜色与字号，圆角/阴影/间距散落硬编码 | 新增 surface / radius / shadow / space / motion 令牌，老人端与暗色主题各一套覆盖 |
| 按钮状态 | 只有 hover | 补齐 `:active`、`:disabled`、`:focus-visible`；老人端禁用态用虚线框而非透明度 |
| 响应式 | 零个宽度断点 | 1280 / 1080 / 900 / 760 / 600 五档；390/900/1440 实测无横向溢出 |
| 品牌 | 顶栏 `Weave` + 副标 `认知花园` | 单标题「织忆」；title、manifest、启动页、引导、分享页、邮件发件人、语言包同步；新增守卫测试 |

---

## 二、验收项

| # | 验收项 | 执行方式 | 通过标准 | 本次实测 |
|---|---|---|---|---|
| 1 | 后端测试 | `pytest tests` | 全绿 | **366 passed**（3.13 本地、3.12 由 CI 复核） |
| 2 | 前端组件测试 | `npx vitest run` | 全绿 | **85 passed**（10 个文件） |
| 3 | 前端静态验算 | `node --test "src/tests/*.spec.mjs"` | 全绿 | **54 passed**（含对比度、字号阶梯、品牌守卫） |
| 4 | 前端构建 | `npm run build` | 成功 | 成功 |
| 5 | 依赖漏洞 | `npm audit --audit-level=moderate` | 0 漏洞 | **0** |
| 6 | 后端静态扫描 | `bandit -r app/ -ll` | 无中危及以上 | **0 High / 0 Medium**（24 Low，均为 subprocess 等已知项） |
| 7 | CI 门禁 | GitHub Actions | 5 项全绿 | **5/5**（backend-security、backend-test、frontend-security、frontend-test、lighthouse） |
| 8 | 部署配置不变量 | `pytest tests/test_deploy_config.py` | 全绿 | **20 passed** |
| 9 | 安全边界 | `pytest tests/test_security_hardening.py` | 全绿 | **19 passed** |
| 9b | 端点冒烟 | `pytest tests/test_endpoint_smoke.py` | 无 5xx | **39 个 GET 端点全部无 5xx** |
| 10 | 反代安全头 | `curl -sI http://<host>/ \| grep -i x-content-type` | 含 `nosniff` | 配置已就位，需在部署环境复核 |
| 11 | 指标不外泄 | `curl -s -o /dev/null -w '%{http_code}' http://<host>/metrics` | `404` | 同上 |
| 12 | 上传目录不外泄 | `curl -s -o /dev/null -w '%{http_code}' http://<host>/uploads/x` | `404` | 同上 |
| 13 | SSE 鉴权 | `curl -s -o /dev/null -w '%{http_code}' http://<host>/events` | `401` | 同上 |
| 14 | 布局无溢出 | 浏览器 390 / 900 / 1440 三视口 | `scrollWidth == clientWidth` | 三档均相等，越界元素 0 |

第 10–13 项依赖真实反代与容器网络，本地无 Docker，改由静态配置断言覆盖（见 `test_deploy_config.py`），部署后需按 README 首启检查表复核一次。

---

## 三、验证结果

测试矩阵：

| 环境 | 后端 | 前端 |
|---|---|---|
| Windows / Python 3.13 | 366 passed | vitest 85、node --test 54、build ok |
| Windows / Python 3.12.13（干净 venv，按 requirements-dev 全新安装） | 依赖安装验证通过；修复前 350 passed，修复后的 354 由 CI 在同一版本复核 | 同左 |
| GitHub Actions / Python 3.12 + Node 22 | 366 passed | 85 passed + 54 passed + build + lighthouse |

依赖版本（本基线）：

- 后端运行时：fastapi 0.162.0、uvicorn 0.54.0、sqlalchemy 2.1.6、pydantic 2.14.2、pydantic-settings 2.16.2、alembic 1.20.1、redis 8.1.0
- 后端开发：pytest 9.2.0、pytest-asyncio 1.4.1.post1、hypothesis 6.170.14、sphinx 9.1.1
- 前端：vite 8.3.6、vitest 5.1.0、jsdom 31.0.0、@playwright/test 1.65.0、@sentry/browser 11.11.0

已知告警：FastAPI 0.162 对 `@app.on_event` 发出弃用警告（两个 startup 钩子功能正常），迁移到 lifespan 记为后续技术债。

**未覆盖的验证**：

- 像素级视觉回归（当前用三视口截图人工核对，无基线工具）
- 微信内置浏览器的真机录音与权限行为（代码有环境检测与引导，未在真机验证）
- 真实方言样本的 ASR 识别率（取决于生产密钥，见风险 1）
- 并发压测与多副本行为（试点规模下未做）

---

## 四、剩余风险

| # | 风险 | 影响 | 责任方 | 闭合条件 |
|---|---|---|---|---|
| 1 | ASR 生产密钥未配置（火山 `asr_volc_*`、百炼 `bailian_api_key`） | Vosk 拒识后方言用户直接 503 | 部署方 | 控制台开通三项凭据，用真实方言样本跑一轮验收 |
| 2 | 试点数据为零 | 无法验证临床价值，P2 优先级无据可依 | 产品 | 试点 2–4 周后产出首份漏斗报告（fill_rate / submit_rate / 误报率 / 告警解决率） |
| 3 | 实时通道为进程内实现 | 多 worker 部署时 SSE 断流 | 工程 | 扩容前接入 Redis pub/sub（广播层已具备）+ 粘性会话或改单 worker |
| 4 | KMS file 模式密钥需人工备份 | wrap key 丢失 = 全部密文不可解 | 运维 | 首启后立即 `GET /backup/kms-wrap-key` 导出并异地保存 |
| 5 | 备份与数据同机 | 整机故障时数据与备份同时丢失 | 运维 | 把 `cg_pg_backups` 卷同步到对象存储 |
| 6 | 无像素级视觉回归基线 | UI 改动可能引入未被发现的视觉偏差 | 前端 | 引入 Percy / Chromatic 或 Playwright 截图基线 |
| 7 | `on_event` 已弃用 | 未来 FastAPI 版本移除后启动钩子失效 | 工程 | 迁移到 lifespan（两个钩子，改动集中） |
| 8 | 自助注册不含管理员 | 新环境无人可开管理员 | 部署方 | 首启按 README 执行一次 `UPDATE users SET role='admin'` |
| 9 | 微信内录音依赖用户手动切换浏览器 | 落地页到录音的转化可能损失 | 产品 | 试点期间统计微信内来源占比，据此决定是否做小程序形态 |
| 10 | 多家属 / 多老人未支持（1:1 绑定） | 多子女家庭需共享账号 | 产品 | 试点后按家庭形态数据评估 |

风险 1、4、5、8 属于部署动作，代码侧已就绪但无法在本仓库内闭合；2、9、10 需要真实用户数据才能排期。

---

## 五、部署与首启检查

部署步骤见 README「容器化部署」，必填变量见 `.env.example`。首启后按 README 的首启检查表逐项执行：健康检查、安全响应头、`/metrics` 与 `/uploads` 返回 404、`/events` 返回 401、迁移版本与 `alembic heads` 一致。

管理员开通：

```bash
docker compose exec postgres psql -U cg_user -d cognitive_garden \
  -c "UPDATE users SET role='admin' WHERE username='<用户名>';"
```

## 六、回滚

应用回滚：`git checkout <上一稳定 tag>` 后重建镜像。数据库回滚需先确认迁移可逆（`alembic downgrade -1`）；本仓库迁移以新增列/表为主，破坏性变更需先恢复 pg 备份再切回旧镜像。镜像回滚不会自动回滚 schema，升级前需确认最近一次 `pg-backup` 成功。

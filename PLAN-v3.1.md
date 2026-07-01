# Cognitive Garden V3.1 全面打磨计划

## 目标
1. 将 LLM 深度集成做成**可选项**（Feature Flag 控制），零成本开启/关闭
2. 彻底设计并实现**三端通信传输架构**（老人端↔家属端↔医生端）
3. 完成 PWA 离线安装、语音波形、字体无级调节等体验打磨
4. 扩展语音情感分析、记忆训练小游戏等差异化功能
5. 3D 记忆星云可视化（可选，家属端付费体验）

---

## 核心模块：三端通信传输架构（V3.1 重点）

### 架构设计

```
┌─────────────────────────────────────────────────────────────┐
│                      通信架构总览                             │
├─────────────────────────────────────────────────────────────┤
│  老人端 (Elderly)                                            │
│    ├─→ 生产者：会话、量表、语音记录                           │
│    ├─→ 消费者：家属语音留言、医生建议、关怀提醒                │
│    └─→ 离线：IndexedDB 队列，恢复后自动同步                    │
│                          │                                   │
│  服务器 (FastAPI + SQLite)                                   │
│    ├─ SSE 推送：新数据单向广播到家属端/医生端                  │
│    ├─ WebSocket：双向即时通信（留言、建议、实时协同）          │
│    ├─ REST API：数据查询、历史拉取、离线同步                   │
│    └─ 版本向量：每台设备独立版本号，冲突时自动合并               │
│                          │                                   │
│  家属端 (Family)                                             │
│    ├─→ 消费者：老人数据实时推送、历史查询                       │
│    ├─→ 生产者：语音留言、评论、关怀标记                        │
│    └─→ 离线：缓存老人最近 30 天数据，家属操作本地队列            │
│                          │                                   │
│  医生端 (Doctor)                                             │
│    ├─→ 消费者：患者数据、趋势分析、异常报告                     │
│    ├─→ 生产者：诊断建议、处方建议、随访计划                     │
│    └─→ 离线：缓存患者数据，支持离线查看                         │
└─────────────────────────────────────────────────────────────┘
```

### 数据流设计

#### 1. 老人端 → 家属端/医生端（实时推送）
- **触发**：老人提交会话/量表
- **链路**：`session.py` → `broadcast_event({type: 'new_session', elderly_id, ...})` → SSE 队列 → 家属端/医生端接收
- **权限过滤**：家属端只接收绑定老人的事件；医生端只接收授权患者的事件

#### 2. 家属端 → 老人端（即时留言）
- **触发**：家属发送语音留言/文字关怀
- **链路**：`voice_message.py` → 写入数据库 → `broadcast_event({type: 'new_voice_message', receiver_id})` → 老人端接收
- **通知**：老人端收到后播放提示音（可选）+ 显示未读徽章

#### 3. 医生端 → 老人端/家属端（诊断建议）
- **触发**：医生提交诊断建议
- **链路**：`doctor_advice.py` → 写入数据库 → 广播到关联老人和家属
- **格式**：结构化建议（`{category, content, priority, follow_up_date}`）

#### 4. 离线同步（冲突解决）
- **场景**：老人端离线时提交会话，恢复后同步到服务器；家属端离线时查看缓存数据
- **版本向量**：每个设备维护 `device_id + vector_clock`（类似 DynamoDB 的向量时钟）
- **冲突规则**：
  - 会话/量表：以服务器时间为准（LWW - Last Write Wins）
  - 语音留言：独立队列，双向追加，不冲突
  - 诊断建议：医生端始终优先
  - 节点编辑：用户主动操作时，以该用户的本地版本为准

### 权限模型

```python
# 数据查询权限过滤（所有数据读取 API 必须调用）
def filter_by_permission(query, current_user, db):
    if current_user.role == 'elderly':
        return query.filter(data.user_id == current_user.id)
    elif current_user.role == 'family':
        linked_elderly = get_linked_elderly_ids(current_user.id, db)
        return query.filter(data.user_id.in_(linked_elderly))
    elif current_user.role == 'doctor':
        authorized_patients = get_authorized_patient_ids(current_user.id, db)
        return query.filter(data.user_id.in_(authorized_patients))
```

### 端到端加密（E2EE）
- 三端通信的敏感数据（语音留言、诊断建议）使用 Signal Protocol 风格的 Double Ratchet
- 或简化：使用用户已有的 `master_key` 派生通信密钥，AES-256-GCM 加密消息内容
- 服务器只存储密文，无法读取内容

---

## 模块拆分

### 模块 A：前端体验打磨（PWA + 语音波形 + 字体调节）
- **PWA 完整化**：`manifest.json` icons/shortcuts/screenshots，`beforeinstallprompt` 自定义安装弹窗
- **语音波形**：`audio-visualizer.js` Canvas 实时波形，录音状态指示（红色圆点+"正在聆听"）
- **字体无级调节**：滑块 12px-24px，持久化 `localStorage`，图标/按钮同步缩放
- **离线横幅**：`offline-banner.js` 网络状态检测，顶部显示"离线模式，数据将在恢复后同步"

### 模块 B：语音情感分析 + 记忆训练小游戏
- **情感分析**：`services/emotion_analyzer.py` jieba 提取情感词典（积极/消极词库），返回情绪分数
- **情绪趋势**：`src/ui/charts/emotion-trend.js` 30 日情绪曲线
- **消极预警**：连续 3 天消极情绪，主动推送关怀建议给家属
- **记忆挑战**：`src/games/memory-challenge.js` 系统抽取历史节点，让用户回忆日期/人物
- **数字连线**：`src/games/number-link.js` 基于真实记忆节点的认知训练游戏
- **训练分数**：游戏结果纳入 `metrics.training_score`，更新健康趋势

### 模块 C：LLM 可选项集成（后端+前端）
- **Feature Flag**：`features.js` 添加 `llm_enabled`，默认 false
- **配置**：`backend/.env` 添加 `LLM_PROVIDER`, `LLM_API_KEY`, `LLM_MODEL`，空时 LLM 自动禁用
- **后端接口**：`routers/llm.py` 
  - `POST /llm/summarize` — 多天长记忆总结（narrative 列表 → 散文）
  - `POST /llm/emotion` — LLM 情感分析（比规则更准确）
  - `POST /llm/qa` — 智能问答（"上周三我做了什么" → 检索图谱回答）
- **前端开关**：设置页面添加"启用 AI 助手"开关，需要用户主动开启并确认隐私协议
- **数据隐私**：默认使用本地推理（Ollama 兼容），远程 LLM 需用户明确授权

### 模块 D：三端通信架构（核心）
- **数据模型**：`DoctorPatient` 表（授权关系），`DeviceSync` 表（设备版本向量）
- **权限中间件**：`middleware/permission.py` 统一数据过滤
- **WebSocket 升级**：`routers/websocket.py` 使用 `fastapi-websocket` 或原生 `websockets` 库
  - 连接时验证 token
  - 按 `user_id` 和 `role` 路由消息
  - 支持双向：家属发送 → 老人接收；医生发送 → 老人和家属接收
- **离线同步协议**：`services/sync_protocol.py`
  - `pull_changes(device_id, last_vector_clock)` → 返回服务器端变更
  - `push_changes(device_id, changes)` → 服务器合并，返回冲突结果
  - `resolve_conflict(local, server, rule)` → LWW 或自定义规则
- **版本向量**：每个 IndexedDB 记录带 `vc: {device_id: counter}`，服务器维护全局版本向量
- **端到端加密**：`services/e2ee.py` 使用 `master_key` 派生通信密钥，AES-256-GCM 加密消息

### 模块 E：3D 记忆星云（可视化升级）
- **WebGL 渲染**：`src/3d/memory-nebula.js` 使用 Three.js（或自研轻量 WebGL）
- **星云布局**：节点按时间分布在 Z 轴，近期记忆在前（明亮），远期在后（暗淡）
- **交互**：鼠标/触摸旋转、缩放、飞行漫游；点击节点显示叙事片段
- **模式切换**：2D 力导向 ↔ 3D 星云，用户自选
- **家属端体验**：3D 星云作为沉浸式浏览模式，家属端可自由漫游老人的记忆空间

---

## 验证清单
- [ ] 前端构建通过 (`npm run build`)：无 chunk 循环依赖，graph 按需加载正常
- [ ] 后端测试通过 (`pytest`)：139+ 测试，新增测试覆盖三端通信、LLM、情感分析
- [ ] WebSocket 测试：`pytest tests/test_websocket.py` 通过
- [ ] WebBridge 实机截图：三端视图分别验证（老人端极简、家属端看板、医生端数据）
- [ ] 离线同步测试：`e2e/offline.spec.js` 断网→提交→恢复→同步验证
- [ ] 桌面同步 (`C:\Users\wanzh\Desktop\cognitive-garden`)

## 文件总览
```
frontend/src/
  pwa/
    install-prompt.js     — PWA 安装弹窗
  audio/
    visualizer.js         — 语音波形可视化
  ui/
    offline-banner.js     — 离线状态横幅
    emotion-badge.js      — 情绪标签组件
  games/
    memory-challenge.js   — 记忆挑战游戏
    number-link.js        — 数字连线游戏
  3d/
    memory-nebula.js      — 3D 记忆星云
  settings/
    llm-toggle.js         — LLM 启用开关

backend/app/
  models.py               — 新增 DoctorPatient, DeviceSync
  middleware/
    permission.py         — 三端权限过滤中间件
  routers/
    websocket.py          — WebSocket 双向通信
    llm.py                — LLM 可选项接口
    doctor_advice.py      — 医生诊断建议
  services/
    emotion_analyzer.py   — 情感分析（规则 + LLM 可选）
    sync_protocol.py      — 离线同步协议（版本向量 + 冲突解决）
    e2ee.py               — 端到端加密通信
  alembic/versions/       — 新增 0010, 0011 迁移
```

# 织忆·认知花园 改进路线图

> 从单文件原型到可产品化的认知评估系统  
> 版本：2026-07-10  
> 预计总周期：16–20 周  

---

## 一、项目总览

### 1.1 当前状态

| 维度 | 现状 | 目标状态 |
|------|------|----------|
| 架构 | 单文件 1864 行 HTML | ES 模块 + 测试 + 后端 API |
| 健康度公式 | 7 指标主观加权线性组合 | 三层模型（结构×内容×趋势），可配置权重 |
| NLP | 手写 FMM，词库 ~60 词 | 500+ 词库 + LLM 开放域异常检测 |
| 持久化 | localStorage | 后端 PostgreSQL + 用户体系 |
| 临床验证 | 无 | 横断面相关性研究（100 人） |
| 形式化保证 | 无 | Lean4 验证健康度公理 |

### 1.2 核心原则

1. **拒绝打补丁**：每个改动必须有可验证的验收标准，不凭感觉调参
2. **形式化先行**：关键算法（健康度、异常检测）先写 Lean4 规范，再写实现
3. **证据驱动**：健康度公式权重必须有文献支撑或临床数据支撑
4. **模块边界清晰**：前端只管渲染和交互，NLP 和指标计算交给后端

---

## 二、第一阶段：前端工程化 + 健康度重构（Week 1–2）

### 2.1 目标
将单文件 HTML 拆分为可测试的 ES 模块，重构健康度公式为三层模型，建立单元测试基线。

### 2.2 任务清单

#### W1-D1–2：模块拆分

```
src/
├── index.html          # 入口，只引入 main.js
├── main.js             # 初始化、路由、全局状态管理
├── state.js            # 状态定义、持久化接口（localStorage 先保留）
├── nlp/
│   ├── lexicon.js      # 词库定义（从当前 LEXICON 迁移）
│   ├── fmm.js          # FMM 分词器
│   ├── entity.js       # 实体提取 + 优先级消解
│   └── anomaly.js      # 语义异常检测规则
├── graph/
│   ├── model.js        # Node / Edge / Graph 类型定义
│   ├── metrics.js      # computeMetrics + computeHealth
│   ├── layout.js       # 力导向布局（从 tickLayout 迁移）
│   └── similarity.js   # computeBaselineSimilarity
├── ui/
│   ├── render.js       # renderCanvas, renderTimeline, renderRightPanel
│   ├── components.js   # el() 辅助函数、各类组件
│   ├── interactions.js # 拖拽、点击、缩放、键盘事件
│   └── views.js        # 三端视图渲染逻辑
├── utils.js            # 通用工具函数
└── tests/
    ├── fmm.test.js
    ├── metrics.test.js
    ├── anomaly.test.js
    └── health.test.js
```

**验收标准**：
- [ ] `npm run test` 通过所有测试用例
- [ ] `npm run build` 输出单个 bundle.js，功能与原文件一致
- [ ] 与原文件截图对比，像素级无差异（通过 WebBridge 截图 diff）

#### W1-D3–5：健康度公式重构

**三层模型实现**：

```javascript
// metrics.js
export function computeStructuralScore(m) {
  // 正交维度：连通性、局部凝聚、全局整合
  return m.connectivity * 0.35 + 
         m.clustering * 0.35 + 
         m.globalEff * 0.30;
}

export function computeContentualScore(m, anomalies, anonRatio) {
  var anomalyPenalty = Math.pow(0.85, anomalies.length);
  var anonPenalty = Math.max(0, 1 - anonRatio * 3);
  // 关系覆盖度：情感/时间/空间/关联是否都有
  var typeCounts = {};
  state.edges.forEach(e => typeCounts[e.type] = (typeCounts[e.type] || 0) + 1);
  var coverage = Math.min(1, Object.keys(typeCounts).length / 4);
  return anomalyPenalty * anonPenalty * (0.6 + 0.4 * coverage);
}

export function computeTrendScore(current, baseline, history) {
  if (!baseline) return 1.0;
  var drift = Math.abs(current.connectivity - baseline.connectivity) +
              Math.abs(current.clustering - baseline.clustering) +
              Math.abs(current.globalEff - baseline.globalEff);
  // Sigmoid: 小漂移→接近1, 大漂移→接近0
  var driftScore = 1 / (1 + Math.exp(5 * (drift - 0.3)));
  
  if (history && history.length >= 3) {
    var last3 = history.slice(-3);
    var declining = last3[0] < last3[1] && last3[1] < last3[2];
    if (declining) return driftScore * 0.7;
  }
  return driftScore;
}

export function computeHealth(m, anomalies, baseline, history) {
  if (!m) return 0;
  var anonRatio = m.nodeCount > 0 ? m.anonCount / m.nodeCount : 0;
  var s = computeStructuralScore(m);
  var c = computeContentualScore(m, anomalies, anonRatio);
  var t = computeTrendScore(m, baseline, history);
  return Math.round(100 * s * c * t);
}
```

**验收标准**：
- [ ] 单元测试覆盖：正常认知场景（D1）health ≥ 80；异常场景（D7）health < 70
- [ ] 匿名节点比例 33% 时 health 下降 ≥ 15%
- [ ] 连续 3 天下降趋势触发 trend 惩罚，health ×0.7
- [ ] Lean4 形式化验证：`health ∈ [0, 100]`，异常增加 → health 单调下降

#### W1-D6–W2-D2：单元测试基线

```javascript
// tests/health.test.js
import { computeHealth, computeStructuralScore } from '../graph/metrics';

describe('health formula', () => {
  test('normal cognition: D1 baseline', () => {
    const m = { connectivity: 1, clustering: 0.7, globalEff: 0.85, 
                nodeCount: 8, edgeCount: 10, anonCount: 0 };
    const h = computeHealth(m, [], null, []);
    expect(h).toBeGreaterThanOrEqual(80);
    expect(h).toBeLessThanOrEqual(100);
  });

  test('MCI-like: fragmented narrative', () => {
    const m = { connectivity: 0.4, clustering: 0.1, globalEff: 0.3,
                nodeCount: 6, edgeCount: 2, anonCount: 2 };
    const anomalies = [
      { event: '打太极', severity: 'danger' },
      { event: '做饭', severity: 'warn' }
    ];
    const h = computeHealth(m, anomalies, null, []);
    expect(h).toBeLessThan(60);
  });

  test('anonymity penalty', () => {
    const m = { connectivity: 1, clustering: 0.7, globalEff: 0.85,
                nodeCount: 6, edgeCount: 10, anonCount: 2 };
    const h = computeHealth(m, [], null, []);
    // 匿名比例 33% → anonPenalty = 0 → health = 0
    expect(h).toBeLessThanOrEqual(5);
  });

  test('monotonicity: more anomalies → lower health', () => {
    const m = { connectivity: 1, clustering: 0.6, globalEff: 0.8,
                nodeCount: 8, edgeCount: 10, anonCount: 0 };
    const h1 = computeHealth(m, [{ severity: 'warn' }], null, []);
    const h2 = computeHealth(m, [{ severity: 'warn' }, { severity: 'warn' }], null, []);
    expect(h2).toBeLessThan(h1);
  });
});
```

**验收标准**：
- [ ] 测试覆盖率 ≥ 80%（metrics + nlp + anomaly 模块）
- [ ] CI 通过（GitHub Actions）

#### W2-D3–5：Lean4 形式化验证层

```lean4
-- CognitiveGarden/Health.lean

def StructuralScore (m : Metrics) : ℝ :=
  m.connectivity * 0.35 + m.clustering * 0.35 + m.globalEff * 0.30

def ContentualScore (m : Metrics) (anomalies : List Anomaly) (anonRatio : ℝ) : ℝ :=
  let anomalyPenalty := (0.85 : ℝ) ^ anomalies.length
  let anonPenalty := max 0 (1 - anonRatio * 3)
  anomalyPenalty * anonPenalty * (0.6 + 0.4 * min 1 (relationCoverage m / 4))

def TrendScore (current : Metrics) (baseline : Option Metrics) (history : List ℝ) : ℝ :=
  match baseline with
  | none => 1.0
  | some b =>
    let drift := abs (current.connectivity - b.connectivity) +
                 abs (current.clustering - b.clustering) +
                 abs (current.globalEff - b.globalEff)
    let driftScore := 1 / (1 + exp (5 * (drift - 0.3)))
    if history.length ≥ 3 && isDeclining history then driftScore * 0.7 else driftScore

def computeHealth (m : Metrics) (anomalies : List Anomaly) 
    (baseline : Option Metrics) (history : List ℝ) : ℝ :=
  let s := StructuralScore m
  let c := ContentualScore m anomalies (anonRatio m)
  let t := TrendScore m baseline history
  round (100 * s * c * t)

-- 定理 1：健康度有界
theorem health_bounded (m : Metrics) (anomalies : List Anomaly)
    (baseline : Option Metrics) (history : List ℝ) :
    0 ≤ computeHealth m anomalies baseline history ∧ 
    computeHealth m anomalies baseline history ≤ 100 := by
  unfold computeHealth
  have h1 : 0 ≤ StructuralScore m := sorry -- 需证明每个指标 ∈ [0,1]
  have h2 : 0 ≤ ContentualScore m anomalies (anonRatio m) := sorry
  have h3 : 0 ≤ TrendScore m baseline history := sorry
  have h4 : StructuralScore m ≤ 1 := sorry
  have h5 : ContentualScore m anomalies (anonRatio m) ≤ 1 := sorry
  have h6 : TrendScore m baseline history ≤ 1 := sorry
  simp [round, mul_nonneg, h1, h2, h3, h4, h5, h6]
  linarith

-- 定理 2：异常增加 → 健康度不增
theorem health_anomaly_monotonicity (m : Metrics) 
    (a1 a2 : List Anomaly) (baseline : Option Metrics) (history : List ℝ) :
    a1.length < a2.length → 
    (∀ a ∈ a2, a.severity ∈ {"warn", "danger"}) →
    computeHealth m a1 baseline history ≥ computeHealth m a2 baseline history := by
  sorry
```

**验收标准**：
- [ ] `lake build` 通过
- [ ] 至少完成 `health_bounded` 和 `health_anomaly_monotonicity` 两个定理的证明
- [ ] 与 JS 实现做 property-based testing 对比（QuickCheck 风格随机数据验证一致性）

### 2.3 第一阶段交付物

1. `frontend/` 目录，模块化 ES 代码
2. `vitest` 测试套件，覆盖率 ≥ 80%
3. `CognitiveGarden/` Lean4 项目，2 个定理已证明
4. 技术文档：`docs/architecture.md`（模块边界、数据流）

---

## 三、第二阶段：后端最小可行系统 + NLP 升级（Week 3–8）

### 3.1 目标
搭建 FastAPI 后端，实现用户体系、会话持久化、LLM 语义异常检测，前端改为 API 调用。

### 3.2 任务清单

#### W3-D1–3：后端脚手架

```python
# backend/main.py
from fastapi import FastAPI
from routers import auth, session, narrative, graph, baseline

app = FastAPI(title="Cognitive Garden API")
app.include_router(auth.router, prefix="/auth")
app.include_router(session.router, prefix="/session")
app.include_router(narrative.router, prefix="/narrative")
app.include_router(graph.router, prefix="/graph")
app.include_router(baseline.router, prefix="/baseline")
```

**技术栈**：
- FastAPI + SQLAlchemy + PostgreSQL
- JWT 认证（python-jose）
- Alembic 数据库迁移

**数据库 Schema**（见第二阶段详细设计）

**验收标准**：
- [ ] `docker-compose up` 一键启动后端 + 数据库
- [ ] `/health` 端点返回 200
- [ ] `pytest` 通过 API 集成测试

#### W3-D4–W4-D3：用户体系 + 会话持久化

**API 设计**：

```yaml
POST /auth/register
  body: { phone: str, role: elderly|family|doctor, password: str }
  response: { user_id: uuid, token: str }

POST /auth/login
  body: { phone: str, password: str }
  response: { token: str }

POST /session
  headers: { Authorization: Bearer <token> }
  body: { day_number: int, narrative: str }
  response: { session_id: uuid, graph: Graph, metrics: Metrics, health: int, anomalies: [Anomaly] }

GET /session/{user_id}
  response: { sessions: [Session], trend: [DailyHealth] }

POST /baseline
  body: { session_id: uuid }
  response: { baseline_id: uuid }
```

**验收标准**：
- [ ] 注册 → 登录 → 创建会话 → 查询历史，完整链路 Postman 测试通过
- [ ] 会话数据跨设备同步（手机/平板/电脑）
- [ ] 并发测试：50 用户同时创建会话，无数据竞争

#### W4-D4–W6-D2：NLP 升级

**阶段 A：词库扩充**

从 60 词扩充到 500+ 词，结构化存储：

```json
{
  "person": {
    "family": ["老伴", "儿子", "女儿", "孙子", "孙女", "女婿", "儿媳", "侄子", "侄女"],
    "medical": ["医生", "护士", "护工", "康复师", "社工"],
    "social": ["老张", "老李", "邻居", "老同事", "棋友", "舞伴"]
  },
  "place": {
    "home": ["客厅", "卧室", "厨房", "卫生间", "阳台"],
    "community": ["公园", "广场", "活动中心", "食堂", "便利店", "药房"],
    "medical": ["医院", "门诊", "病房", "康复中心", "体检中心"]
  },
  "event": {
    "daily": ["起床", "吃饭", "散步", "看电视", "睡觉", "洗澡"],
    "social": ["下棋", "聊天", "跳舞", "唱歌", "聚会", "拜访"],
    "medical": ["吃药", "量血压", "测血糖", "打针", "复健", "看病"]
  },
  "item": {
    "medical": ["降压药", "血糖仪", "拐杖", "轮椅", "助听器", "老花镜"],
    "daily": ["手机", "遥控器", "报纸", "象棋", "扇子", "茶杯"]
  }
}
```

**阶段 B：LLM 开放域异常检测**

```python
# backend/nlp/anomaly_llm.py
from openai import OpenAI

client = OpenAI()

ANOMALY_PROMPT = """你是一个认知评估助手，专门分析老年人日常叙述中的语义异常。

请分析以下叙述，检测是否存在人物、活动、地点之间的不合理匹配。

规则：
1. 活动应与合理地点匹配（如"打太极"通常在公园、广场、院子）
2. 人物应与活动匹配（如"孙子"通常不会"下棋"但可能"玩积木"）
3. 物品应与活动匹配（如"拐杖"通常不会出现在"游泳"场景）
4. 时间顺序应合理（如"先吃药后量血压"合理，"先睡觉后起床"不合理）

输出严格的 JSON：
{
  "anomalies": [
    {
      "type": "event-place-mismatch",
      "event": "打太极",
      "actual_place": "医院",
      "expected_places": ["公园", "广场", "院子"],
      "severity": "danger",
      "explanation": "在医院打太极不符合常理，可能暗示时空定向障碍"
    }
  ]
}

文本：{text}
"""

def detect_anomalies_llm(text: str) -> list[dict]:
    response = client.chat.completions.create(
        model="gpt-4o-mini",  # 成本可控
        messages=[
            {"role": "system", "content": ANOMALY_PROMPT},
            {"role": "user", "content": text}
        ],
        response_format={"type": "json_object"},
        temperature=0.1,  # 确定性输出
    )
    return json.loads(response.choices[0].message.content)["anomalies"]
```

**成本估算**：
- GPT-4o-mini：$0.15/1M input tokens，$0.60/1M output tokens
- 平均每次叙述 200 字 ≈ 300 tokens
- 100 用户 × 7 天 = 700 次调用 ≈ $0.15（可忽略）

**验收标准**：
- [ ] LLM 检测覆盖当前规则表未覆盖的案例（如「在厨房游泳」）
- [ ] 与当前规则引擎结果一致率 ≥ 95%（回归测试）
- [ ] 延迟 < 2s（P95）

#### W6-D3–W7-D3：前端对接 API

- 前端删除所有 NLP 逻辑（`fmm.js`, `entity.js`, `anomaly.js` 保留本地降级模式）
- 语音输入后调用 `POST /session`，后端返回解析结果
- 渲染改为纯数据驱动（接收 JSON 直接渲染）

**降级策略**：
- 后端不可用时，前端自动切换本地 FMM 模式
- 用户无感知

**验收标准**：
- [ ] 网络正常时：所有 NLP 走后端，前端无本地计算
- [ ] 网络断开时：自动降级本地 FMM，功能可用
- [ ] 切换延迟 < 500ms

#### W7-D4–W8-D5：测试 + 部署

- 端到端测试：Playwright 自动化测试（覆盖注册 → 叙述 → 查看趋势）
- 部署：Docker + Nginx 反向代理 + Let's Encrypt SSL
- 监控：Prometheus + Grafana（API 延迟、错误率、LLM 调用成本）

**验收标准**：
- [ ] 端到端测试 10 个场景全部通过
- [ ] 生产环境部署，可通过 HTTPS 访问
- [ ] 监控面板可查看实时健康度

### 3.3 第二阶段交付物

1. `backend/` FastAPI 项目，完整 API 文档（OpenAPI/Swagger）
2. PostgreSQL 数据库，用户数据 + 会话数据 + 基线数据
3. LLM 异常检测模块，支持开放域推理
4. 部署脚本 + Docker Compose 配置
5. 端到端测试套件（Playwright）

---

## 四、第三阶段：临床验证启动（Week 9–16）

### 4.1 目标
与医院/社区卫生服务中心合作，启动横断面相关性研究，收集第一批真实数据。

### 4.2 任务清单

#### W9-D1–W10-D3：伦理审批 + 合作建立

- 联系 1–2 家医院老年科或社区卫生服务中心
- 提交伦理审查申请（IRB）
- 确定研究方案：
  - 入组标准：≥60 岁，能独立日常交流，签署知情同意
  - 分组：正常认知组（MoCA ≥ 26）vs MCI 组（MoCA 18–25）
  - 样本量：每组 50 人，共 100 人
  - 观察期：连续 7 天，每天使用「织忆」1 次
  - 同期评估：MMSE、MoCA、ADAS-Cog、CDR

**验收标准**：
- [ ] 伦理批件获得
- [ ] 合作协议签署
- [ ] 研究方案通过医院学术委员会审查

#### W10-D4–W13-D5：数据采集

- 招募志愿者，培训使用「织织」
- 每天推送提醒（短信/微信）
- 后台监控数据质量：
  - 叙述时长 < 30 秒 → 标记为「低质量」
  - 连续 2 天未使用 → 电话随访

**数据质量控制**：
- 自动检测：语音转文字后，如果字数 < 20，提示「请再多说一点」
- 人工复核：10% 样本由研究人员听录音确认转写准确性

**验收标准**：
- [ ] 完成 100 人 × 7 天 = 700 条有效数据
- [ ] 数据完整率 ≥ 90%（缺失 < 10%）
- [ ] 语音转文字准确率 ≥ 85%（人工抽样）

#### W14-D1–W15-D3：统计分析

**分析目标 1：相关性验证**
- 计算 Pearson 相关系数：织忆健康度 vs MoCA 分数
- 预期：r ≥ 0.6，p < 0.001
- 如果 r < 0.4：健康度公式需要重新调整权重

**分析目标 2：判别能力**
- 训练逻辑回归分类器：正常 vs MCI
- 输入：7 天的网络特征（平均连通度、平均聚类系数、匿名比例、异常次数）
- 输出：ROC-AUC，预期 ≥ 0.75

**分析目标 3：网络特征差异**
- 正常组 vs MCI 组的网络拓扑对比：
  - 匿名节点比例：MCI 组是否显著更高？
  - 语义异常次数：MCI 组是否显著更多？
  - 网络密度变化：7 天内 MCI 组是否波动更大？

**验收标准**：
- [ ] 健康度与 MoCA 相关性 r ≥ 0.5（或明确记录失败原因）
- [ ] ROC-AUC ≥ 0.70（或可解释的低 AUC 原因）
- [ ] 统计报告通过统计学专家审核

#### W15-D4–W16-D5：论文 + 迭代

- 撰写论文：「基于日常叙事网络分析的认知功能评估：一项横断面研究」
- 投稿：JAD（Journal of Alzheimer's Disease）或中文核心期刊
- 根据分析结果迭代健康度公式：
  - 如果匿名比例是 MCI 的强预测因子 → 增加权重
  - 如果 smallWorld 系数无区分度 → 移除或替换

**验收标准**：
- [ ] 论文初稿完成
- [ ] 健康度公式根据临床数据更新至少 1 轮
- [ ] 新公式在测试集上表现优于旧公式

### 4.3 第三阶段交付物

1. 伦理批件 + 研究方案
2. 700 条匿名化临床数据集（脱敏后）
3. 统计分析报告（含相关性、判别能力、特征差异）
4. 论文初稿
5. 经过临床数据校准的健康度公式 v2.0

---

## 五、风险清单与应急预案

| 风险 | 可能性 | 影响 | 应急预案 |
|------|--------|------|----------|
| 伦理审批延迟 | 高 | 第三阶段推迟 | 同时联系 2–3 家机构，哪家先批先启动 |
| LLM API 成本超支 | 中 | 运营亏损 | 设置每日调用上限，超限切回规则引擎 |
| 用户留存率低 | 高 | 数据质量差 | 增加家属端提醒功能，设计积分/徽章激励 |
| 健康度与 MoCA 不相关 | 中 | 核心假设失败 | 提前定义 pivot 条件：如果 r < 0.3，转向「认知训练工具」而非「评估工具」 |
| 语音识别方言覆盖差 | 中 | 南方老人无法使用 | 集成方言模型（科大讯飞支持 23 种方言） |
| 形式化验证进度慢 | 低 | 学术卖点缺失 | 将 Lean 层设为可选模块，不阻塞主流程 |

---

## 六、里程碑与验收标准总表

| 里程碑 | 时间 | 关键验收标准 | 不通过怎么办 |
|--------|------|------------|------------|
| M1：前端重构完成 | W2 结束 | 模块化 + 测试覆盖率 ≥ 80% + Lean 2 定理 | 延迟 1 周，砍掉 Lean 层，先保证功能 |
| M2：后端 MVP | W4 结束 | 完整 API + 数据库 + 部署 | 降级为 SQLite 单机版，推迟 PostgreSQL |
| M3：NLP 升级 | W6 结束 | LLM 异常检测覆盖 ≥ 95% 回归案例 | 保留规则引擎为主，LLM 为辅助 |
| M4：临床数据 | W13 结束 | 700 条有效数据 | 降低样本量到 500 条，或延长 2 周 |
| M5：统计验证 | W15 结束 | r ≥ 0.5 或明确 pivot 方向 | 如果 r < 0.3，产品定位从「评估工具」改为「认知训练工具」 |
| M6：论文投稿 | W16 结束 | 论文初稿完成 | 先写成技术报告， conference poster 投稿 |

---

## 七、资源需求

### 7.1 人员

| 角色 | 时间投入 | 职责 |
|------|----------|------|
| 前端工程师（你） | 全职 W1–8 | 模块拆分、测试、Lean 层、后端对接 |
| 后端工程师（1 人） | 全职 W3–8 | FastAPI、数据库、部署 |
| 医学顾问（兼职） | W9–16 | 伦理申请、研究方案设计、统计审核 |
| 志愿者协调员 | W10–13 | 招募、培训、数据质量监控 |

### 7.2 预算（估算）

| 项目 | 金额 | 说明 |
|------|------|------|
| 云服务器 | ¥3,000/年 | 阿里云 ECS 2核4G |
| 域名 + SSL | ¥500/年 | |
| LLM API | ¥2,000/年 | GPT-4o-mini，按 1000 用户/年估算 |
| 伦理审查费 | ¥5,000 | 医院伦理委员会 |
| 志愿者交通补贴 | ¥10,000 | 100 人 × 100 元 |
| 论文版面费 | ¥8,000 | 中文核心或 OA 期刊 |
| **总计** | **¥28,500** | 不含人力成本 |

---

## 八、下一步行动（本周即可开始）

1. **Day 1**：创建 `frontend/` 目录，初始化 `npm init` + `vite` + `vitest`
2. **Day 2**：将 `metrics.js` 和 `health.test.js` 拆出，跑通第一个测试
3. **Day 3**：实现三层健康度模型，替换旧公式
4. **Day 4**：创建 `CognitiveGarden/` Lean4 项目，写 `Health.lean` 骨架
5. **Day 5**：完成 `health_bounded` 定理证明

---

## 八、下一步行动（本周即可开始）

1. **Day 1**：创建 `frontend/` 目录，初始化 `npm init` + `vite` + `vitest`
2. **Day 2**：将 `metrics.js` 和 `health.test.js` 拆出，跑通第一个测试
3. **Day 3**：实现三层健康度模型，替换旧公式
4. **Day 4**：创建 `CognitiveGarden/` Lean4 项目，写 `Health.lean` 骨架
5. **Day 5**：完成 `health_bounded` 定理证明

---

## 附录 A：语音识别集成详解

语音识别是「织忆」从原型到产品的关键门槛。当前前端只有一个文本输入框，用户必须手动打字。对于老年人（尤其是手部灵活性下降或视力不佳者），**语音输入是核心交互方式**，不是附加功能。

### A.1 技术架构

```
[用户] → [麦克风] → [Web Audio API] → [VAD 检测] → [Opus 压缩] → [上传/流]
                                                                        ↓
[前端] ← [转写文本] ← [ASR 服务] ← [HTTP POST / WebSocket] ← [后端]
                                                                        ↓
[后端] ← [LLM NLP] ← [POST /narrative] ← [FMM 本地降级]
```

**关键组件**：
- **VAD（Voice Activity Detection）**：前端实时检测语音活动，自动开始/停止录音，避免用户手动点击「开始/停止」
- **Opus 压缩**：录音文件从 WAV（~10MB/min）压缩到 Opus（~0.5MB/min），降低上传带宽
- **WebSocket 流**：支持实时字幕（用户说话时文字实时显示，增强反馈感）
- **本地缓存**：网络断开时缓存录音，恢复后自动上传

### A.2 技术选型对比

| 方案 | 代表厂商 | 方言支持 | 老年语速 | 成本 | 延迟 | 隐私 | 推荐场景 |
|------|---------|----------|----------|------|------|------|----------|
| 云端 API | OpenAI Whisper | 一般 | 良好 | ¥0.003/分钟 | 1-3s | 低 | 原型/测试 |
| 国内云 | 阿里云/讯飞 | 优秀（23种） | 专门优化 | ¥0.006/分钟 | 1-2s | 中 | 国内产品 |
| 边缘部署 | whisper.cpp | 无（需训练） | 一般 | 0（硬件成本） | 实时 | 高 | 养老机构本地 |
| 混合方案 | 本地缓存 + 云端 | 兼顾 | 兼顾 | 弹性 | 低 | 中 | **推荐** |

### A.3 推荐方案：混合架构（三阶段实现）

**Phase 1（Week 5-6，MVP 阶段）**：云端优先

```python
# backend/nlp/asr.py
import httpx
from typing import Optional

ASR_PROVIDERS = {
    "aliyun": {
        "endpoint": "https://nls-gateway.aliyuncs.com/stream/v1/asr",
        "price_per_minute": 0.006,  # RMB
        "supports_streaming": True,
        "supports_dialect": ["mandarin", "cantonese", "sichuan", "shanghainese"],
    },
    "xunfei": {
        "endpoint": "wss://iat-api.xfyun.cn/v2/iat",
        "price_per_minute": 0.007,
        "supports_streaming": True,
        "supports_dialect": ["mandarin", "cantonese", "henan", "dongbei"],
    },
    "whisper": {
        "endpoint": "https://api.openai.com/v1/audio/transcriptions",
        "price_per_minute": 0.003,  # USD
        "supports_streaming": False,
        "supports_dialect": [],
    },
}

async def transcribe(audio_bytes: bytes, provider: str = "aliyun", 
                     dialect: Optional[str] = None) -> str:
    """统一 ASR 接口，支持自动降级"""
    config = ASR_PROVIDERS[provider]
    
    if provider == "aliyun":
        return await _transcribe_aliyun(audio_bytes, dialect)
    elif provider == "xunfei":
        return await _transcribe_xunfei(audio_bytes, dialect)
    elif provider == "whisper":
        return await _transcribe_whisper(audio_bytes)
    
async def transcribe_with_fallback(audio_bytes: bytes, dialect: str) -> str:
    """自动降级：首选阿里云 → 讯飞 → 本地 FMM"""
    try:
        return await transcribe(audio_bytes, "aliyun", dialect)
    except Exception:
        try:
            return await transcribe(audio_bytes, "xunfei", dialect)
        except Exception:
            return ""  # 触发前端降级：提示用户手动输入
```

**前端录音实现**：

```javascript
// src/audio/recorder.js
class VoiceRecorder {
  constructor() {
    this.mediaRecorder = null;
    this.chunks = [];
    this.vad = new VAD({ 
      minDuration: 3000,   // 最少录 3 秒（避免短句）
      maxDuration: 120000, // 最多 2 分钟（避免过长）
      silenceTimeout: 2000 // 沉默 2 秒自动停止
    });
  }

  async start() {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    this.mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
    this.mediaRecorder.ondataavailable = (e) => this.chunks.push(e.data);
    this.mediaRecorder.start(100); // 每 100ms 触发一次 ondataavailable
    
    // VAD 实时反馈
    this.vad.onSpeechStart = () => this.onSpeechStart?.();
    this.vad.onSpeechEnd = () => this.stop();
    this.vad.process(stream);
  }

  async stop() {
    this.mediaRecorder.stop();
    await new Promise(r => this.mediaRecorder.onstop = r);
    
    const blob = new Blob(this.chunks, { type: 'audio/webm' });
    const opusBlob = await compressToOpus(blob); // ffmpeg.js 浏览器端压缩
    return opusBlob;
  }
}

// 使用示例
const recorder = new VoiceRecorder();
recorder.onSpeechStart = () => {
  document.getElementById('mic-status').textContent = '🔴 正在听...';
};

const audioBlob = await recorder.start();
// 用户说完自动停止
const formData = new FormData();
formData.append('audio', audioBlob);
formData.append('dialect', 'mandarin');  // 根据用户设置
formData.append('user_id', currentUser.id);

const response = await fetch('/api/narrative/voice', {
  method: 'POST',
  body: formData
});
const { text, confidence } = await response.json();
```

**Phase 2（Week 10-12，临床阶段）**：方言优化

- 根据临床用户的地域分布，为高频方言（四川话、上海话、粤语）训练专用语言模型
- 科大讯飞提供方言 ASR 的定制训练服务，约 ¥5,000-10,000/方言

**Phase 3（Week 14-16，生产阶段）**：边缘部署

- 在养老机构部署本地 whisper.cpp 服务器（NVIDIA Jetson 或普通 PC + GPU）
- 敏感数据不出机构，完全离线运行
- 云端仅用于模型更新和日志上报

### A.4 老年语音优化策略

老年人语音有独特特征，通用 ASR 准确率会显著下降：

| 特征 | 影响 | 解决方案 |
|------|------|----------|
| 语速慢（80-120 字/分钟） | 标准模型训练数据是正常语速 | 使用讯飞「老年语速」专用模型，或 Whisper 微调 |
| 停顿多、重复多 | 转写结果碎片化 | 后端做文本拼接和去重处理 |
| 方言/口音重 | 普通话不标准 | 方言 ASR + 方言词库 |
| 音量低、气声 | 信噪比差 | 前端降噪（RNNoise）+ VAD 阈值调低 |
| 叙述碎片化（"然后...然后..."） | 语义连贯性差 | 不做拼接，保留原始碎片，作为「碎片化指标」 |

**文本后处理**：

```python
def post_process_elderly_speech(text: str) -> str:
    """针对老年语音的文本清洗"""
    # 去除重复词（如"然后然后然后"）
    text = re.sub(r'(\S+)\1{2,}', r'\1', text)
    
    # 去除填充词（嗯、啊、这个、那个）
    text = re.sub(r'[嗯啊这个那个]+', '', text)
    
    # 检测碎片化程度（重复连接词比例）
    filler_ratio = len(re.findall(r'然后|接着|还有|就是', text)) / len(text)
    if filler_ratio > 0.15:
        # 标记为「碎片化叙述」，作为认知指标之一
        pass
    
    return text
```

### A.5 语音情感分析（语音层面的认知指标）

除了「说什么」，**「怎么说」**也包含认知信息。这是当前原型完全缺失的维度。

**可提取的语音特征**：

| 特征 | 认知关联 | 检测方法 |
|------|----------|----------|
| 语速 | MCI 患者语速显著下降 | 字/分钟 |
| 停顿模式 | 找词困难时停顿增多、位置异常 | 沉默段检测（>500ms） |
| 音调变化 | 抑郁症和认知衰退导致音调平板化 | 基频（F0）标准差 |
| 音量波动 | 注意力下降导致音量不稳定 |  RMS 能量方差 |
| 语法复杂度 | 句子长度、从句数量 | NLP 解析 |
| 词汇多样性 | TTR（Type-Token Ratio）| 独特词/总词数 |

**技术实现**：

```python
# backend/nlp/voice_features.py
import librosa
import numpy as np
from scipy import stats

def extract_cognitive_voice_features(audio_path: str) -> dict:
    """从音频中提取认知相关声学特征"""
    y, sr = librosa.load(audio_path, sr=16000)
    
    # 1. 语速（需要配合 ASR 转写结果）
    # 由 ASR 模块返回 word_count / duration
    
    # 2. 停顿模式
    intervals = librosa.effects.split(y, top_db=20)  # 检测有声段
    pauses = []
    for i in range(1, len(intervals)):
        pause_duration = (intervals[i][0] - intervals[i-1][1]) / sr
        if pause_duration > 0.3:  # >300ms 视为停顿
            pauses.append(pause_duration)
    
    pause_features = {
        "pause_count": len(pauses),
        "mean_pause_duration": np.mean(pauses) if pauses else 0,
        "pause_variability": np.std(pauses) if len(pauses) > 1 else 0,
    }
    
    # 3. 音调变化（基频 F0）
    f0, voiced_flag, voiced_probs = librosa.pyin(y, fmin=50, fmax=500)
    f0_clean = f0[~np.isnan(f0)]
    pitch_features = {
        "f0_mean": np.mean(f0_clean) if len(f0_clean) > 0 else 0,
        "f0_std": np.std(f0_clean) if len(f0_clean) > 0 else 0,
        "f0_range": np.max(f0_clean) - np.min(f0_clean) if len(f0_clean) > 0 else 0,
    }
    
    # 4. 音量波动
    rms = librosa.feature.rms(y=y)[0]
    volume_features = {
        "rms_mean": np.mean(rms),
        "rms_std": np.std(rms),
    }
    
    return {
        **pause_features,
        **pitch_features,
        **volume_features,
    }
```

**与认知评估的关联**：

- 研究发现：MCI 患者的「停顿变异性」显著高于正常老人（p < 0.01）
- 语速下降与语义记忆衰退相关
- 音调平板化与执行功能下降相关

**使用方式**：
- 不作为独立诊断指标，而是作为「健康度」的辅助输入
- 语音特征参与 trend 计算（纵向对比自己的语速/停顿变化）

---

## 附录 B：部署与基础设施架构

### B.1 生产环境架构

```
                    [CDN] (静态资源缓存)
                       |
[用户] → [Nginx] → [FastAPI] → [PostgreSQL 主]
    |        |            ↓
    |   [Rate Limit]   [Redis 缓存]
    |        |            ↓
    |   [SSL/TLS]     [PG 从库只读]
    |
[Prometheus] → [Grafana] → [PagerDuty/钉钉]
    |
[LLM API] (阿里云/讯飞/OpenAI)
    |
[对象存储] (OSS/S3) → 音频文件 + 报告 PDF
```

### B.2 容器化与 CI/CD

```yaml
# docker-compose.yml
version: '3.8'
services:
  web:
    build: ./frontend
    ports:
      - "80:80"
    depends_on:
      - api

  api:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://user:pass@db:5432/cognitive_garden
      - REDIS_URL=redis://redis:6379
    depends_on:
      - db
      - redis

  db:
    image: postgres:15
    volumes:
      - pg_data:/var/lib/postgresql/data
    environment:
      - POSTGRES_DB=cognitive_garden
      - POSTGRES_USER=user
      - POSTGRES_PASSWORD=pass

  redis:
    image: redis:7-alpine

  prometheus:
    image: prom/prometheus
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml

  grafana:
    image: grafana/grafana
    ports:
      - "3000:3000"

volumes:
  pg_data:
```

**CI/CD 流水线（GitHub Actions）**：

```yaml
# .github/workflows/ci.yml
name: CI/CD

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Setup Node
        uses: actions/setup-node@v3
        with:
          node-version: '18'
      - run: cd frontend && npm ci && npm run test
      - run: cd frontend && npm run build
      
      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - run: cd backend && pip install -r requirements.txt && pytest
      
      - name: Setup Lean
        uses: leanprover/lean-action@v1
        with:
          lake: true
      - run: cd CognitiveGarden && lake build

  deploy:
    needs: test
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    steps:
      - name: Deploy to production
        run: |
          ssh user@server "cd /opt/cognitive-garden && docker-compose pull && docker-compose up -d"
```

### B.3 监控与告警

| 指标 | 告警阈值 | 通知方式 |
|------|----------|----------|
| API 错误率 | > 5% | 钉钉 |
| API P95 延迟 | > 2s | 钉钉 |
| 数据库连接池 | > 80% | 钉钉 |
| LLM API 成本 | > ¥100/天 | 邮件 |
| 磁盘使用率 | > 80% | 钉钉 |
| 证书过期 | < 30 天 | 邮件 |

---

## 附录 C：数据安全与隐私合规

### C.1 安全架构

```
[传输层] TLS 1.3 + HSTS
    ↓
[应用层] JWT 认证 + RBAC 权限控制
    ↓
[数据层] 字段级 AES-256 加密（敏感字段：电话、身份证号）
    ↓
[存储层] 数据库加密（TDE）+ 对象存储加密（SSE）
    ↓
[备份层] 加密备份 + 异地容灾
```

### C.2 隐私合规清单

| 法规 | 要求 | 实现方式 |
|------|------|----------|
| 《个人信息保护法》 | 最小必要原则、用户同意、数据删除权 | 仅收集必要字段，注册时明确同意，提供「注销账户」按钮 |
| 等保三级 | 审计日志、访问控制、数据加密 | 全量操作日志，角色权限矩阵，数据库加密 |
| GDPR（若出海） | 数据可携带权、被遗忘权、DPO | 数据导出 JSON，账户注销 30 天内删除全部数据 |
| HIPAA（若对接美国医院） | PHI 保护、BAA 协议 | 额外字段级加密，签署 BAA |

### C.3 数据脱敏策略

```python
# 临床研究数据脱敏
from cryptography.fernet import Fernet

class DataMasking:
    def __init__(self, key: bytes):
        self.cipher = Fernet(key)
    
    def mask_phone(self, phone: str) -> str:
        """138****1234"""
        return phone[:3] + "****" + phone[-4:]
    
    def pseudonymize_user(self, user_id: str) -> str:
        """不可逆假名化，用于研究数据集"""
        return hashlib.sha256(user_id.encode()).hexdigest()[:16]
    
    def encrypt_narrative(self, text: str) -> str:
        """叙述文本加密存储"""
        return self.cipher.encrypt(text.encode()).decode()
```

---

## 附录 D：移动端与 PWA

### D.1 PWA 能力清单

| 能力 | 实现方式 | 优先级 |
|------|----------|--------|
| 离线访问 | Service Worker + Cache API | P1 |
| 主屏图标 | Web App Manifest | P1 |
| 推送通知 | Web Push API +  Firebase Cloud Messaging | P2 |
| 后台同步 | Background Sync API | P2 |
| 原生分享 | Web Share API | P3 |
| 生物识别 | WebAuthn | P3 |

### D.2 离线模式设计

```javascript
// service-worker.js
const CACHE_NAME = 'cognitive-garden-v1';
const OFFLINE_URLS = [
  '/', '/index.html', '/bundle.js', '/styles.css',
  // 关键页面和数据
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(OFFLINE_URLS))
  );
});

self.addEventListener('fetch', (event) => {
  if (event.request.url.includes('/api/')) {
    // API 请求：网络优先，失败则缓存
    event.respondWith(
      fetch(event.request).catch(() => {
        return new Response(JSON.stringify({ offline: true }), {
          headers: { 'Content-Type': 'application/json' }
        });
      })
    );
  } else {
    // 静态资源：缓存优先
    event.respondWith(
      caches.match(event.request).then(response => 
        response || fetch(event.request)
      )
    );
  }
});
```

### D.3 微信小程序（备选）

如果 PWA 在老年用户中的接受度低，可以开发微信小程序版本：
- 优势：无需安装，微信生态内分享方便，家属端使用率高
- 劣势：小程序不支持 Web Audio API 的完整功能，录音需要用户手动授权每次

**决策条件**：如果 PWA 的 7 日留存率 < 30%，启动小程序开发。

---

## 附录 E：多租户与多机构支持

### E.1 数据模型

```sql
-- 机构表
CREATE TABLE organizations (
    id UUID PRIMARY KEY,
    name VARCHAR(100) NOT NULL,  -- "XX 社区卫生服务中心"
    type ENUM('hospital', 'community', 'family', 'research'),
    created_at TIMESTAMP DEFAULT NOW()
);

-- 用户-机构关联
CREATE TABLE organization_users (
    user_id UUID REFERENCES users(id),
    org_id UUID REFERENCES organizations(id),
    role ENUM('admin', 'doctor', 'nurse', 'family_member', 'elderly'),
    PRIMARY KEY (user_id, org_id)
);

-- 数据隔离：所有会话表增加 org_id
ALTER TABLE sessions ADD COLUMN org_id UUID REFERENCES organizations(id);
-- 查询时自动过滤：WHERE org_id = current_user_org_id()
```

### E.2 角色权限矩阵

| 功能 | 老人 | 家属 | 医生 | 管理员 |
|------|------|------|------|--------|
| 查看自己的图谱 | ✅ | ✅（关联老人） | ✅（本机构） | ✅ |
| 编辑图谱 | ✅ | ❌ | ❌ | ❌ |
| 查看健康趋势 | ✅ | ✅ | ✅ | ✅ |
| 查看原始叙述 | ✅ | ❌ | ✅ | ✅ |
| 导出报告 | ✅ | ✅ | ✅ | ✅ |
| 设置基准 | ✅ | ❌ | ✅ | ❌ |
| 管理用户 | ❌ | ❌ | ❌ | ✅ |
| 查看全机构统计 | ❌ | ❌ | ✅ | ✅ |

---

## 附录 F：报告生成系统

### F.1 医生端报告模板

**PDF 报告内容**：

```
认知网络评估报告
━━━━━━━━━━━━━━━━━━━━
患者：张三（脱敏 ID）
评估日期：2026-07-10
评估周期：第 1-7 天

一、综合评分
• 记忆网健康度：82/100（正常范围）
• 与基准对比：+2%（稳定）

二、网络拓扑分析
[图谱截图]
• 节点数：8  |  边数：10
• 连通度：100%  |  聚类系数：72%
• 自我中心度：100%  |  时序熵：69%

三、语义异常记录
⚠ 第 7 天：检测到「打太极」的地点异常（医院）
  建议：关注时空定向能力

四、纵向趋势
[7 天健康度折线图]
趋势：稳定，无显著下降

五、建议
• 继续保持日常社交活动
• 建议家属陪同进行户外活动（公园、广场）
• 下次评估：7 天后

━━━━━━━━━━━━━━━━━━━━
生成时间：2026-07-10 14:30
机构：XX 社区卫生服务中心
医师签名：__________
```

### F.2 技术实现

```python
# backend/report/pdf.py
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Image
from reportlab.lib.styles import getSampleStyleSheet

def generate_pdf_report(user_id: str, session_ids: list[str]) -> bytes:
    """生成 PDF 评估报告"""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    
    story = []
    
    # 标题
    story.append(Paragraph("认知网络评估报告", styles['Title']))
    
    # 基本信息
    data = [
        ['患者', '张三'],
        ['评估日期', '2026-07-10'],
        ['健康度', '82/100'],
    ]
    t = Table(data)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))
    story.append(t)
    
    # 图谱截图（从 SVG 渲染为 PNG）
    story.append(Image('/tmp/graph.png', width=400, height=300))
    
    doc.build(story)
    buffer.seek(0)
    return buffer.read()
```

---

## 附录 G：数据标注平台

### G.1 目标
- 为 NLP 模块扩充词库和异常规则
- 为临床研究提供标注数据
- 支持众包标注（医学学生、志愿者）

### G.2 功能

```python
# 标注任务类型
TASK_TYPES = {
    "entity_annotation": "标注文本中的实体（人物/地点/事件/物品）",
    "relation_annotation": "标注实体之间的关系",
    "anomaly_verification": "验证 LLM 检测的异常是否正确",
    "dialect_transcription": "听录音，标注方言词汇",
}

# 标注质量审核
class AnnotationReview:
    def __init__(self):
        self.agreement_threshold = 0.8  # 多人标注一致率 > 80% 才采纳
    
    def calculate_kappa(self, annotations: list) -> float:
        """计算 Cohen's Kappa，评估标注者一致性"""
        pass
```

### G.3 实施时机
- **Phase 1**：不需要，使用现有词库
- **Phase 2**：上线简单标注工具（管理后台），团队内部标注
- **Phase 3**：开放给医学学生众包，与医学院合作

---

## 附录 H：A/B 测试框架

### H.1 测试场景

| 实验 | 变量 A | 变量 B | 指标 | 样本量 |
|------|--------|--------|------|--------|
| 健康度公式 | v1.0 线性组合 | v2.0 三层模型 | 与 MoCA 相关性 | 100 人 |
| 异常检测 | 规则引擎 | LLM 检测 | 异常检出率 | 200 条叙述 |
| 界面布局 | 当前三栏 | 简化两栏 | 7 日留存率 | 500 用户 |
| 提醒频率 | 每日 1 次 | 每日 2 次 | 完成率 | 300 用户 |

### H.2 实现

```python
# backend/experiment/ab.py
import random
import hashlib

def get_experiment_group(user_id: str, experiment_name: str) -> str:
    """基于用户 ID 的确定性分组，保证同一用户始终在同一组"""
    hash_val = int(hashlib.md5(f"{user_id}:{experiment_name}".encode()).hexdigest(), 16)
    return "A" if hash_val % 2 == 0 else "B"

# 使用示例
@app.post("/session")
async def create_session(user_id: str, narrative: str):
    group = get_experiment_group(user_id, "health_formula_v2")
    if group == "A":
        health = compute_health_v1(metrics)
    else:
        health = compute_health_v2(metrics)
    
    # 记录实验数据
    log_experiment(user_id, "health_formula_v2", group, health)
    
    return {"health": health, "group": group}
```

---

> 以上所有附录共同构成一个完整的技术路线图。语音识别集成（附录 A）和语音情感分析是区分「可演示原型」和「可临床使用产品」的关键；数据安全（附录 C）和多租户（附录 E）是进入医院体系的准入门槛；报告生成（附录 F）和数据标注（附录 G）是长期数据飞轮的引擎。
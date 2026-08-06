# AI Village — 多智能体虚拟小镇 项目规划 (v2)

## Context

构建一个**社会模拟类多智能体项目**。虚拟小镇中有 7 个 AI Agent，各自拥有独立的性格、职业和日常作息。它们在小镇中自主移动、思考、对话、建立社交关系，用户通过浏览器观看实时动态，并通过监测面板评估 Agent 表现。

- **目的**: 学习多智能体协作原理、LangGraph 工作流、FastAPI 全栈开发流程
- **技术栈**: Python + FastAPI + LangChain + LangGraph + DeepSeek Flash + HTML/CSS/JS (Canvas)
- **运行环境**: 用户本地 Windows 电脑，浏览器打开 `http://localhost:8000` 即可观看

---

## 项目架构总览

```
drill/
├── backend/
│   ├── main.py                  # FastAPI 入口：挂载静态文件、启动世界引擎后台任务
│   ├── config.py                # 配置：从 .env 读取 API Key、世界参数、Agent 参数
│   ├── world/
│   │   ├── __init__.py
│   │   ├── engine.py            # 世界引擎：asyncio tick 循环、虚拟时间、并发调度
│   │   ├── map.py               # 2D 网格地图：碰撞检测、移动合法性、邻近查询
│   │   └── locations.py         # 地点定义 + 具体坐标布局
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── base_agent.py        # Agent 数据类：属性、状态、动作结果
│   │   ├── agent_manager.py     # Agent 管理器：创建、状态汇总、关系/心情更新
│   │   ├── personalities.py     # 性格系统（大五人格简化，3 维度）
│   │   └── routines.py          # 日常作息：优先级表，作为 LLM 决策的约束条件
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── client.py            # DeepSeek Flash 客户端封装（含超时、重试、降级）
│   │   └── prompts.py           # 所有 Prompt 模板（决策、对话、评估）
│   ├── graph/
│   │   ├── __init__.py
│   │   ├── agent_graph.py       # LangGraph：Agent 单 tick 决策工作流（5 节点）
│   │   └── conversation_graph.py # LangGraph：双人对话子图（2-4 轮）
│   ├── memory/
│   │   ├── __init__.py
│   │   ├── store.py             # JSON 文件存储 + 内存索引
│   │   └── manager.py           # 记忆管理器：检索（时间+关键词）、存储、遗忘
│   ├── api/
│   │   ├── __init__.py
│   │   ├── routes.py            # REST：/api/world, /api/agents/{id}, /api/events, /api/metrics
│   │   └── websocket.py         # WebSocket：双向通信（状态推送 + 控制命令接收）
│   ├── monitor/
│   │   ├── __init__.py
│   │   ├── tracer.py            # LangSmith 追踪（可选，环境变量开关）
│   │   ├── metrics.py           # 指标采集：每个 tick 每个 Agent
│   │   ├── evaluator.py         # LLM-as-Judge：每 20 tick 评估一次
│   │   └── reporter.py          # 报告生成：汇总 JSON → 前端消费
│   └── data/
│       ├── agents.json          # 7 个 Agent 的完整初始配置
│       └── memories/            # 运行时生成的记忆文件（按 Agent 分文件）
├── frontend/
│   ├── index.html               # 主页面（三个标签页切换）
│   ├── css/
│   │   └── style.css            # 全局样式 + 地图 + 面板 + 监测
│   └── js/
│       ├── app.js               # 主入口：标签切换、全局状态
│       ├── map.js               # Canvas 2D 地图：网格绘制 + 平滑动画插值
│       ├── agent_panel.js       # Agent 详情面板（Profile/记忆/关系/当前状态）
│       ├── event_log.js         # 事件日志（右侧滚动）
│       ├── monitor_dashboard.js # 监测面板：指标卡片 + 排行榜 + 情绪图
│       └── websocket.js         # WebSocket 客户端：收发消息、自动重连
├── .env.example                 # 环境变量示例
├── requirements.txt
└── README.md
```

---

## 核心设计

---

### 1. 世界系统 (World Engine)

#### 1.1 地图布局（10×10 网格）

坐标原点 (0,0) 为左上角，x 向右，y 向下：

```
   0  1  2  3  4  5  6  7  8  9
0  🏠  🏠  🏠  ·  🌳  🌳  ·  🏪  🏪  ·
1  🏠  🏠  🏠  ·  🌳  🌳  ·  🏪  🏪  ·
2  ·   ·   ·   ·  🌳  ·   ·  ·   ·   ·
3  ·   🏠  🏠  ·  ·   ·   ·  ☕  ☕  ·
4  ·   🏠  🏠  ·  🎨  ·   ·  ☕  ☕  ·
5  ·   ·   ·   ·  🎨  ·   ·  ·   ·   ·
6  🏠  🏠  ·   ·  ·   ·   ·  ·   🏠  🏠
7  🏠  🏠  ·   ·  ⛲  ⛲  ·  ·   🏠  🏠
8  ·   ·   ·   ·  ⛲  ⛲  ·  ·   ·   ·
9  ·   ·   ·   ·  ·   ·   ·  ·   ·   ·
```

| 地点 | 坐标范围 | 说明 |
|------|---------|------|
| 🏠 住宅区 A | (0,0)-(2,1) | 小明、小红、老王的家 |
| 🏠 住宅区 B | (1,3)-(2,4) | 阿花、小李的家 |
| 🏠 住宅区 C | (0,6)-(1,7) | 老张的家 |
| 🏠 住宅区 D | (8,6)-(9,7) | 小美的家 |
| 🌳 公园 | (4,0)-(5,1), (4,2) | 散步、聊天、休息 |
| 🏪 市场 | (7,0)-(8,1) | 购物、偶遇 |
| ☕ 咖啡馆 | (7,3)-(8,4) | 聊天、阅读 |
| 🎨 广场 | (4,4)-(5,4) | 活动、聚会 |
| ⛲ 喷泉 | (4,7)-(5,8) | 约会、思考 |

每个 Agent 的"家"坐标是明确的个人住宅格。其余为非住宅公共区域。

#### 1.2 移动规则

- **一格一动**: 每次 `move` 动作移动 1 格（上下左右或停留）
- **不可穿墙**: 地图边界不可跨越
- **不可重叠**: 同一时刻一个格子最多站 1 个 Agent。后来者需选择相邻空位
- **路径计算**: Agent 不自己算路径。LLM 决策输出方向（上/下/左/右/停留），world engine 校验合法性后执行移动

#### 1.3 时间系统

```
虚拟时间流速: 1 真实秒 = 10 虚拟分钟
一天 = 144 真实秒 ≈ 2.4 分钟
活动时间: 06:00 - 23:00 (17 虚拟小时 ≈ 102 真实秒)
睡眠时间: 23:00 - 06:00 (加速跳过，见 1.5)
Tick 间隔: 1.5 真实秒 = 15 虚拟分钟
每天 ≈ 96 个 tick
```

#### 1.4 Tick 循环机制（核心）

```
每个 tick 的执行流程：

┌─ tick_N 开始 ────────────────────────────────────────┐
│                                                       │
│  1. 世界时钟 +15 分钟                                  │
│                                                       │
│  2. 并行处理所有 Agent (asyncio.gather):               │
│     ┌─ Agent:小明 ──────────────────────────┐         │
│     │  [Perceive] → [Think(LLM)] → [Act] → [Remember]│
│     │  超时: 5s, 降级: 规则决策              │         │
│     └────────────────────────────────────────┘         │
│     ┌─ Agent:小红 ──────────────────────────┐         │
│     │  ... 同上，独立的协程                  │         │
│     └────────────────────────────────────────┘         │
│     ... 7 个 Agent 同时运行                           │
│                                                       │
│  3. 处理冲突:                                          │
│     - 移动冲突: 先到先得，后来者停在相邻空位           │
│     - 对话匹配: A 想找 B，B 也想找 A → 触发对话       │
│                  A 想找 B，B 未回应 A → A 等待/换方案  │
│                                                       │
│  4. 执行对话 (如果有):                                 │
│     - 不影响其他 Agent 的当前 tick                     │
│     - 对话在独立协程中运行，2-4 轮                      │
│     - 结果在下一个 tick 广播                           │
│                                                       │
│  5. 更新关系值 & 心情 (基于本 tick 事件)               │
│                                                       │
│  6. 收集指标到 monitor/metrics                         │
│                                                       │
│  7. 广播世界状态到所有 WebSocket 客户端                │
│                                                       │
└───────────────────────────────────────────────────────┘
```

**关键设计:**
- Agent 决策是**异步并行**的（7 个协程同时启动）
- 每个 Agent 的 LLM 调用有 **5 秒超时**，超时自动走规则降级
- 最慢的 Agent 决定 tick 速度，但不会超过 5 秒
- **对话不阻塞**其他 Agent — 对话在独立协程中运行

#### 1.5 睡眠阶段处理

- 虚拟时间到 22:30 时，Agent 开始倾向回家
- 23:00 时，所有 Agent **自动传送到各自的家**，状态设为"睡觉"
- 23:00 - 06:00 期间，**Tick 暂停，时间快进**（等待 3 秒后直接跳到 06:00）
- 06:00 时，Agent 醒来，心情重置为 0.7 基准，开始新一天
- 前端在睡眠阶段显示 🌙 夜间模式 + "天亮了..."倒计时

---

### 2. Agent 系统

#### 2.1 Agent 完整属性

```python
@dataclass
class Agent:
    # 基础身份
    id: str                    # "agent_xiaoming"
    name: str                  # "小明"
    age: int                   # 28
    job: str                   # "教师"
    home: tuple[int, int]      # (0, 0) — 个人住宅坐标

    # 性格 (3 维度，每个 0~1)
    extraversion: float        # 外向性 (0=内向独处, 1=热衷社交)
    openness: float            # 开放性 (0=保守传统, 1=好奇探索)
    conscientiousness: float   # 尽责性 (0=随性散漫, 1=严谨自律)

    # 技能 (每个 0~1，表示熟练度)  ← 🆕
    skills: dict[str, float]   # {"教学": 0.9, "园艺": 0.3, "烹饪": 0.5, ...}

    # 动态状态
    x: int                     # 当前 X 坐标
    y: int                     # 当前 Y 坐标
    activity: str              # 当前活动: "睡觉"/"工作"/"散步"/"购物"/"聊天"/"休息"
    mood: float                # 心情 0~1 (0.5 基准)
    energy: float              # 精力 0~1 (早晨 0.9, 睡前 0.2)

    # 社交
    relationships: dict[str, float]  # {agent_id: -10 ~ +10}
    conversation_cooldown: int       # 距离上次对话的 tick 数 (防止话痨)

    # 记忆
    short_term: deque          # 最近 10 条 (内存)
    long_term_count: int       # 长期记忆条数

    # 统计
    tick_count: int            # 该 Agent 自启动以来的总 tick 数
    total_tokens: int          # 累计消耗 token
```

#### 2.2 7 个 Agent 预设（含技能）

| ID | 名字 | 年龄 | 职业 | 家 | 外向 | 开放 | 尽责 | 核心技能 |
|----|------|------|------|-----|------|------|------|---------|
| agent_xiaoming | 小明 | 28 | 教师 | (0,0) | 0.7 | 0.6 | 0.8 | 教学(0.9)、沟通(0.8)、园艺(0.3) |
| agent_xiaohong | 小红 | 25 | 花店店主 | (1,1) | 0.8 | 0.7 | 0.5 | 花艺(0.9)、社交(0.85)、手工(0.7)、商业(0.5) |
| agent_laowang | 老王 | 62 | 退休老人 | (2,0) | 0.3 | 0.2 | 0.9 | 下棋(0.9)、养生(0.8)、木工(0.7)、讲故事(0.6) |
| agent_ahua | 阿花 | 22 | 学生 | (1,3) | 0.5 | 0.9 | 0.3 | 学习(0.7)、摄影(0.8)、音乐(0.7)、编程(0.5) |
| agent_xiaoli | 小李 | 30 | 面包师 | (1,4) | 0.4 | 0.4 | 0.8 | 烘焙(0.95)、烹饪(0.7)、记账(0.6) |
| agent_laozhang | 老张 | 55 | 医生 | (0,6) | 0.6 | 0.5 | 0.9 | 诊断(0.9)、急救(0.85)、养生(0.7)、沟通(0.7) |
| agent_xiaomei | 小美 | 27 | 艺术家 | (8,6) | 0.3 | 0.9 | 0.2 | 绘画(0.95)、创意(0.9)、花艺(0.4)、摄影(0.5) |

#### 2.3 技能系统设计 🆕

##### 技能的作用

技能不是装饰，它影响 Agent 在多个层面的行为：

| 作用层面 | 机制 |
|----------|------|
| **活动选择** | 高技能活动出现在 LLM Prompt 的"擅长活动"列表中，Agent 更倾向选择 |
| **对话话题** | 技能 → 对话知识领域。烘焙师聊面包；医生聊健康。技能越高，这个话题被选中的概率越大 |
| **协作触发** | 当 Agent A 的技能和 Agent B 的需求匹配时，产生"协作机会" |
| **心情反馈** | 做擅长的事 → 心情小幅提升（+0.03/tick）；被迫做不擅长的事 → 无加成 |
| **日常产出** | 高技能 Agent 在工作时段有更丰富的活动描述（"精心烤了一炉牛角包" vs "应付着做了些面包"） |

##### 技能互补与协作

这是多智能体协作的核心——**没有人全能，相互需要**：

```
技能依赖关系图（谁能帮谁）：

  老张(医生) ──养生建议──→ 老王(退休)
       │                      │
   健康咨询                 木工修理
       ↓                      ↓
  小明(教师) ←──买面包── 小李(面包师)
       │                      │
   知识传授                 烹饪教学
       ↓                      ↓
  阿花(学生) ──拍照记录──→ 小美(艺术家)
       │                      │
   帮看店                   花艺交流
       ↓                      ↓
  小红(花店) ←──────────────┘
```

| 互补关系 | 说明 |
|----------|------|
| 小李 → 所有人 | 只有他会烤面包，大家想吃好的都找他 |
| 老张 → 所有人 | 唯一的医生，健康问题都问他 |
| 老王 → 邻居 | 家里东西坏了找他修（木工） |
| 小红 → 小美 | 花艺交流，但小红是专业的 → 小美向她学习 |
| 小明 → 阿花 | 师生关系，知识传授 |
| 小美 → 阿花 | 摄影同好，一起出去拍照 |

##### 技能在 Prompt 中的体现

LLM 决策时收到的 Prompt 片段：

```
## 你的技能
- 烘焙(精通): 你能烤出全镇最好的面包，大家都喜欢你做的可颂
- 烹饪(熟练): 家常菜不在话下
- 记账(入门): 基本的账目能算清楚

## 今天你可能帮助别人
- 小明明天有课，可能需要准备早餐面包
- 老张提过想学烘焙，你可以主动教他
```

这样 LLM 在做决策时自然会"扮演"有技能的角色，行为也更加合理。

##### 技能对关系的影响

共享技能（如小美和小红都懂花艺）→ 初始关系 +2，对话时更容易产生正向互动。

互补技能（如老张帮老王调理身体）→ 每次成功的"技能帮助"事件，关系 +0.8（高于普通对话的 +0.5）。

##### 技能的后期扩展性 🆕

技能系统按三层递进设计，基础版本只实现 L1，L2/L3 作为后续扩展方向：

| 层次 | 能力 | 实现方式 | 建议阶段 |
|------|------|---------|---------|
| **L1 静态技能** | 7 个 Agent 预设技能，从 `agents.json` 加载 | 当前设计，开箱即用 | 阶段 3 完成 |
| **L2 运行时修改** | 通过 API/配置文件热更新 Agent 技能，无需重启 | `PUT /api/agents/{id}/skills` + WebSocket 通知前端刷新 | 后期扩展 |
| **L3 技能成长** | Agent 做某件事越多，对应技能值缓慢提升（如小李每天烤面包，烘焙从 0.95 → 0.96） | 每成功执行一次技能相关活动，技能值 +0.001；长期不练习衰减 -0.0005/天 | 后期扩展 |

**全局技能池**也支持扩展——只需在 `data/skills_pool.json` 中注册新技能名，所有 Agent 即可使用：

```json
// data/skills_pool.json — 定义小镇中存在的所有技能
{
  "skills": {
    "教学":     {"category": "知识", "icon": "📚"},
    "烘焙":     {"category": "手艺", "icon": "🥐"},
    "花艺":     {"category": "手艺", "icon": "🌸"},
    "诊断":     {"category": "知识", "icon": "🩺"},
    "绘画":     {"category": "艺术", "icon": "🎨"},
    "摄影":     {"category": "艺术", "icon": "📷"},
    "下棋":     {"category": "娱乐", "icon": "♟️"},
    "木工":     {"category": "手艺", "icon": "🔧"},
    "编程":     {"category": "知识", "icon": "💻"},
    "音乐":     {"category": "艺术", "icon": "🎵"},
    "烹饪":     {"category": "手艺", "icon": "🍳"},
    "养生":     {"category": "知识", "icon": "🌿"},
    "社交":     {"category": "社交", "icon": "💬"},
    "沟通":     {"category": "社交", "icon": "🗣️"},
    "记账":     {"category": "知识", "icon": "📊"},
    "手工":     {"category": "手艺", "icon": "✂️"},
    "创意":     {"category": "艺术", "icon": "💡"},
    "讲故事":   {"category": "社交", "icon": "📖"},
    "商业":     {"category": "知识", "icon": "💰"},
    "急救":     {"category": "知识", "icon": "🚑"},
    "学习":     {"category": "知识", "icon": "📝"}
  }
}
```

新增技能只需在此文件加一行，再给某个 Agent 的 `skills` 字段加一项即可——不改代码。

#### 2.4 初始关系矩阵

初始化时设定已有关系（非零值），其余为 0：

```
           小明  小红  老王  阿花  小李  老张  小美
小明        -    +3    +5    0     0    +2    0
小红       +3    -     0    +4    0     0    +1
老王       +5    0     -     0    +2    +6    0
阿花        0   +4     0     -     0     0    +3
小李        0    0    +2     0     -    +4    0
老张       +2    0    +6     0    +4     -    0
小美        0   +1     0    +3    0     0     -
```

关系解读: 小明和老王是忘年交(+5)，老王和老张是老友(+6)，阿花和小红是闺蜜(+4)，小美比较孤僻(大多数关系为 0)。

#### 2.5 日常作息约束

作息不是强制指令，而是给 LLM 的**强约束提示**。LLM 在所有非约束时段可自由决策：

| 时间段 | 约束 | 说明 |
|--------|------|------|
| 06:00-07:00 | 倾向：起床、早餐 | LLM 可决定具体吃什么、在哪吃 |
| 07:00-08:00 | 倾向：通勤（前往工作地附近） | 学生→学校=广场；教师→广场；面包师→市场；花店→市场；医生→广场；艺术家→广场；退休→自由 |
| 08:00-12:00 | 倾向：工作相关活动 | 教师/医生在广场；烘焙师在市场；花店在市场；学生在广场/咖啡馆；退休/艺术家自由 |
| 12:00-13:00 | 倾向：午餐 | LLM 自由选择地点和同伴 |
| 13:00-17:00 | 倾向：工作/自由活动 | 较宽松，LLM 自主权增大 |
| 17:00-19:00 | 自由时间 | LLM 完全自主决策 |
| 19:00-21:00 | 倾向：晚餐、社交 | 鼓励社交行为 |
| 21:00-22:30 | 倾向：回家方向 | 逐渐向住宅区移动 |
| 22:30-23:00 | 强约束：必须回家 | 只允许向家移动 |
| 23:00-06:00 | 睡眠 | 系统接管，传送回家 |

**约束机制**: 在 LLM Prompt 中注入当前时间段对应的约束文本。约束文本作为 Prompt 中**高优先级的上下文**，但 LLM 在自由时段拥有完全自主权。

---

### 3. LangGraph 决策工作流

#### 3.1 状态 Schema

```python
class AgentState(TypedDict):
    # 输入（由 world engine 填充）
    agent_profile: str        # 名字、年龄、职业、性格的文字描述
    current_time: str         # "14:30"
    time_period: str          # "自由时间"
    location_name: str        # 当前位置的地点名（"公园"/"咖啡馆"/...）
    nearby_agents: list[str]  # 相邻 3 格内的 Agent 名字列表
    nearby_locations: list[str]  # 相邻格子的地点名

    # 约束
    routine_constraint: str   # 当前时段约束文本（空字符串=完全自由）

    # 记忆
    recent_memories: str      # 最近 10 条记忆的格式化文本

    # 关系
    relationships_text: str   # 关系文本: "小明(+3), 老王(+5)..."

    # 当前状态
    mood: float               # 0~1
    energy: float             # 0~1
    current_activity: str     # 上一 tick 的活动

    # LLM 输出（由 think 节点填充）
    thought: str              # LLM 内心独白
    action_type: str          # "move" | "chat" | "do" | "rest"
    action_detail: str        # move: "向上/下/左/右/停留"
                              # chat: "和XXX聊聊关于YYY"
                              # do: "在公园看书" / "在市场购物"
                              # rest: "在长椅上休息"
    action_reason: str        # 为什么做这个决定

    # 执行结果（由 act 节点填充）
    action_success: bool
    action_result: str        # 执行结果的文字描述

    # 记忆（由 remember 节点填充）
    new_memory: str           # 新生成的记忆文本
```

#### 3.2 工作流图

```
                ┌──────────┐
                │ START    │
                └────┬─────┘
                     ▼
              ┌──────────────┐
              │  perceive    │  收集：附近的人、地点、当前时段约束
              │  (纯逻辑)    │  不需要 LLM
              └────┬─────────┘
                   ▼
              ┌──────────────┐
              │  think       │  LLM 调用：输入状态 → 输出决策
              │  (LLM)       │  核心 Prompt: decision_prompt
              └────┬─────────┘
                   ▼
              ┌──────────────┐
              │  validate    │  解析 LLM 输出，校验合法性
              │  (纯逻辑)    │  "向上"是否在地图内？chat 对象是否仍在附近？
              └────┬─────────┘
                   │
              ┌────┴───── 校验失败 → 规则降级
              │
              ▼ (校验通过)
              ┌──────────────┐
              │  act         │  执行动作，更新世界状态
              │  (纯逻辑)    │  移动坐标 / 触发对话 / 修改 activity
              └────┬─────────┘
                   ▼
              ┌──────────────┐
              │  remember    │  判断是否值得记忆 → LLM 生成记忆文本
              │  (LLM可选)   │  简单事件（纯移动）跳过，重要事件才调 LLM
              └────┬─────────┘
                   ▼
              ┌──────────┐
              │ END      │
              └──────────┘
```

**思考→校验→降级的闭环**是可靠性的关键。校验节点是一道"防火墙"：LLM 输出不合法时自动切换为规则逻辑，保证 Agent 永远不会卡住。

#### 3.3 降级策略（三层）

| 层级 | 触发条件 | 行为 |
|------|---------|------|
| L1 正常 | LLM 正常返回 + 校验通过 | 使用 LLM 决策 |
| L2 输出修正 | LLM 返回但校验失败（如"移动到地图外"） | 丢弃非法部分，用规则补全（如随机选合法方向） |
| L3 完全降级 | LLM 超时(5s) / 网络错误 / 连续 3 次 L2 | 纯规则决策：按作息约束走，无约束时随机探索 |

降级发生时记录到 metrics，前端监测面板可看到降级率。

---

### 4. Agent 间对话

#### 4.1 触发条件

对话需要**双向意愿匹配**：
1. Agent A 的决策是 `action_type="chat"`，目标是 Agent B
2. Agent B **在同一 tick 或上一 tick** 的决策也是 `action_type="chat"`，目标是 Agent A
3. 双方在同一格或相邻格
4. 双方的 `conversation_cooldown` ≤ 0（防止同一对人每 tick 都聊）

如果 A 想找 B，但 B 没有回应（B 在做别的事），则 A 的对话失败，改为在附近做其他事（规则降级）。

#### 4.2 对话流程（独立协程，不阻塞 tick）

```python
# 对话在 asyncio 独立协程中执行
async def run_conversation(agent_a, agent_b, world_context):
    rounds = random.randint(2, 4)
    history = []
    speaker, listener = agent_a, agent_b

    for i in range(rounds):
        msg = await llm_generate_conversation_turn(
            speaker=speaker,
            listener=listener,
            history=history,
            world_context=world_context
        )
        history.append({"speaker": speaker.name, "message": msg})
        speaker, listener = listener, speaker  # 轮流发言

    # 更新关系值（基于 LLM 对对话质量的评分）
    quality_score = await llm_evaluate_conversation(history)
    update_relationship(agent_a, agent_b, quality_score)

    # 双方各自存储对话记忆
    store_conversation_memory(agent_a, agent_b, history, quality_score)

    # 生成事件
    emit_event(f"{agent_a.name}和{agent_b.name}聊了{rounds}轮，{'相谈甚欢' if quality_score > 0.6 else '简短交流'}")
```

对话结果在下一次 WebSocket 广播中发送给前端。

---

### 5. 关系与心情系统

#### 5.1 关系值变化规则

| 事件 | 关系变化 | 说明 |
|------|---------|------|
| 成功对话（LLM 评分 0.7+） | +0.5 | 相谈甚欢 |
| 成功对话（LLM 评分 0.4-0.7） | +0.2 | 普通交流 |
| 成功对话（LLM 评分 <0.4） | -0.1 | 话不投机 |
| 在同一地点共处（未对话） | +0.05/tick | 默默陪伴 |
| 每日互动超过 5 次 | 后续收益减半 | 防止过度社交刷分 |
| 连续 1 天无互动 | -0.1/天 | 关系自然衰减 |

#### 5.2 心情变化规则

| 触发 | 心情变化 | 说明 |
|------|---------|------|
| 成功社交（对话评分高） | +0.1 | 社交满足 |
| 对话被拒绝 | -0.05 | 小失落 |
| 完成工作时段活动 | +0.05 | 成就感 |
| 违背作息约束 | -0.1 | 焦虑感（针对高尽责性 Agent 加倍） |
| 精力过低 (<0.2) | -0.1 | 疲惫 |
| 睡眠后 | 重置为 0.7 | 新的一天 |
| 在喜欢的地点（公园→外向者，咖啡馆→开放者...） | +0.02/tick | 环境愉悦 |

---

### 6. 记忆系统

#### 6.1 存储结构

```
data/memories/
├── agent_xiaoming.json   # {"memories": [{"tick": 12, "time": "07:30", "content": "...", "importance": 0.8}, ...]}
├── agent_xiaohong.json
├── ...
```

每条记忆：
```json
{
  "tick": 120,
  "virtual_time": "14:30",
  "content": "在公园遇到了小红，聊了聊天气和最近读的书，小红推荐了一本小说",
  "importance": 0.8,
  "tags": ["公园", "小红", "聊天", "读书"],
  "related_agents": ["agent_xiaohong"]
}
```

#### 6.2 检索策略

LLM 决策时传递给 Agent 的记忆选取：
1. **最近性**: 最近 10 条（始终包含）
2. **相关性**: 从长期记忆中按标签匹配（如当前在公园 → 搜索 tags 含"公园"的记忆，取 3 条）
3. **重要性**: 高 importance (>0.7) 的记忆保留更久，优先检索

总共传递给 LLM 约 10-15 条记忆，保证 Token 可控。

#### 6.3 遗忘机制

- 每个 Agent 长期记忆上限：**100 条**
- 超过时，按 `importance × 时间衰减系数` 排序，删除最低分的
- 时间衰减：超过 3 个虚拟日（约 7 分钟真实时间）后，每天衰减 20%

---

### 7. LLM 接入

#### 7.1 DeepSeek 客户端

```python
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    model="deepseek-chat",          # DeepSeek Flash
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com/v1",
    temperature=0.8,
    timeout=5.0,                    # 5 秒超时
    max_retries=1,                  # 最多重试 1 次
    max_tokens=256,                 # 决策输出不需要太长
)
```

#### 7.2 Prompt 设计原则

- **结构化输出**: 要求 LLM 返回 JSON 格式（含 thought/action_type/action_detail/action_reason）
- **约束注入**: 在 Prompt 开头注入作息约束、地图边界规则
- **性格注入**: 用性格维度生成行为指南（如高外向: "你热衷社交，主动找人聊天"）
- **Few-shot 示例**: 每个 Prompt 附带 2 个正确格式的示例

---

### 8. WebSocket 双向通信协议

#### 8.1 后端 → 前端 (server push)

```json
{
  "type": "world_update",
  "virtual_time": "14:30",
  "virtual_day": 1,
  "tick": 120,
  "is_sleeping": false,
  "agents": [
    {
      "id": "agent_xiaoming", "name": "小明", "emoji": "👨‍🏫",
      "x": 3, "y": 5, "target_x": 3, "target_y": 4,
      "activity": "散步", "mood": 0.8, "energy": 0.6,
      "action_emoji": "🚶"
    }
  ],
  "events": [
    {"time": "14:30", "text": "小明在公园遇到了小红，聊了聊天气"}
  ],
  "metrics_snapshot": {
    "total_tokens": 15250,
    "avg_latency_ms": 210,
    "degradation_rate": 0.02
  }
}
```

#### 8.2 前端 → 后端 (client command)

```json
{"type": "command", "action": "pause"}
{"type": "command", "action": "resume"}
{"type": "command", "action": "set_speed", "value": 2.0}
{"type": "command", "action": "get_agent_detail", "agent_id": "agent_xiaoming"}
```

后端响应：
```json
{"type": "agent_detail", "agent": {...完整Agent数据含记忆+关系...}}
```

---

### 9. 前端可视化

#### 9.1 页面布局

```
┌──────────────────────────────────────────────────────┐
│  🏘️ AI Village    [🌍 世界] [📊 监测] [📋 全部日志]  │
├────────────────────┬──────────────┬──────────────────┤
│                    │              │                  │
│   2D Canvas 地图   │  Agent 详情  │  实时事件        │
│   600×600 px      │  250px 宽    │  250px 宽        │
│   网格 + 平滑动画  │              │                  │
│                    │              │                  │
├────────────────────┴──────────────┴──────────────────┤
│  [▶ 运行] [⏸ 暂停] [⏩ 2x] [🐢 0.5x]  Day 1 · ⏰ 14:30 │
└──────────────────────────────────────────────────────┘
```

#### 9.2 Canvas 地图渲染

- 每个格子 60×60 px
- 地点用不同底色：住宅=浅棕、公园=绿色、市场=橙色、咖啡馆=棕色、广场=浅蓝、喷泉=蓝色
- Agent 用圆形头像表示：40px 圆 + emoji + 名字缩写
- **平滑动画**: 收到新坐标后，Agent 在 300ms 内线性插值移动到目标格（requestAnimationFrame），不是瞬移
- 睡眠模式：整体降低亮度 + 月光覆盖层

#### 9.3 交互逻辑

- **点击 Agent**: 右侧面板显示该 Agent 详情（Profile / 心情精力条 / 最近记忆列表 / 人际关系雷达图 / 今日活动时间线）
- **点击空白格**: 右侧面板显示该格子的地点信息
- **悬停 Agent**: 显示 tooltip（名字 + 当前活动）
- **控制栏**: 暂停/运行/变速切换

---

### 10. 监测与评估体系

#### 层次 1: LangSmith 调用链追踪（可选）

通过环境变量 `LANGCHAIN_TRACING_V2=true` 自动启用。追踪每条 LangChain/LangGraph 调用链路，用于调试决策过程。

#### 层次 2: 运行时指标

每个 tick 自动采集（无需 LLM）：

| 指标 | 说明 |
|------|------|
| 决策耗时 | 每个 Agent 从 perceive 到 remember 的总耗时 |
| Token 消耗 | 本次 LLM 调用的 token 数 |
| 降级次数 | L2/L3 降级次数 |
| 社交次数 | 当天对话成功次数 |
| 唯一接触人数 | 当天互动过的不同 Agent 数 |
| 心情均值 | 所有 Agent 心情的平均值 |
| 活动熵值 | 衡量行为多样性（总是做同一件事=低熵） |

#### 层次 3: LLM-as-Judge 定期评估

每 20 tick 调用一次 LLM（用独立 Prompt），从 5 个维度打分 1-10：
- 角色一致性 / 社交合理性 / 记忆真实性 / 行为多样性 / 情感真实性

#### 层次 4: 前端监测面板

"📊 监测" 标签页展示：实时指标卡片 + Agent 评分排行 + 情绪波动图（Canvas 折线图）+ 最近评估报告

---

## 实现步骤（共 9 个阶段）

### 阶段 1: 项目骨架
- 目录结构、`requirements.txt`、`.env.example`
- `config.py`：读取环境变量
- `backend/main.py`：FastAPI 最小应用 + 挂载静态文件 + 生命期管理
- `frontend/index.html`：三标签页空壳

### 阶段 2: 世界引擎 + 地图
- `world/locations.py`：地点数据类 + 5 个地点的坐标范围
- `world/map.py`：网格数据类、碰撞检测、邻近查询
- `world/engine.py`：虚拟时钟 + asyncio tick 循环（先用假 Agent 验证）

### 阶段 3: Agent 系统
- `agents/personalities.py`：性格数据类 + 7 个预设
- `agents/routines.py`：作息约束表
- `agents/base_agent.py`：Agent 数据类 + 基础方法
- `agents/agent_manager.py`：注册、状态汇总
- `data/agents.json`：7 个 Agent 完整初始配置（含初始关系矩阵）

### 阶段 4: LLM + LangGraph
- `llm/client.py`：DeepSeek 客户端（含超时/重试/降级）
- `llm/prompts.py`：决策 Prompt（含约束注入 + few-shot）+ 对话 Prompt
- `graph/agent_graph.py`：5 节点 LangGraph（perceive→think→validate→act→remember）

### 阶段 5: 记忆系统
- `memory/store.py`：JSON 读写
- `memory/manager.py`：检索（时间+标签）+ 存储 + 遗忘

### 阶段 6: Agent 对话
- `graph/conversation_graph.py`：多轮对话子图
- 关系值更新 + 心情更新逻辑

### 阶段 7: API + WebSocket
- `api/routes.py`：REST 端点
- `api/websocket.py`：WebSocket 双向通信
- World Engine 与 WebSocket 广播对接

### 阶段 8: 前端可视化
- `js/websocket.js`：WebSocket 客户端
- `js/map.js`：Canvas 地图 + 平滑动画
- `js/agent_panel.js`：Agent 详情面板
- `js/event_log.js`：事件日志
- `css/style.css`：全局样式

### 阶段 9: 监测与评估
- `monitor/tracer.py`：LangSmith 配置
- `monitor/metrics.py`：指标采集
- `monitor/evaluator.py`：LLM-as-Judge
- `monitor/reporter.py`：报告生成
- `js/monitor_dashboard.js`：监测面板
- API 端点扩展

---

## 关键设计决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| Agent 并行 | asyncio.gather | 7 个 Agent 同时决策，tick 只等最慢的一个 |
| LLM 超时 | 5s + 1 次重试 | 保证 tick 循环不卡死 |
| 降级策略 | 三层 (正常→修正→纯规则) | 任何情况下系统都能继续运行 |
| 记忆存储 | JSON 文件 | 零依赖，直接可读，方便调试 |
| 对话机制 | 双向意愿匹配 | 避免"单人尬聊"，更真实 |
| 作息约束 | Prompt 注入而非硬编码 | 保留 LLM 灵活性，让行为更自然 |
| 地图 | 10×10 网格 | 一屏展示，逻辑简单 |
| Agent 数量 | 7 个 | 性格/职业多样性足够，API 开销可控 |
| 前端框架 | 纯 HTML/CSS/JS | 符合用户技术栈 |
| 页面结构 | 三标签页（世界/监测/日志） | 功能分区清晰 |
| LangSmith | 可选（环境变量） | 不强制依赖外部服务 |

---

## 验证方式

1. **阶段 1-2**: 启动服务，`/api/world` 返回地图和时间信息
2. **阶段 3**: `/api/agents` 返回 7 个 Agent 完整数据
3. **阶段 4**: 单 Agent 手动 tick，LLM 返回合理决策，超时时降级生效
4. **阶段 5**: tick 后 `data/memories/` 下有文件生成
5. **阶段 6**: 双向意愿匹配 → 对话产生 → 关系值变化
6. **阶段 7**: WebSocket 连接 + 双向通信正常
7. **阶段 8**: 浏览器看到地图、Agent 平滑移动、点击交互、控制栏生效
8. **阶段 9**: 监测面板显示实时指标，每 20 tick 自动评估

---

## 运行方式

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置
cp .env.example .env
# 编辑 .env 填入 DEEPSEEK_API_KEY=sk-xxx

# 3. 启动
python -m uvicorn backend.main:app --reload

# 4. 打开浏览器
# http://localhost:8000
```

---

## 实际实现说明（与规划的差异）

### 新增功能

| 功能 | 说明 |
|------|------|
| **存档系统** | `world/save_load.py` — 支持保存/加载/删除存档。前端弹窗选择继续或新游戏。每 30 秒自动存档。 |
| **REST 命令降级** | `POST /api/command/{action}` — WebSocket 未连接时，暂停/恢复通过 HTTP 降级发送 |
| **事件轮询兜底** | 前端每 3 秒通过 REST 拉取事件历史，WebSocket 断连也不丢事件 |
| **事件去重** | 前端 `event_log.js` 基于时间+内容去重，避免 WebSocket 和轮询产生重复 |
| **引擎默认暂停** | 启动后引擎 `paused=True`，等待用户点击 ▶ 运行 |
| **前端初始渲染** | 页面加载时先通过 REST API 渲染地图和 Agent，不依赖 WebSocket |

### 前端架构调整

- `app.js` — 主入口，负责初始化、存档弹窗、事件轮询、标签切换
- `websocket.js` — WebSocket 连接 + `window._wsSend` 返回值修复
- `event_log.js` — 带去重的事件日志
- `monitor_dashboard.js` — 监测面板，切换标签时自动拉取指标和评估
- `map.js` / `agent_panel.js` — Canvas 地图渲染和 Agent 详情

### 文件变动

| 文件 | 状态 |
|------|------|
| `backend/api/routes.py` | 已删除（端点合入 main.py） |
| `backend/world/save_load.py` | 新增（存档系统） |
| `backend/graph/agent_graph.py` | 集成记忆存储 + 对话触发 + 关系更新 |
| `backend/graph/conversation_graph.py` | 多轮对话 + 质量评估 + 关系更新 |
| `backend/world/engine.py` | 事件历史缓冲区 + 默认暂停 + 处理 Agent 结果生成事件 |
| `backend/main.py` | 存档 API + 事件 API + REST 命令端点 + 评估集成 |
| `frontend/js/*.js` | 全部重写，解决竞态和去重问题 |

### 前端关键设计

- **按钮状态**：由用户手动控制，WebSocket 消息不覆盖（避免暂停/恢复闪烁）
- **暂停时停止轮询**：`pollEvents` 和监测刷新在 `APP_STATE.running=false` 时立即停止
- **存档弹窗**：检测到存档时显示模态框，阻塞初始化直到用户选择

### 更新后的项目结构

```
drill/
├── backend/
│   ├── main.py                  # FastAPI 入口 + 全部 API 端点
│   ├── config.py                # 全局配置
│   ├── world/
│   │   ├── engine.py            # 世界引擎（默认暂停、事件历史）
│   │   ├── map.py               # 2D 网格地图
│   │   ├── locations.py         # 地点定义
│   │   └── save_load.py         # 存档系统 🆕
│   ├── agents/
│   │   ├── base_agent.py        # Agent 数据类
│   │   ├── agent_manager.py     # Agent 管理器
│   │   ├── personalities.py     # 性格系统
│   │   └── routines.py          # 日常作息
│   ├── llm/
│   │   ├── client.py            # DeepSeek 客户端
│   │   └── prompts.py           # Prompt 模板
│   ├── graph/
│   │   ├── agent_graph.py       # LangGraph 决策流
│   │   └── conversation_graph.py # 对话模块
│   ├── memory/
│   │   ├── store.py             # JSON 存储
│   │   └── manager.py           # 记忆管理器
│   ├── api/
│   │   └── websocket.py         # WebSocket 双向通信
│   ├── monitor/
│   │   ├── metrics.py           # 指标采集
│   │   ├── evaluator.py         # LLM-as-Judge
│   │   └── reporter.py          # 报告生成
│   └── data/
│       ├── agents.json          # Agent 配置
│       ├── skills_pool.json     # 技能池
│       ├── savegame.json        # 存档文件 🆕
│       ├── memories/            # 记忆文件
│       └── evaluations/         # 评估报告
├── frontend/
│   ├── index.html               # 主页面（含存档弹窗）🆕
│   ├── css/style.css            # 样式（含弹窗）🆕
│   └── js/
│       ├── app.js               # 主入口（存档+轮询+去重）🆕
│       ├── map.js               # Canvas 地图
│       ├── agent_panel.js       # Agent 详情
│       ├── event_log.js         # 事件日志（去重）🆕
│       ├── monitor_dashboard.js # 监测面板
│       └── websocket.js         # WebSocket 客户端
├── PLAN.md                      # 本文件
├── README.md
├── requirements.txt
├── .env.example
└── .gitignore
```

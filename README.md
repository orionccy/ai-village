# 🏘️ AI Village — 多智能体虚拟小镇

7 个 AI Agent 在虚拟小镇中自主生活、社交、协作。每个 Agent 由 LLM 驱动，拥有独立的性格、技能、记忆和人际关系，在 2D 地图上实时移动和互动。

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置 API Key
cp .env.example .env
# 编辑 .env，填入 DEEPSEEK_API_KEY=sk-xxx

# 3. 启动
python -m uvicorn backend.main:app --reload

# 4. 浏览器打开 http://localhost:8000
```

## Agent 阵容

| 头像 | 名字 | 职业 | 性格 | 核心技能 |
|------|------|------|------|----------|
| 👨‍🏫 | 小明 | 教师 | 热情开朗 | 教学、沟通、园艺 |
| 👩‍🌾 | 小红 | 花店店主 | 社交达人 | 花艺、社交、手工、商业 |
| 👴 | 老王 | 退休老人 | 安静规律 | 下棋、养生、木工、讲故事 |
| 👩‍🎓 | 阿花 | 学生 | 好奇随性 | 摄影、音乐、学习、编程 |
| 👨‍🍳 | 小李 | 面包师 | 勤劳稳重 | 烘焙、烹饪、记账 |
| 👨‍⚕️ | 老张 | 医生 | 稳重热心 | 诊断、急救、养生、沟通 |
| 👩‍🎨 | 小美 | 艺术家 | 内向敏感 | 绘画、创意、花艺、摄影 |

## 功能特性

- **LLM 驱动决策** — LangGraph 工作流：感知 → 思考(LLM) → 校验 → 执行 → 记忆
- **技能系统** — 21 种技能池，Agent 各有所长，技能互补驱动协作
- **实时对话** — Agent 相遇时自动多轮对话，话题受性格和记忆影响
- **关系网络** — 初始关系 + 对话质量动态调整，双向更新
- **记忆系统** — 短期/长期记忆，自动检索相关记忆辅助 LLM 决策
- **2D 可视化** — Canvas 地图实时渲染，Agent 平滑移动动画
- **监测面板** — 实时指标 + LLM-as-Judge 每 20 tick 自动评估
- **存档系统** — 自动存档，下次打开可选继续或新游戏
- **降级策略** — 三层保障，LLM 不可用时自动切换规则模式

## 技术栈

| 层 | 技术 |
|----|------|
| 后端框架 | FastAPI + Uvicorn |
| Agent 编排 | LangChain + LangGraph |
| LLM | DeepSeek Flash |
| 实时通信 | WebSocket |
| 前端 | HTML5 Canvas + 原生 JS |
| 存储 | JSON 文件 |

## 项目结构

```
drill/
├── backend/
│   ├── main.py              # FastAPI 入口 + 全部 API 端点
│   ├── config.py            # 全局配置
│   ├── world/               # 世界引擎 + 地图 + 地点 + 存档
│   ├── agents/              # Agent 系统 (性格/技能/作息)
│   ├── llm/                 # LLM 客户端 + Prompt 模板
│   ├── graph/               # LangGraph 决策流 + 对话模块
│   ├── memory/              # 记忆 JSON 存储 + 检索
│   ├── api/                 # WebSocket 双向通信
│   ├── monitor/             # 指标采集 + LLM评估 + 报告
│   └── data/                # Agent配置 + 技能池 + 记忆 + 存档
├── frontend/
│   ├── index.html           # 三标签页主界面 (世界/监测/日志)
│   ├── css/style.css        # 全局样式 + 存档弹窗
│   └── js/                  # 前端脚本 (地图/面板/日志/监测)
├── PLAN.md                  # 完整设计文档
├── requirements.txt
└── .env.example
```

## 详细文档

完整架构设计、决策流程、技能系统、监测体系参见 [PLAN.md](PLAN.md)。

## License

MIT

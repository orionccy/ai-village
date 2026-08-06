"""
============================================================
AI Village — FastAPI 主入口
============================================================
这是整个项目的启动文件。它负责:
1. 创建 FastAPI 应用实例
2. 挂载前端静态文件目录
3. 管理世界引擎的生命周期（启动时开始 tick 循环，关闭时停止）
4. 注册 API 路由和 WebSocket 端点
5. 提供首页 HTML

启动方式:
    python -m uvicorn backend.main:app --reload
    然后访问 http://localhost:8000
============================================================
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.config import FRONTEND_DIR, LLM_ENABLED
from backend.world.engine import WorldEngine
from backend.agents.agent_manager import AgentManager
from backend.graph.agent_graph import run_agent_tick
from backend.monitor.metrics import metrics_collector
from backend.monitor.evaluator import run_evaluation
from backend.monitor.reporter import report_generator
from backend.api.websocket import router as ws_router
from backend.world.save_load import save_exists, save_game, load_game, delete_save

# ============================================================
# 日志配置
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("ai_village")

# ============================================================
# 应用生命周期管理
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI 生命周期管理器。

    启动时 (yield 之前):
        - 初始化世界引擎
        - 启动后台 tick 循环

    关闭时 (yield 之后):
        - 停止世界引擎
        - 保存所有 Agent 的记忆到磁盘
    """
    logger.info("=" * 50)
    logger.info("🏘️  AI Village 启动中...")
    logger.info("=" * 50)

    # ---- 初始化 Agent 管理器 ----
    agent_manager = AgentManager()
    agent_manager.load_from_json()
    app.state.agent_manager = agent_manager

    # ---- 初始化世界引擎 ----
    world_engine = WorldEngine()
    app.state.world_engine = world_engine

    # 将 Agent 管理器注入引擎
    world_engine.agent_manager = agent_manager

    # 注册 Agent tick 回调：引擎每 tick 调用此函数处理每个 Agent 的决策
    async def agent_tick_callback(agent_id: str, world_ctx: dict) -> dict:
        agent = agent_manager.get(agent_id)
        if agent is None:
            return {}

        result = await run_agent_tick(agent, agent_manager, world_ctx)

        # 记录指标
        metrics_collector.record(
            agent_id=agent_id,
            tick=world_ctx.get("tick", 0),
            action_type=result.get("action_type", ""),
            degrade_level=result.get("degrade_level", 0),
            new_memory=result.get("new_memory", ""),
            mood=agent.mood,
        )

        # 每 20 tick 运行 LLM 评估
        tick = world_ctx.get("tick", 0)
        if tick > 0 and tick % 20 == 0 and agent_id == agent_manager.get_all_ids()[-1]:
            # 只在最后一个 Agent 处理完后运行一次评估
            asyncio.create_task(_run_eval_task(tick))

        return result

    async def _run_eval_task(tick: int):
        """后台运行评估任务。"""
        try:
            logger.info(f"📊 运行 Tick {tick} 评估...")
            evals = await run_evaluation(agent_manager, metrics_collector, tick)
            report_generator.add_report(tick, evals)
            latest = report_generator.get_latest()
            if latest:
                logger.info(f"📊 评估完成: 综合 {latest['overall']}/10")
        except Exception as e:
            logger.error(f"评估失败: {e}")

    world_engine.set_agent_tick_callback(agent_tick_callback)

    # 启动后台 tick 循环（asyncio Task）
    tick_task = asyncio.create_task(world_engine.run())

    logger.info(f"🤖 LLM: {'已启用 (DeepSeek)' if LLM_ENABLED else '未配置 — 将使用规则降级模式'}")
    logger.info("✅ AI Village 已就绪")
    logger.info("   打开浏览器访问: http://localhost:8000")
    logger.info("")

    yield  # ← 应用在此运行

    # ========== 关闭逻辑 ==========
    logger.info("🛑 AI Village 正在关闭...")

    # 停止世界引擎
    world_engine.stop()
    await tick_task

    logger.info("👋 AI Village 已关闭")


# ============================================================
# FastAPI 应用实例
# ============================================================

app = FastAPI(
    title="AI Village",
    description="多智能体虚拟小镇 — 7 个 AI Agent 在小镇中生活、社交、协作",
    version="0.1.0",
    lifespan=lifespan,
)

# ============================================================
# 静态文件挂载
# ============================================================

# 将 frontend 目录挂载为静态文件服务
# 访问 /css/style.css → frontend/css/style.css
# 访问 /js/app.js     → frontend/js/app.js
frontend_path = Path(FRONTEND_DIR)
if frontend_path.exists():
    app.mount("/css", StaticFiles(directory=str(frontend_path / "css")), name="css")
    app.mount("/js", StaticFiles(directory=str(frontend_path / "js")), name="js")
    logger.info(f"📁 静态文件目录已挂载: {frontend_path}")
else:
    logger.warning(f"⚠️  前端目录不存在: {frontend_path}")


# ============================================================
# 路由
# ============================================================

@app.get("/")
async def root():
    """
    首页 — 返回 AI Village 主页面。
    使用 FileResponse 直接返回 HTML 文件。
    """
    index_path = frontend_path / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return {"message": "AI Village API is running. Frontend not found."}


@app.get("/api/health")
async def health_check():
    """
    健康检查端点。
    用于确认后端服务是否正常运行。
    """
    engine = app.state.world_engine if hasattr(app.state, 'world_engine') else None
    return {
        "status": "ok",
        "version": "0.1.0",
        "llm_enabled": LLM_ENABLED,
        "tick": engine.tick_count if engine else 0,
        "virtual_time": engine.clock.time_str if engine else "06:00",
    }


@app.get("/api/world")
async def get_world_state():
    """
    获取当前世界状态。
    前端通过此端点获取初始状态。
    """
    engine: WorldEngine = app.state.world_engine
    return {
        "day": engine.clock.day,
        "time": engine.clock.time_str,
        "time_period": engine.clock.get_time_period(),
        "tick": engine.tick_count,
        "is_sleeping": engine.clock.is_sleep_time,
        "running": engine.running,
        "paused": engine.paused,
        "speed": engine.speed_multiplier,
        "stats": engine.get_stats(),
    }


@app.get("/api/agents")
async def get_agents():
    """
    获取所有 Agent 的列表和基本信息。
    用于前端初始化和 Agent 面板。
    """
    agent_manager: AgentManager = app.state.agent_manager
    return {
        "count": agent_manager.agent_count,
        "agents": agent_manager.get_all_dicts(),
    }


@app.get("/api/agents/{agent_id}")
async def get_agent_detail(agent_id: str):
    """
    获取某个 Agent 的详细信息（含记忆、关系等）。
    用于 Agent 详情面板。
    """
    agent_manager: AgentManager = app.state.agent_manager
    agent = agent_manager.get(agent_id)
    if not agent:
        return {"error": "Agent not found"}, 404
    return agent.to_detail_dict()


@app.get("/api/metrics")
async def get_metrics():
    """获取实时运行指标。"""
    engine = app.state.world_engine
    agent_manager = app.state.agent_manager
    summary = metrics_collector.get_summary()

    from backend.llm.client import get_token_stats
    token_stats = get_token_stats()

    return {
        "tick": engine.tick_count,
        "day": engine.clock.day,
        "time": engine.clock.time_str,
        "running": engine.running,
        "total_tokens": token_stats["total_tokens"],
        "total_llm_calls": token_stats["total_calls"],
        "avg_latency_ms": engine.avg_latency_ms,
        "agent_count": agent_manager.agent_count,
        "avg_mood": round(agent_manager.avg_mood, 2),
        "metrics_summary": summary,
    }


@app.post("/api/command/{action}")
async def post_command(action: str):
    """
    REST 命令端点 — WebSocket 未连接时的降级通道。
    支持: pause, resume
    """
    engine: WorldEngine = app.state.world_engine
    if action == "pause":
        engine.pause()
        return {"status": "paused"}
    elif action == "resume":
        engine.resume()
        return {"status": "resumed"}
    else:
        return {"error": "unknown command"}, 400


@app.get("/api/events")
async def get_events():
    """获取最近事件（从历史记录，不清空）。"""
    engine = app.state.world_engine
    history = [e.to_dict() for e in engine.event_history[-50:]]
    return {"events": history}


@app.get("/api/evaluations")
async def get_evaluations():
    """获取评估报告列表。"""
    latest = report_generator.get_latest()
    return {
        "latest": latest,
        "total_reports": len(report_generator.reports),
    }


# ============================================================
# 存档 API
# ============================================================

@app.get("/api/save/check")
async def check_save():
    """检查是否存在存档。"""
    return {"exists": save_exists()}


@app.post("/api/save")
async def api_save():
    """保存游戏。"""
    engine: WorldEngine = app.state.world_engine
    agent_manager: AgentManager = app.state.agent_manager
    return save_game(engine, agent_manager)


@app.post("/api/load")
async def api_load():
    """加载存档。"""
    engine: WorldEngine = app.state.world_engine
    agent_manager: AgentManager = app.state.agent_manager
    return load_game(engine, agent_manager)


@app.post("/api/save/delete")
async def api_delete_save():
    """删除存档（开始新游戏）。"""
    return delete_save()


app.include_router(ws_router)


# ============================================================
# 直接运行支持
# ============================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)

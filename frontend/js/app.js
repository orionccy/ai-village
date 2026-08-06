/**
 * app.js — AI Village 主入口（修复版）
 */
const APP_STATE = {
    activeTab: 'world', running: false, speed: 1.0,
    connected: false, day: 1, time: '06:00', tick: 0, totalTokens: 0,
};

// ============================================================
// 标签切换
// ============================================================
function switchTab(tabName) {
    APP_STATE.activeTab = tabName;
    document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
    const c = document.getElementById('tab-' + tabName);
    if (c) c.classList.add('active');
    const b = document.querySelector('[data-tab="' + tabName + '"]');
    if (b) b.classList.add('active');

    // 切换到监测页时自动刷新
    if (tabName === 'monitor' && typeof refreshMonitor === 'function') {
        refreshMonitor();
    }
}

// ============================================================
// 控制栏 - 带 REST 降级
// ============================================================
async function togglePlay() {
    const wasRunning = APP_STATE.running;
    const newRunning = !wasRunning;
    const action = newRunning ? 'resume' : 'pause';

    // 1. 先通过 WebSocket 发送
    let sent = false;
    if (window._wsSend) {
        sent = window._wsSend({ type: 'command', action: action });
    }

    // 2. WebSocket 没连上？用 REST 降级
    if (!sent) {
        try {
            await fetch('/api/command/' + action, { method: 'POST' });
        } catch (e) {
            console.error('命令发送失败:', e);
            return;
        }
    }

    // 3. 更新本地状态和 UI
    APP_STATE.running = newRunning;
    updatePlayButton();

    // 暂停时清理监测定时器
    if (!newRunning && typeof _monitorTimer !== 'undefined' && _monitorTimer) {
        clearInterval(_monitorTimer);
        _monitorTimer = null;
    }
}

function updatePlayButton() {
    const btn = document.getElementById('btn-play');
    if (APP_STATE.running) {
        btn.innerHTML = '⏸ 暂停';
        btn.classList.add('active');
    } else {
        btn.innerHTML = '▶ 运行';
        btn.classList.remove('active');
    }
}

async function setSpeed(s) {
    APP_STATE.speed = s;
    document.querySelectorAll('.speed-btn').forEach(b => {
        b.classList.toggle('active', parseFloat(b.dataset.speed) === s);
    });
    if (window._wsSend) window._wsSend({ type: 'command', action: 'set_speed', value: s });
}

function clearLogs() {
    document.getElementById('full-log-list').innerHTML = '<p class="placeholder-text">日志已清空</p>';
}

// ============================================================
// 连接状态
// ============================================================
function updateConnectionStatus(connected) {
    APP_STATE.connected = connected;
    const dot = document.getElementById('connection-status');
    const text = document.getElementById('status-text');
    if (connected) {
        dot.className = 'status-dot connected';
        text.textContent = '已连接';
    }
}

// ============================================================
// 核心回调：来自 WebSocket 或 REST 轮询
// ============================================================
function onWorldUpdate(data) {
    if (!data || !data.agents) return;

    // ==========================================
    // 1. 事件日志 — 最先处理，不依赖 DOM/Canvas
    // ==========================================
    if (data.events && data.events.length > 0 && typeof addEvents === 'function') {
        try { addEvents(data.events); } catch(e) { console.error('addEvents error:', e); }
    }

    // ==========================================
    // 2. 时间/状态栏
    // ==========================================
    APP_STATE.day = data.virtual_day || APP_STATE.day;
    APP_STATE.time = data.virtual_time || APP_STATE.time;
    APP_STATE.tick = data.tick || APP_STATE.tick;

    // 注意: 不同步 data.paused 到按钮状态
    // 按钮由用户手动控制（togglePlay），WebSocket 消息不覆盖

    try {
        const dd = document.getElementById('day-display');
        const td = document.getElementById('time-display');
        const tk = document.getElementById('tick-display');
        if (dd) dd.textContent = 'Day ' + APP_STATE.day;
        if (td) td.textContent = '⏰ ' + APP_STATE.time;
        if (tk) tk.textContent = 'Tick: ' + APP_STATE.tick;
    } catch(e) { console.error('status bar error:', e); }

    if (data.metrics_snapshot) {
        APP_STATE.totalTokens = data.metrics_snapshot.total_tokens || 0;
        const tokenEl = document.getElementById('token-display');
        if (tokenEl) tokenEl.textContent = '🪙 Token: ' + APP_STATE.totalTokens.toLocaleString();
    }

    // ==========================================
    // 3. 地图 — 最后处理
    // ==========================================
    if (typeof updateMap === 'function') {
        try { updateMap(data.agents, data.is_sleeping); } catch(e) { console.error('updateMap error:', e); }
    }
}

// ============================================================
// 初始化
// ============================================================
// ============================================================
// 存档系统
// ============================================================

async function continueGame() {
    document.getElementById('save-modal').style.display = 'none';
    await fetch('/api/load', { method: 'POST' });
    await _doLoadInitialState();  // 跳过存档检测，直接加载
}

async function newGame() {
    document.getElementById('save-modal').style.display = 'none';
    await fetch('/api/save/delete', { method: 'POST' });
    await _doLoadInitialState();  // 跳过存档检测，直接加载
}

async function loadInitialState() {
    // 检查存档
    try {
        const check = await fetch('/api/save/check');
        const { exists } = await check.json();
        if (exists) {
            // 有存档 → 弹窗让用户选择
            const saveResp = await fetch('/api/world');
            const saveInfo = await saveResp.json();
            // 存档的世界状态在 savegame.json 中，这里用 REST 拿不到
            // 用 /api/save/check 只告诉我们存在，具体信息需要额外接口
            document.getElementById('save-modal-info').textContent =
                '检测到存档，是否继续上次的游戏？';
            document.getElementById('save-modal').style.display = 'flex';
            // 先连接 WebSocket（等用户选择后再加载状态）
            if (typeof connectWebSocket === 'function' && !APP_STATE.connected) {
                connectWebSocket();
            }
            return;
        }
    } catch (e) { /* ignore */ }

    // 无存档 → 直接加载
    await _doLoadInitialState();
}

async function _doLoadInitialState() {
    try {
        const [worldResp, agentsResp] = await Promise.all([
            fetch('/api/world'),
            fetch('/api/agents'),
        ]);
        const world = await worldResp.json();
        const agentsData = await agentsResp.json();

        console.log('[Init] Day', world.day, world.time, 'Tick', world.tick);

        APP_STATE.running = !world.paused;
        updatePlayButton();

        onWorldUpdate({
            virtual_time: world.time,
            virtual_day: world.day,
            tick: world.tick,
            is_sleeping: world.is_sleeping,
            agents: agentsData.agents,
            events: [{ time: world.time, text: '🌅 欢迎来到 AI Village！点击 ▶ 运行 开始模拟' }],
            metrics_snapshot: world.stats || {},
        });
    } catch (err) {
        console.error('[Init] REST 失败:', err);
    }

    console.log('[Init] 连接 WebSocket...');
    if (typeof connectWebSocket === 'function' && !APP_STATE.connected) {
        connectWebSocket();
    }
}

// ============================================================
// 自动存档 — 每 30 秒保存一次
// ============================================================
setInterval(async () => {
    if (APP_STATE.running) {
        try { await fetch('/api/save', { method: 'POST' }); } catch (e) { /* ignore */ }
    }
}, 30000);

// ============================================================
// 事件轮询兜底 — 每 3 秒 REST 拉事件（与 WebSocket 互补）
// ============================================================
let _seenEventKeys = new Set();

function _eventKey(e) { return e.time + '|' + e.text.slice(0, 30); }

async function pollEvents() {
    if (!APP_STATE.running) return;  // 暂停时不拉
    try {
        const resp = await fetch('/api/events');
        const data = await resp.json();
        const events = data.events || [];
        const newEvents = events.filter(e => {
            const k = _eventKey(e);
            if (_seenEventKeys.has(k)) return false;
            _seenEventKeys.add(k);
            return true;
        });
        if (newEvents.length > 0 && typeof addEvents === 'function') {
            addEvents(newEvents);
        }
    } catch(e) { /* ignore */ }
}

document.addEventListener('DOMContentLoaded', () => {
    loadInitialState();
    setInterval(pollEvents, 3000);  // 始终每3秒拉一次
});

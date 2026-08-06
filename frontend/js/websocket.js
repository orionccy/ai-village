/**
 * websocket.js — WebSocket 客户端 + REST 轮询降级
 */
let ws = null;
let reconnectCount = 0;
const MAX_RECONNECT = 5;

function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = `${protocol}//${window.location.host}/ws`;
    console.log('[WS] 连接:', url);

    try {
        ws = new WebSocket(url);
    } catch (err) {
        console.error('[WS] 创建失败:', err);
        fallbackToPolling();
        return;
    }

    ws.onopen = () => {
        console.log('[WS] 已连接');
        reconnectCount = 0;
        updateConnectionStatus(true);
        // 清除轮询
        if (window._pollTimer) { clearInterval(window._pollTimer); window._pollTimer = null; }
    };

    ws.onmessage = (event) => {
        try {
            handleMessage(JSON.parse(event.data));
        } catch (err) {
            console.error('[WS] 解析失败:', err);
        }
    };

    ws.onclose = (event) => {
        console.log('[WS] 断开 (code:', event.code, ')');
        updateConnectionStatus(false);
        if (reconnectCount < MAX_RECONNECT) {
            reconnectCount++;
            console.log('[WS] 3s后重连...');
            setTimeout(connectWebSocket, 3000);
        } else {
            console.log('[WS] 重连失败，切换到轮询模式');
            fallbackToPolling();
        }
    };

    ws.onerror = () => {
        // onclose 会接着触发，这里只记录
        console.warn('[WS] 连接错误');
    };
}

/** WebSocket 失败时用 REST 轮询兜底 */
function fallbackToPolling() {
    console.log('[Poll] 启动 HTTP 轮询 (每2秒)');
    updateConnectionStatus(false);
    document.getElementById('status-text').textContent = '轮询中';

    if (window._pollTimer) clearInterval(window._pollTimer);

    async function poll() {
        try {
            const resp = await fetch('/api/world');
            const world = await resp.json();
            const agentsResp = await fetch('/api/agents');
            const agentsData = await agentsResp.json();

            // 模拟 world_update 消息格式
            onWorldUpdate({
                virtual_time: world.time,
                virtual_day: world.day,
                tick: world.tick,
                is_sleeping: world.is_sleeping,
                agents: agentsData.agents,
                events: [],
                metrics_snapshot: world.stats || {},
            });
        } catch (err) {
            console.error('[Poll] 请求失败:', err);
        }
    }

    poll(); // 立即执行一次
    window._pollTimer = setInterval(poll, 2000);
}

function handleMessage(msg) {
    switch (msg.type) {
        case 'world_update':
            if (typeof onWorldUpdate === 'function') onWorldUpdate(msg);
            break;
        case 'agent_detail':
            if (typeof showAgentDetail === 'function') showAgentDetail(msg.agent);
            break;
        case 'evaluation':
            if (typeof showEvaluation === 'function') showEvaluation(msg);
            break;
    }
}

window._wsSend = function(data) {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify(data));
        return true;
    }
    console.warn('[WS] 未连接，无法发送:', data);
    return false;  // ← 告诉调用方：没发出去！
};

// 心跳
setInterval(() => {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'ping' }));
    }
}, 30000);

// 注意：不在此处自动连接。
// 由 app.js 在 DOMContentLoaded 之后调用 connectWebSocket()，
// 确保所有依赖函数（如 onWorldUpdate）已就绪。

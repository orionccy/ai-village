/**
 * ============================================================
 * map.js — Canvas 2D 地图渲染
 * ============================================================
 * 职责:
 * - 绘制 10×10 网格地图
 * - 渲染地点底色和图标
 * - 渲染 Agent 圆形头像 + 名字
 * - 平滑动画插值 (requestAnimationFrame)
 * - 点击 Agent → 请求详情
 * - 悬停 tooltip
 * ============================================================
 */

// ============================================================
// 地图配置
// ============================================================

const CELL_SIZE = 60;
const MAP_SIZE = 10;
const AGENT_RADIUS = 22;
const ANIMATION_DURATION = 300; // ms

// 地点颜色映射
const LOCATION_COLORS = {
    '住宅区 A': '#c9a96e',
    '住宅区 B': '#c9a96e',
    '住宅区 C': '#c9a96e',
    '住宅区 D': '#c9a96e',
    '公园': '#4caf50',
    '市场': '#ff9800',
    '咖啡馆': '#795548',
    '广场': '#5c6bc0',
    '喷泉': '#42a5f5',
    '空地': '#2a2a2a',
};

// 地点 emoji 映射
const LOCATION_EMOJI = {
    '住宅区 A': '🏠', '住宅区 B': '🏠', '住宅区 C': '🏠', '住宅区 D': '🏠',
    '公园': '🌳', '市场': '🏪', '咖啡馆': '☕', '广场': '🎨', '喷泉': '⛲',
};

// ============================================================
// 地图状态
// ============================================================

let canvas, ctx;
let agentsData = [];
let agentTargets = {};  // {agent_id: {x, y}} 用于动画
let animationId = null;
let lastTickTime = 0;

// 预定义的地点网格 (对应规划文档中的坐标)
const locationGrid = buildLocationGrid();

function buildLocationGrid() {
    const grid = Array.from({length: MAP_SIZE}, () => Array(MAP_SIZE).fill('空地'));
    // 住宅区 A
    for (let y = 0; y <= 1; y++) for (let x = 0; x <= 2; x++) grid[y][x] = '住宅区 A';
    // 住宅区 B
    for (let y = 3; y <= 4; y++) for (let x = 1; x <= 2; x++) grid[y][x] = '住宅区 B';
    // 住宅区 C
    for (let y = 6; y <= 7; y++) for (let x = 0; x <= 1; x++) grid[y][x] = '住宅区 C';
    // 住宅区 D
    for (let y = 6; y <= 7; y++) for (let x = 8; x <= 9; x++) grid[y][x] = '住宅区 D';
    // 公园
    for (let y = 0; y <= 2; y++) for (let x = 4; x <= 5; x++) grid[y][x] = '公园';
    // 市场
    for (let y = 0; y <= 1; y++) for (let x = 7; x <= 8; x++) grid[y][x] = '市场';
    // 咖啡馆
    for (let y = 3; y <= 4; y++) for (let x = 7; x <= 8; x++) grid[y][x] = '咖啡馆';
    // 广场
    for (let x = 4; x <= 5; x++) grid[4][x] = '广场';
    // 喷泉
    for (let y = 7; y <= 8; y++) for (let x = 4; x <= 5; x++) grid[y][x] = '喷泉';
    return grid;
}

// ============================================================
// 初始化
// ============================================================

document.addEventListener('DOMContentLoaded', () => {
    canvas = document.getElementById('world-canvas');
    if (!canvas) return;
    ctx = canvas.getContext('2d');

    // 点击事件
    canvas.addEventListener('click', (e) => {
        const rect = canvas.getBoundingClientRect();
        const mx = e.clientX - rect.left;
        const my = e.clientY - rect.top;
        handleClick(mx, my);
    });

    // 悬停事件
    canvas.addEventListener('mousemove', (e) => {
        const rect = canvas.getBoundingClientRect();
        const mx = e.clientX - rect.left;
        const my = e.clientY - rect.top;
        handleHover(mx, my);
    });

    // 初始绘制
    drawMap();
    // 启动动画循环
    requestAnimationFrame(animationLoop);
});

// ============================================================
// 绘制
// ============================================================

function drawMap() {
    if (!ctx) return;
    ctx.clearRect(0, 0, 600, 600);

    // 1. 绘制网格和地点底色
    for (let y = 0; y < MAP_SIZE; y++) {
        for (let x = 0; x < MAP_SIZE; x++) {
            const locName = locationGrid[y][x];
            const color = LOCATION_COLORS[locName] || '#2a2a2a';

            // 填充
            ctx.fillStyle = color;
            ctx.fillRect(x * CELL_SIZE, y * CELL_SIZE, CELL_SIZE, CELL_SIZE);

            // 网格线
            ctx.strokeStyle = 'rgba(255,255,255,0.05)';
            ctx.strokeRect(x * CELL_SIZE, y * CELL_SIZE, CELL_SIZE, CELL_SIZE);

            // 地点 emoji（放在每个地点的中心格）
            const emoji = LOCATION_EMOJI[locName];
            if (emoji && isLocationCenter(x, y, locName)) {
                ctx.font = '20px sans-serif';
                ctx.textAlign = 'center';
                ctx.textBaseline = 'middle';
                ctx.fillText(emoji, x * CELL_SIZE + CELL_SIZE / 2, y * CELL_SIZE + CELL_SIZE / 2);
            }
        }
    }

    // 2. 绘制 Agent
    for (const agent of agentsData) {
        drawAgent(agent);
    }
}

function isLocationCenter(x, y, locName) {
    // 只在每个地点的中心格子绘制 emoji
    const centers = {
        '住宅区 A': [1, 0], '住宅区 B': [1, 3], '住宅区 C': [0, 6], '住宅区 D': [8, 6],
        '公园': [4, 1], '市场': [7, 0], '咖啡馆': [7, 3], '广场': [4, 4], '喷泉': [4, 7],
    };
    const c = centers[locName];
    return c && c[0] === x && c[1] === y;
}

function drawAgent(agent) {
    const target = agentTargets[agent.id];
    const displayX = target ? target.x * CELL_SIZE + CELL_SIZE / 2 : agent.x * CELL_SIZE + CELL_SIZE / 2;
    const displayY = target ? target.y * CELL_SIZE + CELL_SIZE / 2 : agent.y * CELL_SIZE + CELL_SIZE / 2;

    // 阴影
    ctx.beginPath();
    ctx.arc(displayX, displayY + 2, AGENT_RADIUS, 0, Math.PI * 2);
    ctx.fillStyle = 'rgba(0,0,0,0.3)';
    ctx.fill();

    // 圆形背景
    ctx.beginPath();
    ctx.arc(displayX, displayY, AGENT_RADIUS, 0, Math.PI * 2);

    // 根据心情设置颜色
    const mood = agent.mood || 0.5;
    const r = Math.floor(255 * (1 - mood));
    const g = Math.floor(100 + 155 * mood);
    const b = Math.floor(80);
    ctx.fillStyle = `rgb(${r},${g},${b})`;
    ctx.fill();
    ctx.strokeStyle = '#fff';
    ctx.lineWidth = 2;
    ctx.stroke();

    // Emoji
    ctx.font = '20px sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(agent.emoji || '👤', displayX, displayY - 2);

    // 名字标签
    ctx.font = '10px "Microsoft YaHei", sans-serif';
    ctx.fillStyle = '#fff';
    ctx.fillText(agent.name, displayX, displayY + AGENT_RADIUS + 12);
}

// ============================================================
// 交互
// ============================================================

function handleClick(mx, my) {
    const gx = Math.floor(mx / CELL_SIZE);
    const gy = Math.floor(my / CELL_SIZE);

    // 查找点击的 Agent
    for (const agent of agentsData) {
        const ax = agent.x, ay = agent.y;
        const cx = ax * CELL_SIZE + CELL_SIZE / 2;
        const cy = ay * CELL_SIZE + CELL_SIZE / 2;
        const dist = Math.sqrt((mx - cx) ** 2 + (my - cy) ** 2);
        if (dist <= AGENT_RADIUS + 4) {
            // 通过 WebSocket 请求 Agent 详情
            if (window._wsSend) {
                window._wsSend({ type: 'get_agent_detail', agent_id: agent.id });
            }
            return;
        }
    }

    // 点击了空地
    const locName = locationGrid[gy]?.[gx] || '空地';
    if (typeof showLocationInfo === 'function') {
        showLocationInfo(gx, gy, locName);
    }
}

function handleHover(mx, my) {
    const tooltip = document.getElementById('map-tooltip');
    if (!tooltip) return;

    let found = false;
    for (const agent of agentsData) {
        const cx = agent.x * CELL_SIZE + CELL_SIZE / 2;
        const cy = agent.y * CELL_SIZE + CELL_SIZE / 2;
        const dist = Math.sqrt((mx - cx) ** 2 + (my - cy) ** 2);
        if (dist <= AGENT_RADIUS + 4) {
            tooltip.textContent = `${agent.name} — ${agent.activity}`;
            tooltip.style.left = (mx + 12) + 'px';
            tooltip.style.top = (my - 20) + 'px';
            tooltip.classList.remove('hidden');
            found = true;
            break;
        }
    }

    if (!found) {
        tooltip.classList.add('hidden');
    }
}

// ============================================================
// 更新与动画
// ============================================================

/**
 * 收到世界更新时调用。
 * @param {Array} agents - Agent 数据数组
 * @param {boolean} isSleeping - 是否睡眠中
 */
function updateMap(agents, isSleeping) {
    if (!agents) return;

    // 记录旧位置用于动画
    for (const oldAgent of agentsData) {
        if (!agentTargets[oldAgent.id]) {
            agentTargets[oldAgent.id] = { x: oldAgent.x, y: oldAgent.y, startX: oldAgent.x, startY: oldAgent.y };
        }
    }

    // 更新目标位置
    for (const newAgent of agents) {
        const old = agentsData.find(a => a.id === newAgent.id);
        if (old && (old.x !== newAgent.x || old.y !== newAgent.y)) {
            agentTargets[newAgent.id] = {
                x: newAgent.x, y: newAgent.y,
                startX: old.x, startY: old.y,
                startTime: performance.now(),
            };
        } else if (!old) {
            agentTargets[newAgent.id] = {
                x: newAgent.x, y: newAgent.y,
                startX: newAgent.x, startY: newAgent.y,
                startTime: performance.now(),
            };
        }
    }

    agentsData = agents;
    lastTickTime = performance.now();
    drawMap();
}

/**
 * 动画循环 — 在 tick 之间平滑插值 Agent 位置。
 */
function animationLoop(timestamp) {
    let needsRedraw = false;

    for (const agent of agentsData) {
        const target = agentTargets[agent.id];
        if (!target) continue;

        const elapsed = timestamp - (target.startTime || timestamp);
        const progress = Math.min(1, elapsed / ANIMATION_DURATION);

        if (progress < 1) {
            // 还在动画中
            target.x = target.startX + (agent.x - target.startX) * progress;
            target.y = target.startY + (agent.y - target.startY) * progress;
            needsRedraw = true;
        } else {
            // 动画完成
            target.x = agent.x;
            target.y = agent.y;
        }
    }

    if (needsRedraw) {
        drawMap();
    }

    animationId = requestAnimationFrame(animationLoop);
}

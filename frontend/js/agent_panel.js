/**
 * ============================================================
 * agent_panel.js — Agent 详情面板
 * ============================================================
 */

/**
 * 显示 Agent 详情。
 */
function showAgentDetail(agent) {
    if (!agent) return;
    const panel = document.getElementById('agent-panel');
    if (!panel) return;

    const skills = Object.entries(agent.skills || {})
        .map(([k, v]) => `${k}: ${(v * 100).toFixed(0)}%`)
        .join(', ');

    const relations = Object.entries(agent.relationships || {})
        .map(([k, v]) => `${k.replace('agent_', '')}: ${v > 0 ? '+' : ''}${v.toFixed(1)}`)
        .join(', ') || '暂无关系';

    const recentMemories = (agent.short_term_memories || [])
        .slice(-5)
        .map(m => `<li>${m}</li>`)
        .join('');

    panel.innerHTML = `
        <div class="panel-header"><h3>👤 ${agent.name}</h3></div>
        <div class="panel-body">
            <div class="agent-profile">
                <p><strong>${agent.emoji} ${agent.name}</strong></p>
                <p>${agent.age}岁 · ${agent.job}</p>
                <p>性格: ${agent.personality?.description || ''}</p>
            </div>

            <div class="agent-mood-bar">
                <span>心情</span>
                <div class="bar-bg"><div class="bar-fill mood-fill" style="width:${(agent.mood||0)*100}%"></div></div>
                <span class="bar-val">${((agent.mood||0)*100).toFixed(0)}%</span>
            </div>
            <div class="agent-energy-bar">
                <span>精力</span>
                <div class="bar-bg"><div class="bar-fill energy-fill" style="width:${(agent.energy||0)*100}%"></div></div>
                <span class="bar-val">${((agent.energy||0)*100).toFixed(0)}%</span>
            </div>

            <p><strong>当前活动:</strong> ${agent.activity || '未知'}</p>
            <p><strong>技能:</strong> <span style="font-size:12px">${skills || '无'}</span></p>
            <p><strong>人际关系:</strong> <span style="font-size:12px">${relations}</span></p>
            <p><strong>Token 消耗:</strong> ${agent.total_tokens || 0}</p>

            ${recentMemories ? `<div class="memories-section">
                <p><strong>最近记忆:</strong></p>
                <ul class="memories-list">${recentMemories}</ul>
            </div>` : ''}
        </div>
    `;
}

function showLocationInfo(x, y, locName) {
    const panel = document.getElementById('agent-panel');
    if (!panel) return;
    panel.innerHTML = `
        <div class="panel-header"><h3>📍 地点信息</h3></div>
        <div class="panel-body">
            <p><strong>坐标:</strong> (${x}, ${y})</p>
            <p><strong>地点:</strong> ${locName}</p>
            <p class="placeholder-text">点击 Agent 查看详情</p>
        </div>
    `;
}

/**
 * monitor_dashboard.js — 监测面板
 * refreshMonitor() 由 app.js 的 switchTab 触发
 */
let _monitorTimer = null;

async function refreshMonitor() {
    try {
        const [mResp, eResp] = await Promise.all([
            fetch('/api/metrics'),
            fetch('/api/evaluations'),
        ]);
        const m = await mResp.json();
        const evals = await eResp.json();

        renderMetricsCards(m);
        renderRankingList(evals);
        renderMoodChart(m);

        // 在监测页且运行时每 5 秒刷新，暂停时停止
        if (!_monitorTimer && typeof APP_STATE !== 'undefined' && APP_STATE.running) {
            _monitorTimer = setInterval(refreshMonitor, 5000);
        }
        if (_monitorTimer && typeof APP_STATE !== 'undefined' && !APP_STATE.running) {
            clearInterval(_monitorTimer);
            _monitorTimer = null;
        }
    } catch (err) {
        console.error('[Monitor] 加载失败:', err);
        const el = document.getElementById('metrics-cards');
        if (el) el.innerHTML = '<p class="placeholder-text">数据加载失败</p>';
    }
}

function renderMetricsCards(m) {
    const container = document.getElementById('metrics-cards');
    if (!container) return;

    const cards = [
        { label: 'Tick', value: m.tick || 0 },
        { label: '活跃 Agent', value: (m.agent_count || 0) + '/7' },
        { label: '总 Token', value: (m.total_tokens || 0).toLocaleString() },
        { label: 'LLM 调用次数', value: m.total_llm_calls || 0 },
        { label: '平均心情', value: (m.avg_mood || 0).toFixed(2) },
        { label: '降级率', value: ((m.metrics_summary?.degradation_rate || 0) * 100).toFixed(1) + '%' },
    ];

    container.innerHTML = cards.map(c =>
        '<div class="metric-card">' +
        '<div class="metric-value">' + c.value + '</div>' +
        '<div class="metric-label">' + c.label + '</div>' +
        '</div>'
    ).join('');
}

function renderRankingList(evals) {
    const container = document.getElementById('ranking-list');
    if (!container) return;

    if (!evals || !evals.latest || !evals.latest.evaluations) {
        container.innerHTML = '<p class="placeholder-text">暂无评估报告<br><small>需要运行 20 tick 后自动生成</small></p>';
        return;
    }

    const sorted = [...evals.latest.evaluations].sort(
        (a, b) => (b.scores?.overall || 0) - (a.scores?.overall || 0)
    );

    container.innerHTML = '<div style="font-size:12px;color:#8899aa;margin-bottom:8px">Tick ' + evals.latest.tick + ' 综合评分: ' + evals.latest.overall + '/10  |  最佳: ' + (evals.latest.top_performer || 'N/A') + '</div>' +
        sorted.map((e, i) => {
            const score = e.scores?.overall || 0;
            const stars = score >= 8 ? '★★★' : score >= 6 ? '★★' : '★';
            return '<div class="ranking-item" style="display:flex;justify-content:space-between;padding:4px 0;font-size:13px;border-bottom:1px solid rgba(255,255,255,0.04)">' +
                '<span>' + (i + 1) + '. ' + e.name + '</span>' +
                '<span>' + stars + ' ' + score + '/10</span>' +
                '</div>';
        }).join('');
}

function renderMoodChart(m) {
    const canvas = document.getElementById('mood-chart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const w = canvas.width, h = canvas.height;
    ctx.clearRect(0, 0, w, h);
    ctx.font = '14px "Microsoft YaHei", sans-serif';
    ctx.fillStyle = '#8899aa';
    ctx.textAlign = 'center';
    ctx.fillText('Day ' + (m.day || 1) + ' · ' + (m.time || '06:00') + ' · 平均心情: ' + (m.avg_mood || 0).toFixed(2) + ' · Token: ' + ((m.total_tokens || 0)).toLocaleString(), w / 2, h / 2);
}

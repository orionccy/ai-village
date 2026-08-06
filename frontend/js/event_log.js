/**
 * event_log.js — 事件日志（带去重）
 */
const MAX_LOG_ENTRIES = 200;
let allLogEntries = [];
let seenKeys = new Set();

function eventKey(e) { return e.time + '|' + e.text.slice(0, 40); }

function addEvents(events) {
    if (!events || events.length === 0) return;

    let added = false;
    for (const evt of events) {
        const k = eventKey(evt);
        if (seenKeys.has(k)) continue;
        seenKeys.add(k);
        allLogEntries.push(evt);
        added = true;
    }

    // 裁剪
    if (allLogEntries.length > MAX_LOG_ENTRIES) {
        allLogEntries = allLogEntries.slice(-MAX_LOG_ENTRIES);
    }

    if (added) {
        updateEventPanel();
        updateFullLog();
    }
}

function updateEventPanel() {
    const list = document.getElementById('event-list');
    if (!list) return;
    const recent = allLogEntries.slice(-8);
    list.innerHTML = recent.map(e =>
        '<div class="log-entry">' +
        '<span class="log-time">' + e.time + '</span> ' +
        '<span class="log-text">' + e.text + '</span>' +
        '</div>'
    ).join('');
    list.scrollTop = list.scrollHeight;
}

function updateFullLog() {
    const list = document.getElementById('full-log-list');
    if (!list) return;
    if (allLogEntries.length === 0) {
        list.innerHTML = '<p class="placeholder-text">暂无事件</p>';
        return;
    }
    list.innerHTML = allLogEntries.map(e =>
        '<div class="log-entry">' +
        '<span class="log-time">' + e.time + '</span> ' +
        '<span class="log-text">' + e.text + '</span>' +
        '</div>'
    ).join('');
    list.scrollTop = list.scrollHeight;
}

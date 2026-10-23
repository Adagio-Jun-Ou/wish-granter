"""FastAPI web application for WishGranter."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from wish_granter.engine import WishGranter, WishGranterConfig
from wish_granter.models.wish import Wish, WishStatus


class WishRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=10000)
    priority: int = Field(default=5, ge=1, le=10)
    max_iterations: int = Field(default=50, ge=1, le=500)
    metadata: dict[str, Any] = Field(default_factory=dict)


class WishResponse(BaseModel):
    wish_id: str
    text: str
    status: str
    category: str
    current_iteration: int
    max_iterations: int
    plan: Optional[dict] = None
    result: Optional[dict] = None
    thinking_log: list[dict] = Field(default_factory=list)
    created_at: float
    updated_at: float


class StepRequest(BaseModel):
    wish_id: str
    step_id: str
    params_override: dict[str, Any] = Field(default_factory=dict)


def create_app(config: WishGranterConfig | None = None) -> FastAPI:
    app = FastAPI(
        title="WishGranter",
        description="AI-powered omnipotent wish-granting machine",
        version="0.1.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    granter = WishGranter(config or WishGranterConfig())
    ws_connections: list[WebSocket] = []

    async def broadcast(event: str, data: dict):
        msg = json.dumps({"event": event, "data": data})
        dead = []
        for ws in ws_connections:
            try:
                await ws.send_text(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            ws_connections.remove(ws)

    async def on_wish_event(data: dict):
        await broadcast("wish_event", data)

    granter.on("wish_created", on_wish_event)
    granter.on("wish_planned", on_wish_event)
    granter.on("wish_executing", on_wish_event)
    granter.on("step_started", on_wish_event)
    granter.on("step_completed", on_wish_event)
    granter.on("step_failed", on_wish_event)
    granter.on("wish_completed", on_wish_event)

    def wish_to_response(wish: Wish) -> WishResponse:
        plan_dict = None
        if wish.plan:
            plan_dict = {
                "plan_id": wish.plan.plan_id,
                "category": wish.plan.category.value,
                "steps": [
                    {
                        "step_id": s.step_id,
                        "description": s.description,
                        "capability": s.capability.value,
                        "params": s.params,
                        "status": s.status.value,
                        "result": s.result,
                        "error": s.error,
                    }
                    for s in wish.plan.steps
                ],
                "reasoning": wish.plan.reasoning,
                "revision": wish.plan.revision,
                "progress_pct": wish.plan.progress_pct,
            }
        result_dict = None
        if wish.result:
            result_dict = {
                "status": wish.result.status.value,
                "summary": wish.result.summary,
                "total_iterations": wish.result.total_iterations,
                "total_time_seconds": wish.result.total_time_seconds,
                "plan_revisions": wish.result.plan_revisions,
            }
        return WishResponse(
            wish_id=wish.wish_id,
            text=wish.text,
            status=wish.status.value,
            category=wish.category.value,
            current_iteration=wish.current_iteration,
            max_iterations=wish.max_iterations,
            plan=plan_dict,
            result=result_dict,
            thinking_log=[{"thought": t.thought, "action": t.action, "result": t.result, "iteration": t.iteration, "is_reflection": t.is_reflection} for t in wish.thinking_log],
            created_at=wish.created_at,
            updated_at=wish.updated_at,
        )

    @app.get("/", response_class=HTMLResponse)
    async def dashboard():
        return DASHBOARD_HTML

    @app.post("/api/wish", response_model=WishResponse)
    async def create_wish(req: WishRequest):
        if req.max_iterations:
            original_max = granter.config.max_iterations
            granter.config.max_iterations = req.max_iterations
        wish = await granter.grant_wish(req.text, req.priority, req.metadata)
        if req.max_iterations:
            granter.config.max_iterations = original_max
        return wish_to_response(wish)

    @app.get("/api/wish/{wish_id}", response_model=WishResponse)
    async def get_wish(wish_id: str):
        wish = granter.get_wish(wish_id)
        if not wish:
            raise HTTPException(404, f"Wish {wish_id} not found")
        return wish_to_response(wish)

    @app.get("/api/wishes", response_model=list[WishResponse])
    async def list_wishes(status: str | None = None):
        wishes = granter.list_wishes()
        if status:
            wishes = [w for w in wishes if w.status.value == status]
        return [wish_to_response(w) for w in wishes]

    @app.post("/api/wish/{wish_id}/pause")
    async def pause_wish(wish_id: str):
        ok = await granter.pause_wish(wish_id)
        if not ok:
            raise HTTPException(400, f"Cannot pause wish {wish_id}")
        wish = granter.get_wish(wish_id)
        return wish_to_response(wish)

    @app.post("/api/wish/{wish_id}/resume")
    async def resume_wish(wish_id: str):
        wish = await granter.resume_wish(wish_id)
        if not wish:
            raise HTTPException(400, f"Cannot resume wish {wish_id}")
        return wish_to_response(wish)

    @app.post("/api/wish/{wish_id}/cancel")
    async def cancel_wish(wish_id: str):
        ok = await granter.cancel_wish(wish_id)
        if not ok:
            raise HTTPException(404, f"Wish {wish_id} not found")
        return {"status": "cancelled", "wish_id": wish_id}

    @app.get("/api/capabilities")
    async def list_capabilities():
        return {
            name: {"name": cap.name, "description": cap.description}
            for name, cap in granter.capabilities.items()
        }

    @app.get("/api/status")
    async def status():
        wishes = granter.list_wishes()
        by_status = {}
        for w in wishes:
            s = w.status.value
            by_status[s] = by_status.get(s, 0) + 1
        return {
            "version": "0.1.0",
            "total_wishes": len(wishes),
            "by_status": by_status,
            "capabilities": list(granter.capabilities.keys()),
            "model": granter.config.model,
        }

    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket):
        await ws.accept()
        ws_connections.append(ws)
        try:
            while True:
                data = await ws.receive_text()
                msg = json.loads(data) if data else {}
                if msg.get("type") == "ping":
                    await ws.send_text(json.dumps({"type": "pong"}))
        except WebSocketDisconnect:
            ws_connections.remove(ws)

    return app


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>WishGranter - Omnipotent AI</title>
<style>
:root {
    --bg: #0a0a0f;
    --surface: #12121a;
    --surface2: #1a1a2e;
    --border: #2a2a3e;
    --text: #e0e0f0;
    --text-dim: #8888aa;
    --primary: #7c3aed;
    --primary-glow: rgba(124,58,237,0.3);
    --success: #10b981;
    --warning: #f59e0b;
    --error: #ef4444;
    --info: #3b82f6;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body { background: var(--bg); color: var(--text); font-family: 'SF Mono', 'Fira Code', monospace; overflow-x: hidden; }
.container { max-width: 1200px; margin: 0 auto; padding: 20px; }

/* Animated background */
.bg-gradient {
    position: fixed; top: 0; left: 0; right: 0; bottom: 0; z-index: -1;
    background: radial-gradient(ellipse at 20% 50%, rgba(124,58,237,0.08) 0%, transparent 50%),
                radial-gradient(ellipse at 80% 20%, rgba(59,130,246,0.06) 0%, transparent 50%),
                radial-gradient(ellipse at 50% 80%, rgba(16,185,129,0.04) 0%, transparent 50%),
                var(--bg);
}

/* Header */
.header { text-align: center; padding: 40px 0 30px; }
.header h1 {
    font-size: 2.5em; font-weight: 800;
    background: linear-gradient(135deg, #7c3aed, #3b82f6, #10b981);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    letter-spacing: -0.02em;
}
.header p { color: var(--text-dim); font-size: 0.9em; margin-top: 8px; }
.pulse-dot { display: inline-block; width: 8px; height: 8px; background: var(--success); border-radius: 50%; animation: pulse 2s infinite; margin-left: 8px; }
@keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.4; } }

/* Wish Input */
.wish-input {
    background: var(--surface); border: 1px solid var(--border); border-radius: 16px;
    padding: 24px; margin-bottom: 24px; position: relative; overflow: hidden;
}
.wish-input::before {
    content: ''; position: absolute; top: 0; left: 0; right: 0; height: 2px;
    background: linear-gradient(90deg, transparent, var(--primary), transparent);
}
.wish-input label { display: block; font-size: 0.75em; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 8px; }
.wish-textarea {
    width: 100%; min-height: 80px; background: var(--bg); border: 1px solid var(--border);
    border-radius: 8px; color: var(--text); padding: 12px; font-family: inherit;
    font-size: 1em; resize: vertical; transition: border-color 0.2s;
}
.wish-textarea:focus { outline: none; border-color: var(--primary); box-shadow: 0 0 0 3px var(--primary-glow); }
.wish-textarea::placeholder { color: var(--text-dim); }
.wish-options { display: flex; gap: 12px; margin-top: 12px; align-items: center; flex-wrap: wrap; }
.btn {
    padding: 10px 24px; border: none; border-radius: 8px; cursor: pointer;
    font-family: inherit; font-size: 0.9em; font-weight: 600; transition: all 0.2s;
}
.btn-primary {
    background: linear-gradient(135deg, var(--primary), #5b21b6); color: white;
    box-shadow: 0 4px 15px var(--primary-glow);
}
.btn-primary:hover { transform: translateY(-1px); box-shadow: 0 6px 20px var(--primary-glow); }
.btn-secondary { background: var(--surface2); color: var(--text); border: 1px solid var(--border); }
.btn-secondary:hover { border-color: var(--primary); }
.btn-sm { padding: 6px 14px; font-size: 0.8em; }
select, input[type="number"] {
    background: var(--bg); border: 1px solid var(--border); color: var(--text);
    padding: 8px 12px; border-radius: 6px; font-family: inherit; font-size: 0.85em;
}

/* Status badges */
.status-badge {
    display: inline-block; padding: 3px 10px; border-radius: 12px; font-size: 0.75em;
    font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em;
}
.status-pending { background: rgba(136,136,170,0.15); color: #8888aa; }
.status-planning { background: rgba(59,130,246,0.15); color: #3b82f6; }
.status-executing { background: rgba(245,158,11,0.15); color: #f59e0b; }
.status-thinking { background: rgba(124,58,237,0.15); color: #7c3aed; animation: pulse 1.5s infinite; }
.status-granted { background: rgba(16,185,129,0.15); color: #10b981; }
.status-partial { background: rgba(59,130,246,0.15); color: #3b82f6; }
.status-failed { background: rgba(239,68,68,0.15); color: #ef4444; }
.status-paused { background: rgba(136,136,170,0.15); color: #8888aa; }

/* Wishes list */
.wishes-section { margin-top: 24px; }
.wishes-section h2 { font-size: 1.2em; margin-bottom: 16px; color: var(--text-dim); }
.wish-card {
    background: var(--surface); border: 1px solid var(--border); border-radius: 12px;
    padding: 20px; margin-bottom: 12px; transition: border-color 0.2s; cursor: pointer;
}
.wish-card:hover { border-color: var(--primary); }
.wish-card-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px; }
.wish-card-header h3 { font-size: 1em; font-weight: 600; flex: 1; margin-right: 12px; }
.wish-card-meta { display: flex; gap: 12px; font-size: 0.75em; color: var(--text-dim); margin-top: 6px; flex-wrap: wrap; }
.wish-card-meta span { display: inline-flex; align-items: center; gap: 4px; }

/* Thinking log */
.thinking-log {
    background: var(--bg); border: 1px solid var(--border); border-radius: 8px;
    padding: 12px; margin-top: 12px; max-height: 200px; overflow-y: auto;
    font-size: 0.8em;
}
.thinking-entry { margin-bottom: 8px; padding: 6px 8px; border-radius: 4px; }
.thinking-entry.reflection { background: rgba(124,58,237,0.08); border-left: 3px solid var(--primary); }
.thinking-entry.action { background: rgba(59,130,246,0.05); border-left: 3px solid var(--info); }
.thinking-entry .thought { color: var(--text); }
.thinking-entry .meta { color: var(--text-dim); font-size: 0.85em; margin-top: 2px; }

/* Progress bar */
.progress-bar {
    height: 4px; background: var(--surface2); border-radius: 2px; margin-top: 8px; overflow: hidden;
}
.progress-fill {
    height: 100%; border-radius: 2px; transition: width 0.5s ease;
    background: linear-gradient(90deg, var(--primary), var(--success));
}

/* Steps */
.steps-list { margin-top: 12px; }
.step-item {
    display: flex; align-items: center; gap: 8px; padding: 6px 0; font-size: 0.85em;
}
.step-icon { width: 20px; text-align: center; }
.step-icon.done { color: var(--success); }
.step-icon.running { color: var(--warning); animation: pulse 1s infinite; }
.step-icon.pending { color: var(--text-dim); }
.step-icon.failed { color: var(--error); }
.step-desc { flex: 1; }
.step-cap { color: var(--text-dim); font-size: 0.85em; }

/* Detail panel */
.detail-panel {
    background: var(--surface); border: 1px solid var(--border); border-radius: 12px;
    padding: 24px; margin-top: 16px; display: none;
}
.detail-panel.visible { display: block; }
.detail-panel h2 { margin-bottom: 12px; }
.detail-section { margin-bottom: 16px; }
.detail-section h4 { color: var(--text-dim); font-size: 0.75em; text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 6px; }

/* Result area */
.result-area {
    background: rgba(16,185,129,0.05); border: 1px solid rgba(16,185,129,0.2); border-radius: 8px;
    padding: 16px; margin-top: 12px; white-space: pre-wrap; line-height: 1.6;
}
.result-area.granted { background: rgba(16,185,129,0.08); border-color: rgba(16,185,129,0.3); }
.result-area.failed { background: rgba(239,68,68,0.05); border-color: rgba(239,68,68,0.2); }

/* Scrollbar */
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: var(--bg); }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: var(--primary); }

/* Toast */
.toast {
    position: fixed; bottom: 20px; right: 20px; padding: 12px 20px; border-radius: 8px;
    font-size: 0.85em; z-index: 1000; opacity: 0; transform: translateY(10px);
    transition: all 0.3s; pointer-events: none;
}
.toast.show { opacity: 1; transform: translateY(0); pointer-events: auto; }
.toast-success { background: rgba(16,185,129,0.9); color: white; }
.toast-error { background: rgba(239,68,68,0.9); color: white; }
.toast-info { background: rgba(59,130,246,0.9); color: white; }

/* Empty state */
.empty-state { text-align: center; padding: 60px 20px; color: var(--text-dim); }
.empty-state .icon { font-size: 3em; margin-bottom: 12px; }

/* Responsive */
@media (max-width: 768px) {
    .container { padding: 12px; }
    .header h1 { font-size: 1.8em; }
    .wish-options { flex-direction: column; }
}
</style>
</head>
<body>
<div class="bg-gradient"></div>
<div class="container">
    <div class="header">
        <h1>WishGranter <span class="pulse-dot"></span></h1>
        <p>Omnipotent AI Wish-Granting Engine &mdash; Make a wish, and the machine thinks until it's granted</p>
    </div>

    <div class="wish-input">
        <label>Make Your Wish</label>
        <textarea class="wish-textarea" id="wishInput" placeholder="I wish to understand quantum computing principles with practical examples..." rows="3"></textarea>
        <div class="wish-options">
            <select id="prioritySelect">
                <option value="5">Normal Priority</option>
                <option value="8">High Priority</option>
                <option value="3">Low Priority</option>
            </select>
            <input type="number" id="maxIterInput" value="50" min="1" max="500" title="Max iterations" style="width:80px">
            <button class="btn btn-primary" onclick="grantWish()">Grant My Wish</button>
            <button class="btn btn-secondary" onclick="refreshWishes()">Refresh</button>
        </div>
    </div>

    <div class="wishes-section">
        <h2 id="wishesTitle">Wishes (0)</h2>
        <div id="wishesList">
            <div class="empty-state">
                <div class="icon">&#9889;</div>
                <p>No wishes yet. Make your first wish above.</p>
            </div>
        </div>
    </div>

    <div class="detail-panel" id="detailPanel">
        <h2 id="detailTitle">Wish Details</h2>
        <div id="detailContent"></div>
    </div>
</div>

<div class="toast" id="toast"></div>

<script>
const API = '';
let ws = null;
let wishes = [];
let selectedWish = null;
let pollInterval = null;

function connectWS() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    ws = new WebSocket(`${proto}://${location.host}/ws`);
    ws.onmessage = (e) => {
        try {
            const msg = JSON.parse(e.data);
            if (msg.event === 'wish_event' || msg.data) {
                refreshWishes();
            }
        } catch {}
    };
    ws.onclose = () => setTimeout(connectWS, 3000);
    ws.onerror = () => {};
}
connectWS();

pollInterval = setInterval(refreshWishes, 5000);

async function grantWish() {
    const text = document.getElementById('wishInput').value.trim();
    if (!text) { showToast('Enter a wish first!', 'error'); return; }
    const priority = parseInt(document.getElementById('prioritySelect').value);
    const maxIter = parseInt(document.getElementById('maxIterInput').value);
    try {
        const resp = await fetch(`${API}/api/wish`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({text, priority, max_iterations: maxIter})
        });
        const wish = await resp.json();
        document.getElementById('wishInput').value = '';
        showToast(`Wish ${wish.wish_id} created!`, 'success');
        refreshWishes();
    } catch (e) {
        showToast('Error creating wish: ' + e.message, 'error');
    }
}

async function refreshWishes() {
    try {
        const resp = await fetch(`${API}/api/wishes`);
        wishes = await resp.json();
        renderWishes();
        if (selectedWish) {
            const w = wishes.find(w => w.wish_id === selectedWish);
            if (w) renderDetail(w);
        }
    } catch {}
}

function renderWishes() {
    document.getElementById('wishesTitle').textContent = `Wishes (${wishes.length})`;
    const container = document.getElementById('wishesList');
    if (!wishes.length) {
        container.innerHTML = '<div class="empty-state"><div class="icon">&#9889;</div><p>No wishes yet. Make your first wish above.</p></div>';
        return;
    }
    container.innerHTML = wishes.map(w => {
        const progress = w.plan ? Math.round(w.plan.progress_pct) : 0;
        const thinkingCount = w.thinking_log ? w.thinking_log.length : 0;
        const lastThought = thinkingCount > 0 ? w.thinking_log[w.thinking_log.length - 1].thought : '';
        return `
        <div class="wish-card" onclick="selectWish('${w.wish_id}')">
            <div class="wish-card-header">
                <h3>${escHtml(w.text.substring(0, 100))}${w.text.length > 100 ? '...' : ''}</h3>
                <span class="status-badge status-${w.status}">${w.status}</span>
            </div>
            <div class="progress-bar"><div class="progress-fill" style="width:${progress}%"></div></div>
            <div class="wish-card-meta">
                <span>&#128260; ${w.current_iteration}/${w.max_iterations}</span>
                <span>&#127919; ${progress}%</span>
                <span>&#129504; ${thinkingCount} thoughts</span>
                <span>&#128196; ${w.category}</span>
                ${w.plan ? `<span>&#128736; Rev ${w.plan.revision}</span>` : ''}
            </div>
            ${lastThought ? `<div class="thinking-log" style="max-height:60px;margin-top:8px"><div class="thinking-entry action"><div class="thought">${escHtml(lastThought.substring(0, 120))}</div></div></div>` : ''}
            <div style="margin-top:8px;display:flex;gap:6px">
                ${w.status === 'executing' || w.status === 'thinking' ? `<button class="btn btn-sm btn-secondary" onclick="event.stopPropagation();pauseWish('${w.wish_id}')">Pause</button>` : ''}
                ${w.status === 'paused' ? `<button class="btn btn-sm btn-primary" onclick="event.stopPropagation();resumeWish('${w.wish_id}')">Resume</button>` : ''}
                ${w.status !== 'granted' && w.status !== 'cancelled' && w.status !== 'failed' ? `<button class="btn btn-sm btn-secondary" onclick="event.stopPropagation();cancelWish('${w.wish_id}')" style="color:var(--error)">Cancel</button>` : ''}
            </div>
        </div>`;
    }).join('');
}

async function selectWish(id) {
    selectedWish = id;
    const resp = await fetch(`${API}/api/wish/${id}`);
    const wish = await resp.json();
    renderDetail(wish);
}

function renderDetail(w) {
    const panel = document.getElementById('detailPanel');
    panel.classList.add('visible');
    document.getElementById('detailTitle').textContent = `Wish: ${w.text.substring(0, 60)}...`;
    const progress = w.plan ? Math.round(w.plan.progress_pct) : 0;
    let html = `
        <div class="detail-section">
            <h4>Status</h4>
            <span class="status-badge status-${w.status}">${w.status}</span>
            <span style="margin-left:12px;color:var(--text-dim)">${w.current_iteration}/${w.max_iterations} iterations &bull; ${progress}% complete</span>
        </div>`;

    if (w.plan) {
        html += `<div class="detail-section"><h4>Plan (Revision ${w.plan.revision})</h4><p style="color:var(--text-dim);font-size:0.85em">${escHtml(w.plan.reasoning)}</p>`;
        html += '<div class="steps-list">';
        for (const s of w.plan.steps) {
            const icon = s.status === 'granted' ? '&#10003;' : s.status === 'executing' ? '&#9654;' : s.status === 'failed' ? '&#10007;' : '&#9675;';
            const cls = s.status === 'granted' ? 'done' : s.status === 'executing' ? 'running' : s.status === 'failed' ? 'failed' : 'pending';
            html += `<div class="step-item"><span class="step-icon ${cls}">${icon}</span><span class="step-desc">${escHtml(s.description)}</span><span class="step-cap">${s.capability}</span></div>`;
        }
        html += '</div></div>';
    }

    if (w.thinking_log && w.thinking_log.length) {
        html += `<div class="detail-section"><h4>Thinking Process (${w.thinking_log.length} thoughts)</h4><div class="thinking-log">`;
        for (const t of w.thinking_log) {
            const cls = t.is_reflection ? 'reflection' : 'action';
            html += `<div class="thinking-entry ${cls}"><div class="thought">${escHtml(t.thought)}</div><div class="meta">Iter ${t.iteration} &bull; ${t.action}${t.result ? ' &bull; ' + escHtml(t.result.substring(0, 80)) : ''}</div></div>`;
        }
        html += '</div></div>';
    }

    if (w.result) {
        const resultClass = w.result.status === 'granted' ? 'granted' : w.result.status === 'failed' ? 'failed' : '';
        html += `<div class="detail-section"><h4>Result</h4><div class="result-area ${resultClass}">${escHtml(w.result.summary || 'No summary')}</div>`;
        html += `<div style="margin-top:8px;color:var(--text-dim);font-size:0.8em">${w.result.total_iterations} iterations &bull; ${w.result.total_time_seconds?.toFixed(1)}s &bull; ${w.result.plan_revisions} plan revisions</div></div>`;
    }

    document.getElementById('detailContent').innerHTML = html;
}

async function pauseWish(id) {
    await fetch(`${API}/api/wish/${id}/pause`, {method: 'POST'});
    showToast('Wish paused', 'info');
    refreshWishes();
}

async function resumeWish(id) {
    await fetch(`${API}/api/wish/${id}/resume`, {method: 'POST'});
    showToast('Wish resumed', 'info');
    refreshWishes();
}

async function cancelWish(id) {
    await fetch(`${API}/api/wish/${id}/cancel`, {method: 'POST'});
    showToast('Wish cancelled', 'info');
    refreshWishes();
}

function showToast(msg, type) {
    const t = document.getElementById('toast');
    t.textContent = msg;
    t.className = `toast toast-${type} show`;
    setTimeout(() => t.classList.remove('show'), 3000);
}

function escHtml(s) {
    const d = document.createElement('div');
    d.textContent = s || '';
    return d.innerHTML;
}

document.getElementById('wishInput').addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); grantWish(); }
});

refreshWishes();
</script>
</body>
</html>"""
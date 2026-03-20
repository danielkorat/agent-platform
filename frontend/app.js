/**
 * Agent Platform — Frontend Application
 *
 * Handles task submission, SSE streaming, result display, and metrics.
 */
"use strict";

// ── DOM refs ────────────────────────────────────────────────
const scenarioSelect = document.getElementById("scenario-select");
const queryInput = document.getElementById("query-input");
const submitBtn = document.getElementById("submit-btn");
const progressSection = document.getElementById("progress-section");
const taskTitle = document.getElementById("task-title");
const taskBadge = document.getElementById("task-badge");
const progressBar = document.getElementById("progress-bar");
const stepsLog = document.getElementById("steps-log");
const thinkingPanel = document.getElementById("thinking-panel");
const thinkingText = document.getElementById("thinking-text");
const resultSection = document.getElementById("result-section");
const resultOutput = document.getElementById("result-output");
const hwBadges = document.getElementById("hw-badges");
const citationsSection = document.getElementById("citations-section");
const citationsList = document.getElementById("citations-list");
const metricsContent = document.getElementById("metrics-content");
const traceContent = document.getElementById("trace-content");
const taskList = document.getElementById("task-list");
const healthStatus = document.getElementById("health-status");

// ── State ───────────────────────────────────────────────────
let currentTaskId = null;
const tasks = [];

// ── Health check ────────────────────────────────────────────
async function checkHealth() {
    try {
        const resp = await fetch("/health");
        if (resp.ok) {
            healthStatus.textContent = "Connected";
            healthStatus.className = "badge badge-green";
        } else {
            healthStatus.textContent = "Error";
            healthStatus.className = "badge badge-red";
        }
    } catch {
        healthStatus.textContent = "Disconnected";
        healthStatus.className = "badge badge-red";
    }
}
checkHealth();
setInterval(checkHealth, 30000);

// ── Example buttons ─────────────────────────────────────────
document.querySelectorAll(".example-btn").forEach(btn => {
    btn.addEventListener("click", () => {
        scenarioSelect.value = btn.dataset.scenario;
        queryInput.value = btn.dataset.query;
        queryInput.focus();
    });
});

// ── Submit task ─────────────────────────────────────────────
submitBtn.addEventListener("click", submitTask);
queryInput.addEventListener("keydown", e => {
    if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        submitTask();
    }
});

async function submitTask() {
    const query = queryInput.value.trim();
    if (!query) return;

    submitBtn.disabled = true;
    resetUI();
    progressSection.classList.remove("hidden");

    try {
        const resp = await fetch("/api/task", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                query,
                scenario: scenarioSelect.value,
            }),
        });

        if (!resp.ok) {
            const err = await resp.json();
            throw new Error(err.detail || "Failed to submit task");
        }

        const data = await resp.json();
        currentTaskId = data.task_id;

        tasks.unshift({
            id: data.task_id,
            query: query.slice(0, 60) + (query.length > 60 ? "..." : ""),
            scenario: scenarioSelect.value,
            status: "running",
        });
        renderTaskList();

        taskTitle.textContent = `Task ${data.task_id}`;
        startSSE(data.task_id);

    } catch (err) {
        addStep("Error: " + err.message, "error");
        submitBtn.disabled = false;
    }
}

// ── SSE streaming ───────────────────────────────────────────
function startSSE(taskId) {
    const evtSource = new EventSource(`/api/task/${taskId}/stream`);
    let lastPct = 0;

    evtSource.onmessage = (event) => {
        const data = JSON.parse(event.data);

        // Stream ended
        if (data.status === "done") {
            evtSource.close();
            fetchResult(taskId);
            submitBtn.disabled = false;
            return;
        }

        // Update progress bar (monotonic)
        if (data.progress_pct > lastPct) {
            lastPct = data.progress_pct;
            progressBar.style.width = lastPct + "%";
        }

        // Update status badge
        updateBadge(data.status);

        // Thinking chunks
        if (data.thinking_chunk) {
            thinkingPanel.classList.remove("hidden");
            thinkingText.textContent += data.thinking_chunk;
            thinkingText.scrollTop = thinkingText.scrollHeight;
            return;
        }

        // Step events
        if (data.message && data.message.trim()) {
            addStep(data.message, data.status, data.hardware, data.component);
        }

        // HW summary on complete
        if (data.hw_summary && Object.keys(data.hw_summary).length > 0) {
            showHwSummary(data.hw_summary);
        }
    };

    evtSource.onerror = () => {
        evtSource.close();
        submitBtn.disabled = false;
        updateBadge("failed");
    };
}

// ── Fetch final result ──────────────────────────────────────
async function fetchResult(taskId) {
    try {
        const resp = await fetch(`/api/task/${taskId}`);
        if (!resp.ok) {
            resultOutput.textContent = "Server error. Results may be unavailable.";
            resultSection.classList.remove("hidden");
            return;
        }
        const data = await resp.json();

        // Update task list
        const task = tasks.find(t => t.id === taskId);
        if (task) task.status = data.status;
        renderTaskList();

        // Show result
        resultSection.classList.remove("hidden");
        resultOutput.textContent = data.final_output || "(No output)";

        // Citations
        if (data.citations && data.citations.length > 0) {
            citationsSection.classList.remove("hidden");
            citationsList.innerHTML = data.citations.map(c =>
                `<li><strong>${c.source_id || c.source || ""}</strong>: ${c.title || ""} (score: ${(c.score || 0).toFixed(2)})</li>`
            ).join("");
        }

        // Metrics
        if (data.metrics) {
            showMetrics(data.metrics);
        }

        updateBadge(data.status);

    } catch (err) {
        resultOutput.textContent = "Failed to fetch result: " + err.message;
        resultSection.classList.remove("hidden");
    }
}

// ── UI helpers ──────────────────────────────────────────────
function resetUI() {
    progressSection.classList.add("hidden");
    resultSection.classList.add("hidden");
    citationsSection.classList.add("hidden");
    stepsLog.innerHTML = "";
    thinkingText.textContent = "";
    thinkingPanel.classList.add("hidden");
    resultOutput.textContent = "";
    citationsList.innerHTML = "";
    metricsContent.innerHTML = "";
    traceContent.textContent = "";
    hwBadges.innerHTML = "";
    progressBar.style.width = "0%";
}

function addStep(message, status, hardware, component) {
    const div = document.createElement("div");
    div.className = "step-item";

    const dot = document.createElement("span");
    dot.className = `step-dot ${status === "running" ? "running" : "done"}`;

    const text = document.createElement("span");
    text.textContent = message;

    div.appendChild(dot);
    div.appendChild(text);

    if (hardware) {
        const hw = document.createElement("span");
        hw.className = "step-hw badge " + (hardware === "XPU" ? "badge-blue" : "badge-purple");
        hw.textContent = hardware;
        div.appendChild(hw);
    }

    stepsLog.appendChild(div);
    stepsLog.scrollTop = stepsLog.scrollHeight;
}

function updateBadge(status) {
    const map = {
        pending: ["Pending", "badge-gray"],
        running: ["Running", "badge-yellow"],
        complete: ["Complete", "badge-green"],
        failed: ["Failed", "badge-red"],
    };
    const [text, cls] = map[status] || ["Unknown", "badge-gray"];
    taskBadge.textContent = text;
    taskBadge.className = `badge ${cls}`;
}

function showHwSummary(summary) {
    hwBadges.innerHTML = Object.entries(summary).map(([hw, stats]) => {
        const cls = hw === "XPU" ? "badge-blue" : "badge-purple";
        const model = stats.model ? stats.model.split("/").pop() : "";
        return `<span class="badge ${cls}">${hw}: ${model} · ${stats.tps || 0} tok/s · ↑${(stats.in_tokens || 0).toLocaleString()} ↓${(stats.out_tokens || 0).toLocaleString()} tok</span>`;
    }).join("");
}

function showMetrics(metrics) {
    const cards = [
        { label: "Total Time", value: `${(metrics.elapsed_s || 0).toFixed(1)}s` },
        { label: "LLM Calls", value: metrics.llm_calls || 0 },
        { label: "Input Tokens", value: (metrics.input_tokens || 0).toLocaleString() },
        { label: "Output Tokens", value: (metrics.output_tokens || 0).toLocaleString() },
        { label: "Execution Path", value: metrics.execution_path || "" },
        { label: "Hardware", value: (metrics.model_endpoints_used || []).join(", ") },
    ];

    metricsContent.innerHTML = cards.map(c => `
        <div class="metric-card">
            <div class="metric-label">${c.label}</div>
            <div class="metric-value">${c.value}</div>
        </div>
    `).join("");

    // Latency breakdown
    if (metrics.latency_breakdown) {
        traceContent.textContent = JSON.stringify(metrics.latency_breakdown, null, 2);
    }
    if (metrics.hw_utilization) {
        traceContent.textContent += "\n\nHW Utilization:\n" + JSON.stringify(metrics.hw_utilization, null, 2);
    }
}

function renderTaskList() {
    if (tasks.length === 0) {
        taskList.innerHTML = '<p class="muted">No tasks yet</p>';
        return;
    }
    taskList.innerHTML = tasks.map(t => {
        const cls = t.id === currentTaskId ? "task-item active" : "task-item";
        const badgeCls = t.status === "complete" ? "badge-green" :
                         t.status === "failed" ? "badge-red" : "badge-yellow";
        return `<div class="${cls}">
            <span class="badge ${badgeCls}" style="font-size:10px">${t.status}</span>
            ${t.query}
            <span class="task-scenario">${t.scenario}</span>
        </div>`;
    }).join("");
}

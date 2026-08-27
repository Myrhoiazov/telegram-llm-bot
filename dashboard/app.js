const state = {
  traces: new Map(),
  selectedTraceId: null,
  followLive: true,
};

function escapeHtml(value) {
  const div = document.createElement("div");
  div.textContent = value == null ? "" : String(value);
  return div.innerHTML;
}

async function fetchJson(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${url} -> ${response.status}`);
  return response.json();
}

function statusBadge(status) {
  return `<span class="status-badge status-${escapeHtml(status)}">${escapeHtml(status)}</span>`;
}

function renderTraceList() {
  const container = document.getElementById("trace-list");
  const rows = Array.from(state.traces.values()).sort(
    (a, b) => new Date(b.started_at) - new Date(a.started_at)
  );
  container.innerHTML = rows
    .map((trace) => {
      const selected = trace.trace_id === state.selectedTraceId ? " selected" : "";
      const duration = trace.duration_ms != null ? `${trace.duration_ms}ms` : "…";
      return `
        <div class="trace-row${selected}" data-trace-id="${escapeHtml(trace.trace_id)}">
          <div class="trace-row-title">${statusBadge(trace.status)} ${escapeHtml(trace.user_message).slice(0, 60)}</div>
          <div class="trace-row-meta">${escapeHtml(trace.started_at)} · ${duration} · steps ${escapeHtml(trace.agent_steps)} · tools ${escapeHtml(trace.tool_calls)}</div>
        </div>`;
    })
    .join("");
  container.querySelectorAll(".trace-row").forEach((row) => {
    row.addEventListener("click", () => selectTrace(row.dataset.traceId));
  });
}

function eventSummary(event) {
  const p = event.payload || {};
  switch (event.event_type) {
    case "context_loaded":
      return `Context: ${p.message_count} / ${p.max_context_messages} messages`;
    case "agent_step_started":
      return `Step ${p.step} / ${p.max_steps}`;
    case "llm_started":
      return `model=${p.model} messages=${p.message_count}`;
    case "llm_completed":
      return `duration=${p.duration_ms}ms prompt_tokens=${p.prompt_tokens ?? "?"} completion_tokens=${p.completion_tokens ?? "?"}`;
    case "tool_requested":
      return `${p.tool}(${JSON.stringify(p.arguments)})`;
    case "tool_started":
      return `${p.command}`;
    case "tool_completed":
      return `exit=${p.exit_code} duration=${p.duration_ms}ms${p.timed_out ? " TIMED OUT" : ""}${p.truncated ? " truncated" : ""}`;
    case "final_answer":
      return (p.content || "").slice(0, 80);
    case "trace_failed":
      return `${p.error_type}: ${p.message}`;
    case "max_steps_reached":
      return `max_steps=${p.max_steps}`;
    default:
      return "";
  }
}

function renderTimeline(events) {
  const container = document.getElementById("trace-detail");
  container.innerHTML = events
    .map(
      (event, index) => `
        <div class="timeline-card" data-index="${index}">
          <div class="timeline-card-header">
            <strong>${escapeHtml(event.event_type)}</strong>
            <span>${escapeHtml(event.timestamp)}</span>
            ${event.step != null ? `<span>step ${escapeHtml(event.step)}</span>` : ""}
            ${event.duration_ms != null ? `<span>${escapeHtml(event.duration_ms)}ms</span>` : ""}
          </div>
          <div class="timeline-card-summary">${escapeHtml(eventSummary(event))}</div>
        </div>`
    )
    .join("");
  container.querySelectorAll(".timeline-card").forEach((card) => {
    card.addEventListener("click", () => renderEventDetail(events[Number(card.dataset.index)]));
  });
}

function renderEventDetail(event) {
  const container = document.getElementById("event-detail");
  const pre = document.createElement("pre");
  pre.textContent = JSON.stringify(event, null, 2);
  container.innerHTML = "";
  container.appendChild(pre);
}

async function selectTrace(traceId) {
  state.selectedTraceId = traceId;
  renderTraceList();
  const events = await fetchJson(`/api/traces/${encodeURIComponent(traceId)}/events`);
  renderTimeline(events);
}

async function refreshStats() {
  const stats = await fetchJson("/api/stats");
  document.getElementById("header-stats").textContent =
    `active ${stats.running} · total ${stats.total_traces} · failed ${stats.failed} · avg ${stats.average_duration_ms ?? "-"}ms`;
}

async function loadInitialTraces() {
  const traces = await fetchJson("/api/traces");
  traces.forEach((trace) => state.traces.set(trace.trace_id, trace));
  renderTraceList();
  await refreshStats();
}

function setConnectionState(label) {
  const dot = document.getElementById("connection-dot");
  const text = document.getElementById("connection-label");
  dot.className = `dot dot-${label.toLowerCase()}`;
  text.textContent = label;
}

function applyLiveEvent(event) {
  if (event.event_type === "trace_started") {
    state.traces.set(event.trace_id, {
      trace_id: event.trace_id,
      status: "RUNNING",
      user_message: event.payload.user_message || "",
      started_at: event.timestamp,
      duration_ms: null,
      agent_steps: 0,
      tool_calls: 0,
    });
    if (state.followLive) {
      state.selectedTraceId = event.trace_id;
    }
  }
  const trace = state.traces.get(event.trace_id);
  if (trace) {
    if (event.event_type === "agent_step_started") trace.agent_steps = event.payload.step;
    if (event.event_type === "tool_completed") trace.tool_calls = (trace.tool_calls || 0) + 1;
    if (["trace_completed", "trace_failed", "max_steps_reached"].includes(event.event_type)) {
      trace.duration_ms = event.duration_ms;
      trace.status = { trace_completed: "COMPLETED", trace_failed: "FAILED", max_steps_reached: "MAX_STEPS_REACHED" }[
        event.event_type
      ];
    }
  }
  renderTraceList();
  refreshStats();
  if (state.followLive && event.trace_id === state.selectedTraceId) {
    selectTrace(event.trace_id);
  }
}

function connectStream() {
  const source = new EventSource("/api/events/stream");
  setConnectionState("RECONNECTING");
  source.addEventListener("open", () => setConnectionState("LIVE"));
  source.addEventListener("agent_event", (message) => applyLiveEvent(JSON.parse(message.data)));
  source.addEventListener("ping", () => {});
  source.onerror = () => {
    setConnectionState("DISCONNECTED");
  };
}

document.getElementById("follow-live").addEventListener("change", (event) => {
  state.followLive = event.target.checked;
});

loadInitialTraces();
connectStream();
setInterval(refreshStats, 15000);

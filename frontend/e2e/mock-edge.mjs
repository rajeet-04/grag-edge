// Hermetic stand-in for the Edge API: serves the built console (dist/) and /api/v1/edge/*,
// including a real SSE stream, so a real browser can be driven without Docker services.
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { extname, join, normalize } from "node:path";

const PORT = Number(process.env.MOCK_PORT ?? 4173);
const DIST = new URL("../dist/", import.meta.url).pathname;
const TYPES = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml" };

const state = { conflict: false, connectivity: "ONLINE", events: [], seq: 0, streams: new Set() };
const MEMORY = {
  memory_id: "m-1", logical_id: "l-1", revision: 2, content: "Pump P-41 seal replaced by ROBOT-01",
  device_id: "ROBOT-01", source_type: "operator", sync_state: "SYNCHRONIZED", origin: "FLEET", confidence: 0.9,
};

const CONFLICT = { conflict_id: "conflict_abc123", logical_id: "l-1", local_memory_id: "m-1", fleet_memory_id: "m-2", status: "OPEN" };
const FLEET_SIDE = { ...MEMORY, memory_id: "m-2", device_id: "ROBOT-01", content: "Pump P-41 seal replaced with type B" };
const QUEUE = [{ memory_id: "m-9", status: "RETRY_WAIT", retry_count: 2, last_error: "ConnectionError: fleet unreachable" }];

const ANSWER = "Based on the provided data...\n\n**Equipment Status & Observations:**\n*  **Pump P-41:** Currently experiencing fluctuating discharge pressure.\n*  **Compressor C-17:** Oil level nominal.\n\n## Reasoning Steps\n\n1. Identify equipment -> Categorize -> Synthesize\n\n## Graph Reasoning Path\n```mermaid\ngraph TD\n    A[User Query] --> B[Scan_Context]\n    B --> C[Identify_Equipment]\n    C --> D[Extract_Status]\n    D --> E[Identify_Procedures]\n    E --> F[Synthesize_Answer]\n    F --> G[Final_Response]\n```\n";

function emit(type, message) {
  const event = { event_id: String(++state.seq).padStart(6, "0"), event_type: type, message, device_id: "ROBOT-02",
    timestamp: new Date().toISOString() };
  state.events.unshift(event);
  for (const res of state.streams) res.write(`id: ${event.event_id}\nevent: ${type}\ndata: ${JSON.stringify(event)}\n\n`);
}
const stats = () => ({ local_memory_count: 1, fleet_memory_count: 1, pending_sync: 0, last_sync: null, sync_success_count: 1,
  open_conflict_count: 0, sync_failure_count: 0, search_latency_ms: 4, connectivity: state.connectivity });
const json = (res, body, status = 200) => { res.writeHead(status, { "content-type": "application/json" }); res.end(JSON.stringify(body)); };

createServer(async (req, res) => {
  const url = new URL(req.url, "http://x");
  const p = url.pathname;
  if (p === "/__mock/connectivity") { state.connectivity = url.searchParams.get("state"); emit(state.connectivity === "OFFLINE" ? "CLOUD_LINK_DOWN" : "CLOUD_LINK_UP", "link " + state.connectivity); return json(res, { ok: true }); }
  if (p === "/v1/chat/completions") return json(res, { choices: [{ message: { role: "assistant", content: ANSWER } }] });
  if (p === "/api/v1/edge/events") {
    res.writeHead(200, { "content-type": "text/event-stream", "cache-control": "no-cache" });
    res.write(": open\n\n");
    state.streams.add(res);
    req.on("close", () => state.streams.delete(res));
    return;
  }
  if (p === "/api/v1/edge/status") return json(res, { status: "READY", device_id: "ROBOT-02", connectivity: state.connectivity });
  if (p === "/api/v1/edge/stats") return json(res, stats());
  if (p === "/api/v1/edge/activity") return json(res, state.events);
  if (p === "/api/v1/edge/memories") return json(res, [MEMORY]);
  if (p === "/api/v1/edge/search") return json(res, { results: [{ ...MEMORY, score: 0.03, dense_score: 0.9, sparse_score: 0.4 }] });
  if (p === "/api/v1/edge/sync/status") return json(res, { connectivity: { connectivity: state.connectivity }, pending: 0, queued: 0, retry_wait: 0, uploading: 0, uploaded: 0, snapshot_pending: 0, synchronized: 1, last_attempt_at: null });
  if (p === "/__mock/conflict") { state.conflict = url.searchParams.get("on") === "1"; return json(res, { ok: true }); }
  if (p === "/api/v1/edge/conflicts") return json(res, state.conflict ? [CONFLICT] : []);
  if (p === "/api/v1/edge/conflicts/conflict_abc123") return json(res, { conflict: CONFLICT, local: MEMORY, fleet: FLEET_SIDE, history: [] });
  if (p === "/api/v1/edge/sync/queue") return json(res, state.conflict ? QUEUE : []);
  if (p === "/api/v1/edge/sync/history") return json(res, []);
  if (p.startsWith("/api/")) return json(res, { detail: "not found" }, 404);
  try {
    const file = normalize(join(DIST, p === "/" ? "index.html" : p));
    const data = await readFile(file.startsWith(DIST) ? file : join(DIST, "index.html"));
    res.writeHead(200, { "content-type": TYPES[extname(file)] ?? "application/octet-stream" }); res.end(data);
  } catch {
    res.writeHead(200, { "content-type": "text/html" }); res.end(await readFile(join(DIST, "index.html")));
  }
}).listen(PORT, () => console.log("mock edge on " + PORT));

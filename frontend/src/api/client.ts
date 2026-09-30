import type {
  ActivityEvent, ConflictRecord, EdgeStats, EdgeStatus, MemoryFilters, MemoryRecord,
  Resolution, SearchHit, SyncQueueItem, SyncStatus,
} from "./types";

const env = (import.meta as unknown as { env?: Record<string, string | undefined> }).env ?? {};
export const API_BASE: string = (env.VITE_EDGE_API_BASE ?? "/api").replace(/\/$/, "");
const EDGE = `${API_BASE}/v1/edge`;

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${EDGE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    throw new ApiError(0, "Edge API unreachable. Check that the GRAG Edge service is running.");
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
    } catch { /* keep statusText */ }
    throw new ApiError(res.status, detail || `HTTP ${res.status}`);
  }
  return (await res.json()) as T;
}

function query(params: Record<string, string | number | undefined>): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== "") q.set(k, String(v));
  const s = q.toString();
  return s ? `?${s}` : "";
}

export const eventsUrl = () => `${EDGE}/events`;

export const api = {
  status: () => request<EdgeStatus>("/status"),
  stats: () => request<EdgeStats>("/stats"),
  activity: (limit = 100) => request<ActivityEvent[]>(`/activity${query({ limit })}`),
  memories: (filters: MemoryFilters = {}) => request<MemoryRecord[]>(`/memories${query({ ...filters })}`),
  memory: (id: string) => request<MemoryRecord>(`/memories/${encodeURIComponent(id)}`),
  search: (q: string, mode: "semantic" | "keyword" | "hybrid" = "hybrid", limit = 10) =>
    request<{ results: SearchHit[] }>("/search", {
      method: "POST",
      body: JSON.stringify({ query: q, mode, limit }),
    }),
  ask: async (q: string): Promise<string> => {
    let res: Response;
    try {
      res = await fetch(`${API_BASE.replace(/\/api$/, "")}/v1/chat/completions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model: "grag-pipeline-v1", stream: false, messages: [{ role: "user", content: q }] }),
      });
    } catch {
      throw new ApiError(0, "Edge API unreachable. Check that the GRAG Edge service is running.");
    }
    if (!res.ok) throw new ApiError(res.status, `Ask GRAG failed (HTTP ${res.status})`);
    const body = await res.json();
    return body.choices?.[0]?.message?.content ?? "";
  },
  syncStatus: () => request<SyncStatus>("/sync/status"),
  syncQueue: (limit = 100) => request<SyncQueueItem[]>(`/sync/queue${query({ limit })}`),
  syncHistory: (limit = 100) => request<Record<string, unknown>[]>(`/sync/history${query({ limit })}`),
  runSync: () => request<{ status: string }>("/sync/run", { method: "POST" }),
  approve: (id: string) => request<unknown>(`/sync/${encodeURIComponent(id)}/approve`, { method: "POST" }),
  reject: (id: string) => request<unknown>(`/sync/${encodeURIComponent(id)}/reject`, { method: "POST" }),
  conflicts: () => request<ConflictRecord[]>("/conflicts"),
  conflict: (id: string) =>
    request<{ conflict: ConflictRecord; local: MemoryRecord | null; fleet: MemoryRecord | null; history: MemoryRecord[] }>(
      `/conflicts/${encodeURIComponent(id)}`),
  resolveConflict: (id: string, resolution: Resolution, merged_content?: string) =>
    request<ConflictRecord>(`/conflicts/${encodeURIComponent(id)}/resolve`, {
      method: "POST",
      body: JSON.stringify({ resolution, merged_content }),
    }),
};

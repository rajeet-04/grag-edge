export type Connectivity = "ONLINE" | "OFFLINE" | string;

export interface EdgeStatus {
  status: string;
  device_id: string;
  connectivity: Connectivity;
  local_ai?: string;
  qdrant_edge?: string;
  fleet_link?: string;
  [key: string]: unknown;
}

export interface EdgeStats {
  local_memory_count: number;
  fleet_memory_count: number;
  pending_sync: number;
  last_sync: string | null;
  sync_success_count: number;
  open_conflict_count: number;
  sync_failure_count: number;
  search_latency_ms: number | null;
  connectivity: Connectivity;
}

export interface ActivityEvent {
  event_id: string;
  event_type: string;
  device_id?: string;
  memory_id?: string | null;
  timestamp?: string;
  severity?: string;
  message?: string;
  metadata?: Record<string, unknown>;
}

export interface MemoryRecord {
  memory_id: string;
  logical_id?: string;
  revision: number;
  content: string;
  device_id: string;
  source_type: string;
  source_id?: string | null;
  memory_type?: string;
  importance?: string;
  tags?: string[];
  sync_state: string;
  origin?: string;
  confidence?: number | null;
  created_at?: string;
  is_deleted?: boolean;
  [key: string]: unknown;
}

export interface MemoryFilters {
  source?: string;
  memory_type?: string;
  sync_state?: string;
  importance?: string;
  device_id?: string;
  tag?: string;
  from_time?: string;
  to_time?: string;
}

export type SearchMode = "memory" | "ask";

export interface SearchHit {
  memory_id: string;
  origin: string;
  score: number;
  dense_score?: number | null;
  sparse_score?: number | null;
  revision: number;
  sync_state: string;
  content: string;
  device_id: string;
  source_type: string;
  source_id?: string | null;
  confidence?: number | null;
}

export interface SyncQueueItem {
  memory_id: string;
  status: string;
  retry_count: number;
  last_error?: string | null;
  policy_reason?: string | null;
  updated_at?: string;
  [key: string]: unknown;
}

export interface SyncStatus {
  connectivity: { connectivity: Connectivity; [key: string]: unknown } | Connectivity;
  pending: number;
  queued: number;
  retry_wait: number;
  uploading: number;
  uploaded: number;
  snapshot_pending: number;
  synchronized: number;
  last_attempt_at: string | null;
}

export interface ConflictRecord {
  conflict_id: string;
  logical_id: string;
  local_memory_id: string;
  fleet_memory_id: string;
  status?: string;
  reason?: string;
  [key: string]: unknown;
}

export type Resolution = "KEEP_LOCAL" | "ACCEPT_FLEET" | "MERGE";

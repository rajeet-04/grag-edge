import { act, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";
import Overview from "./Overview";
import { api } from "../api/client";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return { ...actual, api: { status: vi.fn(), stats: vi.fn(), activity: vi.fn() } };
});

class FakeEventSource {
  static instances: FakeEventSource[] = [];
  listeners: Record<string, ((e: MessageEvent) => void)[]> = {};
  onerror: (() => void) | null = null;
  closed = false;
  constructor(public url: string) { FakeEventSource.instances.push(this); }
  addEventListener(type: string, fn: (e: MessageEvent) => void) { (this.listeners[type] ??= []).push(fn); }
  close() { this.closed = true; }
  emit(type: string, data: object, id: string) {
    for (const fn of this.listeners[type] ?? []) fn(new MessageEvent(type, { data: JSON.stringify(data), lastEventId: id }));
  }
}

const stats = (connectivity: string, pending = 0, conflicts = 0) => ({
  local_memory_count: 3, fleet_memory_count: 1, pending_sync: pending, last_sync: null, sync_success_count: 0,
  open_conflict_count: conflicts, sync_failure_count: 0, search_latency_ms: null, connectivity,
});
const status = (connectivity: string) => ({ status: "READY", device_id: "robot-1", connectivity });

beforeEach(() => {
  FakeEventSource.instances = [];
  vi.stubGlobal("EventSource", FakeEventSource);
  vi.mocked(api.activity).mockResolvedValue([]);
});
afterEach(() => vi.unstubAllGlobals());

test("ONLINE flips to OFFLINE live via SSE without reload", async () => {
  vi.mocked(api.status).mockResolvedValue(status("ONLINE"));
  vi.mocked(api.stats).mockResolvedValue(stats("ONLINE"));
  render(<Overview />);
  await waitFor(() => expect(screen.getByTestId("fleet-link")).toHaveTextContent("ONLINE"));

  vi.mocked(api.status).mockResolvedValue(status("OFFLINE"));
  vi.mocked(api.stats).mockResolvedValue(stats("OFFLINE", 2, 1));
  act(() => FakeEventSource.instances[0].emit("CLOUD_LINK_DOWN",
    { event_id: "e1", event_type: "CLOUD_LINK_DOWN", message: "Cloud link is offline", timestamp: "2026-01-01T00:00:00Z" }, "e1"));

  await waitFor(() => expect(screen.getByTestId("fleet-link")).toHaveTextContent("OFFLINE"));
  expect(screen.getByTestId("pending-sync")).toHaveTextContent("2");
  expect(screen.getByTestId("conflicts")).toHaveTextContent("1");
  expect(screen.getByText("Cloud link is offline")).toBeInTheDocument();
  expect(screen.getByText(/operating locally/i)).toBeInTheDocument();
});

test("replayed events after reconnect do not duplicate activity rows", async () => {
  vi.mocked(api.status).mockResolvedValue(status("ONLINE"));
  vi.mocked(api.stats).mockResolvedValue(stats("ONLINE"));
  vi.mocked(api.activity).mockResolvedValue([
    { event_id: "e1", event_type: "SYNC_COMPLETED", message: "Sync done", timestamp: "2026-01-01T00:00:00Z" }]);
  render(<Overview />);
  await screen.findByText("Sync done");
  const evt = { event_id: "e1", event_type: "SYNC_COMPLETED", message: "Sync done", timestamp: "2026-01-01T00:00:00Z" };
  act(() => FakeEventSource.instances[0].emit("SYNC_COMPLETED", evt, "e1"));
  act(() => FakeEventSource.instances[0].emit("SYNC_COMPLETED", evt, "e1"));
  expect(screen.getAllByText("Sync done")).toHaveLength(1);
});

test("empty activity shows intentional copy and API failure shows actionable banner", async () => {
  vi.mocked(api.status).mockRejectedValue(new Error("Edge API unreachable"));
  vi.mocked(api.stats).mockRejectedValue(new Error("Edge API unreachable"));
  render(<Overview />);
  expect(await screen.findByRole("alert")).toHaveTextContent(/unreachable/i);
  expect(screen.getByText(/no activity yet/i)).toBeInTheDocument();
});

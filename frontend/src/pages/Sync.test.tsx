import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import Sync from "./Sync";
import { api } from "../api/client";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return { ...actual, api: { syncStatus: vi.fn(), syncQueue: vi.fn(), memories: vi.fn(), runSync: vi.fn(), approve: vi.fn(), reject: vi.fn() } };
});

class FakeES {
  static last: FakeES;
  l: Record<string, ((e: MessageEvent) => void)[]> = {};
  constructor() { FakeES.last = this; }
  addEventListener(t: string, f: (e: MessageEvent) => void) { (this.l[t] ??= []).push(f); }
  close() {}
}
const st = (over = {}) => ({ connectivity: { connectivity: "ONLINE" }, pending: 0, queued: 0, retry_wait: 0, uploading: 0, uploaded: 0,
  snapshot_pending: 0, synchronized: 0, last_attempt_at: null, ...over });

beforeEach(() => {
  vi.stubGlobal("EventSource", FakeES);
  vi.mocked(api.memories).mockResolvedValue([]);
});
afterEach(() => vi.unstubAllGlobals());

test("shows counts, queue rows, and updates on SYNC_COMPLETED without refresh", async () => {
  vi.mocked(api.syncStatus).mockResolvedValue(st({ pending: 2, queued: 1, retry_wait: 1 }));
  vi.mocked(api.syncQueue).mockResolvedValue([
    { memory_id: "m1", status: "QUEUED", retry_count: 0 },
    { memory_id: "m2", status: "RETRY_WAIT", retry_count: 3, last_error: "cloud unreachable" }]);
  render(<Sync />);
  expect(await screen.findByTestId("count-pending")).toHaveTextContent("2");
  expect(screen.getByTestId("count-retry")).toHaveTextContent("1");
  expect(screen.getByText(/cloud unreachable/)).toBeInTheDocument();

  vi.mocked(api.syncStatus).mockResolvedValue(st({ synchronized: 2 }));
  vi.mocked(api.syncQueue).mockResolvedValue([]);
  act(() => FakeES.last.l["SYNC_COMPLETED"][0](new MessageEvent("SYNC_COMPLETED", { data: JSON.stringify({ event_id: "x", event_type: "SYNC_COMPLETED", message: "done" }) })));
  await waitFor(() => expect(screen.getByTestId("count-pending")).toHaveTextContent("0"));
  expect(screen.getByText(/queue is empty/i)).toBeInTheDocument();
});

test("awaiting-approval memories show policy reasons and can be approved", async () => {
  vi.mocked(api.syncStatus).mockResolvedValue(st());
  vi.mocked(api.syncQueue).mockResolvedValue([]);
  vi.mocked(api.memories).mockResolvedValue([{ memory_id: "m9", revision: 1, content: "incident text", device_id: "d", source_type: "s",
    sync_state: "AWAITING_APPROVAL", sync_reason_codes: ["INCIDENT_REQUIRES_APPROVAL"] }]);
  vi.mocked(api.approve).mockResolvedValue({});
  render(<Sync />);
  expect(await screen.findByText(/INCIDENT_REQUIRES_APPROVAL/)).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /approve/i }));
  expect(api.approve).toHaveBeenCalledWith("m9");
});

test("shows an actionable error when the API is down", async () => {
  vi.mocked(api.syncStatus).mockRejectedValue(new Error("Edge API unreachable"));
  vi.mocked(api.syncQueue).mockRejectedValue(new Error("Edge API unreachable"));
  render(<Sync />);
  expect(await screen.findByRole("alert")).toHaveTextContent(/unreachable/i);
});

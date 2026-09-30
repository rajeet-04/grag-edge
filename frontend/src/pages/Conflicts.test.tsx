import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import Conflicts from "./Conflicts";
import { api } from "../api/client";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return { ...actual, api: { conflicts: vi.fn(), conflict: vi.fn(), resolveConflict: vi.fn() } };
});

class FakeES {
  static last: FakeES;
  l: Record<string, ((e: MessageEvent) => void)[]> = {};
  constructor() { FakeES.last = this; }
  addEventListener(t: string, f: (e: MessageEvent) => void) { (this.l[t] ??= []).push(f); }
  close() {}
}
const c = { conflict_id: "c1", logical_id: "l1", local_memory_id: "ml", fleet_memory_id: "mf" };
const mem = (id: string, content: string, device: string) => ({ memory_id: id, revision: 2, content, device_id: device, source_type: "s", sync_state: "X" });

beforeEach(() => {
  vi.stubGlobal("EventSource", FakeES);
  vi.mocked(api.conflict).mockResolvedValue({ conflict: c, local: mem("ml", "local text", "robot-1"), fleet: mem("mf", "fleet text", "robot-2"), history: [] });
});
afterEach(() => vi.unstubAllGlobals());

test("empty state", async () => {
  vi.mocked(api.conflicts).mockResolvedValue([]);
  render(<Conflicts />);
  expect(await screen.findByText(/no open conflicts/i)).toBeInTheDocument();
});

test("KEEP_LOCAL, ACCEPT_FLEET and MERGE resolution actions", async () => {
  vi.mocked(api.conflicts).mockResolvedValue([c]);
  vi.mocked(api.resolveConflict).mockResolvedValue(c);
  render(<Conflicts />);
  await userEvent.click(await screen.findByRole("button", { name: /c1/ }));
  expect(await screen.findByText("local text")).toBeInTheDocument();
  expect(screen.getByText("fleet text")).toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: "Keep local" }));
  await waitFor(() => expect(api.resolveConflict).toHaveBeenLastCalledWith("c1", "KEEP_LOCAL", undefined));
  await userEvent.click(await screen.findByRole("button", { name: /c1/ }));
  await userEvent.click(await screen.findByRole("button", { name: "Accept fleet" }));
  await waitFor(() => expect(api.resolveConflict).toHaveBeenLastCalledWith("c1", "ACCEPT_FLEET", undefined));
  await userEvent.click(await screen.findByRole("button", { name: /c1/ }));
  await userEvent.type(await screen.findByLabelText(/merged content/i), "merged");
  await userEvent.click(screen.getByRole("button", { name: "Merge" }));
  await waitFor(() => expect(api.resolveConflict).toHaveBeenLastCalledWith("c1", "MERGE", "merged"));
});

test("resolution errors are shown and new conflicts appear live", async () => {
  vi.mocked(api.conflicts).mockResolvedValue([]);
  render(<Conflicts />);
  await screen.findByText(/no open conflicts/i);
  vi.mocked(api.conflicts).mockResolvedValue([c]);
  act(() => FakeES.last.l["CONFLICT_DETECTED"][0](new MessageEvent("CONFLICT_DETECTED", { data: JSON.stringify({ event_id: "z", event_type: "CONFLICT_DETECTED", message: "m" }) })));
  await userEvent.click(await screen.findByRole("button", { name: /c1/ }));
  vi.mocked(api.resolveConflict).mockRejectedValue(new Error("conflict already resolved"));
  await userEvent.click(await screen.findByRole("button", { name: "Keep local" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(/already resolved/);
});

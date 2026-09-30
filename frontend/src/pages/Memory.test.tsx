import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import Memory from "./Memory";
import { api } from "../api/client";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return { ...actual, api: { memories: vi.fn(), memory: vi.fn() } };
});

const rec = (id: string, over = {}) => ({
  memory_id: id, logical_id: "l-" + id, revision: 1, content: "hello " + id, device_id: "robot-1", source_type: "sensor",
  sync_state: "LOCAL_ONLY", importance: "normal", memory_type: "observation", tags: ["a"], ...over,
});

test("lists memories, filters via the API, and opens detail", async () => {
  vi.mocked(api.memories).mockResolvedValue([rec("m1"), rec("m2", { content: "y".repeat(4000), memory_id: "z".repeat(200) })]);
  vi.mocked(api.memory).mockResolvedValue(rec("m1"));
  render(<Memory />);
  expect(await screen.findAllByTestId("memory-row")).toHaveLength(2);
  await userEvent.selectOptions(screen.getByLabelText(/sync state/i), "QUEUED");
  await userEvent.type(screen.getByLabelText(/^tag$/i), "valve");
  await userEvent.click(screen.getByRole("button", { name: /apply filters/i }));
  await waitFor(() => expect(api.memories).toHaveBeenLastCalledWith(expect.objectContaining({ sync_state: "QUEUED", tag: "valve" })));
  const rows = await screen.findAllByTestId("memory-row");
  await userEvent.click(rows[0]);
  expect(await screen.findByTestId("memory-detail")).toHaveTextContent("hello m1");
  expect(screen.getAllByTestId("memory-row")[1].querySelector(".content")).toBeTruthy();
});

test("empty and error states", async () => {
  vi.mocked(api.memories).mockResolvedValueOnce([]);
  render(<Memory />);
  expect(await screen.findByText(/no memories match/i)).toBeInTheDocument();
  vi.mocked(api.memories).mockRejectedValueOnce(new Error("Edge API unreachable"));
  await userEvent.click(screen.getByRole("button", { name: /apply filters/i }));
  expect(await screen.findByRole("alert")).toHaveTextContent(/unreachable/i);
});

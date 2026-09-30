import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import Search from "./Search";
import { api } from "../api/client";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return { ...actual, api: { search: vi.fn(), ask: vi.fn() } };
});

const LONG = "x".repeat(5000);
const hit = (over = {}) => ({
  memory_id: "m-".padEnd(80, "a"), origin: "FLEET", score: 0.91, dense_score: 0.8, sparse_score: 0.5, revision: 3,
  sync_state: "SYNCHRONIZED", content: LONG, device_id: "robot-9", source_type: "sensor", source_id: "s1", confidence: 0.77, ...over,
});

test("evidence cards show provenance and hide component scores until advanced is on", async () => {
  vi.mocked(api.search).mockResolvedValue({ results: [hit(), hit({ memory_id: "m2", origin: "LOCAL", content: "short" })] });
  render(<Search />);
  await userEvent.type(screen.getByRole("searchbox"), "valve");
  await userEvent.click(screen.getByRole("button", { name: /^search$/i }));
  const cards = await screen.findAllByTestId("evidence-card");
  expect(cards).toHaveLength(2);
  expect(cards[0]).toHaveTextContent("FLEET");
  expect(cards[0]).toHaveTextContent("robot-9");
  expect(cards[0]).toHaveTextContent("rev 3");
  expect(cards[0]).toHaveTextContent("0.77");
  expect(cards[0]).toHaveTextContent("SYNCHRONIZED");
  expect(cards[1]).toHaveTextContent("LOCAL");
  expect(screen.queryByText(/dense/i)).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("checkbox", { name: /advanced/i }));
  expect(screen.getAllByText(/dense 0\.80/i).length).toBeGreaterThan(0);
  expect(screen.getAllByText(/sparse 0\.50/i).length).toBeGreaterThan(0);
  expect(cards[0].querySelector(".content")).toBeTruthy(); // bounded scroll container for long content
});

test("empty result and error are explicit", async () => {
  vi.mocked(api.search).mockResolvedValueOnce({ results: [] });
  render(<Search />);
  await userEvent.type(screen.getByRole("searchbox"), "nothing");
  await userEvent.click(screen.getByRole("button", { name: /^search$/i }));
  expect(await screen.findByText(/no matching memories/i)).toBeInTheDocument();
  vi.mocked(api.search).mockRejectedValueOnce(new Error("Edge API unreachable"));
  await userEvent.click(screen.getByRole("button", { name: /^search$/i }));
  expect(await screen.findByRole("alert")).toHaveTextContent(/unreachable/i);
});

test("Ask GRAG mode calls the chat endpoint", async () => {
  vi.mocked(api.ask).mockResolvedValue("Close valve B first.");
  render(<Search />);
  await userEvent.click(screen.getByRole("radio", { name: /ask grag/i }));
  await userEvent.type(screen.getByRole("searchbox"), "what next?");
  await userEvent.click(screen.getByRole("button", { name: /^ask$/i }));
  await waitFor(() => expect(api.ask).toHaveBeenCalledWith("what next?"));
  expect(await screen.findByText("Close valve B first.")).toBeInTheDocument();
});

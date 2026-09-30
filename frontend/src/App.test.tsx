import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import App from "./App";

vi.mock("./pages/Overview", () => ({ default: () => <p>overview page</p> }));
vi.mock("./pages/Search", () => ({ default: () => <p>search page</p> }));
vi.mock("./pages/Memory", () => ({ default: () => <p>memory page</p> }));
vi.mock("./pages/Sync", () => ({ default: () => <p>sync page</p> }));
vi.mock("./pages/Conflicts", () => ({ default: () => <p>conflicts page</p> }));

const renderAt = (path: string) => render(<MemoryRouter initialEntries={[path]}><App /></MemoryRouter>);

test("shows the five destinations", () => {
  renderAt("/");
  const nav = screen.getByRole("navigation", { name: /primary/i });
  for (const label of ["Overview", "Search", "Memory", "Sync", "Conflicts"]) {
    expect(nav).toHaveTextContent(label);
  }
  expect(nav.querySelectorAll("a")).toHaveLength(5);
});

test("marks the active route", () => {
  renderAt("/sync");
  expect(screen.getByRole("link", { name: "Sync" })).toHaveAttribute("aria-current", "page");
  expect(screen.getByRole("link", { name: "Overview" })).not.toHaveAttribute("aria-current");
  expect(screen.getByText("sync page")).toBeInTheDocument();
});

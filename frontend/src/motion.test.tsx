import { act, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";
import { Cell } from "./components/StatusRail";

const setReduced = (reduced: boolean) =>
  vi.stubGlobal("matchMedia", (q: string) => ({ matches: reduced && q.includes("reduce"), media: q, addEventListener() {}, removeEventListener() {} }));
afterEach(() => vi.unstubAllGlobals());

test("with reduced motion a changed number is shown immediately", () => {
  setReduced(true);
  const { rerender } = render(<Cell label="Pending" value={1} id="p" />);
  rerender(<Cell label="Pending" value={9} id="p" />);
  expect(screen.getByTestId("p")).toHaveTextContent("9");
});

test("without reduced motion a changed number rolls and always lands on the new value", async () => {
  setReduced(false);
  const { rerender } = render(<Cell label="Pending" value={0} id="p" />);
  expect(screen.getByTestId("p")).toHaveTextContent("0");
  await act(async () => { rerender(<Cell label="Pending" value={5} id="p" />); });
  await waitFor(() => expect(screen.getByTestId("p")).toHaveTextContent("5"), { timeout: 1500 });
});

test("the first value and non-numeric values are never animated", () => {
  setReduced(false);
  render(<Cell label="Fleet link" value="OFFLINE" id="l" />);
  expect(screen.getByTestId("l")).toHaveTextContent("OFFLINE");
});

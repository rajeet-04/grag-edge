import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";

const mermaidMock = vi.hoisted(() => ({
  initialize: vi.fn(),
  render: vi.fn(async (id: string) => ({ svg: `<svg id="${id}" data-testid="mm-svg" viewBox="0 0 10 10"></svg>` })),
}));
vi.mock("mermaid", () => ({ default: mermaidMock }));

import AnswerMarkdown from "./AnswerMarkdown";

const SAMPLE =
  "Based on the provided data...\n\n**Equipment Status & Observations:**\n*  **Pump P-41:** Currently experiencing fluctuating discharge pressure.\n*  **Compressor C-17:** Oil level nominal.\n\n## Reasoning Steps\n\n1. Identify equipment -> Categorize -> Synthesize\n\n## Graph Reasoning Path\n```mermaid\ngraph TD\n    A[User Query] --> B[Scan_Context]\n    B --> C[Identify_Equipment]\n    C --> D[Extract_Status]\n    D --> E[Identify_Procedures]\n    E --> F[Synthesize_Answer]\n    F --> G[Final_Response]\n```\n";

beforeEach(() => { mermaidMock.initialize.mockClear(); mermaidMock.render.mockClear(); });

test("markdown renders as real elements: bold, bullets, headings, numbered list", async () => {
  const { container } = render(<AnswerMarkdown text={SAMPLE.replace(/```mermaid[\s\S]*$/, "")} />);
  expect(container.querySelectorAll("strong").length).toBeGreaterThanOrEqual(3);
  expect(screen.getAllByRole("listitem").length).toBe(3);
  expect(container.querySelector("ul")).toBeTruthy();
  expect(container.querySelector("ol")).toBeTruthy();
  expect(screen.getByRole("heading", { name: "Reasoning Steps" })).toBeInTheDocument();
  expect(container.textContent).not.toContain("**");
});

test("GFM tables render as a table", () => {
  render(<AnswerMarkdown text={"| Asset | State |\n|---|---|\n| P-41 | fault |"} />);
  expect(screen.getByRole("table")).toBeInTheDocument();
  expect(screen.getByRole("columnheader", { name: "Asset" })).toBeInTheDocument();
  expect(screen.getByRole("cell", { name: "fault" })).toBeInTheDocument();
});

test("mermaid fence renders a diagram figure with strict security and a source toggle", async () => {
  render(<AnswerMarkdown text={SAMPLE} />);
  expect(await screen.findByTestId("mm-svg")).toBeInTheDocument();
  expect(mermaidMock.initialize).toHaveBeenCalledWith(expect.objectContaining({ securityLevel: "strict", startOnLoad: false }));
  const fig = screen.getByRole("figure");
  expect(fig).toHaveTextContent(/graph reasoning path/i);
  expect(screen.getByRole("img", { name: /graph reasoning path/i })).toBeInTheDocument();
  expect(screen.queryByText(/graph TD/)).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /view source/i }));
  expect(screen.getByText(/graph TD/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /hide source/i })).toHaveAttribute("aria-expanded", "true");
});

test("two diagrams get unique ids", async () => {
  const two = "```mermaid\ngraph TD\nA-->B\n```\n\n```mermaid\ngraph TD\nC-->D\n```";
  render(<AnswerMarkdown text={two} />);
  await waitFor(() => expect(mermaidMock.render).toHaveBeenCalledTimes(2));
  const ids = mermaidMock.render.mock.calls.map((c) => c[0]);
  expect(new Set(ids).size).toBe(2);
});

test("invalid mermaid falls back to source in a code block with a muted note", async () => {
  mermaidMock.render.mockRejectedValueOnce(new Error("Parse error"));
  const { container } = render(<AnswerMarkdown text={"```mermaid\nnot a graph ((\n```"} />);
  expect(await screen.findByText(/could not be rendered/i)).toBeInTheDocument();
  expect(container.querySelector("pre code")).toHaveTextContent("not a graph ((");
  expect(screen.queryByTestId("mm-svg")).not.toBeInTheDocument();
});

test("an unclosed (streaming) mermaid fence is not rendered as a diagram yet", async () => {
  const { container, rerender } = render(<AnswerMarkdown text={"intro\n```mermaid\ngraph TD\n A-->B"} />);
  expect(container.querySelector("pre code")).toHaveTextContent("graph TD");
  expect(mermaidMock.render).not.toHaveBeenCalled();
  rerender(<AnswerMarkdown text={"intro\n```mermaid\ngraph TD\n A-->B\n```\n"} />);
  expect(await screen.findByTestId("mm-svg")).toBeInTheDocument();
  expect(mermaidMock.render).toHaveBeenCalledTimes(1);
});

test("raw HTML in the answer is never rendered as HTML", () => {
  const { container } = render(
    <AnswerMarkdown text={'hello <script>window.__pwn = 1</script> <img src=x onerror="window.__pwn=2"> [x](javascript:alert(1))'} />,
  );
  expect(container.querySelector("script")).toBeNull();
  expect(container.querySelector("img")).toBeNull();
  expect(container.querySelector("[onerror]")).toBeNull();
  expect(container.querySelector('a[href^="javascript"]')).toBeNull();
  expect((window as unknown as { __pwn?: number }).__pwn).toBeUndefined();
});

test("plain text answers still show as text", () => {
  render(<AnswerMarkdown text="Close valve B first." />);
  expect(screen.getByText("Close valve B first.")).toBeInTheDocument();
});

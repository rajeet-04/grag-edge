import { execFile } from "node:child_process";
import { expect, test, type Page } from "@playwright/test";

// Runs against the REAL stack (see playwright.real.config.ts). Preconditions, prepared by
// scripts/demo/e2e_real.sh: make demo-start (fleet + local seeds), grag-edge-ui up, make demo-conflict.
const DEMO_ROOT = process.env.DEMO_ROOT ?? "/repo";
const demo = (script: string) => new Promise<void>((resolve, reject) => {
  const child = execFile("bash", [`scripts/demo/${script}`], { cwd: DEMO_ROOT, env: process.env, timeout: 150000 },
    (err, stdout, stderr) => (err ? reject(new Error(`${script} failed: ${stderr || stdout}`)) : resolve()));
  child.stdout?.pipe(process.stdout);
});
const getJson = async (page: Page, path: string) => (await page.request.get(path)).json();

test.describe.configure({ mode: "serial" });

let problems: string[] = [];
test.beforeEach(({ page }) => {
  problems = [];
  page.on("pageerror", (e) => problems.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") problems.push(m.text()); });
});
test.afterEach(() => { expect(problems).toEqual([]); });

test("status rail shows the real edge state served through nginx", async ({ page }) => {
  const status = await getJson(page, "/api/v1/edge/status");
  const stats = await getJson(page, "/api/v1/edge/stats");
  expect(status.status).toBe("READY");
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "GRAG Edge" })).toBeVisible();
  await expect(page.getByTestId("device")).toHaveText(status.device_id);
  await expect(page.getByTestId("fleet-link")).toHaveText("ONLINE");
  await expect(page.getByText("CONNECTED")).toBeVisible();
  await expect(page.getByText("READY", { exact: true })).toBeVisible();
  const metrics = page.getByRole("region", { name: "Metrics" });
  await expect(metrics).toContainText(`Local memories${stats.local_memory_count}`);
  await expect(metrics).toContainText(`Fleet memories${stats.fleet_memory_count}`);
  expect(stats.fleet_memory_count).toBeGreaterThanOrEqual(6);
});

test("real hybrid search returns evidence with provenance for fleet and local memories", async ({ page }) => {
  await page.goto("/search");
  await page.getByLabel("Query").fill("Pump P-41 seal leak");
  await page.getByRole("button", { name: "Search" }).click();
  const cards = page.getByTestId("evidence-card");
  await expect(cards.first()).toBeVisible({ timeout: 30000 });
  const api = await page.request.post("/api/v1/edge/search", { data: { query: "Pump P-41 seal leak", mode: "hybrid", limit: 10 } });
  const results = (await api.json()).results;
  expect(results.length).toBeGreaterThan(0);
  // The top card is the real top hit: same memory, origin and device as the API returned.
  const top = results[0];
  await expect(cards.first()).toContainText(top.memory_id);
  await expect(cards.first()).toContainText(String(top.device_id));
  await expect(cards.first()).toContainText(String(top.origin).toUpperCase().includes("FLEET") ? "FLEET" : "LOCAL");
  await expect(cards.first()).toContainText(`rev ${top.revision}`);
  await expect(cards.first()).toContainText(String(top.source_type));
  // Provenance of another robot's memory: the fleet seed arrives as FLEET origin from robot-edge-002.
  const fleetCard = cards.filter({ hasText: "seal leak" });
  await expect(fleetCard).toHaveCount(1);
  await expect(fleetCard).toContainText("FLEET");
  await expect(fleetCard).toContainText("robot-edge-002");
  await expect(fleetCard).toContainText("fleet_seed:fleet-seed-1");
});

test("sync page reflects real queue state and Run sync works", async ({ page }) => {
  await page.goto("/sync");
  const status = await getJson(page, "/api/v1/edge/sync/status");
  await expect(page.getByRole("button", { name: "Run sync now" })).toBeVisible();
  await expect(page.getByTestId("count-pending")).toHaveText(String(status.pending));
  await page.getByRole("button", { name: "Run sync now" }).click();
  await expect(page.getByRole("alert")).toHaveCount(0);
  await expect(page.getByRole("region", { name: "Sync counts" })).toBeVisible();
});

test("real conflict (make demo-conflict) is listed and opens both branches", async ({ page }) => {
  const conflicts = await getJson(page, "/api/v1/edge/conflicts");
  expect(conflicts.length).toBeGreaterThanOrEqual(1);
  const id = conflicts[0].conflict_id;
  const detail = await getJson(page, `/api/v1/edge/conflicts/${id}`);
  await page.goto("/");
  await expect(page.getByTestId("conflicts")).not.toHaveText("0");
  await page.getByRole("link", { name: "Conflicts" }).click();
  await page.getByRole("button", { name: id }).click();
  const panel = page.getByRole("region", { name: "Resolve conflict" });
  await expect(panel).toContainText(detail.local.content);
  await expect(panel).toContainText(detail.fleet.content);
  await expect(panel).toContainText("Valve V-22");
  await expect(panel.getByRole("button", { name: "Keep local" })).toBeVisible();
});

test("real offline/online transition via the demo network controls", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("fleet-link")).toHaveText("ONLINE");

  // scripts/demo/offline.sh really detaches the API container from the cloud network.
  let exitedAt = 0;
  const offline = demo("offline.sh").then(() => { exitedAt = Date.now(); });
  await expect(page.getByTestId("fleet-link")).toHaveText("OFFLINE", { timeout: 60000 });
  const seenAt = Date.now();
  await offline;
  // The script returns once the API reports OFFLINE; the browser must not lag it by more than 2 s.
  expect(seenAt - (exitedAt || seenAt)).toBeLessThan(2000);
  await expect(page.getByText(/Fleet link is offline/)).toBeVisible();

  // Local search keeps working offline.
  await page.getByRole("link", { name: "Search" }).click();
  await page.getByLabel("Query").fill("Pump P-41 seal leak");
  await page.getByRole("button", { name: "Search" }).click();
  await expect(page.getByTestId("evidence-card").filter({ hasText: "seal leak" })).toHaveCount(1);
  await page.getByRole("link", { name: "Overview" }).click();
  await expect(page.getByTestId("fleet-link")).toHaveText("OFFLINE");

  const online = demo("online.sh");
  await expect(page.getByTestId("fleet-link")).toHaveText("ONLINE", { timeout: 60000 });
  await online;
  await expect(page.getByText(/Fleet link is offline/)).toHaveCount(0);
});

import { expect, test } from "@playwright/test";

const setLink = (page: import("@playwright/test").Page, state: "ONLINE" | "OFFLINE") =>
  page.request.get(`/__mock/connectivity?state=${state}`);

test("console loads, navigates, searches, and reflects a link transition in under 2 s", async ({ page }) => {
  const problems: string[] = [];
  page.on("pageerror", (e) => problems.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") problems.push(m.text()); });

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "GRAG Edge" })).toBeVisible();
  await expect(page.getByTestId("device")).toHaveText("ROBOT-02");
  await expect(page.getByTestId("fleet-link")).toHaveText("ONLINE");
  await expect(page.getByText("CONNECTED")).toBeVisible();

  // design section 28: dashboard connectivity update < 2 s after a detected transition
  let started = Date.now();
  await setLink(page, "OFFLINE");
  await expect(page.getByTestId("fleet-link")).toHaveText("OFFLINE", { timeout: 2000 });
  expect(Date.now() - started).toBeLessThan(2000);
  await expect(page.getByText(/Fleet link is offline/)).toBeVisible();
  await expect(page.getByText("CLOUD_LINK_DOWN")).toBeVisible();
  started = Date.now();
  await setLink(page, "ONLINE");
  await expect(page.getByTestId("fleet-link")).toHaveText("ONLINE", { timeout: 2000 });
  expect(Date.now() - started).toBeLessThan(2000);

  await page.getByRole("link", { name: "Search" }).click();
  await page.getByLabel("Query").fill("pump seal");
  await page.getByRole("button", { name: "Search" }).click();
  const card = page.getByTestId("evidence-card");
  await expect(card).toContainText("FLEET");
  await expect(card).toContainText("ROBOT-01");
  await expect(card).toContainText("Pump P-41 seal replaced");

  await page.getByRole("link", { name: "Memory" }).click();
  await expect(page.getByRole("heading", { name: "Memory" })).toBeVisible();
  await expect(page.getByText("Pump P-41 seal replaced by ROBOT-01")).toBeVisible();
  await page.getByRole("link", { name: "Sync" }).click();
  await expect(page.getByRole("button", { name: "Run sync now" })).toBeVisible();
  await page.getByRole("link", { name: "Conflicts" }).click();
  await expect(page.getByRole("heading", { name: "Conflicts" })).toBeVisible();

  // keyboard: nav links are reachable by Tab and show a focus indicator
  await page.goto("/");
  await page.keyboard.press("Tab");
  const outline = await page.evaluate(() => getComputedStyle(document.activeElement!).outlineStyle);
  expect(outline).not.toBe("none");

  expect(problems).toEqual([]);
});

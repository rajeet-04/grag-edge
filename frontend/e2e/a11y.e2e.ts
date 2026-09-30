import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

// Accessibility audit: every page, light and dark theme, WCAG 2.x A/AA + best-practice rules.
// Serious and critical violations fail the test; lesser impacts are still listed in the message.
const PAGES = [
  { name: "overview", path: "/" },
  { name: "search", path: "/search" },
  { name: "search results", path: "/search", prepare: async (page: Page) => {
      await page.getByLabel("Query").fill("pump seal");
      await page.getByRole("button", { name: "Search" }).click();
      await expect(page.getByTestId("evidence-card")).toBeVisible();
      await page.getByLabel("Advanced scores").check();
    } },
  { name: "memory", path: "/memory" },
  { name: "memory detail", path: "/memory", prepare: async (page: Page) => {
      await page.getByTestId("memory-row").first().click();
      await expect(page.getByTestId("memory-detail")).toBeVisible();
    } },
  { name: "sync", path: "/sync" },
  { name: "conflicts", path: "/conflicts" },
  { name: "conflict resolve", path: "/conflicts", conflict: true, prepare: async (page: Page) => {
      await page.getByRole("button", { name: "conflict_abc123" }).click();
      await expect(page.getByRole("button", { name: "Keep local" })).toBeVisible();
    } },
];

for (const scheme of ["light", "dark"] as const) {
  test.describe(`axe ${scheme}`, () => {
    test.use({ colorScheme: scheme });
    for (const entry of PAGES) {
      test(`${entry.name} has no serious or critical violations`, async ({ page }) => {
        await page.request.get(`/__mock/connectivity?state=ONLINE`);
        await page.request.get(`/__mock/conflict?on=${entry.conflict ? 1 : 0}`);
        await page.goto(entry.path);
        await expect(page.locator("main h2").first()).toBeVisible();
        const bg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
        expect(bg).toBe(scheme === "light" ? "rgb(244, 246, 248)" : "rgb(11, 13, 16)"); // the audited theme really is applied
        await entry.prepare?.(page);
        await page.waitForTimeout(300); // let transitions settle so contrast is measured on final colors
        const { violations } = await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"])
          .analyze();
        const summary = violations.map((v) => `${v.impact} ${v.id}: ${v.nodes.map((n) => n.target.join(" ")).slice(0, 4).join(" | ")}`);
        const blocking = violations.filter((v) => v.impact === "serious" || v.impact === "critical");
        expect(blocking.map((v) => v.id), summary.join("\n")).toEqual([]);
        expect(violations.length, "minor violations: " + summary.join("\n")).toBe(0);
      });
    }
  });
}

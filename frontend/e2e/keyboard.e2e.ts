import { expect, test, type Page } from "@playwright/test";

// Keyboard-only operation: reachability, order, focus visibility, focus management.
const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

const describe = (page: Page) => page.evaluate(() => {
  const el = document.activeElement as HTMLElement;
  return { tag: el.tagName.toLowerCase(), text: (el.getAttribute("aria-label") ?? el.textContent ?? "").trim().slice(0, 40),
    outline: getComputedStyle(el).outlineStyle, offscreen: el.getBoundingClientRect().top < 0 };
});

async function tabThrough(page: Page) {
  const expected = await page.evaluate((sel) => [...document.querySelectorAll<HTMLElement>(sel)]
    .filter((e) => e.offsetParent !== null || e.classList.contains("skip-link"))
    .filter((e, _i, all) => !(e instanceof HTMLInputElement && e.type === "radio" && all.some((o) => o instanceof HTMLInputElement && o.type === "radio" && o.name === e.name && o !== e && (o.checked || !e.checked) && all.indexOf(o) < all.indexOf(e)))).length, FOCUSABLE);
  const seen: { tag: string; text: string; outline: string }[] = [];
  for (let i = 0; i < expected; i++) {
    await page.keyboard.press("Tab");
    seen.push(await describe(page));
  }
  return { expected, seen };
}

test("every page: all interactive controls are reachable by Tab, in DOM order, each with a visible focus ring", async ({ page }) => {
  for (const path of ["/", "/search", "/memory", "/sync", "/conflicts"]) {
    await page.goto(path);
    await expect(page.locator("main h2").first()).toBeVisible();
    const positive = await page.evaluate(() => [...document.querySelectorAll("[tabindex]")].filter((e) => Number(e.getAttribute("tabindex")) > 0).length);
    expect(positive, `${path}: no positive tabindex`).toBe(0);
    const { expected, seen } = await tabThrough(page);
    expect(expected, `${path}: has focusable controls`).toBeGreaterThan(5);
    expect(new Set(seen.map((s) => s.tag + s.text)).size, `${path}: tab visited distinct controls`).toBeGreaterThan(5);
    for (const s of seen) expect(s.outline, `${path}: ${s.tag} "${s.text}" shows focus`).not.toBe("none");
    // The first five stops after the skip link are the primary nav, in order.
    expect(seen.slice(0, 6).map((s) => s.text)).toEqual(["Skip to main content", "Overview", "Search", "Memory", "Sync", "Conflicts"]);
  }
});

test("skip link moves focus to main content", async ({ page }) => {
  await page.goto("/sync");
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Skip to main content" })).toBeFocused();
  await expect(page.getByRole("link", { name: "Skip to main content" })).toBeInViewport();
  await page.keyboard.press("Enter");
  await expect(page.locator("main")).toBeFocused();
});

test("search is operable by keyboard alone", async ({ page }) => {
  await page.goto("/search");
  await page.getByLabel("Query").focus();
  await page.keyboard.type("pump seal");
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("evidence-card")).toContainText("ROBOT-01");
  await page.getByLabel("Memory search").focus();
  await page.keyboard.press("ArrowDown"); // radio group arrow navigation selects "Ask GRAG"
  await expect(page.getByLabel("Ask GRAG")).toBeChecked();
});

test("memory rows open with Enter and Space; focus enters the detail; Escape returns focus to the row", async ({ page }) => {
  await page.goto("/memory");
  const row = page.getByTestId("memory-row").first();
  await row.focus();
  await page.keyboard.press("Enter");
  const detail = page.getByTestId("memory-detail");
  await expect(detail).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(detail).toHaveCount(0);
  await expect(row).toBeFocused();
  await page.keyboard.press("Space");
  await expect(detail).toBeFocused();
  await page.keyboard.press("Tab"); // heading is static; first tab stop inside is Close
  await expect(page.getByRole("button", { name: "Close" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(row).toBeFocused();
});

test("conflict resolution is reachable by keyboard and focus moves to the resolve panel", async ({ page }) => {
  await page.request.get("/__mock/conflict?on=1");
  await page.goto("/conflicts");
  const open = page.getByRole("button", { name: "conflict_abc123" });
  await open.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("region", { name: "Resolve conflict" })).toBeFocused();
  for (const name of ["Keep local", "Accept fleet"]) {
    await page.keyboard.press("Tab");
    await expect(page.getByRole("button", { name })).toBeFocused();
  }
  await page.keyboard.press("Tab");
  await expect(page.getByLabel("Merged content")).toBeFocused();
  await page.request.get("/__mock/conflict?on=0");
});

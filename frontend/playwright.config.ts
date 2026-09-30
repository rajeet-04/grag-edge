import { defineConfig } from "@playwright/test";

// Runs against the built console served by e2e/mock-edge.mjs (hermetic, no Docker services).
// CHROMIUM_PATH points at a system Chromium (e.g. `apk add chromium` in node:alpine).
export default defineConfig({
  testDir: "./e2e",
  testMatch: /.*\.e2e\.ts/,
  timeout: 30000,
  use: { baseURL: "http://127.0.0.1:4173", launchOptions: { executablePath: process.env.CHROMIUM_PATH, args: ["--no-sandbox"] } },
  webServer: { command: "node e2e/mock-edge.mjs", url: "http://127.0.0.1:4173/api/v1/edge/status", reuseExistingServer: false },
});

import { defineConfig } from "@playwright/test";

// Real-stack run: the BUILT console served by nginx (grag-edge-ui) proxying the real Edge API in the
// live Compose stack. Driven by scripts/demo/e2e_real.sh (make demo-e2e-real); no mock server.
// REAL_UI_URL defaults to the UI container on the Compose network.
export default defineConfig({
  testDir: "./e2e",
  testMatch: /.*\.real\.ts/,
  timeout: 180000,
  workers: 1,
  use: { baseURL: process.env.REAL_UI_URL ?? "http://grag-edge-ui", launchOptions: { executablePath: process.env.CHROMIUM_PATH, args: ["--no-sandbox"] } },
});

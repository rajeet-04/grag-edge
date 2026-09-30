/// <reference types="vitest" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: Object.fromEntries(["/api", "/v1"].map((p) => [p, { target: process.env.EDGE_API_TARGET ?? "http://localhost:8000", changeOrigin: true }])),
  },
  test: { environment: "jsdom", globals: true, setupFiles: ["./src/setupTests.ts"], css: false },
});

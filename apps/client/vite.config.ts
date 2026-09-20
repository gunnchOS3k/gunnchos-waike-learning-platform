/// <reference types="vitest/config" />
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  clearScreen: false,
  server: { port: 1420, strictPort: true },
  envPrefix: ["VITE_", "TAURI_"],
  build: { target: "esnext" },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    globals: true,
    testTimeout: 15000,
    hookTimeout: 15000,
    // Live-hub tests own a server lifecycle; they run from vitest.live.config.ts.
    exclude: ["node_modules/**", "dist/**", "src/test/live/**"],
  },
});

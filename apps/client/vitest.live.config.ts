/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

/**
 * Live-hub suite: the client talks to a real uvicorn process over HTTP.
 * Kept separate from the jsdom unit suite because it owns a server lifecycle.
 */
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "node",
    globalSetup: ["./src/test/live/globalSetup.ts"],
    include: ["src/test/live/**/*.live.test.ts", "src/test/live/**/*.live.test.tsx"],
    testTimeout: 30_000,
    hookTimeout: 60_000,
    // One hub, one database: parallel files would race on shared section state.
    fileParallelism: false,
  },
});

import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The client builds into `dist/client`, next to the compiled service in `dist/`.
// The Fastify process serves that directory, so one Cloud Run service ships the
// API and the app together and the session cookie is always first-party.
export default defineConfig({
  root: "client",
  plugins: [react()],
  base: "/",
  build: {
    outDir: "../dist/client",
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      // Dev only: in production the same Fastify process serves both.
      "/v1": "http://127.0.0.1:8080",
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    include: ["client/src/**/*.test.ts", "client/src/**/*.test.tsx"],
    setupFiles: ["client/src/test-setup.ts"],
  },
});

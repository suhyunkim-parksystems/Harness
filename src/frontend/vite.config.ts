import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";

const backendPort = process.env.BACKEND_PORT ?? "8000";
const backendTarget = process.env.VITE_API_PROXY_TARGET ?? `http://127.0.0.1:${backendPort}`;
const frontendHost = process.env.FRONTEND_HOST ?? "0.0.0.0";
const testSetupFile = fileURLToPath(new URL("../../tests/frontend/setupTests.ts", import.meta.url));
const modulePath = (path: string) => fileURLToPath(new URL(`node_modules/${path}`, import.meta.url));

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: [
      {
        find: /^@testing-library\/react$/,
        replacement: modulePath("@testing-library/react/dist/@testing-library/react.esm.js")
      },
      { find: /^react\/jsx-runtime$/, replacement: modulePath("react/jsx-runtime.js") },
      { find: /^react\/jsx-dev-runtime$/, replacement: modulePath("react/jsx-dev-runtime.js") },
      { find: /^react$/, replacement: modulePath("react/index.js") },
      { find: /^react-dom\/client$/, replacement: modulePath("react-dom/client.js") },
      { find: /^react-dom\/test-utils$/, replacement: modulePath("react-dom/test-utils.js") },
      { find: /^react-dom$/, replacement: modulePath("react-dom/index.js") },
      { find: /^vitest$/, replacement: modulePath("vitest/dist/index.js") }
    ]
  },
  server: {
    host: frontendHost,
    port: Number(process.env.FRONTEND_PORT ?? "5173"),
    proxy: {
      "/api": {
        target: backendTarget,
        changeOrigin: true
      }
    }
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: testSetupFile
  }
});

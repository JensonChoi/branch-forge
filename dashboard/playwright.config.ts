import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "e2e",
  use: {
    baseURL: "http://127.0.0.1:5179",
    viewport: { width: 1440, height: 1000 },
  },
  webServer: [
    {
      command: "npm run dev -- --port 5179 --strictPort",
      url: "http://127.0.0.1:5179",
      env: { BRANCHFORGE_API_URL: "http://127.0.0.1:8019" },
      reuseExistingServer: false,
    },
    {
      command:
        "../.venv/bin/uvicorn branchforge.api.app:app --host 127.0.0.1 --port 8019",
      url: "http://127.0.0.1:8019/api/health",
      env: { BRANCHFORGE_RUNS_DIR: "../runs" },
      reuseExistingServer: false,
    },
  ],
});

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
      reuseExistingServer: false,
    },
    {
      command:
        "../.venv/bin/uvicorn branchforge.api.app:app --host 127.0.0.1 --port 8000",
      url: "http://127.0.0.1:8000/api/health",
      env: { BRANCHFORGE_RUNS_DIR: "../runs" },
      reuseExistingServer: false,
    },
  ],
});

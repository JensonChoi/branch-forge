import process from "node:process";
import { defineConfig } from "vite";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      "/api": process.env.BRANCHFORGE_API_URL ?? "http://127.0.0.1:8000",
    },
  },
});

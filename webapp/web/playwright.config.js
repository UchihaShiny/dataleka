import { defineConfig } from "@playwright/test";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
const root = resolve(fileURLToPath(new URL("../..", import.meta.url)));
const store = mkdtempSync(join(tmpdir(), "datae-browser-"));
process.on("exit", () => rmSync(store, { recursive: true, force: true }));
const baseURL = "http://127.0.0.1:8601";
const python = resolve(
  root,
  process.platform === "win32"
    ? ".venv/Scripts/python.exe"
    : ".venv/bin/python",
);
export default defineConfig({
  testDir: "./tests",
  workers: 1,
  retries: 0,
  timeout: 120000,
  use: { baseURL, headless: true, trace: "retain-on-failure" },
  webServer: {
    command: `"${python}" -m uvicorn webapp.api.main:app --host 127.0.0.1 --port 8601 --no-access-log`,
    cwd: root,
    url: `${baseURL}/api/meta`,
    reuseExistingServer: false,
    env: {
      DATAE_MODE: "demo",
      PYTHON_DOTENV_DISABLED: "1",
      DATAE_DEMO_STORE: store,
    },
  },
  reporter: [["list"], ["json", { outputFile: "test-results/results.json" }]],
});

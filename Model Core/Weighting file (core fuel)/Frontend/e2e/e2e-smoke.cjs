"use strict";

// J3 launcher: spawns the real Electron app in E2E mode and reports the
// runner exit code. Run with: npm run test:e2e
// Requires a display-capable Windows session (real window creation).

const { spawn } = require("node:child_process");
const path = require("node:path");

const electronPath = require("electron"); // binary path when required from Node

const projectRoot = path.resolve(__dirname, "..");
const child = spawn(electronPath, ["."], {
  cwd: projectRoot,
  env: { ...process.env, MOLING_E2E: "1" },
  stdio: ["ignore", "pipe", "pipe"],
});

let stdout = "";
let stderr = "";
child.stdout.on("data", (chunk) => {
  stdout += chunk.toString();
});
child.stderr.on("data", (chunk) => {
  stderr += chunk.toString();
});

const timeout = setTimeout(() => {
  console.error("E2E timed out after 120s; killing Electron.");
  child.kill();
  process.exit(2);
}, 120_000);

child.on("exit", (code) => {
  clearTimeout(timeout);
  const match = stdout.match(/MOLING_E2E_RESULT=([\s\S]*)/);
  if (match) {
    try {
      const results = JSON.parse(match[1]);
      for (const r of results) {
        console.log((r.pass ? "PASS" : "FAIL") + "  " + r.scenario + (r.detail ? "  ->  " + r.detail : ""));
      }
    } catch {
      console.log(stdout);
    }
  } else {
    console.log(stdout);
    console.log(stderr);
  }
  process.exit(code === null || code === undefined ? 1 : code);
});
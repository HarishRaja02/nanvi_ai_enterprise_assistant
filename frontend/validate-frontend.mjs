import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL(".", import.meta.url));
const main = fs.readFileSync(path.join(root, "src/main.tsx"), "utf8");
const api = fs.readFileSync(path.join(root, "src/api.ts"), "utf8");
const css = fs.readFileSync(path.join(root, "src/styles.css"), "utf8");
const packageJson = JSON.parse(fs.readFileSync(path.join(root, "package.json"), "utf8"));

const checks = [
  ["typed API boundary", api.includes("class NanviApiClient")],
  ["401 session handling", api.includes("response.status === 401")],
  ["logout clears session", main.includes("sessionStorage.removeItem(TOKEN_KEY)")],
  ["backend identity", main.includes("api.me()")],
  ["frontend role switcher is demo-only", main.includes("DEMO_MODE &&")],
  ["no frontend role authorization", main.includes("Backend authorization remains authoritative") || main.includes("backend request")],
  ["source reauthorization boundary", main.includes("api.source(source.id)")],
  ["report download backend URL", main.includes("api.reportDownloadUrl(reportId)")],
  ["no file upload UI without backend support", !main.includes("type=\"file\"")],
  ["loading state", main.includes("Securing your session") && main.includes("Nanvi is checking authorized sources")],
  ["error state", main.includes("role=\"alert\"") && main.includes("bubble-error")],
  ["keyboard submit", main.includes("e.key === \"Enter\"")],
  ["max query length", main.includes("maxLength={4000}")],
  ["responsive breakpoints", css.includes("@media(max-width:850px)") && css.includes("@media(max-width:560px)")],
  ["reduced motion", css.includes("prefers-reduced-motion")],
  ["test script", packageJson.scripts?.test === "vitest run"],
  ["typecheck script", packageJson.scripts?.typecheck === "tsc --noEmit"],
  ["lint script", packageJson.scripts?.lint === "eslint . --max-warnings 0"],
  ["build script", packageJson.scripts?.build === "vite build"],
];

const failed = checks.filter(([, ok]) => !ok);
for (const [name, ok] of checks) console.log(`${ok ? "PASS" : "FAIL"}  ${name}`);
if (failed.length) process.exit(1);
console.log(`\n${checks.length} static frontend checks passed.`);

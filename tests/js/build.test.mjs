import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

import { ALLOWED_EXTERNAL_IMPORTS, buildBundle } from "../../scripts/build_desktop.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const BUILD = path.join(ROOT, "scripts", "build_desktop.mjs");
const PLUGIN = path.join(ROOT, "desktop", "plugin.js");

function runBuild(args) {
  return spawnSync(process.execPath, [BUILD, ...args], { cwd: ROOT, encoding: "utf8" });
}

test("checked-in plugin.js matches a fresh build", () => {
  assert.equal(readFileSync(PLUGIN, "utf8"), buildBundle({ root: ROOT }));
});

test("plugin.js imports only react and registers the TempleOS pane", () => {
  const plugin = readFileSync(PLUGIN, "utf8");
  const imports = [...plugin.matchAll(/^import\s+.*?from\s+["']([^"']+)["'];$/gm)].map((match) => match[1]);
  assert.ok(imports.length > 0);
  for (const specifier of imports) {
    assert.ok(ALLOWED_EXTERNAL_IMPORTS.includes(specifier), specifier);
  }
  assert.doesNotMatch(plugin, /\bimport\s*\(/);
  assert.doesNotMatch(plugin, /\beval\s*\(/);
  assert.doesNotMatch(plugin, /\bnew Function\b/);
  assert.match(plugin, /templeos-desktop-styles/);
  assert.match(plugin, /export function register\s*\(ctx\)/);
  assert.match(plugin, /export default __tosPlugin/);
  assert.match(plugin, /TempleOS/);
  assert.equal(plugin.includes("127.0.0.1"), false);
  assert.equal(plugin.includes("localStorage"), false);
  assert.equal(plugin.includes("sessionStorage"), false);
});

test("--check accepts the bundle and rejects a stale one", () => {
  const current = runBuild(["--check"]);
  assert.equal(current.status, 0, current.stderr || current.stdout);
  assert.match(current.stdout, /desktop\/plugin\.js is up to date/);

  const fixture = mkdtempSync(path.join(ROOT, "tests", "js", ".build-"));
  try {
    const ui = path.join(fixture, "desktop", "src", "ui");
    mkdirSync(ui, { recursive: true });
    writeFileSync(
      path.join(ui, "index.js"),
      [
        "export function createDesktopPlugin() {",
        "  return { id: \"templeos\", name: \"TempleOS\", register: function () { return true; } };",
        "}",
        "export function registerTempleOSPane() { return true; }",
        "",
      ].join("\n")
    );
    writeFileSync(path.join(ui, "styles.css"), ".tos-pane { display: flex; }\n");
    const built = spawnSync(process.execPath, [BUILD, "--root", fixture], { encoding: "utf8" });
    assert.equal(built.status, 0, built.stderr || built.stdout);
    const ok = spawnSync(process.execPath, [BUILD, "--root", fixture, "--check"], { encoding: "utf8" });
    assert.equal(ok.status, 0, ok.stderr || ok.stdout);
    const pluginPath = path.join(fixture, "desktop", "plugin.js");
    writeFileSync(pluginPath, readFileSync(pluginPath, "utf8") + "\n// stale\n");
    const stale = spawnSync(process.execPath, [BUILD, "--root", fixture, "--check"], { encoding: "utf8" });
    assert.notEqual(stale.status, 0);
    assert.match(stale.stderr, /stale/);
  } finally {
    rmSync(fixture, { recursive: true, force: true });
  }
});

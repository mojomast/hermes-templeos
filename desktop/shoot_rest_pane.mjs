/**
 * Screenshot the live pane through a mocked ctx.rest.
 *
 * The static shoot_pane path injects a v4 draw script and never calls
 * GET /companion/clip, so it cannot see a bundle load that never finishes.
 * This mode bundles the real pane. transport.rest answers /companion/clip,
 * /frame, /status, and /log the way the host's ctx.rest does.
 *
 * Usage:
 *   TEMPLEOS_SHOT_REST=1 node --import ./tests/js/register-mocks.mjs desktop/shoot_pane.mjs
 */
import { spawnSync } from "node:child_process";
import { mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";

const DEPS = process.env.TEMPLEOS_SHOT_DEPS || "/tmp/tos-shot-deps";

function ensureDeps() {
  const react = path.join(DEPS, "node_modules", "react", "package.json");
  const esbuild = path.join(DEPS, "node_modules", "esbuild", "package.json");
  if (exists(react) && exists(esbuild)) return;
  mkdirSync(DEPS, { recursive: true });
  const install = spawnSync(
    "npm",
    ["install", "--silent", "--no-fund", "--no-audit", "react@18.3.1", "react-dom@18.3.1", "esbuild@0.24.2"],
    { cwd: DEPS, encoding: "utf8", timeout: 120000 }
  );
  if (install.status !== 0) {
    throw new Error(install.stderr || install.stdout || "npm install failed");
  }
}

function exists(file) {
  try {
    readFileSync(file);
    return true;
  } catch (err) {
    return false;
  }
}

function loadFixture(root) {
  const v4 = path.join(root, "desktop", "assets", "companion", "terry", "v4");
  const registry = JSON.parse(readFileSync(path.join(v4, "parts.json"), "utf8"));
  const speech = JSON.parse(readFileSync(path.join(v4, "speech.json"), "utf8"));
  const smoke = JSON.parse(readFileSync(path.join(v4, "smoke", "smoke.json"), "utf8"));
  const baked = JSON.parse(readFileSync(path.join(v4, "baked-presets.json"), "utf8"));
  const clips = {};
  for (const name of ["idle", "greet", "talking"]) {
    if (baked[name]) clips[name] = baked[name];
  }
  const parts = {};
  const collect = (folder) => {
    for (const entry of readdirSync(folder, { withFileTypes: true })) {
      const file = path.join(folder, entry.name);
      if (entry.isDirectory()) collect(file);
      else if (entry.name.endsWith(".png")) {
        const rel = path.relative(v4, file).split(path.sep).join("/");
        parts[rel] = readFileSync(file).toString("base64");
      }
    }
  };
  collect(path.join(v4, "parts"));
  collect(path.join(v4, "smoke", "assets"));
  const frame = readFileSync(path.join(root, "tests", "fixtures", "frames", "tinkeros-mouse-click.png")).toString("base64");
  return {
    registry: registry,
    speech: speech,
    smoke: smoke,
    clips: clips,
    parts: parts,
    frame: frame,
  };
}

async function bundlePane(root, fixture) {
  ensureDeps();
  const fixtureFile = path.join(DEPS, "fixture.js");
  writeFileSync(fixtureFile, "export default " + JSON.stringify(fixture) + ";\n");
  const entry = path.join(DEPS, "entry.js");
  const pane = path.join(root, "desktop", "src", "ui", "pane.js");
  writeFileSync(
    entry,
    [
      'import { createElement } from "react";',
      'import { createRoot } from "react-dom/client";',
      `import { TempleOSPane } from ${JSON.stringify(pane)};`,
      `import fixture from ${JSON.stringify(fixtureFile)};`,
      "",
      "const status = {",
      "  running: true,",
      '  mode: "shared",',
      "  agent_paused: false,",
      "  agent_busy: false,",
      "  setup_needed: false,",
      "  ready: true,",
      '  flavor: "tinkeros",',
      '  flavor_name: "TinkerOS 5.20-rc10",',
      '  accel: "tcg",',
      "  kvm: false,",
      '  snapshot: "golden",',
      "  checks: { qemu: true, iso: true, kvm: false },",
      "  width: 640,",
      "  height: 480,",
      "  user_may_input: true,",
      "  companion: {",
      "    enabled: true,",
      "    hidden: false,",
      '    character: "terry",',
      '    animation: "idle",',
      '    costume: "base",',
      '    speech: { active: true, text: "Hello from Hermes" },',
      "  },",
      "};",
      "",
      "const log = [",
      "  { id: 1, source: 'agent', tool: 'templeos_vm', op: 'start', ok: true, at: '2026-11-10T15:34:21.000Z', summary: 'templeos_vm start' },",
      "];",
      "",
      "function rest(path) {",
      "  const url = String(path);",
      "  window.__tosCalls = window.__tosCalls || [];",
      "  window.__tosCalls.push(url);",
      "  if (url.indexOf('/companion/clip') === 0) {",
      "    const query = url.split('?')[1] || '';",
      "    const params = new URLSearchParams(query);",
      "    const name = params.get('name') || '';",
      "    if (name === 'v4:bundle' || name === 'v4' || name === 'v4-bundle') {",
      "      return Promise.resolve({",
      "        ok: true,",
      "        registry: fixture.registry,",
      "        speech: fixture.speech,",
      "        smoke: fixture.smoke,",
      "        costumes: { base: {}, cowboy: { cap: 'cowboy' }, wizard: { cap: 'wizard' }, chef: { cap: 'chef' } },",
      "        parts: fixture.parts,",
      "      });",
      "    }",
      "    const token = name.indexOf('v4:') === 0 ? name.slice(3) : name;",
      "    return Promise.resolve({ ok: true, name: token, clip: fixture.clips[token] || fixture.clips.idle });",
      "  }",
      "  if (url.indexOf('/frame') === 0) {",
      "    return Promise.resolve({ ok: true, mime: 'image/png', data: fixture.frame, sha256: 'rest-frame', width: 640, height: 480 });",
      "  }",
      "  if (url.indexOf('/log') === 0) return Promise.resolve({ ok: true, events: log });",
      "  return Promise.resolve(Object.assign({ ok: true }, status));",
      "}",
      "",
      "createRoot(document.getElementById('root')).render(",
      "  createElement(TempleOSPane, {",
      "    transport: { rest: rest },",
      "    initial: { theme: 'hermes', status: status, log: log },",
      "  })",
      ");",
      "",
    ].join("\n")
  );
  const outfile = path.join(DEPS, "pane.js");
  const esbuildPath = path.join(DEPS, "node_modules", "esbuild", "lib", "main.js");
  const esbuild = (await import(pathToFileURL(esbuildPath).href)).default;
  await esbuild.build({
    entryPoints: [entry],
    bundle: true,
    format: "iife",
    platform: "browser",
    target: "es2020",
    outfile: outfile,
    absWorkingDir: DEPS,
    nodePaths: [path.join(DEPS, "node_modules")],
    logLevel: "warning",
  });
  return outfile;
}

function writePage(css, scriptFile) {
  const htmlPath = path.join(path.dirname(scriptFile), "index.html");
  const html = `<!doctype html>
<html>
<head>
<meta charset="utf-8">
<style>
  html, body, #root { height: 100%; margin: 0; background: #000010; }
  #root { display: flex; min-height: 0; }
  .tos-pane { flex: 1 1 auto; min-height: 0; }
  ${css}
</style>
</head>
<body><div id="root"></div><script src="./pane.js"></script></body>
</html>`;
  writeFileSync(htmlPath, html);
  return htmlPath;
}

function shoot(chrome, htmlPath, size, dest) {
  const result = spawnSync(
    chrome,
    [
      "--headless=new",
      "--no-sandbox",
      "--disable-gpu",
      "--disable-dev-shm-usage",
      "--hide-scrollbars",
      "--allow-file-access-from-files",
      "--user-data-dir=/tmp/tos-chrome-profile",
      "--force-device-scale-factor=1",
      "--virtual-time-budget=8000",
      "--timeout=12000",
      `--window-size=${size}`,
      `--screenshot=${dest}`,
      `file://${htmlPath}`,
    ],
    { encoding: "utf8", timeout: 30000 }
  );
  if (result.status !== 0) {
    throw new Error(result.stderr || result.stdout || "chrome screenshot failed");
  }
}

export async function shootRestPane({ root, css, chrome }) {
  const fixture = loadFixture(root);
  const scriptFile = await bundlePane(root, fixture);
  const htmlPath = writePage(css, scriptFile);
  const out = process.env.TEMPLEOS_SHOT_DIR
    ? path.resolve(process.env.TEMPLEOS_SHOT_DIR)
    : "/opt/cursor/artifacts";
  mkdirSync(out, { recursive: true });
  const large = path.join(out, "terry-fit-large.png");
  const small = path.join(out, "terry-fit-small.png");
  shoot(chrome, htmlPath, "1680,1100", large);
  shoot(chrome, htmlPath, "980,720", small);
  console.log("wrote", large);
  console.log("wrote", small);
}

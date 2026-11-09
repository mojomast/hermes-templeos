/**
 * Render the TempleOS pane with the mock host and screenshot it.
 * Usage: node --import ./tests/js/register-mocks.mjs desktop/shoot_pane.mjs
 */
import { spawnSync } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { TempleOSPane } from "./src/ui/pane.js";
import { resetFiber, rerender } from "../tests/js/shims/jsx-runtime.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const OUT = process.env.TEMPLEOS_SHOT_DIR
  ? path.resolve(process.env.TEMPLEOS_SHOT_DIR)
  : path.join(ROOT, "desktop", "screenshots");
const CSS = readFileSync(path.join(ROOT, "desktop", "src", "ui", "styles.css"), "utf8");
const FRAMES = process.env.TEMPLEOS_SHOTS || path.join(ROOT, "tests", "fixtures", "frames");

function findChrome() {
  if (process.env.CHROME) return process.env.CHROME;
  for (const name of ["google-chrome", "chromium", "chromium-browser"]) {
    const probe = spawnSync("which", [name], { encoding: "utf8" });
    if (probe.status === 0) return name;
  }
  return "google-chrome";
}

function frameDataUrl(name) {
  const file = path.join(FRAMES, name);
  const bytes = readFileSync(file);
  return "data:image/png;base64," + bytes.toString("base64");
}

function escapeText(value) {
  return String(value).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function escapeAttr(value) {
  return escapeText(value).replace(/"/g, "&quot;");
}

function styleOf(value) {
  if (!value || typeof value !== "object") return "";
  return Object.entries(value)
    .map(([key, item]) => {
      const name = key.replace(/[A-Z]/g, (letter) => "-" + letter.toLowerCase());
      const out = typeof item === "number" ? item + "px" : item;
      return name + ":" + out;
    })
    .join(";");
}

const VOID = new Set(["img", "input", "br", "hr", "meta", "link"]);

function toHtml(node, parentValue) {
  if (node == null || node === false || node === true) return "";
  if (Array.isArray(node)) return node.map((child) => toHtml(child, parentValue)).join("");
  if (typeof node === "string" || typeof node === "number") return escapeText(node);
  if (typeof node.type === "function") return toHtml(node.type(node.props || {}), parentValue);
  const props = node.props || {};
  const attrs = [];
  for (const [key, value] of Object.entries(props)) {
    if (key === "children" || key === "key" || key === "ref" || value == null || typeof value === "function") continue;
    if (key === "value" && node.type === "select") continue;
    if (key === "className") attrs.push(`class="${escapeAttr(value)}"`);
    else if (key === "style" && typeof value === "object") attrs.push(`style="${escapeAttr(styleOf(value))}"`);
    else if (typeof value === "boolean") {
      if (value) attrs.push(key);
    } else attrs.push(`${key}="${escapeAttr(value)}"`);
  }
  if (node.type === "option" && parentValue != null && String(props.value) === String(parentValue)) {
    attrs.push("selected");
  }
  const open = `<${node.type}${attrs.length ? " " + attrs.join(" ") : ""}>`;
  if (VOID.has(node.type)) return open.replace(/>$/, " />");
  const nextParent = node.type === "select" ? props.value : undefined;
  return open + toHtml(props.children, nextParent) + `</${node.type}>`;
}

function page(body) {
  return `<!doctype html>
<html>
<head>
<meta charset="utf-8">
<style>
  :root {
    --ui-text-primary: #ffff55;
    --ui-text-secondary: #aaaaaa;
    --ui-text-tertiary: #555555;
    --ui-stroke-secondary: rgba(255, 255, 85, 0.25);
    --ui-accent: #55ffff;
  }
  html, body { margin: 0; height: 100%; background: #000010; color: var(--ui-text-primary); }
  #root { min-height: 100vh; }
  ${CSS}
</style>
</head>
<body><div id="root">${body}</div></body>
</html>`;
}

function render(initial) {
  resetFiber();
  return page(
    toHtml(
      rerender(TempleOSPane, {
        transport: { rest: () => Promise.resolve({ ok: true }) },
        initial: { skipLoad: true, ...initial },
      })
    )
  );
}

const tinkeros = frameDataUrl("tinkeros-mouse-click.png");
const prompt = frameDataUrl("tinkeros-holyc-prompt.png");

const ready = {
  running: true,
  mode: "shared",
  agent_paused: false,
  agent_busy: false,
  setup_needed: false,
  ready: true,
  flavor: "tinkeros",
  flavor_name: "TinkerOS 5.20-rc10",
  accel: "tcg",
  kvm: false,
  snapshot: "golden",
  snapshots: ["golden"],
  checks: { qemu: true, iso: true, kvm: false },
  width: 640,
  height: 480,
  user_may_input: true,
};

const log = [
  {
    id: 1,
    source: "agent",
    tool: "templeos_vm",
    op: "start",
    ok: true,
    at: "2026-11-09T18:58:12.000Z",
    summary: "templeos_vm start",
  },
  {
    id: 2,
    source: "agent",
    tool: "templeos_screen",
    op: "look",
    ok: true,
    at: "2026-11-09T18:58:14.000Z",
    summary: "templeos_screen look",
  },
  {
    id: 3,
    source: "agent",
    tool: "templeos_input",
    op: "click",
    ok: true,
    at: "2026-11-09T18:58:16.000Z",
    summary: "templeos_input click",
  },
  {
    id: 4,
    source: "agent",
    tool: "templeos_input",
    op: "type",
    ok: true,
    at: "2026-11-09T18:58:18.000Z",
    summary: "templeos_input type",
  },
];

const shots = {
  "pane-onboarding.png": {
    size: "1280,1100",
    html: render({
      status: {
        running: false,
        mode: "shared",
        agent_paused: false,
        setup_needed: true,
        ready: false,
        flavor: "tinkeros",
        flavor_name: "TinkerOS 5.20-rc10",
        accel: null,
        kvm: false,
        snapshot: null,
        checks: { qemu: false, iso: false, kvm: "unknown" },
      },
    }),
  },
  "pane-running.png": {
    size: "1680,1180",
    html: render({
      scale: 2,
      viewport: { width: 1680, height: 1180 },
      frameUrl: tinkeros,
      status: ready,
    }),
  },
  "pane-user-driving.png": {
    size: "1680,1180",
    html: render({
      scale: 2,
      focused: true,
      viewport: { width: 1680, height: 1180 },
      frameUrl: prompt,
      status: {
        ...ready,
        mode: "user",
        agent_paused: true,
        user_may_input: true,
      },
    }),
  },
  "pane-agent-log.png": {
    size: "1680,1180",
    html: render({
      scale: 2,
      viewport: { width: 1680, height: 1180 },
      frameUrl: tinkeros,
      status: {
        ...ready,
        agent_busy: true,
        accel: "kvm",
        kvm: true,
      },
      log,
    }),
  },
  "pane-theme-hermes-running.png": {
    size: "1680,1180",
    html: render({
      theme: "hermes",
      scale: 2,
      viewport: { width: 1680, height: 1180 },
      frameUrl: tinkeros,
      status: ready,
    }),
  },
  "pane-theme-hermes-onboarding.png": {
    size: "1280,1100",
    html: render({
      theme: "hermes",
      status: {
        running: false,
        mode: "shared",
        agent_paused: false,
        setup_needed: true,
        ready: false,
        flavor: "tinkeros",
        flavor_name: "TinkerOS 5.20-rc10",
        accel: null,
        kvm: false,
        snapshot: null,
        checks: { qemu: false, iso: false, kvm: "unknown" },
      },
    }),
  },
  "pane-theme-hermes-user-driving.png": {
    size: "1680,1180",
    html: render({
      theme: "hermes",
      scale: 2,
      focused: true,
      viewport: { width: 1680, height: 1180 },
      frameUrl: prompt,
      status: {
        ...ready,
        mode: "user",
        agent_paused: true,
        user_may_input: true,
      },
    }),
  },
  "pane-theme-hermes-agent-log.png": {
    size: "1680,1180",
    html: render({
      theme: "hermes",
      scale: 2,
      viewport: { width: 1680, height: 1180 },
      frameUrl: tinkeros,
      status: {
        ...ready,
        agent_busy: true,
        accel: "kvm",
        kvm: true,
      },
      log,
    }),
  },
  "pane-theme-vga-running.png": {
    size: "1680,1180",
    html: render({
      theme: "vga",
      scale: 2,
      viewport: { width: 1680, height: 1180 },
      frameUrl: tinkeros,
      status: ready,
    }),
  },
};

mkdirSync(OUT, { recursive: true });
const chrome = findChrome();
for (const [name, shot] of Object.entries(shots)) {
  const file = path.join("/tmp", name.replace(".png", ".html"));
  writeFileSync(file, shot.html);
  const dest = path.join(OUT, name);
  const result = spawnSync(
    chrome,
    [
      "--headless=new",
      "--no-sandbox",
      "--disable-gpu",
      "--disable-dev-shm-usage",
      "--hide-scrollbars",
      "--force-device-scale-factor=1",
      "--virtual-time-budget=2500",
      "--timeout=4000",
      `--window-size=${shot.size}`,
      `--screenshot=${dest}`,
      `file://${file}`,
    ],
    { encoding: "utf8", timeout: 20000 }
  );
  if (result.status !== 0) {
    console.error(result.stderr || result.stdout);
    process.exit(1);
  }
  console.log("wrote", path.relative(ROOT, dest));
}

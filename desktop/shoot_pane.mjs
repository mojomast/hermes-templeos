/**
 * Render the TempleOS pane with the mock host and screenshot it.
 * Usage: node --import ./tests/js/register-mocks.mjs desktop/shoot_pane.mjs
 */
import { spawnSync } from "node:child_process";
import { mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import { TempleOSPane } from "./src/ui/pane.js";
import { resetFiber, rerender } from "../tests/js/shims/jsx-runtime.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const OUT = process.env.TEMPLEOS_SHOT_DIR
  ? path.resolve(process.env.TEMPLEOS_SHOT_DIR)
  : path.join(ROOT, "desktop", "screenshots");
const CSS = readFileSync(path.join(ROOT, "desktop", "src", "ui", "styles.css"), "utf8");
const FRAMES = process.env.TEMPLEOS_SHOTS || path.join(ROOT, "tests", "fixtures", "frames");
const ONLY = (process.env.TEMPLEOS_SHOT_ONLY || "")
  .split(",")
  .map((name) => name.trim())
  .filter(Boolean);

const V4_ROOT = path.join(ROOT, "desktop", "assets", "companion", "terry", "v4");
const V5_EXPORTS = path.join(ROOT, "desktop", "assets", "companion", "terry", "v5", "exports");
const V4_SOURCE = readFileSync(path.join(ROOT, "desktop", "src", "ui", "terry_v4.js"), "utf8")
  .replace(/^export\s+/gm, "");

function loadV4() {
  const registry = JSON.parse(readFileSync(path.join(V4_ROOT, "parts.json"), "utf8"));
  const speech = JSON.parse(readFileSync(path.join(V4_ROOT, "speech.json"), "utf8"));
  const smoke = JSON.parse(readFileSync(path.join(V4_ROOT, "smoke", "smoke.json"), "utf8"));
  const baked = JSON.parse(readFileSync(path.join(V4_ROOT, "baked-presets.json"), "utf8"));
  const parts = {};
  const collect = (folder) => {
    for (const entry of readdirSync(folder, { withFileTypes: true })) {
      const file = path.join(folder, entry.name);
      if (entry.isDirectory()) collect(file);
      else if (entry.name.endsWith(".png")) {
        const rel = path.relative(V4_ROOT, file).split(path.sep).join("/");
        parts[rel] = "data:image/png;base64," + readFileSync(file).toString("base64");
      }
    }
  };
  collect(path.join(V4_ROOT, "parts"));
  collect(path.join(V4_ROOT, "smoke", "assets"));
  return { registry, speech, smoke, baked, parts };
}

const V4 = loadV4();
const QUOTES = JSON.parse(readFileSync(path.join(ROOT, "desktop", "terry-quotes.json"), "utf8"));
const LONG_QUOTE =
  Array.isArray(QUOTES) && QUOTES.length
    ? QUOTES.reduce((best, entry) => (String(entry.text || "").length > String(best.text || "").length ? entry : best), QUOTES[0])
    : null;
const SPEECH_TEXT = LONG_QUOTE ? String(LONG_QUOTE.text) : "TEST_FIXTURE_ONLY";

function v4Script(options) {
  const clips = {};
  for (const name of options.clips || [options.animation || "idle"]) {
    if (V4.baked[name]) clips[name] = V4.baked[name];
  }
  const data = {
    registry: V4.registry,
    speech: V4.speech,
    smoke: V4.smoke,
    parts: V4.parts,
    clips,
    animation: options.animation || "idle",
    costume: options.costume || "base",
    time: Number(options.time) || 0,
  };
  return `<script>window.__TERRY_V4__ = ${JSON.stringify(data)};</script>
<script type="module">
${V4_SOURCE}
const DATA = window.__TERRY_V4__;
const canvas = document.querySelector('canvas[data-companion-v4]');
const images = new Map();
await Promise.all(Object.entries(DATA.parts).map(([name, url]) => new Promise((resolve) => {
  const image = new Image();
  image.onload = () => { images.set(name, image); resolve(); };
  image.onerror = () => resolve();
  image.src = url;
})));
const clip = DATA.clips[DATA.animation] || DATA.clips.idle;
const frame = sampleClip(clip, DATA.time);
if (DATA.animation === 'talking' && frame) {
  frame.variants.head_base = speechPlate(DATA.speech.events, DATA.time, frame.variants.head_base);
}
if (frame) {
  renderScene(canvas, DATA, images, frame, DATA.costume);
  canvas.dataset.terryPainted = '1';
  const dock = canvas.closest('[data-testid="companion-dock"]');
  if (dock) dock.dataset.ready = '1';
  const loading = document.querySelector('[data-testid="companion-loading"]');
  if (loading) loading.remove();
  document.documentElement.dataset.terryV4 = 'drawn';
}
</script>`;
}

function v5Script(clip) {
  const urls = {};
  for (const name of ["idle", "smoking", "speaking", "typing", "walk", "wave"]) {
    urls[name] = pathToFileURL(path.join(V5_EXPORTS, name + ".webm")).href;
  }
  const name = clip || "idle";
  return `<script>window.__TERRY_V5__ = ${JSON.stringify(urls)};</script>
<script>
(function () {
  var urls = window.__TERRY_V5__;
  var clip = ${JSON.stringify(name)};
  function start() {
    var videos = document.querySelectorAll('video[data-companion-video]');
    if (!videos.length) { setTimeout(start, 50); return; }
    var video = videos[0];
    var done = function () {
      var loading = document.querySelector('[data-testid="companion-loading"]');
      if (loading) loading.remove();
      var dock = document.querySelector('[data-testid="companion-dock"]');
      if (dock) dock.dataset.ready = '1';
      document.documentElement.dataset.terryV5 = 'drawn';
    };
    video.classList.add('is-front');
    video.src = urls[clip] || urls.idle;
    video.addEventListener('canplay', function () {
      try { video.currentTime = 0.6; } catch (err) {}
      done();
    }, { once: true });
    video.addEventListener('loadeddata', done, { once: true });
    var played = video.play();
    if (played && played.catch) played.catch(function () {});
    setTimeout(done, 2500);
  }
  if (document.readyState === 'complete') start();
  else window.addEventListener('load', start);
})();
</script>`;
}

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

function page(body, script = "") {
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
  html, body { margin: 0; height: 100%; overflow: hidden; background: #000010; color: var(--ui-text-primary); }
  #root { height: 100vh; overflow: hidden; }
  ${CSS}
</style>
</head>
<body><div id="root">${body}</div>${script}
<script>
window.addEventListener("load", function () {
  var started = Date.now();
  function readyToMeasure() {
    if (document.documentElement.dataset.terryV4 === "drawn") return true;
    var loading = document.querySelector('[data-testid="companion-loading"]');
    if (loading && loading.getClientRects().length && getComputedStyle(loading).display !== "none") return false;
    return Date.now() - started >= 1200;
  }
  function measure() {
    if (!readyToMeasure() && Date.now() - started < 5000) {
      setTimeout(measure, 50);
      return;
    }
    var map = {
      screen: '[data-testid="screen"]',
      log: '[data-testid="agent-log"]',
      terry: '[data-testid="companion-dock"]',
      bubble: '[data-testid="companion-bubble"]'
    };
    var out = {};
    Object.keys(map).forEach(function (key) {
      var el = document.querySelector(map[key]);
      if (!el) return;
      var r = el.getBoundingClientRect();
      out[key] = { x: r.x, y: r.y, width: r.width, height: r.height };
    });
    var loading = document.querySelector('[data-testid="companion-loading"]');
    out.loading = {
      present: !!loading,
      visible: !!(loading && loading.getClientRects().length && getComputedStyle(loading).display !== "none")
    };
    var bubble = document.querySelector('[data-testid="companion-bubble"]');
    if (bubble) {
      out.bubbleText = {
        scrollHeight: bubble.scrollHeight,
        clientHeight: bubble.clientHeight,
        overflowY: getComputedStyle(bubble).overflowY
      };
    }
    var pre = document.createElement("pre");
    pre.id = "__layout_rects";
    pre.textContent = JSON.stringify(out);
    pre.style.position = "fixed";
    pre.style.left = "-9999px";
    pre.style.top = "0";
    document.body.appendChild(pre);
  }
  setTimeout(measure, 1200);
});
</script>
</body>
</html>`;
}

function render(initial, options) {
  resetFiber();
  const body = toHtml(
    rerender(TempleOSPane, {
      transport: { rest: () => Promise.resolve({ ok: true }) },
      initial: { skipLoad: true, ...initial },
    })
  );
  if (options && options.v5) return page(body, v5Script(options.clip));
  return page(body, options ? v4Script(options) : "");
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

const worldReady = {
  ...ready,
  companion: {
    enabled: true,
    hidden: false,
    character: "terry",
    animation: "talking",
    costume: "base",
    speech: { active: true, text: SPEECH_TEXT },
  },
};

const shots = {
  "pane-1920x1240.png": {
    size: "1920,1240",
    html: render(
      {
        theme: "hermes",
        scale: 1.5,
        viewport: { width: 1920, height: 1240 },
        frameUrl: tinkeros,
        log,
        status: worldReady,
      },
      { v5: true, clip: "speaking" }
    ),
  },
  "pane-1280x800.png": {
    size: "1280,800",
    html: render(
      {
        theme: "hermes",
        scale: 0.72,
        viewport: { width: 1280, height: 800 },
        frameUrl: prompt,
        log,
        status: worldReady,
      },
      { v5: true, clip: "speaking" }
    ),
  },
  "pane-narrow.png": {
    size: "780,900",
    html: render(
      {
        theme: "hermes",
        scale: 0.9,
        viewport: { width: 780, height: 900 },
        frameUrl: tinkeros,
        log,
        status: worldReady,
      },
      { v5: true, clip: "speaking" }
    ),
  },
  "pane-typing.png": {
    size: "1920,1240",
    html: render(
      {
        theme: "hermes",
        scale: 1.5,
        viewport: { width: 1920, height: 1240 },
        frameUrl: tinkeros,
        log,
        status: {
          ...worldReady,
          agent_busy: true,
          companion: {
            enabled: true,
            hidden: false,
            character: "terry",
            animation: "typing",
            costume: "base",
            speech: { active: false, text: "" },
          },
        },
      },
      { v5: true, clip: "typing" }
    ),
  },
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
  "pane-flavor-picker.png": {
    size: "1680,1180",
    html: render({
      theme: "hermes",
      viewport: { width: 1680, height: 1180 },
      status: {
        running: false,
        mode: "shared",
        agent_paused: false,
        setup_needed: true,
        ready: false,
        flavor: "templeoh",
        flavor_name: "Temple of Hermes 0.1.3",
        preferred_flavor: "templeoh",
        sha_state: "verified",
        flavor_sha256: "fbaa3d6f0a8f9190f295e933c32cb833a61b3cb43a708309acb6c98ff51ac4fd",
        flavors: [
          { id: "templeoh", name: "Temple of Hermes 0.1.3", sha_state: "verified", sha256: "fbaa3d6f0a8f9190f295e933c32cb833a61b3cb43a708309acb6c98ff51ac4fd", bytes: 14053376, default: true },
          { id: "tinkeros", name: "TinkerOS 5.20-rc10", sha_state: "missing", sha256: "feb5cb570a79fefbefeb7d7a7133e3eac0e3b4ffcd6adf8a0fd29049476a1cc4" },
          { id: "templeos", name: "TempleOS 5.03", sha_state: "missing" },
          { id: "zealos", name: "ZealOS", sha_state: "missing" },
        ],
        accel: null,
        kvm: false,
        snapshot: null,
        checks: { qemu: true, iso: true, kvm: false },
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
  "terry-hermes-dark.png": {
    size: "1920,1240",
    html: render(
      {
        theme: "hermes",
        scale: 2,
        viewport: { width: 1920, height: 1240 },
        frameUrl: tinkeros,
        status: {
          ...ready,
          companion: {
            enabled: true,
            hidden: false,
            character: "terry",
            animation: "greet",
            costume: "base",
            speech: { active: true, text: "Hello from Hermes" },
          },
        },
      },
      { animation: "greet", costume: "base", time: 800, clips: ["greet"] }
    ),
  },
  "terry-hermes-typing.png": {
    size: "1920,1240",
    html: render(
      {
        theme: "hermes",
        scale: 2,
        viewport: { width: 1920, height: 1240 },
        frameUrl: tinkeros,
        status: {
          ...ready,
          agent_busy: true,
          companion: {
            enabled: true,
            hidden: false,
            character: "terry",
            animation: "typing",
            costume: "base",
            speech: { active: false, text: "" },
          },
        },
        log,
      },
      { animation: "typing", costume: "base", time: 800, clips: ["typing"] }
    ),
  },
  "terry-big.png": {
    size: "1920,1240",
    html: render(
      {
        theme: "hermes",
        scale: 2,
        viewport: { width: 1920, height: 1240 },
        frameUrl: tinkeros,
        log,
        status: {
          ...ready,
          agent_busy: true,
          companion: {
            enabled: true,
            hidden: false,
            character: "terry",
            animation: "typing",
            costume: "base",
            speech: { active: true, text: "Hello from Hermes" },
          },
        },
      },
      { animation: "talking", costume: "base", time: 900, clips: ["talking"] }
    ),
  },
  "terry-hermes-hidden.png": {
    size: "1920,1240",
    html: render({
      theme: "hermes",
      scale: 2,
      viewport: { width: 1920, height: 1240 },
      frameUrl: tinkeros,
      companionHidden: true,
      status: {
        ...ready,
        companion: {
          enabled: true,
          hidden: true,
          character: "terry",
          animation: "idle",
          costume: "base",
          speech: { active: false, text: "" },
        },
      },
    }),
  },
  "v4-idle.png": {
    size: "1920,1240",
    html: render(
      {
        theme: "hermes",
        scale: 2,
        viewport: { width: 1920, height: 1240 },
        frameUrl: tinkeros,
        status: {
          ...ready,
          companion: {
            enabled: true,
            hidden: false,
            character: "terry",
            animation: "idle",
            costume: "base",
            speech: { active: false, text: "" },
          },
        },
      },
      { animation: "idle", costume: "base", time: 420, clips: ["idle", "greet"] }
    ),
  },
  "v4-typing.png": {
    size: "1920,1240",
    html: render(
      {
        theme: "hermes",
        scale: 2,
        viewport: { width: 1920, height: 1240 },
        frameUrl: tinkeros,
        log,
        status: {
          ...ready,
          agent_busy: true,
          companion: {
            enabled: true,
            hidden: false,
            character: "terry",
            animation: "typing",
            costume: "base",
            speech: { active: false, text: "" },
          },
        },
      },
      { animation: "typing", costume: "base", time: 800, clips: ["idle", "typing"] }
    ),
  },
  "v4-talking.png": {
    size: "1920,1240",
    html: render(
      {
        theme: "hermes",
        scale: 2,
        viewport: { width: 1920, height: 1240 },
        frameUrl: tinkeros,
        log,
        status: {
          ...ready,
          agent_busy: true,
          companion: {
            enabled: true,
            hidden: false,
            character: "terry",
            animation: "talking",
            costume: "base",
            speech: { active: true, text: "Hello from Hermes" },
          },
        },
      },
      { animation: "talking", costume: "base", time: 900, clips: ["idle", "talking"] }
    ),
  },
  "pint2-idle.png": {
    size: "1920,1240",
    html: render(
      {
        theme: "hermes",
        scale: 2,
        viewport: { width: 1920, height: 1240 },
        frameUrl: tinkeros,
        status: {
          ...ready,
          companion: {
            enabled: true,
            hidden: false,
            character: "terry",
            animation: "idle",
            costume: "base",
            speech: { active: false, text: "" },
          },
        },
      },
      { animation: "idle", costume: "base", time: 420, clips: ["idle", "greet"] }
    ),
  },
  "pint2-typing.png": {
    size: "1920,1240",
    html: render(
      {
        theme: "hermes",
        scale: 2,
        viewport: { width: 1920, height: 1240 },
        frameUrl: tinkeros,
        log,
        status: {
          ...ready,
          agent_busy: true,
          companion: {
            enabled: true,
            hidden: false,
            character: "terry",
            animation: "typing",
            costume: "base",
            speech: { active: false, text: "" },
          },
        },
      },
      { animation: "typing", costume: "base", time: 800, clips: ["idle", "typing"] }
    ),
  },
  "v4-costume.png": {
    size: "1920,1240",
    html: render(
      {
        theme: "hermes",
        scale: 2,
        viewport: { width: 1920, height: 1240 },
        frameUrl: tinkeros,
        status: {
          ...ready,
          companion: {
            enabled: true,
            hidden: false,
            character: "terry",
            animation: "idle",
            costume: "cowboy",
            speech: { active: false, text: "" },
          },
        },
      },
      { animation: "idle", costume: "cowboy", time: 420, clips: ["idle"] }
    ),
  },
};

if (process.env.TEMPLEOS_SHOT_REST === "1") {
  const { shootRestPane } = await import("./shoot_rest_pane.mjs");
  await shootRestPane({ root: ROOT, css: CSS, chrome: findChrome() });
  process.exit(0);
}

mkdirSync(OUT, { recursive: true });
const chrome = findChrome();
for (const [name, shot] of Object.entries(shots)) {
  if (ONLY.length && !ONLY.includes(name)) continue;
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
      "--virtual-time-budget=5000",
      "--timeout=9000",
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

const MEASURE_NAMES = new Set(["pane-1920x1240.png", "pane-1280x800.png", "pane-narrow.png", "pane-typing.png"]);
const rects = {};
for (const [name, shot] of Object.entries(shots)) {
  if (!MEASURE_NAMES.has(name)) continue;
  if (ONLY.length && !ONLY.includes(name)) continue;
  const file = path.join("/tmp", name.replace(".png", ".html"));
  // Chrome's --dump-dom viewport is 88px shorter than the --screenshot
  // viewport for the same --window-size in this headless build. Add that
  // chrome allowance here so the measured boxes match the saved PNG.
  const [width, height] = shot.size.split(",").map(Number);
  const measureSize = `${width},${height + 88}`;
  const result = spawnSync(
    chrome,
    [
      "--headless=new",
      "--no-sandbox",
      "--disable-gpu",
      "--disable-dev-shm-usage",
      "--hide-scrollbars",
      "--force-device-scale-factor=1",
      "--virtual-time-budget=5200",
      "--timeout=9000",
      `--window-size=${measureSize}`,
      "--dump-dom",
      `file://${file}`,
    ],
    { encoding: "utf8", timeout: 20000, maxBuffer: 32 * 1024 * 1024 }
  );
  const match = result.stdout && result.stdout.match(/<pre id="__layout_rects"[^>]*>([\s\S]*?)<\/pre>/);
  if (result.status !== 0 || !match) {
    console.error("could not measure", name, result.stderr || "");
    continue;
  }
  try {
    rects[name] = JSON.parse(match[1]);
    console.log("measured", name, JSON.stringify(rects[name]));
  } catch (err) {
    console.error("bad rect JSON for", name, err.message);
  }
}
if (Object.keys(rects).length) {
  writeFileSync(path.join(OUT, "PANE-RECTS.json"), JSON.stringify(rects, null, 2) + "\n");
  console.log("wrote", path.relative(ROOT, path.join(OUT, "PANE-RECTS.json")));
}

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

import { TempleOSPane } from "../../desktop/src/ui/pane.js";
import { TerryCompanionOverlay } from "../../desktop/src/ui/companion.js";
import { resetFiber, rerender } from "./shims/jsx-runtime.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const CSS = readFileSync(path.join(ROOT, "desktop", "src", "ui", "styles.css"), "utf8");
const PLUGIN = readFileSync(path.join(ROOT, "desktop", "plugin.js"), "utf8");

function walk(node, visit) {
  if (node == null || node === false || node === true) return;
  if (Array.isArray(node)) {
    node.forEach((child) => walk(child, visit));
    return;
  }
  if (typeof node === "string" || typeof node === "number") return;
  visit(node);
  if (node.props) walk(node.props.children, visit);
}

function findAll(node, pred) {
  const out = [];
  walk(node, (item) => {
    if (item && item.props && pred(item)) out.push(item);
  });
  return out;
}

function byTestId(node, id) {
  return findAll(node, (item) => item.props["data-testid"] === id);
}

function texts(node) {
  const out = [];
  walk(node, (item) => {
    if (item && item.props && typeof item.props.children === "string") out.push(item.props.children);
  });
  return out.join(" ");
}

function readyStatus(companion) {
  return {
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
    checks: { qemu: true, iso: true, kvm: false },
    width: 640,
    height: 480,
    user_may_input: true,
    companion: companion || {
      enabled: true,
      hidden: false,
      character: "terry",
      animation: "greet",
      costume: "base",
      speech: { active: true, text: "Hello from Hermes" },
    },
  };
}

test("Terry dock is the second child of .tos-stage-row, to the right of the display", () => {
  resetFiber();
  const node = rerender(TempleOSPane, {
    transport: { rest: () => Promise.resolve({ ok: true }) },
    initial: {
      skipLoad: true,
      theme: "hermes",
      frameUrl: "data:image/png;base64,AA==",
      status: readyStatus(),
    },
  });
  const row = byTestId(node, "stage-row");
  assert.equal(row.length, 1);
  const children = row[0].props.children.filter(Boolean);
  assert.equal(children.length, 2);
  assert.match(String(children[0].props.className), /tos-stage/);
  assert.equal(children[1].props["data-testid"], "companion-dock");

  const dock = byTestId(node, "companion-dock")[0];
  const bubble = byTestId(node, "companion-bubble")[0];
  assert.equal(texts(bubble), "Hello from Hermes");
  assert.ok(dock.props.children.indexOf(bubble) < dock.props.children.length - 1);

  const terry = byTestId(node, "companion")[0];
  assert.match(String(terry.props.className), /tos-companion/);
  assert.equal(terry.props["data-costume"], "base");
  const canvas = findAll(terry, (item) => item.type === "canvas");
  assert.equal(canvas.length, 1);
  assert.equal(canvas[0].props["data-companion-v4"], "1");
});

test("Hide Terry hides the dock and the toggle flips to Show Terry", () => {
  resetFiber();
  const node = rerender(TempleOSPane, {
    transport: { rest: () => Promise.resolve({ ok: true }) },
    initial: {
      skipLoad: true,
      companionHidden: true,
      status: readyStatus({
        enabled: true,
        hidden: true,
        character: "terry",
        animation: "idle",
        costume: "base",
      }),
    },
  });
  assert.equal(byTestId(node, "companion-dock").length, 0);
  assert.equal(texts(byTestId(node, "companion-hide")[0]), "Show Terry");
});

test("companion: off removes the dock but keeps the pane renderable", () => {
  resetFiber();
  const node = rerender(TempleOSPane, {
    transport: { rest: () => Promise.resolve({ ok: true }) },
    initial: {
      skipLoad: true,
      status: readyStatus({
        enabled: false,
        hidden: false,
        character: "terry",
        animation: "idle",
        costume: "base",
      }),
    },
  });
  assert.equal(byTestId(node, "companion-dock").length, 0);
  assert.equal(byTestId(node, "screen").length, 1);
});

test("P2 Hermes theme stays the default with a dark pane and reserved dock width", () => {
  resetFiber();
  const node = rerender(TempleOSPane, {
    transport: { rest: () => Promise.resolve({ ok: true }) },
    initial: { skipLoad: true, status: readyStatus() },
  });
  const pane = byTestId(node, "pane")[0];
  assert.equal(pane.props["data-theme"], "hermes");
  assert.equal(byTestId(node, "theme-toggle").length, 1);

  assert.match(CSS, /\.tos-pane\[data-theme="hermes"\]/);
  assert.match(CSS, /background:[^;]*var\(--tos-hermes-ink\)/s);
  assert.match(CSS, /\.tos-stage-row\s*\{[^}]*display:\s*contents/s);
  assert.match(CSS, /\.tos-companion-dock\s*\{[^}]*grid-column:\s*2/s);
  assert.match(CSS, /\.tos-companion-dock\s*\{[^}]*height:\s*var\(--tos-companion-h,\s*750px\)/s);
  assert.match(CSS, /\.tos-companion\s*\{[^}]*height:\s*var\(--tos-companion-h,\s*750px\)/s);
  assert.match(CSS, /\.tos-companion-bubble\s*\{[^}]*max-width:\s*min\(100%,\s*340px\)/s);
  assert.match(CSS, /\.tos-companion-bubble-slot\s*\{[^}]*position:\s*absolute/s);
  assert.match(CSS, /\.tos-companion-static\s*\{[^}]*background-size:\s*800% 900%/s);
  assert.match(CSS, /\.tos-companion-canvas\s*\{[^}]*image-rendering:\s*auto/s);
  assert.doesNotMatch(CSS, /\.tos-companion-canvas\s*\{[^}]*image-rendering:\s*pixelated/s);
});

test("built plugin carries the dock, bubble lane, and Hermes dark theme", () => {
  assert.equal(PLUGIN.includes("127.0.0.1"), false);
  assert.equal(PLUGIN.includes("sessionStorage"), false);
  assert.match(PLUGIN, /templeos\.screenSize/);
  assert.match(PLUGIN, /tos-stage-row/);
  assert.match(PLUGIN, /tos-companion-dock/);
  assert.match(PLUGIN, /tos-companion-bubble-slot/);
  assert.match(PLUGIN, /data-theme=\\"hermes\\"|data-theme/);
  assert.match(PLUGIN, /tos-hermes-ink/);
});

test("overlay renders the live v4 canvas path", () => {
  resetFiber();
  const node = rerender(TerryCompanionOverlay, {
    api: { companionClip: () => Promise.resolve({ ok: true }) },
    animation: "idle",
    costume: "base",
    hidden: false,
    enabled: true,
    speech: null,
  });
  assert.equal(node.props["data-testid"], "companion-dock");
  const canvas = findAll(node, (item) => item.type === "canvas");
  assert.equal(canvas.length, 1);
  assert.equal(canvas[0].props["data-companion-v4"], "1");
  assert.equal(node.props["data-ready"], "0");
  assert.equal(texts(byTestId(node, "companion-loading")[0]), "Summoning Terry…");
});

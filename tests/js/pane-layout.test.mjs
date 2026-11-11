import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

import {
  COMPACT_BREAKPOINT_PX,
  layoutRegions,
  paneLayoutMode,
  rectsOverlap,
} from "../../desktop/src/ui/logic.js";
import { TempleOSPane } from "../../desktop/src/ui/pane.js";
import { resetFiber, rerender } from "./shims/jsx-runtime.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const CSS = readFileSync(path.join(ROOT, "desktop", "src", "ui", "styles.css"), "utf8");

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

function byTestId(node, id) {
  const out = [];
  walk(node, (item) => {
    if (item.props && item.props["data-testid"] === id) out.push(item);
  });
  return out;
}

function frame(initial) {
  resetFiber();
  return rerender(TempleOSPane, {
    transport: { rest: () => Promise.resolve({ ok: true }) },
    initial: {
      skipLoad: true,
      viewport: { width: initial.width, height: initial.height },
      status: {
        running: true,
        mode: "shared",
        setup_needed: false,
        flavor: "tinkeros",
        flavor_name: "TinkerOS 5.20-rc10",
        accel: "tcg",
        snapshot: "golden",
        width: 640,
        height: 480,
        companion: { enabled: true, hidden: false, animation: "idle", costume: "base" },
      },
    },
  });
}

test("documented breakpoint switches between wide column and compact dock", () => {
  assert.equal(COMPACT_BREAKPOINT_PX, 900);
  assert.equal(paneLayoutMode(1920), "wide");
  assert.equal(paneLayoutMode(1280), "wide");
  assert.equal(paneLayoutMode(900), "compact");
  assert.equal(paneLayoutMode(760), "compact");
  assert.equal(paneLayoutMode(0), "wide");

  assert.equal(byTestId(frame({ width: 1920, height: 1240 }), "pane")[0].props["data-layout"], "wide");
  assert.equal(byTestId(frame({ width: 800, height: 1080 }), "pane")[0].props["data-layout"], "compact");
});

test("wide: Terry is a full-height column beside the screen+log column", () => {
  for (const size of [
    { width: 1920, height: 1240 },
    { width: 1280, height: 800 },
  ]) {
    const regions = layoutRegions({ ...size, logHeight: 210, gap: 10 });
    assert.equal(regions.mode, "wide");
    assert.equal(regions.screen.x, regions.log.x);
    assert.equal(regions.screen.width, regions.log.width);
    assert.equal(regions.log.y, regions.screen.y + regions.screen.height + regions.gap);
    assert.ok(regions.terry.x >= regions.screen.x + regions.screen.width);
    assert.equal(regions.terry.height, size.height);
    assert.ok(regions.screen.height > 0);
    assert.equal(rectsOverlap(regions.screen, regions.log), false);
    assert.equal(rectsOverlap(regions.screen, regions.terry), false);
    assert.equal(rectsOverlap(regions.log, regions.terry), false);
  }
});

test("narrow: screen+log stay in row 1 and Terry docks below without overlap", () => {
  const regions = layoutRegions({ width: 800, height: 1080, logHeight: 150, gap: 8 });
  assert.equal(regions.mode, "compact");
  assert.equal(regions.screen.x, 0);
  assert.equal(regions.screen.width, 800);
  assert.ok(regions.screen.height > 0);
  assert.equal(regions.terry.y >= regions.log.y + regions.log.height, true);
  assert.equal(rectsOverlap(regions.screen, regions.log), false);
  assert.equal(rectsOverlap(regions.screen, regions.terry), false);
  assert.equal(rectsOverlap(regions.log, regions.terry), false);
});

test("Terry control group keeps hide, costume, and the quote mute toggle", () => {
  const node = frame({ width: 1920, height: 1240 });
  assert.equal(byTestId(node, "companion-hide").length, 1);
  assert.equal(byTestId(node, "companion-costume").length, 1);
  const mute = byTestId(node, "companion-mute");
  assert.equal(mute.length, 1);
  assert.equal(mute[0].props["aria-pressed"], "false");
  assert.match(String(mute[0].props.title), /quote bubbles/i);
});

test("CSS keeps the same breakpoint and never stacks a 750px figure under the log", () => {
  assert.match(CSS, /@media \(max-width: 900px\)/);
  assert.match(CSS, /\.tos-body\s*\{[^}]*grid-template-rows:\s*minmax\(0,\s*1fr\)\s+168px/s);
  assert.match(CSS, /\.tos-pane \.tos-companion-dock\s*\{[^}]*grid-row:\s*2/s);
  assert.match(CSS, /\.tos-pane \.tos-companion-dock\s*\{[^}]*height:\s*100%/s);
  assert.match(CSS, /\.tos-companion-dock\s*\{[^}]*grid-column:\s*2/s);
  assert.match(CSS, /\.tos-stage-row\s*\{[^}]*display:\s*contents/s);
  assert.match(CSS, /\.tos-companion-bubble\s*\{[^}]*max-width:\s*min\(100%,\s*340px\)/s);
  assert.match(CSS, /\.tos-companion-bubble\s*\{[^}]*max-height:\s*42%/s);
  assert.match(CSS, /\.tos-companion-bubble\s*\{[^}]*overflow:\s*auto/s);
  assert.match(CSS, /@media \(max-width: 900px\)[\s\S]*?\.tos-companion-bubble\s*\{[^}]*max-height:\s*76px/s);
});

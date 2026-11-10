import assert from "node:assert/strict";
import test from "node:test";

import { TempleOSPane } from "../../desktop/src/ui/pane.js";
import { resetTerrySession } from "../../desktop/src/ui/companion.js";
import { resetFiber, rerender, flushEffects } from "./shims/jsx-runtime.mjs";

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

async function tick(times = 8) {
  for (let i = 0; i < times; i += 1) await Promise.resolve();
}

function readyStatus() {
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
    companion: {
      enabled: true,
      hidden: false,
      character: "terry",
      animation: "idle",
      costume: "base",
      speech: { active: false, text: "" },
    },
  };
}

const idleClip = {
  name: "idle",
  duration_ms: 1000,
  loop: true,
  frames: [{ parts: {}, variants: {} }],
};

function paneProps(rest, extra) {
  return {
    transport: { rest: rest },
    initial: {
      skipLoad: true,
      theme: "hermes",
      status: readyStatus(),
      ...(extra || {}),
    },
  };
}

test("re-renders and new hosts load the Terry bundle once", async () => {
  resetTerrySession();
  resetFiber();
  const bundleCalls = [];
  let release;
  const bundlePromise = new Promise((resolve) => {
    release = resolve;
  });
  const rest = () => {
    let generation = 0;
    return function hostRest(path) {
      const url = String(path);
      generation += 1;
      if (url.includes("companion/clip") && url.includes("bundle")) {
        bundleCalls.push({ url: url, generation: generation });
        return bundlePromise;
      }
      if (url.includes("companion/clip")) {
        return Promise.resolve({ ok: true, clip: idleClip });
      }
      return Promise.resolve({ ok: true, running: true, mode: "shared", width: 640, height: 480 });
    };
  };

  let node = rerender(TempleOSPane, paneProps(rest()));
  assert.equal(texts(byTestId(node, "companion-loading")[0]), "Summoning Terry…");
  assert.equal(byTestId(node, "companion-dock")[0].props["data-ready"], "0");
  flushEffects();
  for (let i = 0; i < 5; i += 1) {
    node = rerender(TempleOSPane, paneProps(rest()));
    flushEffects();
  }
  assert.equal(bundleCalls.length, 1, "bundle GET must survive new host objects");

  release({
    ok: true,
    registry: { slots: {} },
    speech: { events: [], duration_ms: 800 },
    smoke: {},
    parts: {},
  });
  await bundlePromise;
  await tick();
  node = rerender(TempleOSPane, paneProps(rest()));
  assert.equal(bundleCalls.length, 1);
  assert.equal(byTestId(node, "companion-dock")[0].props["data-ready"], "1");
  assert.equal(byTestId(node, "companion-loading").length, 0);
  assert.equal(byTestId(node, "screen").length, 1);
  assert.equal(byTestId(node, "agent-log").length, 1);

  resetFiber();
  node = rerender(TempleOSPane, paneProps(rest()));
  flushEffects();
  await tick();
  node = rerender(TempleOSPane, paneProps(rest()));
  assert.equal(bundleCalls.length, 1, "a remount reuses the pane-session bundle");
  assert.equal(byTestId(node, "companion-dock")[0].props["data-ready"], "1");
});

test("a failed bundle load shows the server error", async () => {
  resetTerrySession();
  resetFiber();
  const rest = (path) => {
    const url = String(path);
    if (url.includes("companion/clip") && url.includes("bundle")) {
      return Promise.resolve({
        ok: false,
        error: "Missing Terry v4 asset bundle.",
        fix: "Reinstall the plugin so desktop/assets/companion/terry/v4 is present.",
      });
    }
    return Promise.resolve({ ok: true });
  };
  let node = rerender(TempleOSPane, paneProps(rest));
  flushEffects();
  await tick();
  node = rerender(TempleOSPane, paneProps(rest));
  const loading = byTestId(node, "companion-loading");
  assert.equal(loading.length, 1);
  assert.match(texts(loading[0]), /Missing Terry v4 asset bundle/);
  assert.equal(loading[0].props["data-state"], "error");
  assert.equal(byTestId(node, "companion-dock")[0].props["data-ready"], "0");
});

test("Fit is the default, drag clamps to manual, and double-click returns to Fit", () => {
  resetFiber();
  const store = new Map();
  const previous = globalThis.localStorage;
  globalThis.localStorage = {
    getItem(key) {
      return store.has(key) ? store.get(key) : null;
    },
    setItem(key, value) {
      store.set(key, String(value));
    },
  };
  const listeners = {};
  const previousWindow = globalThis.window;
  globalThis.window = {
    addEventListener(type, fn) {
      listeners[type] = listeners[type] || [];
      listeners[type].push(fn);
    },
    removeEventListener(type, fn) {
      listeners[type] = (listeners[type] || []).filter((item) => item !== fn);
    },
  };
  try {
    const viewport = { width: 2000, height: 1200, rail: 300 };
    const props = paneProps(() => Promise.resolve({ ok: true }), { viewport: viewport });
    let node = rerender(TempleOSPane, props);
    const fit = byTestId(node, "screen-fit")[0];
    assert.equal(texts(fit), "Fit");
    assert.equal(fit.props["aria-pressed"], "true");
    const screen = byTestId(node, "screen")[0];
    assert.equal(screen.props["data-screen-mode"], "fit");
    assert.equal(screen.props.style.width, 1600);
    assert.equal(screen.props.style.height, 1200);
    assert.equal(screen.props.style.imageRendering, undefined);
    const img = findAll(screen, (item) => item.type === "img");
    assert.equal(img.length, 0);

    byTestId(node, "screen-resize")[0].props.onPointerDown({
      button: 0,
      clientX: 500,
      preventDefault() {},
      stopPropagation() {},
    });
    assert.equal(listeners.pointermove.length, 1);
    listeners.pointermove[0]({ clientX: 300 });
    node = rerender(TempleOSPane, props);
    const manual = byTestId(node, "screen")[0];
    assert.equal(manual.props["data-screen-mode"], "manual");
    assert.equal(manual.props.style.width, 1400);
    assert.equal(manual.props.style.height, 1050);
    listeners.pointermove[0]({ clientX: 500 + 5000 });
    node = rerender(TempleOSPane, props);
    assert.equal(byTestId(node, "screen")[0].props.style.width, 1600);
    listeners.pointermove[0]({ clientX: 500 - 5000 });
    node = rerender(TempleOSPane, props);
    assert.equal(byTestId(node, "screen")[0].props.style.width, 640);

    byTestId(node, "screen-resize")[0].props.onDoubleClick({
      preventDefault() {},
      stopPropagation() {},
    });
    node = rerender(TempleOSPane, props);
    assert.equal(byTestId(node, "screen")[0].props["data-screen-mode"], "fit");
    assert.equal(byTestId(node, "screen")[0].props.style.width, 1600);
    assert.equal(byTestId(node, "screen-fit")[0].props["aria-pressed"], "true");

    flushEffects();
    assert.match(store.get("templeos.screenSize") || "", /"mode":"fit"/);
  } finally {
    if (previous === undefined) delete globalThis.localStorage;
    else globalThis.localStorage = previous;
    if (previousWindow === undefined) delete globalThis.window;
    else globalThis.window = previousWindow;
  }
});

test("a stored manual width is restored for the pane session", () => {
  resetFiber();
  const previous = globalThis.localStorage;
  globalThis.localStorage = {
    getItem(key) {
      if (key === "templeos.screenSize") return JSON.stringify({ mode: "manual", width: 960 });
      return null;
    },
    setItem() {},
  };
  try {
    const node = rerender(
      TempleOSPane,
      paneProps(() => Promise.resolve({ ok: true }), {
        viewport: { width: 1800, height: 1000, rail: 360 },
      })
    );
    const screen = byTestId(node, "screen")[0];
    assert.equal(screen.props["data-screen-mode"], "manual");
    assert.equal(screen.props.style.width, 960);
    assert.equal(screen.props.style.height, 720);
    assert.equal(byTestId(node, "companion-dock").length, 1);
    assert.equal(byTestId(node, "agent-log").length, 1);
  } finally {
    if (previous === undefined) delete globalThis.localStorage;
    else globalThis.localStorage = previous;
  }
});

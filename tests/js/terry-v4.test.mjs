import assert from "node:assert/strict";
import test from "node:test";

import {
  COSTUME_VARIANTS,
  drawFrame,
  renderScene,
  sampleClip,
  speechPlate,
} from "../../desktop/src/ui/terry_v4.js";

function fakeContext() {
  const calls = [];
  const ctx = {
    imageSmoothingEnabled: false,
    imageSmoothingQuality: "low",
    setTransform(...args) { calls.push(["setTransform", ...args]); },
    clearRect(...args) { calls.push(["clearRect", ...args]); },
    save() { calls.push(["save"]); },
    restore() { calls.push(["restore"]); },
    translate(...args) { calls.push(["translate", ...args]); },
    rotate(...args) { calls.push(["rotate", ...args]); },
    scale(...args) { calls.push(["scale", ...args]); },
    drawImage(...args) { calls.push(["drawImage", ...args]); },
  };
  return { ctx, calls };
}

function fakeCanvas(width, height, dpr = 2) {
  const { ctx, calls } = fakeContext();
  return {
    width: 0,
    height: 0,
    clientWidth: width,
    clientHeight: height,
    getBoundingClientRect: () => ({ width, height }),
    getContext: () => ctx,
    _ctx: ctx,
    _calls: calls,
    _dpr: dpr,
  };
}

function image(name) {
  return { name, width: 100, height: 100 };
}

const REGISTRY = {
  slots: {
    torso: { layer: 30, size: [56, 70], pivot: [28, 62], variants: { default: "parts/torso/default.png" } },
    torso_overlay: {
      layer: 35,
      size: [56, 70],
      pivot: [28, 62],
      variants: { cowboy_vest: "parts/torso_overlay/cowboy_vest.png" },
    },
    head_base: {
      layer: 70,
      size: [64, 84],
      pivot: [32, 76],
      variants: {
        neutral: "parts/head_base/neutral.png",
        talk_a: "parts/head_base/talk_a.png",
      },
    },
    eye_l: { layer: 75, size: [10, 10], pivot: [5, 5], variants: { open: "parts/eye_l/open.png" } },
    cap: {
      layer: 90,
      size: [78, 44],
      pivot: [39, 32],
      variants: {
        default: "parts/cap/default.png",
        cowboy: "parts/cap/cowboy.png",
      },
    },
  },
};

function frame() {
  return {
    parts: {
      torso: { x: 96, y: 100 },
      head_base: { x: 96, y: 90 },
      eye_l: { x: 96, y: 80 },
      cap: { x: 96, y: 90 },
    },
    variants: { head_base: "neutral" },
  };
}

test("sampleClip wraps loops and clamps one-shots", () => {
  const loop = { duration_ms: 1000, loop: true, frames: [{ a: 1 }, { a: 2 }] };
  assert.equal(sampleClip(loop, 0).a, 1);
  assert.equal(sampleClip(loop, 500).a, 2);
  assert.equal(sampleClip(loop, 1000).a, 1);
  const once = { duration_ms: 1000, loop: false, frames: [{ a: 1 }, { a: 2 }] };
  assert.equal(sampleClip(once, 0).a, 1);
  assert.equal(sampleClip(once, 1000).a, 2);
  assert.equal(sampleClip(once, 5000).a, 2);
});

test("speechPlate picks the latest discrete whole-head plate", () => {
  const events = [
    { time_ms: 0, plate: "neutral" },
    { time_ms: 100, plate: "talk_a" },
    { time_ms: 200, plate: "talk_o" },
  ];
  assert.equal(speechPlate(events, 50, "neutral"), "neutral");
  assert.equal(speechPlate(events, 150, "neutral"), "talk_a");
  assert.equal(speechPlate(events, 900, "neutral"), "talk_o");
});

test("drawFrame skips omitted face stubs and applies costume variants", () => {
  const images = new Map([
    ["parts/torso/default.png", image("torso")],
    ["parts/torso_overlay/cowboy_vest.png", image("vest")],
    ["parts/head_base/neutral.png", image("neutral")],
    ["parts/eye_l/open.png", image("eye")],
    ["parts/cap/cowboy.png", image("cowboy-cap")],
  ]);
  const { ctx, calls } = fakeContext();
  drawFrame(ctx, frame(), REGISTRY, images, "cowboy");
  const drawn = calls.filter((call) => call[0] === "drawImage").map((call) => call[1].name);
  assert.deepEqual(drawn, ["torso", "vest", "neutral", "cowboy-cap"]);
  assert.equal(drawn.includes("eye"), false);
});

test("drawFrame uses a speech plate override", () => {
  const images = new Map([
    ["parts/torso/default.png", image("torso")],
    ["parts/head_base/neutral.png", image("neutral")],
    ["parts/head_base/talk_a.png", image("talk")],
    ["parts/cap/default.png", image("cap")],
  ]);
  const { ctx, calls } = fakeContext();
  drawFrame(ctx, frame(), REGISTRY, images, "base", { headPlate: "talk_a" });
  const drawn = calls.filter((call) => call[0] === "drawImage").map((call) => call[1].name);
  assert.ok(drawn.includes("talk"));
  assert.equal(drawn.includes("neutral"), false);
});

test("costume map names the base, cowboy, wizard and chef variants", () => {
  assert.deepEqual(Object.keys(COSTUME_VARIANTS), ["base", "cowboy", "wizard", "chef"]);
  assert.equal(COSTUME_VARIANTS.cowboy.torso_overlay, "cowboy_vest");
  assert.equal(COSTUME_VARIANTS.wizard.torso_overlay, "wizard_robe");
  assert.equal(COSTUME_VARIANTS.chef.torso_overlay, "chef_apron");
});

test("renderScene uses a DPR-aware backing store and smooth scaling", () => {
  const previous = globalThis.window;
  globalThis.window = { devicePixelRatio: 2 };
  try {
    const canvas = fakeCanvas(600, 750, 2);
    const images = new Map([
      ["parts/torso/default.png", image("torso")],
      ["parts/head_base/neutral.png", image("neutral")],
      ["parts/cap/default.png", image("cap")],
    ]);
    const result = renderScene(canvas, { registry: REGISTRY }, images, frame(), "base");
    assert.equal(canvas.width, 1200);
    assert.equal(canvas.height, 1500);
    assert.equal(canvas._ctx.imageSmoothingEnabled, true);
    assert.equal(canvas._ctx.imageSmoothingQuality, "high");
    const transform = canvas._calls.find((call) => call[0] === "setTransform");
    assert.deepEqual(transform, ["setTransform", 2, 0, 0, 2, 0, 0]);
    assert.ok(result.scale > 3.5);
  } finally {
    if (previous === undefined) delete globalThis.window;
    else globalThis.window = previous;
  }
});

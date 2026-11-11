import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

import {
  clipForState,
  resolveTerryClip,
  resolveTerryState,
  STATE_CLIP,
  VIDEO_CLIPS,
} from "../../desktop/src/ui/companion.js";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const CSS = readFileSync(path.join(ROOT, "desktop", "src", "ui", "styles.css"), "utf8");
const PLUGIN = readFileSync(path.join(ROOT, "desktop", "plugin.js"), "utf8");
const CLIPS = JSON.parse(
  readFileSync(path.join(ROOT, "desktop", "assets", "companion", "terry", "v5", "clips.json"), "utf8")
);

test("v5 pack exposes exactly the six in-tree loops and its documented state map", () => {
  assert.deepEqual([...VIDEO_CLIPS], ["idle", "smoking", "speaking", "typing", "walk", "wave"]);
  assert.deepEqual(Object.keys(CLIPS.clips).sort(), [...VIDEO_CLIPS].sort());
  assert.equal(CLIPS.width, 720);
  assert.equal(CLIPS.height, 1080);
  assert.equal(CLIPS.fps, 20);
  assert.deepEqual(STATE_CLIP, CLIPS.state_map);
  assert.deepEqual(STATE_CLIP, {
    idle: "idle",
    idle_variant: "smoking",
    typing: "typing",
    speaking: "speaking",
    boot: "wave",
    greet: "wave",
    tool_success: "wave",
    first_appear: "walk",
  });
});

test("every logical state maps to the matching clip name", () => {
  for (const [state, clip] of Object.entries(STATE_CLIP)) {
    assert.equal(clipForState(state), clip, state);
    assert.ok(VIDEO_CLIPS.includes(clip), state);
  }
  assert.equal(clipForState("unknown-state"), "idle");
  assert.equal(clipForState(undefined), "idle");
});

test("host signals map to idle, smoking, typing, speaking, wave, and walk", () => {
  assert.equal(resolveTerryClip({ animation: "idle" }), "idle");
  assert.equal(resolveTerryClip({ animation: "idle", idleVariant: "smoking" }), "smoking");
  assert.equal(resolveTerryClip({ animation: "smoking" }), "smoking");
  assert.equal(resolveTerryClip({ animation: "typing" }), "typing");
  assert.equal(resolveTerryClip({ animation: "idle", agentBusy: true }), "typing");
  assert.equal(resolveTerryClip({ animation: "idle", bubble: "Hello from Hermes" }), "speaking");
  assert.equal(resolveTerryClip({ animation: "talking" }), "speaking");
  for (const animation of ["greet", "waving", "celebrate_short", "vm_booting"]) {
    assert.equal(resolveTerryClip({ animation }), "wave", animation);
  }
  assert.equal(resolveTerryClip({ animation: "idle", firstAppear: true }), "walk");
  assert.equal(resolveTerryClip({ animation: "walk" }), "walk");
});

test("state priority keeps a live bubble speaking while tool calls type", () => {
  assert.equal(resolveTerryState({ animation: "typing", bubble: "quote" }), "speaking");
  assert.equal(resolveTerryState({ animation: "greet", bubble: "quote" }), "speaking");
  assert.equal(resolveTerryState({ animation: "greet", firstAppear: true }), "boot");
  assert.equal(resolveTerryState({ animation: "typing", firstAppear: true }), "typing");
  assert.equal(resolveTerryState({ animation: "idle", firstAppear: true }), "first_appear");
});

test("video renderer CSS stacks two transparent videos with a 200ms crossfade", () => {
  assert.match(CSS, /\.tos-companion-video\s*\{[^}]*position:\s*absolute/s);
  assert.match(CSS, /\.tos-companion-video\s*\{[^}]*object-fit:\s*contain/s);
  assert.match(CSS, /\.tos-companion-video\s*\{[^}]*transition:\s*opacity\s+200ms/s);
  assert.match(CSS, /\.tos-companion-video\.is-front\s*\{[^}]*opacity:\s*1/s);
  assert.doesNotMatch(CSS, /\.tos-companion-video\s*\{[^}]*image-rendering:\s*pixelated/s);
});

test("the bundle references the v5 route without embedding the webm payloads", () => {
  assert.match(PLUGIN, /v5:/);
  assert.equal(PLUGIN.includes("data:video/webm"), false);
  assert.equal(PLUGIN.includes("exports/idle.webm"), false);
  assert.ok(PLUGIN.length < 2_000_000, "plugin.js must not carry the 2.9MB clip pack");
});

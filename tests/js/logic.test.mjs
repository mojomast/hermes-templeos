import assert from "node:assert/strict";
import test from "node:test";

import {
  CONTROL_MODES,
  DEFAULT_HEIGHT,
  DEFAULT_WIDTH,
  POLL_FOCUSED_MS,
  POLL_HIDDEN_MS,
  POLL_IDLE_MS,
  POLL_SLOW_MS,
  POLL_STOPPED_MS,
  POLL_VISIBLE_MS,
  accelLabel,
  drivingChip,
  guestSize,
  integerScale,
  isReleaseHatch,
  keyEventToPayload,
  logLine,
  mapPointerToGuest,
  modeLabel,
  checkState,
  firstCheck,
  needsOnboarding,
  nextMode,
  pollIntervalMs,
  qcodeFor,
  statusSummary,
  userMayInput,
} from "../../desktop/src/ui/logic.js";

test("integer scale never goes below 1x and stays integer", () => {
  assert.deepEqual(integerScale(1280, 960, 640, 480), { scale: 2, width: 1280, height: 960 });
  assert.deepEqual(integerScale(700, 500, 640, 480), { scale: 1, width: 640, height: 480 });
  assert.deepEqual(integerScale(100, 100, 640, 480), { scale: 1, width: 640, height: 480 });
  assert.deepEqual(integerScale(2048, 1536, 1024, 768), { scale: 2, width: 2048, height: 1536 });
});

test("guest size and mode labels", () => {
  assert.deepEqual(guestSize("tinkeros"), { width: DEFAULT_WIDTH, height: DEFAULT_HEIGHT });
  assert.deepEqual(guestSize("zealos"), { width: 1024, height: 768 });
  assert.deepEqual(guestSize("tinkeros", { width: 1024, height: 768 }), { width: 1024, height: 768 });
  assert.deepEqual(CONTROL_MODES, ["watch", "shared", "user"]);
  assert.equal(modeLabel("user", false), "You drive");
  assert.equal(modeLabel("watch", false), "Watch");
  assert.equal(modeLabel("shared", true), "Agent paused");
  assert.equal(modeLabel("shared", false), "Shared");
  assert.equal(accelLabel("tcg", false), "tcg");
  assert.equal(accelLabel(null, true), "kvm");
  assert.equal(
    statusSummary({ running: true, snapshot: "golden", accel: "tcg", mode: "shared", agent_paused: false }),
    "running · golden · tcg · Shared"
  );
});

test("pointer mapping is absolute guest coordinates and clamps", () => {
  const rect = { left: 10, top: 20, width: 1280, height: 960 };
  assert.deepEqual(mapPointerToGuest(10, 20, rect, 640, 480), { x: 0, y: 0 });
  assert.deepEqual(mapPointerToGuest(650, 500, rect, 640, 480), { x: 320, y: 240 });
  assert.deepEqual(mapPointerToGuest(1290, 980, rect, 640, 480), { x: 639, y: 479 });
  assert.deepEqual(mapPointerToGuest(-20, -20, rect, 640, 480), { x: 0, y: 0 });
});

test("adaptive polling stays at or under 5 fps and backs off when idle, hidden, or slow", () => {
  assert.equal(pollIntervalMs({ hidden: true, running: true }), POLL_HIDDEN_MS);
  assert.equal(pollIntervalMs({ running: false }), POLL_STOPPED_MS);
  assert.equal(pollIntervalMs({ running: true, unchanged: true }), POLL_IDLE_MS);
  assert.equal(pollIntervalMs({ running: true, focused: true }), POLL_FOCUSED_MS);
  assert.equal(pollIntervalMs({ running: true }), POLL_VISIBLE_MS);
  assert.equal(pollIntervalMs({ running: true, slow: true }), Math.max(POLL_SLOW_MS, POLL_IDLE_MS));
  assert.ok(POLL_VISIBLE_MS >= 200 && POLL_VISIBLE_MS <= 300);
  assert.ok(POLL_FOCUSED_MS >= 180 && POLL_FOCUSED_MS <= 250);
  assert.ok(POLL_VISIBLE_MS >= 200); // ≤5 fps
});

test("key capture maps qcodes and Esc is the hatch", () => {
  assert.equal(isReleaseHatch({ key: "Escape" }), true);
  assert.equal(isReleaseHatch({ key: "Escape", shiftKey: true }), false);
  assert.deepEqual(keyEventToPayload({ key: "Escape" }), { hatch: true });
  assert.deepEqual(keyEventToPayload({ key: "a" }), { type: "type", text: "a" });
  assert.deepEqual(keyEventToPayload({ key: "Enter", code: "Enter" }), { type: "keys", keys: ["ret"] });
  assert.deepEqual(keyEventToPayload({ key: "c", code: "KeyC", ctrlKey: true }), { type: "keys", keys: ["ctrl", "c"] });
  assert.equal(qcodeFor({ key: "ArrowUp", code: "ArrowUp" }), "up");
  assert.equal(qcodeFor({ key: "F1", code: "F1" }), "f1");
  assert.equal(qcodeFor({ key: "-", code: "Minus" }), "minus");
});

test("mode transitions, onboarding, driving chip, and log lines", () => {
  assert.equal(nextMode("take", "shared"), "user");
  assert.equal(nextMode("handback", "user"), "shared");
  assert.equal(nextMode("watch", "shared"), "watch");
  assert.equal(userMayInput("watch"), false);
  assert.equal(userMayInput("shared"), true);
  assert.equal(needsOnboarding({ running: false, setup_needed: true }), true);
  assert.equal(needsOnboarding({ running: false, code: "qemu_missing" }), true);
  assert.equal(needsOnboarding({ running: false, checks: { qemu: false, iso: true } }), true);
  assert.equal(needsOnboarding({ running: true, setup_needed: true }), false);
  assert.equal(needsOnboarding({ running: false, setup_needed: false, checks: { qemu: true, iso: true } }), false);
  assert.equal(checkState("unknown"), "unknown");
  assert.equal(checkState(false), "no");
  assert.equal(checkState(true), "ok");
  assert.equal(firstCheck({ iso: false, iso_ok: true }, ["iso", "iso_ok"]), false);
  assert.equal(drivingChip({ mode: "user", agent_paused: true }).label, "Agent paused, you're driving");
  assert.equal(drivingChip({ mode: "shared", agent_busy: true }).label, "Agent is typing");
  assert.equal(drivingChip({ mode: "shared", agent_paused: true }).label, "Agent paused, you're driving");
  const line = logLine({
    source: "agent",
    tool: "templeos_input",
    op: "type",
    ok: true,
    at: "2026-11-09T19:00:01.000Z",
    summary: "templeos_input type",
  });
  assert.match(line, /Agent/);
  assert.match(line, /templeos_input type/);
});

import { isAbortError, errorText } from "../../desktop/src/ui/api.js";

test("aborted fetches stay silent in the pane error banner", () => {
  assert.equal(isAbortError({ name: "AbortError", message: "signal is aborted without reason" }), true);
  const abortLike = { name: "AbortError", message: "The operation was aborted." };
  assert.equal(isAbortError(abortLike), true);
  assert.equal(isAbortError({ message: "QEMU missing" }), false);
  assert.equal(errorText({ name: "AbortError", message: "signal is aborted without reason" }), "");
  assert.match(errorText({ message: "TempleOS could not finish that.", fix: "Retry." }), /Retry/);
});

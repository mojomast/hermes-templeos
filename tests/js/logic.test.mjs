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
  clampScreenWidth,
  fitGuestDisplay,
  flavorShaSummary,
  preferredFlavorId,
  shaStateLabel,
  FLAVOR_PICKER_IDS,
  guestSize,
  integerScale,
  isReleaseHatch,
  keyEventToPayload,
  logLine,
  mapPointerToGuest,
  maxScreenWidth,
  measureScreenSpace,
  parseScreenPref,
  screenDisplay,
  serializeScreenPref,
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
  assert.deepEqual(guestSize("templeoh"), { width: DEFAULT_WIDTH, height: DEFAULT_HEIGHT });
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

test("pointer mapping stays correct at fractional CSS scales", () => {
  const rect = { left: 0, top: 0, width: 920, height: 690 };
  assert.deepEqual(mapPointerToGuest(460, 345, rect, 640, 480), { x: 320, y: 240 });
  const fractional = { left: 12.5, top: 8.25, width: 960.5, height: 720.4 };
  assert.deepEqual(
    mapPointerToGuest(12.5 + 960.5 * 0.5, 8.25 + 720.4 * 0.25, fractional, 640, 480),
    { x: 320, y: 120 }
  );
  assert.deepEqual(mapPointerToGuest(12.5 + 960.5, 8.25 + 720.4, fractional, 640, 480), { x: 639, y: 479 });
  const below = { left: 0, top: 0, width: 320, height: 240 };
  assert.deepEqual(mapPointerToGuest(160, 120, below, 640, 480), { x: 320, y: 240 });
});

test("fit scale subtracts the right rail and keeps the guest aspect", () => {
  const wide = fitGuestDisplay({ width: 1600, height: 900 }, { width: 640, height: 480 }, 360, 12);
  assert.equal(wide.availableWidth, 1228);
  assert.equal(wide.availableHeight, 900);
  assert.equal(wide.scale, 1.875);
  assert.equal(wide.width, 1200);
  assert.equal(wide.height, 900);

  const small = fitGuestDisplay({ width: 700, height: 420 }, { width: 640, height: 480 }, 300, 12);
  assert.equal(small.availableWidth, 388);
  assert.ok(Math.abs(small.scale - 0.60625) < 1e-9);
  assert.ok(Math.abs(small.width - 388) < 1e-6);
  assert.ok(Math.abs(small.height - 291) < 1e-6);

  const unmeasured = fitGuestDisplay({ width: 0, height: 0 }, { width: 640, height: 480 }, 0, 12);
  assert.deepEqual(
    { scale: unmeasured.scale, width: unmeasured.width, height: unmeasured.height },
    { scale: 1, width: 640, height: 480 }
  );
});

test("fit subtracts only Terry's column from the width and the log from the height", () => {
  const guest = { width: 640, height: 480 };
  const fit = fitGuestDisplay({ width: 1600, height: 1100 }, guest, 380, 12, 210);
  assert.equal(fit.availableWidth, 1208);
  assert.equal(fit.availableHeight, 890);
  assert.ok(Math.abs(fit.scale - 890 / 480) < 1e-9);
  assert.ok(Math.abs(fit.height - 890) < 1e-6);
  assert.ok(Math.abs(fit.width - (640 * 890) / 480) < 1e-6);

  const fatRail = fitGuestDisplay({ width: 1600, height: 1100 }, guest, 668, 12, 0);
  assert.equal(fatRail.width, 920);
  assert.ok(fit.width > fatRail.width);
  assert.ok(fit.height > fatRail.height);

  const measured = measureScreenSpace({
    bodyWidth: 1600,
    stageWidth: 1200,
    stageRight: 1212,
    stageHeight: 1000,
    railWidth: 380,
    railLeft: 1224,
    hatchHeight: 28,
    logHeight: 210,
  });
  assert.equal(measured.rail, 380);
  assert.equal(measured.log, 210);
  assert.equal(measured.height, 972);
  const fromMeasure = fitGuestDisplay(
    { width: measured.width, height: measured.height },
    guest,
    measured.rail,
    measured.gap,
    measured.log
  );
  assert.equal(fromMeasure.availableWidth, 1208);
  assert.equal(fromMeasure.availableHeight, 762);
});

test("screen space uses a side-by-side rail and ignores a stacked one", () => {
  const side = measureScreenSpace({
    bodyWidth: 1600,
    stageWidth: 900,
    stageRight: 920,
    stageHeight: 800,
    railWidth: 668,
    railLeft: 932,
    hatchHeight: 20,
  });
  assert.deepEqual(side, { width: 1600, height: 780, rail: 668, gap: 12, log: 0 });
  const fitted = fitGuestDisplay(
    { width: side.width, height: side.height },
    { width: 640, height: 480 },
    side.rail,
    side.gap,
    side.log
  );
  assert.equal(fitted.availableWidth, 920);
  assert.equal(fitted.scale, 1.4375);
  assert.equal(fitted.width, 920);
  assert.equal(fitted.height, 690);

  const stacked = measureScreenSpace({
    bodyWidth: 700,
    stageWidth: 700,
    stageRight: 700,
    stageHeight: 400,
    railWidth: 700,
    railLeft: 0,
    railTop: 420,
    hatchHeight: 20,
  });
  assert.equal(stacked.rail, 0);
  assert.equal(stacked.width, 700);
});

test("manual width stays between the guest native size and the remaining space", () => {
  assert.equal(maxScreenWidth(1228, 900, 640, 480), 1200);
  assert.equal(clampScreenWidth(400, 640, 1200), 640);
  assert.equal(clampScreenWidth(2000, 640, 1200), 1200);
  assert.equal(clampScreenWidth(960, 640, 1200), 960);
  const manual = screenDisplay({ mode: "manual", width: 960 }, { width: 1600, height: 900 }, { width: 640, height: 480 }, 360, 12);
  assert.equal(manual.mode, "manual");
  assert.equal(manual.width, 960);
  assert.equal(manual.height, 720);
  const restored = parseScreenPref(serializeScreenPref({ mode: "manual", width: 960.4 }));
  assert.deepEqual(restored, { mode: "manual", width: 960 });
  assert.deepEqual(parseScreenPref("nope"), { mode: "fit", width: 0 });
  assert.equal(serializeScreenPref({ mode: "fit", width: 0 }), '{"mode":"fit","width":0}');
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

test("flavor picker helpers expose version and SHA state", () => {
  assert.deepEqual(FLAVOR_PICKER_IDS, ["templeoh", "tinkeros", "templeos", "zealos"]);
  assert.equal(shaStateLabel("verified"), "SHA verified");
  assert.equal(shaStateLabel("missing"), "ISO not downloaded");
  assert.equal(preferredFlavorId({}), "templeoh");
  assert.equal(preferredFlavorId({ flavor: "tinkeros" }), "tinkeros");
  const summary = flavorShaSummary({
    preferred_flavor: "templeoh",
    flavor_name: "Temple of Hermes 0.1.3",
    sha_state: "verified",
    flavor_sha256: "fbaa3d6f0a8f9190f295e933c32cb833a61b3cb43a708309acb6c98ff51ac4fd",
    flavors: [
      {
        id: "templeoh",
        name: "Temple of Hermes 0.1.3",
        sha_state: "verified",
        sha256: "fbaa3d6f0a8f9190f295e933c32cb833a61b3cb43a708309acb6c98ff51ac4fd",
      },
    ],
  });
  assert.equal(summary.id, "templeoh");
  assert.match(summary.text, /Temple of Hermes 0\.1\.3/);
  assert.match(summary.text, /SHA verified/);
  assert.match(summary.text, /fbaa3d6f0a8f/);
});

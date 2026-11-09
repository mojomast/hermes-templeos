import assert from "node:assert/strict";
import test from "node:test";

import {
  CONTROL_MODES,
  DEFAULT_HEIGHT,
  DEFAULT_WIDTH,
  accelLabel,
  guestSize,
  integerScale,
  modeLabel,
  statusSummary,
} from "../../desktop/src/ui/logic.js";

test("integer scale never goes below 1x and stays integer", () => {
  assert.deepEqual(integerScale(1280, 960, 640, 480), { scale: 2, width: 1280, height: 960 });
  assert.deepEqual(integerScale(700, 500, 640, 480), { scale: 1, width: 640, height: 480 });
  assert.deepEqual(integerScale(100, 100, 640, 480), { scale: 1, width: 640, height: 480 });
});

test("guest size and mode labels", () => {
  assert.deepEqual(guestSize("tinkeros"), { width: DEFAULT_WIDTH, height: DEFAULT_HEIGHT });
  assert.deepEqual(guestSize("zealos"), { width: 1024, height: 768 });
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

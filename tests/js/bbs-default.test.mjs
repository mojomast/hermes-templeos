import assert from "node:assert/strict";
import test from "node:test";

import { bbsChip, bbsJoinVisible } from "../../desktop/src/ui/logic.js";
import { TempleOSPane } from "../../desktop/src/ui/pane.js";
import { resetFiber, rerender } from "./shims/jsx-runtime.mjs";

function walk(node, visit) {
  if (node == null || node === false || node === true) return;
  if (Array.isArray(node)) {
    node.forEach((child) => walk(child, visit));
    return;
  }
  if (typeof node === "string" || typeof node === "number") {
    visit({ text: String(node) });
    return;
  }
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

function frame(bbs) {
  resetFiber();
  return rerender(TempleOSPane, {
    transport: { rest: () => Promise.resolve({ ok: true }) },
    initial: {
      skipLoad: true,
      status: {
        running: false,
        mode: "shared",
        setup_needed: false,
        flavor: "templeoh",
        flavor_name: "Temple of Hermes 0.1.3",
        preferred_flavor: "templeoh",
        bbs,
      },
    },
  });
}

test("bbs chip reflects off, not joined, joined, and error", () => {
  assert.equal(bbsChip({ bbs: { enabled: false, joined: false } }).label, "BBS off");
  assert.equal(bbsChip({ bbs: { enabled: true, joined: false } }).label, "BBS not joined");
  const joined = bbsChip({ bbs: { enabled: true, joined: true, account: "toh-ada-agent" } });
  assert.equal(joined.label, "BBS joined");
  assert.match(joined.title, /toh-ada-agent/);
  assert.equal(bbsChip({ bbs: { enabled: true, joined: false, error: "bbs_unreachable" } }).state, "error");
  assert.equal(bbsChip({ bbs: { enabled: true, joined: false } }, false).label, "BBS checking");
});

test("join is visible only when enabled and not joined", () => {
  assert.equal(bbsJoinVisible({ bbs: { enabled: true, joined: false } }), true);
  assert.equal(bbsJoinVisible({ bbs: { enabled: true, joined: true } }), false);
  assert.equal(bbsJoinVisible({ bbs: { enabled: false, joined: false } }), false);
  assert.equal(bbsJoinVisible({}, false), false);
});

test("pane shows Join BBS when the community BBS is enabled and not joined", () => {
  const notJoined = frame({ enabled: true, configured: true, joined: false, account: null });
  assert.equal(byTestId(notJoined, "bbs-join").length, 1);
  assert.equal(byTestId(notJoined, "bbs-status-chip").length, 1);

  const joined = frame({ enabled: true, configured: true, joined: true, account: "toh-ada-agent" });
  assert.equal(byTestId(joined, "bbs-join").length, 0);

  const off = frame({ enabled: false, configured: false, joined: false, account: null });
  assert.equal(byTestId(off, "bbs-join").length, 0);
  assert.equal(byTestId(off, "bbs-on").length, 1);
});

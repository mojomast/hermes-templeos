import assert from "node:assert/strict";
import test from "node:test";

import { TempleOSPane } from "../../desktop/src/ui/pane.js";
import { createPaneContribution, registerTempleOSPane } from "../../desktop/src/ui/register.js";
import { resetFiber, rerender, flushEffects } from "./shims/jsx-runtime.mjs";

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

function texts(node) {
  const out = [];
  walk(node, (item) => {
    if (item.text) out.push(item.text);
  });
  return out.join(" ");
}

function findAll(node, pred) {
  const out = [];
  walk(node, (item) => {
    if (item.props && pred(item)) out.push(item);
  });
  return out;
}

function byTestId(node, id) {
  return findAll(node, (item) => item.props["data-testid"] === id);
}

test("register wires a TempleOS pane through ctx.rest", () => {
  resetFiber();
  const seen = [];
  const ctx = {
    register(contribution) {
      seen.push(contribution);
    },
    rest(path) {
      return Promise.resolve({ ok: true, path });
    },
  };
  assert.equal(registerTempleOSPane(ctx), true);
  assert.equal(seen.length, 1);
  assert.equal(seen[0].id, "templeos");
  assert.equal(seen[0].title, "TempleOS");
  assert.equal(typeof seen[0].render, "function");
  const contrib = createPaneContribution();
  assert.equal(contrib.id, "templeos");
});

test("pane shows Take control, Hand back, and a status chip", () => {
  resetFiber();
  const calls = [];
  const ctx = {
    register() {},
    rest(path, opts) {
      calls.push({ path, opts });
      if (path === "/status" || path === "/health") {
        return Promise.resolve({
          ok: true,
          running: false,
          mode: "shared",
          agent_paused: false,
          accel: "tcg",
          snapshot: "golden",
          flavor: "tinkeros",
        });
      }
      if (path === "/frame") {
        return Promise.resolve({ ok: false, code: "not_implemented", mime: "image/png", data: null });
      }
      return Promise.resolve({ ok: true, mode: "user", agent_paused: true });
    },
  };
  registerTempleOSPane(ctx);
  const node = rerender(TempleOSPane, {});
  const chip = byTestId(node, "status-chip");
  assert.equal(chip.length, 1);
  assert.match(texts(chip[0]) + texts(node), /stopped|Shared|golden|tcg/i);
  assert.equal(byTestId(node, "take-control").length, 1);
  assert.equal(byTestId(node, "hand-back").length, 1);
  assert.equal(texts(byTestId(node, "take-control")[0]), "Take control");
  assert.equal(texts(byTestId(node, "hand-back")[0]), "Hand back");
  assert.equal(byTestId(node, "screen").length, 1);
  assert.equal(byTestId(node, "agent-log").length, 1);
  const src = TempleOSPane.toString() + registerTempleOSPane.toString();
  assert.equal(src.includes("127.0.0.1"), false);
  assert.equal(src.includes("localStorage"), false);
  flushEffects();
  assert.ok(calls.some((item) => item.path === "/status"));
});

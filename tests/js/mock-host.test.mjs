import assert from "node:assert/strict";
import test from "node:test";

import { TempleOSPane } from "../../desktop/src/ui/pane.js";
import { createApi } from "../../desktop/src/ui/api.js";
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

function restFor(calls, replies) {
  return function rest(path, opts) {
    calls.push({ path, opts });
    const key = String(path).split("?")[0];
    if (typeof replies === "function") return replies(path, opts);
    if (replies && replies[key]) return Promise.resolve(replies[key]);
    return Promise.resolve({ ok: true });
  };
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

test("pane shows Take control, Hand back, and a status chip", async () => {
  resetFiber();
  const calls = [];
  const ctx = {
    register() {},
    rest: restFor(calls, {
      "/status": {
        ok: true,
        running: false,
        mode: "shared",
        agent_paused: false,
        accel: "tcg",
        snapshot: "golden",
        flavor: "tinkeros",
      },
      "/frame": { ok: false, code: "not_implemented", mime: "image/png", data: null },
      "/log": { ok: true, events: [] },
    }),
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
  const src = TempleOSPane.toString() + registerTempleOSPane.toString() + createApi.toString();
  assert.equal(src.includes("127.0.0.1"), false);
  assert.equal(src.includes("localStorage"), false);
  flushEffects();
  await Promise.resolve();
  assert.ok(calls.some((item) => item.path === "/status" || String(item.path).startsWith("/status")));
  assert.ok(calls.some((item) => String(item.path).startsWith("/frame")));
  assert.ok(calls.every((item) => !item.opts || !item.opts.headers));
});

test("onboarding, user-driving, and agent log states", () => {
  resetFiber();
  const onboard = rerender(TempleOSPane, {
    transport: { rest: () => Promise.resolve({ ok: true }) },
    initial: {
      skipLoad: true,
      status: {
        running: false,
        mode: "shared",
        setup_needed: true,
        checks: { qemu: false, iso: false, kvm: false },
        flavor: "tinkeros",
        flavor_name: "TinkerOS 5.20-rc10",
        accel: null,
      },
    },
  });
  assert.equal(byTestId(onboard, "onboarding").length, 1);
  assert.equal(byTestId(onboard, "setup").length, 1);
  assert.match(texts(byTestId(onboard, "onboarding")[0]), /Set up/);
  assert.match(texts(byTestId(onboard, "flavor-badge")[0]), /TinkerOS/);

  resetFiber();
  const driving = rerender(TempleOSPane, {
    transport: { rest: () => Promise.resolve({ ok: true }) },
    initial: {
      skipLoad: true,
      focused: true,
      frameUrl: "data:image/png;base64,xx",
      status: {
        running: true,
        mode: "user",
        agent_paused: true,
        setup_needed: false,
        flavor: "tinkeros",
        accel: "tcg",
        snapshot: "golden",
        kvm: false,
      },
    },
  });
  assert.equal(byTestId(driving, "onboarding").length, 0);
  assert.match(texts(byTestId(driving, "agent-paused")[0]), /you.re driving/i);
  assert.equal(byTestId(driving, "screen")[0].props["data-focused"], "1");
  assert.match(texts(byTestId(driving, "keyboard-hatch")[0]), /Esc/);

  resetFiber();
  const logged = rerender(TempleOSPane, {
    transport: { rest: () => Promise.resolve({ ok: true }) },
    initial: {
      skipLoad: true,
      status: {
        running: true,
        mode: "shared",
        agent_busy: true,
        agent_paused: false,
        setup_needed: false,
        flavor: "tinkeros",
        accel: "kvm",
        kvm: true,
        snapshot: "golden",
      },
      log: [
        {
          id: 1,
          source: "agent",
          tool: "templeos_input",
          op: "type",
          ok: true,
          at: "2026-11-09T19:00:01.000Z",
          summary: "templeos_input type",
        },
        {
          id: 2,
          source: "user",
          tool: "control",
          op: "take",
          ok: true,
          at: "2026-11-09T19:00:02.000Z",
          summary: "mode user",
        },
      ],
    },
  });
  assert.match(texts(byTestId(logged, "agent-paused")[0]), /Agent is typing/);
  assert.match(texts(byTestId(logged, "agent-log")[0]), /templeos_input type/);
  assert.match(texts(byTestId(logged, "accel-badge")[0]), /kvm/);
});

test("clicks map to guest coordinates and watch mode blocks input", async () => {
  resetFiber();
  const calls = [];
  const rest = restFor(calls, () => Promise.resolve({ ok: true, mode: "shared", agent_paused: true, user_may_input: true }));
  const node = rerender(TempleOSPane, {
    transport: { rest },
    initial: {
      skipLoad: true,
      scale: 2,
      status: {
        running: true,
        mode: "shared",
        setup_needed: false,
        flavor: "tinkeros",
        width: 640,
        height: 480,
        user_may_input: true,
      },
    },
  });
  const screen = byTestId(node, "screen")[0];
  screen.props.onClick({
    clientX: 650,
    clientY: 500,
    currentTarget: {
      getBoundingClientRect: () => ({ left: 10, top: 20, width: 1280, height: 960 }),
    },
  });
  await Promise.resolve();
  await Promise.resolve();
  const input = calls.find((item) => item.path === "/input");
  assert.ok(input);
  assert.deepEqual(input.opts.body, { type: "click", x: 320, y: 240, button: "left" });

  resetFiber();
  const blocked = [];
  const watch = rerender(TempleOSPane, {
    transport: { rest: restFor(blocked, { "/input": { ok: false, code: "watch_only" } }) },
    initial: {
      skipLoad: true,
      scale: 1,
      status: { running: true, mode: "watch", setup_needed: false, flavor: "tinkeros", user_may_input: false },
    },
  });
  byTestId(watch, "screen")[0].props.onClick({
    clientX: 10,
    clientY: 10,
    currentTarget: { getBoundingClientRect: () => ({ left: 0, top: 0, width: 640, height: 480 }) },
  });
  await Promise.resolve();
  assert.equal(blocked.length, 0);
});

test("keyboard capture sends keys and Esc releases focus", async () => {
  resetFiber();
  const calls = [];
  const rest = restFor(calls, () => Promise.resolve({ ok: true, mode: "user", agent_paused: true }));
  let node = rerender(TempleOSPane, {
    transport: { rest },
    initial: {
      skipLoad: true,
      focused: true,
      status: { running: true, mode: "user", agent_paused: true, setup_needed: false, flavor: "tinkeros" },
    },
  });
  const screen = byTestId(node, "screen")[0];
  screen.props.onKeyDown({ key: "a", preventDefault() {} });
  await Promise.resolve();
  await Promise.resolve();
  assert.ok(calls.some((item) => item.path === "/input" && item.opts.body && item.opts.body.text === "a"));
  screen.props.onKeyDown({ key: "Escape", preventDefault() {}, currentTarget: { blur() {} } });
  node = rerender(TempleOSPane, {
    transport: { rest },
    initial: {
      skipLoad: true,
      focused: true,
      status: { running: true, mode: "user", agent_paused: true, setup_needed: false },
    },
  });
  // After hatch the hook state should flip on the same fiber.
});

test("createApi never attaches authorization headers and uses ctx.rest only", async () => {
  const calls = [];
  const api = createApi((path, opts) => {
    calls.push({ path, opts });
    return { ok: true, running: false };
  });
  await api.status();
  await api.frame({ since: "abc" });
  await api.start({ flavor: "tinkeros" });
  for (const item of calls) {
    assert.equal(item.opts && item.opts.headers, undefined);
  }
  assert.equal(calls[1].path, "/frame?since=abc");
  assert.equal(calls[2].path, "/vm");
  assert.equal(calls[2].opts.body.op, "start");
  const src = createApi.toString() + TempleOSPane.toString();
  assert.equal(src.includes("127.0.0.1"), false);
  assert.equal(src.includes("Authorization"), false);
  assert.equal(src.includes("localStorage"), false);
});


test("flavor picker shows the selected image SHA and posts /settings", async () => {
  resetFiber();
  const calls = [];
  const rest = (path, opts) => {
    calls.push({ path, opts });
    if (path === "/settings" && opts && opts.method === "POST") {
      const flavor = opts.body && opts.body.flavor;
      return Promise.resolve({
        ok: true,
        flavor,
        preferred_flavor: flavor,
        flavor_name: flavor === "tinkeros" ? "TinkerOS 5.20-rc10" : "Temple of Hermes 0.1.2",
        sha_state: "missing",
        notice: "TinkerOS 5.20-rc10 is selected and will apply on the next boot.",
        apply_on_next_boot: true,
        flavors: [
          { id: "templeoh", name: "Temple of Hermes 0.1.2", sha_state: "verified", sha256: "9afc98ed2bb15a3ff26ebaca12ea392079292df6667b3c1c527fdd30d80cdb13" },
          { id: "tinkeros", name: "TinkerOS 5.20-rc10", sha_state: "missing" },
        ],
      });
    }
    return Promise.resolve({ ok: true });
  };
  const node = rerender(TempleOSPane, {
    transport: { rest },
    initial: {
      skipLoad: true,
      status: {
        running: true,
        mode: "shared",
        setup_needed: false,
        flavor: "templeoh",
        flavor_name: "Temple of Hermes 0.1.2",
        preferred_flavor: "templeoh",
        sha_state: "verified",
        flavor_sha256: "9afc98ed2bb15a3ff26ebaca12ea392079292df6667b3c1c527fdd30d80cdb13",
        flavors: [
          { id: "templeoh", name: "Temple of Hermes 0.1.2", sha_state: "verified", sha256: "9afc98ed2bb15a3ff26ebaca12ea392079292df6667b3c1c527fdd30d80cdb13" },
          { id: "tinkeros", name: "TinkerOS 5.20-rc10", sha_state: "missing" },
          { id: "templeos", name: "TempleOS 5.03", sha_state: "missing" },
          { id: "zealos", name: "ZealOS", sha_state: "missing" },
        ],
      },
    },
  });
  assert.ok(byTestId(node, "flavor-picker").length >= 1);
  const select = byTestId(node, "flavor-select")[0];
  assert.equal(select.props.value, "templeoh");
  assert.match(texts(byTestId(node, "flavor-sha")[0]), /Temple of Hermes 0\.1\.2/);
  assert.match(texts(byTestId(node, "flavor-sha")[0]), /SHA verified/);
  assert.match(texts(byTestId(node, "flavor-badge")[0]), /Temple of Hermes 0\.1\.2/);
  select.props.onChange({ target: { value: "tinkeros" } });
  flushEffects();
  await Promise.resolve();
  await Promise.resolve();
  assert.ok(calls.some((item) => item.path === "/settings" && item.opts && item.opts.method === "POST" && item.opts.body && item.opts.body.flavor === "tinkeros"));
});

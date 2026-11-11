import assert from "node:assert/strict";
import test from "node:test";

import { TempleOSPane } from "../../desktop/src/ui/pane.js";
import { diskImageSummary } from "../../desktop/src/ui/logic.js";
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

function texts(node) {
  const out = [];
  walk(node, (item) => {
    if (item.text) out.push(item.text);
  });
  return out.join(" ");
}

function byTestId(node, id) {
  const out = [];
  walk(node, (item) => {
    if (item.props && item.props["data-testid"] === id) out.push(item);
  });
  return out;
}

function frame(status) {
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
        sha_state: "verified",
        flavors: [
          { id: "templeoh", name: "Temple of Hermes 0.1.3", sha_state: "verified" },
          { id: "tinkeros", name: "TinkerOS 5.20-rc10", sha_state: "missing" },
        ],
        disk_image: {
          enabled: false,
          state: "unpublished",
          verified: false,
          filename: "TempleOfHermes-0.1.3-disk.qcow2",
          text: "Preinstalled disk off (not published)",
        },
        ...(status || {}),
      },
    },
  });
}

test("disk summary labels unpublished, path set and verified", () => {
  assert.equal(diskImageSummary({ disk_image: { enabled: true, state: "not_downloaded" } }).label, "downloads on next start");
  assert.equal(diskImageSummary({ disk_image: { enabled: true, state: "download_failed" } }).label, "download failed, using live ISO");
  assert.equal(diskImageSummary({ disk_image: { enabled: false, state: "unpublished" } }).label, "not published");
  assert.match(
    diskImageSummary({ disk_image: { enabled: true, state: "missing" } }).text,
    /path set/i
  );
  const verified = diskImageSummary({ disk_image: { enabled: true, state: "ok", verified: true } });
  assert.equal(verified.verified, true);
  assert.match(verified.text, /verified/i);
});

test("Temple of Hermes picker shows a disk toggle and status line", () => {
  const node = frame();
  assert.equal(byTestId(node, "disk-image-option").length, 1);
  const toggle = byTestId(node, "disk-image-toggle")[0];
  assert.equal(toggle.props.type, "checkbox");
  assert.equal(toggle.props.checked, false);
  const status = byTestId(node, "disk-image-status")[0];
  assert.match(texts(status), /not published/i);
  assert.equal(status.props["data-state"], "unpublished");
});

test("toggling the disk option posts /settings with disk_image", async () => {
  resetFiber();
  const calls = [];
  const rest = (path, opts) => {
    calls.push({ path, opts });
    return Promise.resolve({
      ok: true,
      disk_image: {
        enabled: true,
        state: "unpublished",
        verified: false,
        text: "Preinstalled disk: not published",
      },
    });
  };
  const node = rerender(TempleOSPane, {
    transport: { rest },
    initial: {
      skipLoad: true,
      status: {
        running: false,
        mode: "shared",
        setup_needed: false,
        flavor: "templeoh",
        flavor_name: "Temple of Hermes 0.1.3",
        preferred_flavor: "templeoh",
        flavors: [{ id: "templeoh", name: "Temple of Hermes 0.1.3" }],
        disk_image: { enabled: false, state: "unpublished", verified: false },
      },
    },
  });
  byTestId(node, "disk-image-toggle")[0].props.onChange({ target: { checked: true } });
  await Promise.resolve();
  await Promise.resolve();
  const posted = calls.find(
    (item) => item.path === "/settings" && item.opts && item.opts.method === "POST"
  );
  assert.ok(posted);
  assert.equal(posted.opts.body.disk_image, "on");
  assert.equal(posted.opts.headers, undefined);
});

test("disk toggle stays hidden for non-Temple-of-Hermes flavors", () => {
  const node = frame({
    flavor: "tinkeros",
    flavor_name: "TinkerOS 5.20-rc10",
    preferred_flavor: "tinkeros",
  });
  assert.equal(byTestId(node, "disk-image-option").length, 0);
});

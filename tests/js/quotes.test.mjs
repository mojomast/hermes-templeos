import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

import {
  createQuotePicker,
  loadQuotes,
  normalizeQuote,
  pickQuote,
  quoteKindForBoot,
  quoteKindForLogEvent,
} from "../../desktop/src/ui/quotes.js";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const PRODUCTION = JSON.parse(readFileSync(path.join(ROOT, "desktop", "terry-quotes.json"), "utf8"));
const FIXTURE = JSON.parse(
  readFileSync(path.join(ROOT, "tests", "fixtures", "terry-quotes-test.json"), "utf8")
);

test("production quotes match the schema and every entry is sourced", () => {
  assert.ok(Array.isArray(PRODUCTION));
  assert.equal(PRODUCTION.length, 69);
  for (const entry of PRODUCTION) {
    assert.ok(entry && typeof entry === "object" && !Array.isArray(entry));
    assert.equal(typeof entry.text, "string");
    assert.ok(entry.text.trim().length > 0);
    assert.equal(typeof entry.source_title, "string");
    assert.ok(entry.source_title.trim().length > 0);
    assert.equal(typeof entry.source_url, "string");
    assert.ok(entry.source_url.trim().length > 0);
    assert.match(entry.source_url, /^https?:\/\//);
    if (entry.date != null) assert.equal(typeof entry.date, "string");
    assert.notEqual(normalizeQuote(entry), null);
  }
  assert.ok(Array.isArray(FIXTURE));
  assert.equal(FIXTURE.length, 1);
  assert.equal(FIXTURE[0].text, "TEST_FIXTURE_ONLY");
  assert.equal(FIXTURE[0].source_title, "test fixture");
  assert.match(FIXTURE[0].source_url, /^https:\/\/example\.invalid\//);
});

test("schema loader ignores malformed entries", () => {
  assert.equal(normalizeQuote(null), null);
  assert.equal(normalizeQuote("quote"), null);
  assert.equal(normalizeQuote({ text: "x", source_title: "y" }), null);
  assert.equal(normalizeQuote({ text: "x", source_title: "y", source_url: "z", date: 7 }), null);
  const loaded = loadQuotes([
    null,
    { text: 42, source_title: "t", source_url: "u" },
    { text: "ok", source_title: "t", source_url: "u", date: "2020-01-01" },
    { text: "no url", source_title: "t" },
    "string",
  ]);
  assert.equal(loaded.length, 1);
  assert.equal(loaded[0].text, "ok");
  assert.equal(loaded[0].date, "2020-01-01");
  assert.deepEqual(loadQuotes({ nope: true }), []);
});

test("approved text is preserved verbatim for the wrapping bubble", () => {
  const long = "Long approved sentence with spaces. ".repeat(20).trim();
  const quote = normalizeQuote({ text: long, source_title: "t", source_url: "https://example.invalid/x" });
  assert.equal(quote.text, long);
  assert.equal(quote.date, undefined);
});

test("empty list keeps Terry silent: picker returns null and says nothing", () => {
  assert.equal(pickQuote([], { random: () => 0 }), null);
  const picker = createQuotePicker([]);
  assert.equal(picker.size, 0);
  assert.equal(picker.pick("idle"), null);
  const said = [];
  assert.equal(picker.say((text) => said.push(text), "boot"), null);
  assert.deepEqual(said, []);
  assert.equal(picker.startIdle((text) => said.push(text)), null);
  picker.stopIdle();
});

test("fixture list returns exactly the fixture quote", () => {
  const picker = createQuotePicker(FIXTURE);
  assert.equal(picker.size, 1);
  const quote = picker.pick("boot");
  assert.equal(quote.text, "TEST_FIXTURE_ONLY");
  assert.equal(quote.source_title, "test fixture");
  assert.equal(quote.kind, "boot");
  const said = [];
  const returned = picker.say((text, opts) => said.push({ text, opts }), "tool_success");
  assert.equal(returned.text, "TEST_FIXTURE_ONLY");
  assert.equal(said.length, 1);
  assert.equal(said[0].text, "TEST_FIXTURE_ONLY");
  assert.equal(said[0].opts.kind, "tool_success");
  assert.equal(said[0].opts.quote.source_url, FIXTURE[0].source_url);
});

test("mute suppresses quote bubbles without hiding Terry", () => {
  const picker = createQuotePicker(FIXTURE);
  const said = [];
  picker.setMuted(true);
  assert.equal(picker.isMuted(), true);
  assert.equal(picker.pick("idle"), null);
  assert.equal(picker.say((text) => said.push(text), "boot"), null);
  assert.deepEqual(said, []);
  assert.equal(picker.startIdle((text) => said.push(text), { setIntervalFn: () => 1 }), null);
  picker.setMuted(false);
  assert.equal(picker.pick("idle").text, "TEST_FIXTURE_ONLY");
  assert.equal(picker.toggleMuted(), true);
});

test("idle timers and event hooks both use the picker", () => {
  const picker = createQuotePicker(FIXTURE, { random: () => 0 });
  const kinds = [];
  let intervalFn = null;
  let cleared = null;
  const handle = picker.startIdle(
    (text, opts) => kinds.push(opts.kind),
    {
      intervalMs: 1000,
      setIntervalFn: (fn, ms) => {
        intervalFn = fn;
        assert.equal(ms, 1000);
        return "timer-1";
      },
      clearIntervalFn: (id) => {
        cleared = id;
      },
    }
  );
  assert.equal(handle, "timer-1");
  assert.equal(typeof intervalFn, "function");
  intervalFn();
  picker.say((text, opts) => kinds.push(opts.kind), "boot");
  picker.say((text, opts) => kinds.push(opts.kind), "tool_success");
  assert.deepEqual(kinds, ["idle", "boot", "tool_success"]);
  picker.stopIdle();
  assert.equal(cleared, "timer-1");
});

test("boot and successful tool events map to picker kinds", () => {
  assert.equal(quoteKindForBoot(false, true), "boot");
  assert.equal(quoteKindForBoot(true, true), null);
  assert.equal(quoteKindForBoot(false, false), null);
  assert.equal(quoteKindForLogEvent({ source: "agent", tool: "templeos_vm", ok: true }), "tool_success");
  assert.equal(quoteKindForLogEvent({ source: "agent", tool: "templeos_vm", ok: false }), null);
  assert.equal(quoteKindForLogEvent({ source: "user", tool: "templeos_input", ok: true }), null);
  assert.equal(quoteKindForLogEvent(null), null);
});

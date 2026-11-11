import assert from "node:assert/strict";
import { readFileSync, writeFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const CSS = readFileSync(path.join(ROOT, "desktop", "src", "ui", "styles.css"), "utf8");
const QUOTES = JSON.parse(readFileSync(path.join(ROOT, "desktop", "terry-quotes.json"), "utf8"));
const QUOTE_INDEXES = [1, 4, 33, 55, 58, 63, 64];

function findChrome() {
  if (process.env.CHROME) return process.env.CHROME;
  for (const name of ["google-chrome", "chromium", "chromium-browser"]) {
    const probe = spawnSync("which", [name], { encoding: "utf8" });
    if (probe.status === 0) return name;
  }
  return null;
}

function escapeText(value) {
  return String(value).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function page(width, height, dockWidth, dockHeight) {
  const cases = QUOTE_INDEXES.map((index) => {
    const quote = QUOTES[index - 1];
    return `<div class="case"><div class="tos-companion-dock" style="position:relative;width:${dockWidth}px;height:${dockHeight}px"><div class="tos-companion-bubble" data-quote="${index}">${escapeText(quote.text)}</div></div></div>`;
  }).join("\n");
  return `<!doctype html>
<html><head><meta charset="utf-8"><style>
html,body{margin:0;background:#000}
${CSS}
.case{margin:0 0 8px}
</style></head>
<body><div class="tos-pane" data-theme="hermes">${cases}</div>
<script>
window.addEventListener("load", function () {
  var out = [];
  document.querySelectorAll(".case").forEach(function (item) {
    var dock = item.querySelector(".tos-companion-dock");
    var bubble = item.querySelector(".tos-companion-bubble");
    var d = dock.getBoundingClientRect();
    var b = bubble.getBoundingClientRect();
    out.push({
      quote: Number(bubble.getAttribute("data-quote")),
      dock: { x: d.x, y: d.y, width: d.width, height: d.height, right: d.right, bottom: d.bottom },
      bubble: { x: b.x, y: b.y, width: b.width, height: b.height, right: b.right, bottom: b.bottom },
      scrollHeight: bubble.scrollHeight,
      clientHeight: bubble.clientHeight,
      overflowY: getComputedStyle(bubble).overflowY
    });
  });
  var pre = document.createElement("pre");
  pre.id = "__bubble_rects";
  pre.textContent = JSON.stringify(out);
  pre.style.position = "fixed";
  pre.style.left = "-9999px";
  document.body.appendChild(pre);
});
</script></body></html>`;
}

function measure(chrome, width, height, dockWidth, dockHeight) {
  const file = path.join("/tmp", `bubble-${width}.html`);
  writeFileSync(file, page(width, height, dockWidth, dockHeight));
  const result = spawnSync(
    chrome,
    [
      "--headless=new",
      "--no-sandbox",
      "--disable-gpu",
      "--disable-dev-shm-usage",
      "--hide-scrollbars",
      "--virtual-time-budget=1500",
      `--window-size=${width},${height}`,
      "--dump-dom",
      `file://${file}`,
    ],
    { encoding: "utf8", timeout: 20000, maxBuffer: 16 * 1024 * 1024 }
  );
  const match = result.status === 0 && result.stdout && result.stdout.match(/<pre id="__bubble_rects"[^>]*>([\s\S]*?)<\/pre>/);
  if (!match) return null;
  return JSON.parse(match[1]);
}

const chrome = findChrome();

test("longest production quotes never clip inside Terry's column", { skip: !chrome && "chromium not available" }, () => {
  const cases = [
    { width: 1920, height: 1300, dockWidth: 520, dockHeight: 1088 },
    { width: 1280, height: 1000, dockWidth: 427, dockHeight: 611 },
    { width: 780, height: 1000, dockWidth: 180, dockHeight: 690 },
    { width: 560, height: 1000, dockWidth: 100, dockHeight: 690 },
  ];
  for (const item of cases) {
    const rows = measure(chrome, item.width, item.height, item.dockWidth, item.dockHeight);
    assert.ok(rows && rows.length === QUOTE_INDEXES.length, "measured " + item.width);
    for (const row of rows) {
      const label = `${item.width}px quote #${row.quote}`;
      assert.ok(row.bubble.x >= row.dock.x - 1, label + " bubble left inside column");
      assert.ok(row.bubble.y >= row.dock.y - 1, label + " bubble top inside column");
      assert.ok(row.bubble.right <= row.dock.right + 1, label + " bubble right inside column");
      assert.ok(row.bubble.bottom <= row.dock.bottom + 1, label + " bubble bottom inside column");
      const fullyVisible = row.scrollHeight <= row.clientHeight + 1;
      const scrolls = row.overflowY === "auto" || row.overflowY === "scroll";
      assert.ok(fullyVisible || scrolls, label + " text must fit or scroll");
    }
  }
});

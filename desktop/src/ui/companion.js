/** Terry companion atlas + v2 clip overlay for the TempleOS pane.
 *
 * Fan tribute to Terry A. Davis — not affiliated with TempleOS or his estate.
 * Loads the nine-row atlas and on-demand clip strips through ctx.rest.
 * Hide / costume preferences persist through the plugin backend (plugin data dir).
 *
 * Speech bubbles: call TerryCompanion.say(text) (also POST /companion {say})
 * to render a bubble to the left/above of Terry. Text is supplied by the
 * caller; nothing is invented.
 */

import { useEffect, useRef, useState } from "react";
import { jsx, jsxs } from "react/jsx-runtime";
import { blobUrlFromBase64, revokeUrl } from "./api.js";

const RICH_CLIPS = {
  vm_booting: true,
  celebrate_short: true,
  greet: true,
  nod: true,
  stretch: true,
  relieved: true,
  typing: true,
  talking: true,
  smoking: true,
  exhaling: true,
  dance: true,
};

const IDLE_VARIETY = ["stretch", "smoking", "exhaling"];
const LONG_IDLE_MS = 22000;
const IDLE_RETRY_MS = 14000;
const IDLE_CHANCE = 0.4;
const TRIPLE_MS = 650;
// atlas.png is 8x9 cells and .tos-companion-static draws it at 800% x 900%,
// so one cell fills the box. A row is then a percentage of the surplus
// height: row 0 = 0%, row 8 = 100%.
const ROWS = 9;

function rowFor(atlas, name) {
  const rows = (atlas && atlas.rows) || [];
  for (let i = 0; i < rows.length; i += 1) {
    if (rows[i] && rows[i].name === name) return rows[i];
  }
  return rows[0] || null;
}

function clipFrames(clip) {
  if (!clip) return [];
  if (clip.frames && clip.frames.length) return clip.frames;
  const count = Number(clip.count) || 0;
  const cell = clip.cell || [192, 208];
  const w = cell[0] || 192;
  const h = cell[1] || 208;
  const frames = [];
  for (let i = 0; i < count; i += 1) frames.push({ x: i * w, y: 0, w: w, h: h });
  return frames;
}

/** Public hook used by the pane and by other UI. Wired when the overlay mounts. */
export const TerryCompanion = {
  say(text, opts) {
    const impl = TerryCompanion._say;
    if (typeof impl === "function") return impl(text, opts);
    return Promise.reject(new Error("Terry companion is not mounted."));
  },
  _say: null,
};

/** Canvas sprite that plays atlas rows or v2 clip strips via requestAnimationFrame. */
export function TerryCompanionOverlay({ api, animation, costume, hidden, enabled, speech, sprite, spriteRow }) {
  const canvasRef = useRef(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");
  const [bubble, setBubble] = useState((speech && speech.text) || "");
  const packRef = useRef(null);
  const clipsRef = useRef(new Map());
  const animRef = useRef(animation || "idle");
  const localRef = useRef({ name: "", until: 0, follow: "" });
  const idleAtRef = useRef(0);
  const rafRef = useRef(0);
  const startRef = useRef(0);
  const lastNameRef = useRef("");
  const clicksRef = useRef([]);

  const hostAnim = animation || "idle";

  useEffect(() => {
    const text = speech && speech.active !== false ? String((speech && speech.text) || "") : "";
    setBubble(text);
  }, [speech && speech.text, speech && speech.active]);

  useEffect(() => {
    TerryCompanion._say = (text, opts) => {
      const raw = String(text || "").trim();
      setBubble(raw);
      if (typeof api.companionSay === "function") {
        return Promise.resolve(api.companionSay({ say: raw, hold_s: opts && opts.hold_s })).catch(() => {});
      }
      return Promise.resolve();
    };
    return () => {
      if (TerryCompanion._say) TerryCompanion._say = null;
    };
  }, [api]);

  useEffect(() => {
    if (hidden || enabled === false) {
      setReady(false);
      return undefined;
    }
    let cancelled = false;
    const chosen = costume || "base";
    Promise.resolve(api.companionAtlas({ costume: chosen }))
      .then((body) => {
        if (cancelled) return;
        if (!body || body.ok === false || !body.data || !body.atlas) {
          setError((body && body.error) || "Could not load Terry atlas.");
          setReady(false);
          return;
        }
        const url = blobUrlFromBase64(body.data, body.mime || "image/png");
        const image = new Image();
        image.onload = () => {
          if (cancelled) {
            revokeUrl(url);
            return;
          }
          const prev = packRef.current;
          if (prev && prev.url) revokeUrl(prev.url);
          packRef.current = { url, image, atlas: body.atlas, costume: body.costume || chosen };
          setError("");
          setReady(true);
        };
        image.onerror = () => {
          revokeUrl(url);
          if (!cancelled) {
            setError("Terry atlas image failed to decode.");
            setReady(false);
          }
        };
        image.src = url;
      })
      .catch((err) => {
        if (!cancelled) {
          setError((err && err.message) || "Terry atlas request failed.");
          setReady(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [api, costume, hidden, enabled]);

  useEffect(() => {
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      const prev = packRef.current;
      if (prev && prev.url) revokeUrl(prev.url);
      packRef.current = null;
      clipsRef.current.forEach((entry) => {
        if (entry && entry.url) revokeUrl(entry.url);
      });
      clipsRef.current = new Map();
    };
  }, []);

  function ensureClip(name) {
    if (!RICH_CLIPS[name]) return Promise.resolve(null);
    const cached = clipsRef.current.get(name);
    if (cached && cached.image) return Promise.resolve(cached);
    if (cached && cached.pending) return cached.pending;
    const pending = Promise.resolve(api.companionClip({ name }))
      .then((body) => {
        if (!body || body.ok === false || !body.data || !body.clip) {
          clipsRef.current.delete(name);
          return null;
        }
        return new Promise((resolve) => {
          const url = blobUrlFromBase64(body.data, body.mime || "image/png");
          const image = new Image();
          image.onload = () => {
            const entry = { url, image, clip: body.clip, name };
            clipsRef.current.set(name, entry);
            resolve(entry);
          };
          image.onerror = () => {
            revokeUrl(url);
            clipsRef.current.delete(name);
            resolve(null);
          };
          image.src = url;
        });
      })
      .catch(() => {
        clipsRef.current.delete(name);
        return null;
      });
    clipsRef.current.set(name, { pending });
    return pending;
  }

  function playLocal(name, durationMs, follow) {
    localRef.current = {
      name: name,
      until: performance.now() + Math.max(200, Number(durationMs) || 1500),
      follow: follow || "",
    };
    startRef.current = performance.now();
    lastNameRef.current = name;
    ensureClip(name);
  }

  function onTerryClick() {
    const now = Date.now();
    const clicks = clicksRef.current.filter((t) => now - t <= TRIPLE_MS);
    clicks.push(now);
    clicksRef.current = clicks;
    if (clicks.length >= 3) {
      clicksRef.current = [];
      playLocal("dance", 7200, "");
    }
  }

  useEffect(() => {
    if (!ready || hidden || enabled === false) {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      rafRef.current = 0;
      return undefined;
    }
    const canvas = canvasRef.current;
    if (!canvas) return undefined;
    const ctx = canvas.getContext("2d");
    if (!ctx) return undefined;
    startRef.current = performance.now();
    lastNameRef.current = "";
    idleAtRef.current = performance.now();

    const tick = (now) => {
      const local = localRef.current;
      if (local.name && now >= local.until) {
        const follow = local.follow;
        localRef.current = { name: "", until: 0, follow: "" };
        if (follow) {
          const nextDur = follow === "exhaling" ? 3200 : 1500;
          playLocal(follow, nextDur, "");
        }
      }
      const busyHost = hostAnim !== "idle";
      if (busyHost && localRef.current.name && localRef.current.name !== "dance") {
        localRef.current = { name: "", until: 0, follow: "" };
      }
      // Dance yields if a real host state takes over (tool, error, boot…).
      if (busyHost && localRef.current.name === "dance" && hostAnim !== "idle") {
        localRef.current = { name: "", until: 0, follow: "" };
      }

      let name = (localRef.current.name && now < localRef.current.until && localRef.current.name) || hostAnim || "idle";
      animRef.current = name;

      if (name === "idle") {
        if (!idleAtRef.current) idleAtRef.current = now;
        if (now - idleAtRef.current >= LONG_IDLE_MS && !localRef.current.name) {
          idleAtRef.current = now + IDLE_RETRY_MS;
          if (Math.random() < IDLE_CHANCE) {
            const pick = IDLE_VARIETY[Math.floor(Math.random() * IDLE_VARIETY.length)];
            const dur = pick === "stretch" ? 3400 : pick === "smoking" ? 5600 : 3200;
            const follow = pick === "smoking" && Math.random() < 0.55 ? "exhaling" : "";
            playLocal(pick, dur, follow);
            name = pick;
            animRef.current = name;
          }
        }
      } else if (!localRef.current.name) {
        idleAtRef.current = now;
      }

      if (name !== lastNameRef.current) {
        startRef.current = now;
        lastNameRef.current = name;
        if (RICH_CLIPS[name]) ensureClip(name);
      }

      const pack = packRef.current;
      const clipEntry = clipsRef.current.get(name);
      let image = null;
      let frames = [];
      let frameMs = 183;
      let loop = true;
      if (clipEntry && clipEntry.image && clipEntry.clip) {
        image = clipEntry.image;
        frames = clipFrames(clipEntry.clip);
        frameMs = Number(clipEntry.clip.frame_ms) || 50;
        loop = clipEntry.clip.loop !== false;
      } else if (pack && pack.image && pack.atlas) {
        const row = rowFor(pack.atlas, name);
        image = pack.image;
        frames = (row && row.frames) || [];
        frameMs = (row && Number(row.frame_ms)) || Number(pack.atlas.loop_ms) / Math.max(1, frames.length) || 183;
        loop = true;
      }

      const cw = 192;
      const ch = 208;
      if (canvas.width !== cw) canvas.width = cw;
      if (canvas.height !== ch) canvas.height = ch;
      ctx.clearRect(0, 0, cw, ch);
      if (image && frames.length) {
        const elapsed = Math.max(0, now - startRef.current);
        let index;
        if (loop) index = Math.floor(elapsed / frameMs) % frames.length;
        else index = Math.min(frames.length - 1, Math.floor(elapsed / frameMs));
        const frame = frames[index];
        ctx.drawImage(image, frame.x, frame.y, frame.w, frame.h, 0, 0, cw, ch);
      }
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      rafRef.current = 0;
    };
  }, [ready, hidden, enabled, hostAnim, api]);

  if (enabled === false) return null;
  if (hidden) return null;

  const staticSheet = typeof sprite === "string" && sprite ? sprite : "";
  const row = Math.max(0, Math.min(ROWS - 1, Number(spriteRow) || 0));
  const rowPct = (row / (ROWS - 1)) * 100;
  const spriteStyle = staticSheet
    ? {
        backgroundImage: `url("${staticSheet}")`,
        backgroundPosition: `0 ${rowPct}%`,
      }
    : undefined;

  return jsxs("aside", {
    className: "tos-companion-dock",
    "data-testid": "companion-dock",
    "data-animation": animRef.current || hostAnim || "idle",
    "aria-label": "Terry companion",
    children: [
      bubble
        ? jsx("div", {
            className: "tos-companion-bubble",
            "data-testid": "companion-bubble",
            children: bubble,
          })
        : jsx("div", { className: "tos-companion-bubble-slot", "aria-hidden": "true" }),
      jsxs("div", {
        className: "tos-companion" + (staticSheet ? " tos-companion-static" : ""),
        "data-testid": "companion",
        "data-animation": hostAnim || "idle",
        "data-costume": costume || "base",
        title: "Terry companion — fan tribute to Terry A. Davis. Triple-click to dance.",
        style: spriteStyle,
        onClick: onTerryClick,
        children: staticSheet
          ? null
          : ready
            ? jsx("canvas", {
                ref: canvasRef,
                className: "tos-companion-canvas",
                width: 192,
                height: 208,
                "aria-hidden": "true",
              })
            : jsx("div", {
                className: "tos-companion-loading",
                "data-testid": "companion-loading",
                children: error || "…",
              }),
      }),
    ],
  });
}

export function CompanionControls({ hidden, onToggleHidden, costume, onCostume, costumes, enabled }) {
  if (enabled === false) return null;
  const options = costumes && costumes.length ? costumes : ["base", "cowboy", "wizard", "chef"];
  return jsxs("div", {
    className: "tos-companion-controls",
    "data-testid": "companion-controls",
    children: [
      jsx("button", {
        type: "button",
        className: "tos-btn tos-companion-hide",
        "data-testid": "companion-hide",
        "aria-pressed": hidden ? "true" : "false",
        title: hidden ? "Show Terry companion" : "Hide Terry companion",
        onClick: onToggleHidden,
        children: hidden ? "Show Terry" : "Hide Terry",
      }),
      jsxs("label", {
        className: "tos-companion-costume",
        children: [
          jsx("span", { className: "tos-sr-only", children: "Costume" }),
          jsxs("select", {
            "data-testid": "companion-costume",
            value: costume || "base",
            onChange: (event) => onCostume && onCostume(event.target.value),
            children: options.map((name) => jsx("option", { value: name, children: name }, name)),
          }),
        ],
      }),
    ],
  });
}

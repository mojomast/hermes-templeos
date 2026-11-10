/** Terry companion v4 high-resolution rig for the TempleOS pane.
 *
 * Fan tribute to Terry A. Davis — not affiliated with TempleOS or his estate.
 * Loads the trimmed 3.5x part bundle and baked clips through ctx.rest, then
 * renders the rig with a smooth, devicePixelRatio-aware canvas. No 192x208
 * atlas is upscaled here.
 *
 * Speech bubbles: call TerryCompanion.say(text) (also POST /companion {say})
 * to render a bubble to the left/above of Terry. Text is supplied by the
 * caller; nothing is invented.
 */

import { useEffect, useRef, useState } from "react";
import { jsx, jsxs } from "react/jsx-runtime";
import { renderScene, sampleClip, speechPlate } from "./terry_v4.js";

const CLIP_NAMES = new Set([
  "idle",
  "typing",
  "talking",
  "vm_booting",
  "celebrate_short",
  "failed",
  "greet",
  "dance",
  "smoking",
  "exhaling",
  "waiting",
  "review",
  "nod",
  "relieved",
  "stretch",
]);

const HOST_MAP = {
  waving: "greet",
  greet: "greet",
  jumping: "celebrate_short",
};

const IDLE_VARIETY = ["stretch", "smoking", "exhaling"];
const LONG_IDLE_MS = 22000;
const IDLE_RETRY_MS = 14000;
const IDLE_CHANCE = 0.4;
const DANCE_CHANCE = 0.04;
const TRIPLE_MS = 650;
const GREET_MS = 2400;

/** Public hook used by the pane and by other UI. Wired when the overlay mounts. */
export const TerryCompanion = {
  say(text, opts) {
    const impl = TerryCompanion._say;
    if (typeof impl === "function") return impl(text, opts);
    return Promise.reject(new Error("Terry companion is not mounted."));
  },
  _say: null,
};

function hostClip(name) {
  return HOST_MAP[name] || name || "idle";
}

/** Canvas rig that plays baked v4 clips via requestAnimationFrame. */
export function TerryCompanionOverlay({ api, animation, costume, hidden, enabled, speech }) {
  const canvasRef = useRef(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");
  const [bubble, setBubble] = useState((speech && speech.text) || "");
  const bundleRef = useRef(null);
  const clipsRef = useRef(new Map());
  const animRef = useRef(animation || "idle");
  const localRef = useRef({ name: "", until: 0, follow: "" });
  const idleAtRef = useRef(0);
  const greetedRef = useRef(false);
  const rafRef = useRef(0);
  const startRef = useRef(0);
  const lastNameRef = useRef("");
  const clicksRef = useRef([]);
  const bubbleRef = useRef(bubble);

  const hostAnim = animation || "idle";
  bubbleRef.current = bubble;

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

  function ensureClip(name) {
    const token = hostClip(name);
    if (!CLIP_NAMES.has(token)) return Promise.resolve(null);
    const cached = clipsRef.current.get(token);
    if (cached && cached.clip) return Promise.resolve(cached.clip);
    if (cached && cached.pending) return cached.pending;
    if (typeof api.companionClip !== "function") return Promise.resolve(null);
    const pending = Promise.resolve(api.companionClip({ name: "v4:" + token }))
      .then((body) => {
        if (!body || body.ok === false || !body.clip) {
          clipsRef.current.delete(token);
          return null;
        }
        const entry = { clip: body.clip, name: token };
        clipsRef.current.set(token, entry);
        return entry.clip;
      })
      .catch(() => {
        clipsRef.current.delete(token);
        return null;
      });
    clipsRef.current.set(token, { pending });
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
    if (hidden || enabled === false) {
      setReady(false);
      return undefined;
    }
    if (bundleRef.current) {
      setReady(true);
      return undefined;
    }
    if (typeof api.companionClip !== "function") {
      setError("Terry v4 is not available in this host.");
      setReady(false);
      return undefined;
    }
    let cancelled = false;
    Promise.resolve(api.companionClip({ name: "v4:bundle" }))
      .then((body) => {
        if (cancelled) return null;
        if (!body || body.ok === false || !body.registry) {
          setError((body && body.error) || "Could not load the Terry v4 rig.");
          setReady(false);
          return null;
        }
        const images = new Map();
        const entries = Object.entries(body.parts || {});
        return Promise.all(
          entries.map(
            ([path, data]) =>
              new Promise((resolve) => {
                if (typeof Image === "undefined") {
                  resolve();
                  return;
                }
                const image = new Image();
                image.onload = () => {
                  images.set(path, image);
                  resolve();
                };
                image.onerror = () => resolve();
                image.src = "data:image/png;base64," + data;
              })
          )
        ).then(() => {
          if (cancelled) return;
          bundleRef.current = {
            registry: body.registry,
            speech: body.speech || { events: [], duration_ms: 2600 },
            smoke: body.smoke || {},
            costumes: body.costumes || {},
            images,
          };
          setError("");
          setReady(true);
          ensureClip("idle");
          ensureClip(hostClip(hostAnim));
        });
      })
      .catch((err) => {
        if (!cancelled) {
          setError((err && err.message) || "Terry v4 request failed.");
          setReady(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [api, hidden, enabled]);

  useEffect(() => {
    if (ready) ensureClip(hostClip(hostAnim));
  }, [ready, hostAnim]);

  useEffect(() => {
    if (!ready || hidden || enabled === false) return undefined;
    if (!greetedRef.current && hostClip(hostAnim) === "idle") {
      greetedRef.current = true;
      playLocal("greet", GREET_MS, "");
    }
    return undefined;
  }, [ready, hostAnim, hidden, enabled]);

  useEffect(() => {
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      rafRef.current = 0;
    };
  }, []);

  useEffect(() => {
    if (!ready || hidden || enabled === false) {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      rafRef.current = 0;
      return undefined;
    }
    const canvas = canvasRef.current;
    if (!canvas) return undefined;
    startRef.current = performance.now();
    lastNameRef.current = "";
    idleAtRef.current = performance.now();

    const tick = (now) => {
      const bundle = bundleRef.current;
      if (!bundle) {
        rafRef.current = requestAnimationFrame(tick);
        return;
      }
      const local = localRef.current;
      if (local.name && now >= local.until) {
        const follow = local.follow;
        localRef.current = { name: "", until: 0, follow: "" };
        if (follow) playLocal(follow, follow === "exhaling" ? 3200 : 1500, "");
      }
      const busyHost = hostAnim !== "idle";
      if (busyHost && localRef.current.name && localRef.current.name !== "dance") {
        localRef.current = { name: "", until: 0, follow: "" };
      }
      if (busyHost && localRef.current.name === "dance" && hostAnim !== "idle") {
        localRef.current = { name: "", until: 0, follow: "" };
      }

      let name =
        (localRef.current.name && now < localRef.current.until && localRef.current.name) ||
        hostClip(hostAnim) ||
        "idle";
      // A live bubble speaks with the discrete whole-head plates.
      if (bubbleRef.current) name = "talking";

      if (name === "idle" && !localRef.current.name) {
        if (!idleAtRef.current) idleAtRef.current = now;
        if (now - idleAtRef.current >= LONG_IDLE_MS) {
          idleAtRef.current = now + IDLE_RETRY_MS;
          const roll = Math.random();
          if (roll < DANCE_CHANCE) {
            playLocal("dance", 7200, "");
            name = "dance";
          } else if (roll < DANCE_CHANCE + IDLE_CHANCE) {
            const pick = IDLE_VARIETY[Math.floor(Math.random() * IDLE_VARIETY.length)];
            const dur = pick === "stretch" ? 3400 : pick === "smoking" ? 5600 : 3200;
            const follow = pick === "smoking" && Math.random() < 0.55 ? "exhaling" : "";
            playLocal(pick, dur, follow);
            name = pick;
          }
        }
      } else if (!localRef.current.name) {
        idleAtRef.current = now;
      }

      if (name !== lastNameRef.current) {
        startRef.current = now;
        lastNameRef.current = name;
        ensureClip(name);
      }
      animRef.current = name;

      let clip = clipsRef.current.get(name) && clipsRef.current.get(name).clip;
      if (!clip) clip = clipsRef.current.get("idle") && clipsRef.current.get("idle").clip;
      if (clip) {
        const elapsed = Math.max(0, now - startRef.current);
        const frame = sampleClip(clip, elapsed);
        if (frame) {
          if (name === "talking") {
            const duration = Number(bundle.speech.duration_ms) || 2600;
            frame.variants.head_base = speechPlate(
              bundle.speech.events,
              elapsed % duration,
              frame.variants.head_base
            );
          }
          renderScene(canvas, bundle, bundle.images, frame, costume || "base", { time: elapsed, smoke: true });
        }
      }
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      rafRef.current = 0;
    };
  }, [ready, hidden, enabled, hostAnim, costume]);

  if (enabled === false) return null;
  if (hidden) return null;

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
        className: "tos-companion",
        "data-testid": "companion",
        "data-animation": hostAnim || "idle",
        "data-costume": costume || "base",
        title: "Terry companion — fan tribute to Terry A. Davis. Triple-click to dance.",
        onClick: onTerryClick,
        children: [
          jsx("canvas", {
            ref: canvasRef,
            className: "tos-companion-canvas",
            "data-companion-v4": "1",
            "data-animation": hostAnim || "idle",
            "data-costume": costume || "base",
            width: 192,
            height: 208,
            "aria-hidden": "true",
          }),
          error
            ? jsx("div", {
                className: "tos-companion-loading",
                "data-testid": "companion-loading",
                children: error,
              })
            : null,
        ],
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

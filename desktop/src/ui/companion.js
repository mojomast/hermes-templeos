/** Terry companion: HD VP9 video loops with the v4 canvas rig as fallback.
 *
 * An original fan tribute with no official TempleOS affiliation.
 * The six transparent 720x1080 VP9 loops live in
 * desktop/assets/companion/terry/v5 and are served through ctx.rest as
 * base64 envelopes, then played from blob URLs. The canvas rig in
 * terry_v4.js stays available for players without VP9 alpha.
 *
 * Speech bubbles: call TerryCompanion.say(text) (also POST /companion {say})
 * to render a bubble to the left/above of Terry. Text is supplied by the
 * caller; nothing is invented.
 */

import { useEffect, useRef, useState } from "react";
import { jsx, jsxs } from "react/jsx-runtime";
import { blobUrlFromBase64, revokeUrl } from "./api.js";
import { renderScene, sampleClip, speechPlate } from "./terry_v4.js";

/** The six in-tree v5 loops. */
export const VIDEO_CLIPS = Object.freeze(["idle", "smoking", "speaking", "typing", "walk", "wave"]);

/** v5/clips.json state map, expressed as logical state -> clip name. */
export const STATE_CLIP = Object.freeze({
  idle: "idle",
  idle_variant: "smoking",
  typing: "typing",
  speaking: "speaking",
  boot: "wave",
  greet: "wave",
  tool_success: "wave",
  first_appear: "walk",
});

const WAVE_ANIMATIONS = new Set(["greet", "waving", "celebrate_short", "vm_booting", "tool_success", "boot"]);
const TYPING_ANIMATIONS = new Set(["typing"]);
const WALK_ANIMATIONS = new Set(["walk", "first_appear"]);

export function clipForState(state) {
  return STATE_CLIP[state] || "idle";
}

/** Resolve the high-level Terry state from the host animation and pane signals. */
export function resolveTerryState({ animation, bubble, agentBusy, firstAppear, idleVariant } = {}) {
  const anim = String(animation || "idle").toLowerCase();
  if (bubble || anim === "talking" || anim === "speaking") return "speaking";
  if (agentBusy || TYPING_ANIMATIONS.has(anim)) return "typing";
  if (WAVE_ANIMATIONS.has(anim)) return "boot";
  if (WALK_ANIMATIONS.has(anim) || firstAppear) return "first_appear";
  if (anim === "smoking" || idleVariant === "smoking") return "idle_variant";
  return "idle";
}

export function resolveTerryClip(options) {
  return clipForState(resolveTerryState(options));
}

const V4_CLIP_NAMES = new Set([
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

const FIRST_APPEAR_MS = 2600;
const SMOKING_VARIANT_MS = 5600;
const SMOKING_CHANCE = 0.28;

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

/** One decoded v4 bundle for this page. Identity changes of ctx.rest must not
 *  refetch it, and a hide/show cycle reuses the same images. */
let sessionBundle = null;
let sessionInflight = null;
let sessionEpoch = 0;
let sessionFallback = false;

export function resetTerrySession() {
  sessionEpoch += 1;
  sessionBundle = null;
  sessionInflight = null;
  sessionFallback = false;
}

function loadPartImages(parts) {
  const images = new Map();
  const entries = Object.entries(parts || {});
  return Promise.all(
    entries.map(
      ([path, data]) =>
        new Promise((resolve) => {
          if (typeof Image === "undefined" || !data) {
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
  ).then(() => images);
}

function bundleFromBody(body) {
  if (!body || body.ok === false || !body.registry) {
    const error = new Error((body && body.error) || "Could not load the Terry v4 rig.");
    error.fix = (body && body.fix) || "";
    throw error;
  }
  return loadPartImages(body.parts).then((images) => ({
    registry: body.registry,
    speech: body.speech || { events: [], duration_ms: 2600 },
    smoke: body.smoke || {},
    costumes: body.costumes || {},
    images: images,
  }));
}

function failText(err) {
  const message = (err && err.message) || "Terry v4 request failed.";
  const fix = err && err.fix;
  return fix ? message + " " + fix : message;
}

function fetchBundle(api) {
  if (sessionBundle) return Promise.resolve(sessionBundle);
  if (sessionInflight) return sessionInflight;
  if (!api || typeof api.companionClip !== "function") {
    return Promise.reject(new Error("Terry v4 is not available in this host."));
  }
  const epoch = sessionEpoch;
  const pending = Promise.resolve(api.companionClip({ name: "v4:bundle" }))
    .then((body) => bundleFromBody(body))
    .then((bundle) => {
      if (epoch === sessionEpoch) {
        sessionBundle = bundle;
        sessionInflight = null;
      }
      return bundle;
    })
    .catch((err) => {
      if (epoch === sessionEpoch) sessionInflight = null;
      throw err;
    });
  sessionInflight = pending;
  return pending;
}

/** VP9 alpha is not reported separately; an empty canPlayType means the
 *  browser has no VP9 WebM at all, so the v4 canvas rig is the honest choice. */
export function vp9Supported() {
  if (typeof document === "undefined" || typeof document.createElement !== "function") return true;
  try {
    const probe = document.createElement("video");
    if (!probe || typeof probe.canPlayType !== "function") return false;
    return !!(probe.canPlayType('video/webm; codecs="vp9"') || probe.canPlayType("video/webm"));
  } catch (err) {
    return false;
  }
}

function externalClipUrls() {
  if (typeof window !== "undefined" && window.__TERRY_V5__ && typeof window.__TERRY_V5__ === "object") {
    return window.__TERRY_V5__;
  }
  return null;
}

function fetchVideoClip(api, name) {
  if (!api || typeof api.companionClip !== "function") {
    return Promise.reject(new Error("Terry v5 is not available in this host."));
  }
  return Promise.resolve(api.companionClip({ name: "v5:" + name })).then((body) => {
    if (!body || body.ok === false || !body.data) {
      throw new Error((body && body.error) || "Terry v5 clip " + name + " is unavailable.");
    }
    const url = blobUrlFromBase64(body.data, body.mime || "video/webm");
    if (!url) throw new Error("Terry v5 clip " + name + " could not be decoded.");
    return url;
  });
}

/** Two stacked <video> elements, crossfaded on clip changes. */
function useVideoRig({ active, api, animation, bubble, agentBusy, clipUrls, onReady, onFallback }) {
  const [urls, setUrls] = useState(null);
  const [slots, setSlots] = useState({
    a: { clip: "", url: "" },
    b: { clip: "", url: "" },
  });
  const [front, setFront] = useState("a");
  const [firstReady, setFirstReady] = useState(false);
  const [firstAppear, setFirstAppear] = useState(true);
  const [idleVariant, setIdleVariant] = useState("");
  const aRef = useRef(null);
  const bRef = useRef(null);
  const madeRef = useRef([]);
  const alphaProbedRef = useRef(false);
  const fallbackRef = useRef(onFallback);
  const readyRef = useRef(onReady);
  fallbackRef.current = onFallback;
  readyRef.current = onReady;

  const clip = resolveTerryClip({ animation, bubble, agentBusy, firstAppear, idleVariant });

  useEffect(() => {
    if (!active) return undefined;
    const timer = setTimeout(() => setFirstAppear(false), FIRST_APPEAR_MS);
    return () => clearTimeout(timer);
  }, [active]);

  useEffect(() => {
    if (!active) return undefined;
    const hostIdle = !bubble && !agentBusy && String(animation || "idle") !== "typing";
    if (!hostIdle || firstAppear) {
      setIdleVariant("");
      return undefined;
    }
    const timer = setInterval(() => {
      if (Math.random() < SMOKING_CHANCE) {
        setIdleVariant("smoking");
        setTimeout(() => setIdleVariant(""), SMOKING_VARIANT_MS);
      }
    }, LONG_IDLE_MS);
    return () => clearInterval(timer);
  }, [active, animation, bubble, agentBusy, firstAppear]);

  useEffect(() => {
    if (!active) return undefined;
    let cancelled = false;
    if (clipUrls) {
      setUrls(clipUrls);
      return () => {
        cancelled = true;
      };
    }
    const preloaded = externalClipUrls();
    if (preloaded) {
      setUrls(preloaded);
      return () => {
        cancelled = true;
      };
    }
    if (!vp9Supported()) {
      if (fallbackRef.current) fallbackRef.current("unsupported");
      return () => {
        cancelled = true;
      };
    }
    (async () => {
      const made = [];
      try {
        const idleUrl = await fetchVideoClip(api, "idle");
        made.push(idleUrl);
        if (cancelled) return;
        madeRef.current = made.slice();
        setUrls({ idle: idleUrl });
        const rest = await Promise.all(
          VIDEO_CLIPS.filter((name) => name !== "idle").map(async (name) => {
            const url = await fetchVideoClip(api, name);
            made.push(url);
            return [name, url];
          })
        );
        if (cancelled) return;
        madeRef.current = made.slice();
        setUrls((prev) => ({ ...(prev || { idle: idleUrl }), ...Object.fromEntries(rest) }));
      } catch (err) {
        made.forEach((url) => revokeUrl(url));
        madeRef.current = [];
        if (!cancelled && fallbackRef.current) fallbackRef.current("load");
      }
    })();
    return () => {
      cancelled = true;
      madeRef.current.forEach((url) => revokeUrl(url));
      madeRef.current = [];
    };
  }, [active, api, clipUrls]);

  useEffect(() => {
    if (!active || !urls) return;
    const url = urls[clip];
    if (!url) return;
    const current = slots[front];
    if (current.clip === clip && current.url === url) return;
    const other = front === "a" ? "b" : "a";
    if (current.clip === clip && current.url !== url) {
      setSlots((prev) => ({ ...prev, [front]: { clip, url } }));
      return;
    }
    if (slots[other].clip !== clip || slots[other].url !== url) {
      setSlots((prev) => ({ ...prev, [other]: { clip, url } }));
      return;
    }
    setFront(other);
  }, [active, clip, urls, slots, front]);

  const frontSlot = slots[front];
  useEffect(() => {
    if (!active) return;
    const node = front === "a" ? aRef.current : bRef.current;
    if (!node || !frontSlot.url) return;
    try {
      if (node.getAttribute && node.getAttribute("src") !== frontSlot.url) node.setAttribute("src", frontSlot.url);
      const played = node.play && node.play();
      if (played && typeof played.catch === "function") played.catch(() => {});
    } catch (err) {
      /* autoplay rejection is harmless; the frame stays on the first keyframe */
    }
  }, [active, front, frontSlot.url, frontSlot.clip]);

  useEffect(() => {
    if (!active) return undefined;
    const outgoing = front === "a" ? bRef.current : aRef.current;
    if (!outgoing) return undefined;
    const timer = setTimeout(() => {
      try {
        outgoing.pause();
      } catch (err) {
        /* an already-paused video is fine */
      }
    }, 240);
    return () => clearTimeout(timer);
  }, [active, front]);

  function noteReady(node) {
    // canPlayType only proves the codec, not the alpha channel. Draw the
    // first frame once and require a non-opaque corner; otherwise the figure
    // would sit on a black rectangle instead of the pane background.
    if (!alphaProbedRef.current && node && node.videoWidth && typeof document !== "undefined") {
      alphaProbedRef.current = true;
      try {
        const probe = document.createElement("canvas");
        probe.width = 2;
        probe.height = 2;
        const ctx = probe.getContext && probe.getContext("2d");
        if (ctx) {
          ctx.drawImage(node, 0, 0, node.videoWidth, node.videoHeight, 0, 0, 2, 2);
          const pixel = ctx.getImageData(0, 0, 1, 1).data;
          if (pixel[3] >= 250) {
            if (fallbackRef.current) fallbackRef.current("alpha");
            return;
          }
        }
      } catch (err) {
        /* a tainted or unavailable canvas must not block the video */
      }
    }
    if (!firstReady) setFirstReady(true);
    if (readyRef.current) readyRef.current(true);
  }

  function video(slotName) {
    const slot = slots[slotName];
    return jsx(
      "video",
      {
        ref: slotName === "a" ? aRef : bRef,
        className: "tos-companion-video" + (front === slotName ? " is-front" : ""),
        "data-companion-video": "1",
        "data-slot": slotName,
        "data-clip": slot.clip || undefined,
        src: slot.url || undefined,
        muted: true,
        playsInline: true,
        loop: true,
        autoPlay: true,
        preload: "auto",
        disablePictureInPicture: true,
        "aria-hidden": "true",
        onCanPlay: (event) => noteReady(event && event.currentTarget),
        onLoadedData: (event) => noteReady(event && event.currentTarget),
        onError: () => fallbackRef.current && fallbackRef.current("playback"),
      },
      slotName
    );
  }

  return [
    video("a"),
    video("b"),
    firstReady
      ? null
      : jsx("div", {
          className: "tos-companion-loading",
          "data-testid": "companion-loading",
          "data-state": "loading",
          children: "Summoning Terry…",
        }),
  ].filter(Boolean);
}

/** Canvas rig that plays baked v4 clips via requestAnimationFrame. */
function useV4Rig({ active, api, animation, costume, bubble, onReady }) {
  const canvasRef = useRef(null);
  const [ready, setReady] = useState(false);
  const [painted, setPainted] = useState(false);
  const [error, setError] = useState("");
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
  const apiRef = useRef(api);
  const paintedRef = useRef(false);

  const hostAnim = animation || "idle";
  apiRef.current = api;
  bubbleRef.current = bubble;

  useEffect(() => {
    if (onReady) onReady(!!(ready || painted));
  }, [ready, painted]);

  useEffect(() => {
    if (!active) return undefined;
    if (typeof window === "undefined" || typeof window.addEventListener !== "function") return undefined;
    const onDrawn = () => {
      paintedRef.current = true;
      setPainted(true);
    };
    window.addEventListener("terry-v4-drawn", onDrawn);
    return () => {
      if (typeof window.removeEventListener === "function") window.removeEventListener("terry-v4-drawn", onDrawn);
    };
  }, [active]);

  function ensureClip(name) {
    const token = hostClip(name);
    if (!V4_CLIP_NAMES.has(token)) return Promise.resolve(null);
    const cached = clipsRef.current.get(token);
    if (cached && cached.clip) return Promise.resolve(cached.clip);
    if (cached && cached.pending) return cached.pending;
    const live = apiRef.current;
    if (!live || typeof live.companionClip !== "function") return Promise.resolve(null);
    const pending = Promise.resolve(live.companionClip({ name: "v4:" + token }))
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
    if (!active) return undefined;
    let cancelled = false;
    fetchBundle(apiRef.current)
      .then((bundle) => {
        if (cancelled || !bundle) return;
        bundleRef.current = bundle;
        setError("");
        setReady(true);
        ensureClip("idle");
        ensureClip(hostClip(hostAnim));
      })
      .catch((err) => {
        if (cancelled) return;
        setError(failText(err));
        setReady(false);
      });
    return () => {
      cancelled = true;
    };
  }, [active]);

  useEffect(() => {
    if (active && ready) ensureClip(hostClip(hostAnim));
  }, [active, ready, hostAnim]);

  useEffect(() => {
    if (!active || !ready) return undefined;
    if (!greetedRef.current && hostClip(hostAnim) === "idle") {
      greetedRef.current = true;
      playLocal("greet", GREET_MS, "");
    }
    return undefined;
  }, [active, ready, hostAnim]);

  useEffect(() => {
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      rafRef.current = 0;
    };
  }, []);

  useEffect(() => {
    if (!active || !ready) {
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
          const drawn = renderScene(canvas, bundle, bundle.images, frame, costume || "base", { time: elapsed, smoke: true });
          if (drawn && !paintedRef.current) {
            paintedRef.current = true;
            canvas.dataset.terryPainted = "1";
            setPainted(true);
          }
        }
      }
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      rafRef.current = 0;
    };
  }, [active, ready, hostAnim, costume]);

  const statusText = error ? error : ready || painted ? "" : "Summoning Terry…";

  return [
    jsx("canvas", {
      ref: canvasRef,
      className: "tos-companion-canvas",
      "data-companion-v4": "1",
      "data-animation": hostAnim || "idle",
      "data-costume": costume || "base",
      width: 192,
      height: 208,
      "aria-hidden": "true",
      onClick: onTerryClick,
    }),
    statusText
      ? jsx("div", {
          className: "tos-companion-loading",
          "data-testid": "companion-loading",
          "data-state": error ? "error" : "loading",
          children: statusText,
        })
      : null,
  ].filter(Boolean);
}

export function TerryCompanionOverlay({
  api,
  animation,
  costume,
  hidden,
  enabled,
  speech,
  agentBusy,
  clipUrls,
  onRendererChange,
}) {
  const [bubble, setBubble] = useState(
    speech && speech.active !== false ? String((speech && speech.text) || "") : ""
  );
  const [bubbleSource, setBubbleSource] = useState("");
  const [renderer, setRenderer] = useState(sessionFallback ? "v4" : "video");
  const [ready, setReady] = useState(false);
  const apiRef = useRef(api);
  apiRef.current = api;

  const live = hidden !== true && enabled !== false;

  function fallback() {
    sessionFallback = true;
    setRenderer("v4");
    setReady(false);
    if (onRendererChange) onRendererChange("v4");
  }

  const videoNodes = useVideoRig({
    active: live && renderer === "video",
    api,
    animation,
    bubble,
    agentBusy,
    clipUrls,
    onReady: (value) => setReady(!!value),
    onFallback: fallback,
  });

  const v4Nodes = useV4Rig({
    active: live && renderer === "v4",
    api,
    animation,
    costume,
    bubble,
    onReady: (value) => setReady(!!value),
  });

  useEffect(() => {
    const text = speech && speech.active !== false ? String((speech && speech.text) || "") : "";
    setBubble(text);
    setBubbleSource("");
  }, [speech && speech.text, speech && speech.active]);

  useEffect(() => {
    TerryCompanion._say = (text, opts) => {
      const raw = String(text || "").trim();
      setBubble(raw);
      const quote = opts && opts.quote;
      setBubbleSource(raw && quote && quote.source_title ? String(quote.source_title) : "");
      const liveApi = apiRef.current;
      if (liveApi && typeof liveApi.companionSay === "function") {
        return Promise.resolve(liveApi.companionSay({ say: raw, hold_s: opts && opts.hold_s })).catch(() => {});
      }
      return Promise.resolve();
    };
    return () => {
      if (TerryCompanion._say) TerryCompanion._say = null;
    };
  }, []);

  if (enabled === false) return null;
  if (hidden) return null;

  const hostAnim = animation || "idle";

  return jsxs("aside", {
    className: "tos-companion-dock",
    "data-testid": "companion-dock",
    "data-animation": hostAnim,
    "data-ready": ready ? "1" : "0",
    "data-renderer": renderer,
    "aria-label": "Terry companion",
    children: [
      bubble
        ? jsx("div", {
            className: "tos-companion-bubble",
            "data-testid": "companion-bubble",
            title: bubbleSource ? "Approved quote — " + bubbleSource : "Terry",
            "data-source": bubbleSource || undefined,
            children: bubble,
          })
        : jsx("div", { className: "tos-companion-bubble-slot", "aria-hidden": "true" }),
      jsxs("div", {
        className: "tos-companion",
        "data-testid": "companion",
        "data-animation": hostAnim || "idle",
        "data-renderer": renderer,
        "data-costume": renderer === "v4" ? costume || "base" : undefined,
        title:
          "Terry companion — An original fan tribute with no official TempleOS affiliation.",
        children: [renderer === "v4" ? v4Nodes : videoNodes],
      }),
    ],
  });
}

export function CompanionControls({
  hidden,
  onToggleHidden,
  costume,
  onCostume,
  costumes,
  enabled,
  muted,
  onToggleMuted,
  fallback,
}) {
  if (enabled === false) return null;
  const options = costumes && costumes.length ? costumes : ["base", "cowboy", "wizard", "chef"];
  return jsxs("div", {
    className: "tos-companion-controls",
    "data-testid": "companion-controls",
    "data-renderer": fallback ? "v4" : "video",
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
      jsx("button", {
        type: "button",
        className: "tos-btn tos-companion-mute" + (muted ? " is-on" : ""),
        "data-testid": "companion-mute",
        "aria-pressed": muted ? "true" : "false",
        title: muted ? "Unmute Terry's quote bubbles (Terry stays visible)" : "Mute Terry's quote bubbles (Terry stays visible)",
        onClick: onToggleMuted,
        children: muted ? "Quotes muted" : "Quotes on",
      }),
      fallback
        ? jsxs("label", {
            className: "tos-companion-costume",
            title: "Choose Terry's costume (v4 fallback rig)",
            children: [
              jsx("span", { className: "tos-sr-only", children: "Costume" }),
              jsxs("select", {
                "data-testid": "companion-costume",
                value: costume || "base",
                onChange: (event) => onCostume && onCostume(event.target.value),
                children: options.map((name) => jsx("option", { value: name, children: name }, name)),
              }),
            ],
          })
        : null,
    ],
  });
}

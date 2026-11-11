import { jsx, jsxs } from "react/jsx-runtime";
import { useEffect, useMemo, useRef, useState } from "react";
import { createApi, blobUrlFromBase64, revokeUrl, errorText, isAbortError } from "./api.js";
import { getHostTransport } from "./host.js";
import { CompanionControls, TerryCompanion, TerryCompanionOverlay } from "./companion.js";
import { HERMES_ASSETS, nextTheme } from "./theme.js";
import { createQuotePicker, quoteKindForBoot, quoteKindForLogEvent, TERRY_IDLE_INTERVAL_MS } from "./quotes.js";
import TERRY_QUOTES from "../../terry-quotes.json" with { type: "json" };
import {
  GOLDEN_SNAPSHOT,
  accelLabel,
  bbsChip,
  drivingChip,
  clampScreenWidth,
  filterLogEvents,
  fitGuestDisplay,
  flavorLabel,
  formatLogTime,
  guestSize,
  guestVersionChip,
  keyEventToPayload,
  logToolKey,
  mapPointerToGuest,
  maxScreenWidth,
  measureScreenSpace,
  paneLayoutMode,
  checkState,
  firstCheck,
  needsOnboarding,
  pollIntervalMs,
  readStoredScreenPref,
  screenDisplay,
  statusSummary,
  userMayInput,
  vmStateChip,
  writeStoredScreenPref,
} from "./logic.js";

function documentIsHidden() {
  return typeof document !== "undefined" && document.visibilityState === "hidden";
}

function themeStyle(theme) {
  if (theme !== "hermes") return undefined;
  return {
    "--tos-hermes-header": `url("${HERMES_ASSETS.paneHeader}")`,
    "--tos-hermes-wallpaper": `url("${HERMES_ASSETS.wallpaper}")`,
    "--tos-hermes-mark": `url("${HERMES_ASSETS.mark}")`,
    "--tos-hermes-chat": `url("${HERMES_ASSETS.iconChat}")`,
    "--tos-hermes-nous": `url("${HERMES_ASSETS.iconNous}")`,
    "--tos-hermes-capy": `url("${HERMES_ASSETS.iconCapy}")`,
  };
}

function applyStatus(body, setStatus) {
  if (!body || typeof body !== "object") return;
  setStatus((prev) => ({ ...prev, ...body }));
}

function rectOf(node) {
  if (!node || typeof node.getBoundingClientRect !== "function") {
    return { width: 0, height: 0, left: 0, top: 0, right: 0, bottom: 0 };
  }
  const rect = node.getBoundingClientRect();
  return {
    width: Number(rect.width) || 0,
    height: Number(rect.height) || 0,
    left: Number(rect.left) || 0,
    top: Number(rect.top) || 0,
    right: Number(rect.right) || 0,
    bottom: Number(rect.bottom) || 0,
  };
}

function measurePane(stage) {
  const body = stage && typeof stage.closest === "function" ? stage.closest(".tos-body") : null;
  const root = body || stage;
  const bodyRect = rectOf(root);
  const stageRect = rectOf(stage);
  const dock = root && typeof root.querySelector === "function" ? root.querySelector(".tos-companion-dock") : null;
  const dockRect = rectOf(dock);
  const log = stage && typeof stage.querySelector === "function" ? stage.querySelector(".tos-log") : null;
  const logRect = rectOf(log);
  const hatch = stage && typeof stage.querySelector === "function" ? stage.querySelector(".tos-hatch") : null;
  const hatchHeight = hatch ? rectOf(hatch).height + 8 : 28;
  const logHeight = log ? logRect.height + 8 : 0;
  return measureScreenSpace({
    bodyWidth: bodyRect.width,
    stageWidth: stageRect.width,
    stageHeight: stageRect.height,
    stageRight: stageRect.right,
    railWidth: dock ? dockRect.width : 0,
    railLeft: dock && dockRect.width > 0 ? dockRect.left : null,
    hatchHeight: hatchHeight,
    logHeight: logHeight,
  });
}

function eventKey(event, index) {
  if (typeof event === "string") return "text:" + index + ":" + event;
  if (event && event.id != null) return "id:" + String(event.id);
  if (!event || typeof event !== "object") return "missing:" + index;
  return [
    event.at || event.ts || "",
    event.source || "",
    event.tool || "",
    event.op || "",
    event.summary || "",
  ].join("|");
}

const ICON_PATHS = {
  power: ["M12 3v9", "M6.6 6.6a8 8 0 1 0 10.8 0"],
  stop: ["M5 5h14v14H5z"],
  reset: ["M4 10a8 8 0 1 1 2.3 6.7", "M4 4v6h6"],
  save: ["M5 4h11l3 3v13H5z", "M8 4v6h7V4", "M8 20v-6h8v6"],
  restore: ["M20 10a8 8 0 1 0-2.3 6.7", "M20 4v6h-6"],
  eye: ["M2 12s3.6-6 10-6 10 6 10 6-3.6 6-10 6S2 12 2 12z", "M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6z"],
  users: ["M8 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7z", "M2 21v-2a5 5 0 0 1 5-5h2a5 5 0 0 1 5 5v2", "M16 4.4a3.5 3.5 0 0 1 0 6.9", "M17.5 14a5 5 0 0 1 4.5 5v2"],
  keyboard: ["M3 6h18v12H3z", "M7 10h.01", "M11 10h.01", "M15 10h.01", "M19 10h.01", "M7 14h10"],
  hand: ["M8 12V5.5a1.5 1.5 0 0 1 3 0V11", "M11 11V4.5a1.5 1.5 0 0 1 3 0V11", "M14 11V5.5a1.5 1.5 0 0 1 3 0V13", "M8 11V9a1.5 1.5 0 0 0-3 0v5a7 7 0 0 0 7 7h2a5 5 0 0 0 5-5v-3"],
  fit: ["M4 9V4h5", "M15 4h5v5", "M20 15v5h-5", "M9 20H4v-5"],
  gear: ["M12 8.5a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7z", "M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2h-4v-.2a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9A1.7 1.7 0 0 0 3 14H2.8v-4H3a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-1.6v-.2h4V3a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.2v4H21a1.7 1.7 0 0 0-1.6 1z"],
  mute: ["M11 5 6 9H3v6h3l5 4z", "M16 9a4 4 0 0 1 0 6", "M19 6a8 8 0 0 1 0 12"],
  sound: ["M11 5 6 9H3v6h3l5 4z", "M15.5 8.5a5 5 0 0 1 0 7"],
  follow: ["M6 3v12", "M6 15a4 4 0 0 0 4 4h8", "M15 16l3 3-3 3", "M6 3l4 4-4 4"],
  lock: ["M6 11h12v10H6z", "M8 11V7a4 4 0 0 1 8 0v4"],
  unlock: ["M6 11h12v10H6z", "M8 11V7a4 4 0 0 1 7.5-2"],
  filter: ["M3 5h18l-7 8v6l-4 2v-8z"],
  terminal: ["M4 4h16v16H4z", "M7 9l3 3-3 3", "M12 15h5"],
};

function Icon({ name, size }) {
  const paths = ICON_PATHS[name] || ICON_PATHS.terminal;
  return jsx("svg", {
    className: "tos-icon",
    viewBox: "0 0 24 24",
    width: size || 14,
    height: size || 14,
    fill: "none",
    stroke: "currentColor",
    strokeWidth: "1.8",
    strokeLinecap: "round",
    strokeLinejoin: "round",
    "aria-hidden": "true",
    focusable: "false",
    children: paths.map((d, index) => jsx("path", { d: d }, String(index))),
  });
}

function actionButton(props) {
  const label = props.label;
  const className =
    "tos-btn" +
    (props.primary ? " tos-primary" : "") +
    (props.pressed ? " is-on" : "") +
    (props.className ? " " + props.className : "");
  return jsxs("button", {
    type: "button",
    className: className,
    "data-testid": props.testid,
    disabled: props.disabled,
    title: props.title || label,
    "aria-pressed": props.pressed == null ? undefined : String(!!props.pressed),
    onClick: props.onClick,
    children: [
      props.icon ? jsx(Icon, { name: props.icon }) : null,
      jsx("span", { className: "tos-btn-label", children: label }),
    ],
  });
}

function logRow(event, index) {
  if (typeof event === "string") {
    return jsx("div", { className: "tos-log-line", children: [
      jsx("time", { className: "tos-log-time", children: "--:--:--" }),
      jsx("span", { className: "tos-log-icon tos-log-icon-chat", "aria-hidden": "true" }),
      jsx("span", { className: "tos-log-summary", children: event }),
    ] }, "text-" + index);
  }
  const toolKey = logToolKey(event);
  const summary = (event && (event.summary || [event.tool, event.op].filter(Boolean).join(" "))) || "event";
  const meta = [
    event && event.source === "user" ? "You" : "Agent",
    event && event.tool ? event.tool : "",
    event && event.op ? event.op : "",
  ].filter(Boolean).join(" · ");
  return jsxs(
    "div",
    {
      className:
        "tos-log-line tos-log-" +
        ((event && event.source) || "agent") +
        (event && event.ok === false ? " is-failed" : ""),
      "data-tool": toolKey,
      children: [
        jsx("time", {
          className: "tos-log-time",
          dateTime: event && (event.at || event.ts) ? String(event.at || event.ts) : undefined,
          children: formatLogTime(event) || "--:--:--",
        }),
        jsx("span", { className: "tos-log-icon tos-log-icon-" + toolKey, "aria-hidden": "true" }),
        jsxs("span", {
          className: "tos-log-body",
          children: [
            jsx("span", { className: "tos-log-summary", children: summary }),
            jsx("span", { className: "tos-log-meta", children: meta }),
          ],
        }),
      ],
    },
    String((event && event.id) || index)
  );
}

function stateChip(testid, chip) {
  return jsx("span", {
    className: "tos-status-chip tos-status-" + chip.state,
    "data-testid": testid,
    "data-state": chip.state,
    title: chip.title,
    children: [
      jsx("span", { className: "tos-status-dot", "aria-hidden": "true" }),
      jsx("span", { children: chip.label }),
    ],
  });
}

function defaultStatus(initial) {
  return {
    running: false,
    mode: "shared",
    agent_paused: false,
    agent_busy: false,
    accel: null,
    snapshot: null,
    snapshots: [GOLDEN_SNAPSHOT],
    flavor: "tinkeros",
    flavor_name: "TinkerOS 5.20-rc10",
    kvm: false,
    setup_needed: false,
    ready: false,
    checks: {},
    user_may_input: true,
    width: 640,
    height: 480,
    companion: { enabled: true, character: "terry", animation: "idle", costume: "base" },
    ...(initial || {}),
  };
}

export function TempleOSPane({ transport, initial } = {}) {
  const host = transport || getHostTransport() || {};
  const skip = !!(initial && initial.skipLoad);
  const api = useMemo(() => createApi(host.rest), [host.rest]);
  const apiRef = useRef(api);
  apiRef.current = api;
  const [status, setStatus] = useState(defaultStatus(initial && initial.status));
  const [error, setError] = useState((initial && initial.error) || "");
  const [info, setInfo] = useState((initial && initial.info) || "");
  const [log, setLog] = useState((initial && initial.log) || []);
  const [frameUrl, setFrameUrl] = useState((initial && initial.frameUrl) || "");
  const [focused, setFocused] = useState(!!(initial && initial.focused));
  const [busy, setBusy] = useState((initial && initial.busy) || "");
  const [hidden, setHidden] = useState(!!(initial && initial.hidden));
  const [companionHidden, setCompanionHidden] = useState(
    !!(initial && (initial.companionHidden || (initial.status && initial.status.companion && initial.status.companion.hidden)))
  );
  const [companionCostume, setCompanionCostume] = useState(
    (initial && initial.companionCostume) ||
      (initial && initial.status && initial.status.companion && initial.status.companion.costume) ||
      "base"
  );
  const [theme, setTheme] = useState((initial && initial.theme) || "hermes");
  const [unchanged, setUnchanged] = useState(!!(initial && initial.unchanged));
  const [logFilter, setLogFilter] = useState("all");
  const [logFollow, setLogFollow] = useState(true);
  const [quotesMuted, setQuotesMuted] = useState(!!(initial && initial.quotesMuted));
  const [statusLoaded, setStatusLoaded] = useState(skip || !!(initial && initial.status));
  const [screenPref, setScreenPref] = useState(() => {
    if (initial && initial.screenPref) return { mode: initial.screenPref.mode === "manual" ? "manual" : "fit", width: Number(initial.screenPref.width) || 0 };
    return readStoredScreenPref();
  });
  const [box, setBox] = useState(() => {
    const vp = initial && initial.viewport;
    if (!vp) return { width: 0, height: 0, rail: 0, log: 0 };
    return {
      width: Number(vp.width) || 0,
      height: Number(vp.height) || 0,
      rail: Number(vp.rail) || 0,
      log: Number(vp.log) || 0,
    };
  });
  const prevUrl = useRef((initial && initial.frameUrl) || "");
  const shaRef = useRef((initial && initial.sha256) || "");
  const statusRef = useRef(status);
  const runningRef = useRef(!!(initial && initial.status && initial.status.running));
  const logScrollRef = useRef(null);
  const logSeenRef = useRef(new Set());
  const logHydratedRef = useRef(false);
  const pickerRef = useRef(null);
  if (!pickerRef.current) {
    pickerRef.current = createQuotePicker(TERRY_QUOTES, { muted: !!quotesMuted });
  }
  const focusedRef = useRef(focused);
  const unchangedRef = useRef(unchanged);
  const hiddenRef = useRef(hidden);
  const lastFrameAt = useRef(0);
  const screenRef = useRef(null);
  const stageRef = useRef(null);
  const spaceRef = useRef(box);
  const sizeRef = useRef({ width: 640, height: 480 });
  const scaledRef = useRef({ width: 640, height: 480 });
  spaceRef.current = box;
  statusRef.current = status;
  focusedRef.current = focused;
  unchangedRef.current = unchanged;
  hiddenRef.current = hidden;

  function noteError(err) {
    if (isAbortError(err)) return;
    const text = errorText(err);
    if (!text) return;
    setError(text);
  }

  function refreshLog(body) {
    if (body && Array.isArray(body.events)) setLog(body.events);
  }

  const slowRef = useRef(false);

  useEffect(() => {
    if (skip) return undefined;
    let cancelled = false;
    const tick = () => {
      const now = Date.now();
      const interval = pollIntervalMs({
        hidden: hiddenRef.current || documentIsHidden(),
        running: !!(statusRef.current && statusRef.current.running),
        unchanged: unchangedRef.current,
        focused: focusedRef.current,
        slow: slowRef.current,
      });
      apiRef.current
        .status()
        .then((body) => {
          if (!cancelled) {
            applyStatus(body, setStatus);
            setStatusLoaded(true);
            if (body && body.companion) {
              if (typeof body.companion.hidden === "boolean") setCompanionHidden(!!body.companion.hidden);
              if (body.companion.costume) setCompanionCostume(body.companion.costume);
            }
            setError("");
          }
        })
        .catch((err) => {
          if (!cancelled) noteError(err);
        });
      apiRef.current
        .log()
        .then((body) => {
          if (!cancelled) refreshLog(body);
        })
        .catch((err) => {
          if (isAbortError(err)) return;
        });
      if (now - lastFrameAt.current < interval) return;
      lastFrameAt.current = now;
      const since = shaRef.current;
      const frameStarted = Date.now();
      apiRef.current
        .frame(since ? { since } : undefined)
        .then((body) => {
          if (cancelled) return;
          const elapsed = Date.now() - frameStarted;
          // Back off when the host is slow so we never stampede /frame.
          slowRef.current = elapsed >= 500;
          if (body && body.sha256) shaRef.current = body.sha256;
          if (body && body.unchanged) {
            setUnchanged(true);
            return;
          }
          const next = blobUrlFromBase64(body && body.data, body && body.mime);
          if (!next) return;
          setUnchanged(false);
          revokeUrl(prevUrl.current);
          prevUrl.current = next;
          setFrameUrl(next);
        })
        .catch((err) => {
          if (isAbortError(err)) return;
          slowRef.current = true;
          /* soft-fail; status still drives the chip */
        });
    };
    tick();
    const intervalFn = typeof host.setInterval === "function" ? host.setInterval : null;
    const handle = intervalFn ? intervalFn(tick, POLL_TICK) : null;
    const onVis = () => setHidden(documentIsHidden());
    if (typeof document !== "undefined" && document.addEventListener) {
      document.addEventListener("visibilitychange", onVis);
    }
    return () => {
      cancelled = true;
      if (handle && typeof host.clearInterval === "function") {
        host.clearInterval(handle);
      }
      if (typeof document !== "undefined" && document.removeEventListener) {
        document.removeEventListener("visibilitychange", onVis);
      }
      revokeUrl(prevUrl.current);
      prevUrl.current = "";
    };
  }, [skip]);

  useEffect(() => {
    writeStoredScreenPref(screenPref);
  }, [screenPref.mode, screenPref.width]);

  function sayQuote(text, opts) {
    Promise.resolve(TerryCompanion.say(text, opts)).catch(() => {});
  }

  function toggleQuotesMuted() {
    const next = !quotesMuted;
    setQuotesMuted(next);
    pickerRef.current.setMuted(next);
    if (next) sayQuote("");
  }

  function onLogScroll(event) {
    const node = event && event.currentTarget;
    if (!node) return;
    const distance = (Number(node.scrollHeight) || 0) - (Number(node.scrollTop) || 0) - (Number(node.clientHeight) || 0);
    setLogFollow(distance <= 24);
  }

  useEffect(() => {
    const picker = pickerRef.current;
    picker.setMuted(quotesMuted);
    if (quotesMuted || picker.size === 0) {
      picker.stopIdle();
      return undefined;
    }
    picker.startIdle(sayQuote, { intervalMs: TERRY_IDLE_INTERVAL_MS });
    return () => picker.stopIdle();
  }, [quotesMuted]);

  useEffect(() => {
    const kind = quoteKindForBoot(runningRef.current, !!status.running);
    runningRef.current = !!status.running;
    if (!kind || quotesMuted) return;
    pickerRef.current.say(sayQuote, kind);
  }, [status.running, quotesMuted]);

  useEffect(() => {
    const events = Array.isArray(log) ? log : [];
    if (!logHydratedRef.current) {
      logHydratedRef.current = true;
      events.forEach((event, index) => logSeenRef.current.add(eventKey(event, index)));
      return;
    }
    events.forEach((event, index) => {
      const key = eventKey(event, index);
      if (logSeenRef.current.has(key)) return;
      logSeenRef.current.add(key);
      if (quotesMuted) return;
      const kind = quoteKindForLogEvent(event);
      if (kind) pickerRef.current.say(sayQuote, kind);
    });
  }, [log, quotesMuted]);

  useEffect(() => {
    if (!logFollow) return;
    const node = logScrollRef.current;
    if (node && typeof node === "object") node.scrollTop = node.scrollHeight;
  }, [log, logFilter, logFollow]);

  useEffect(() => {
    const stage = stageRef.current;
    if (!stage || typeof ResizeObserver === "undefined") return undefined;
    let frame = 0;
    const measure = () => {
      const next = measurePane(stage);
      if (!next || next.width <= 0 || next.height <= 0) return;
      setBox((prev) => {
        if (
          prev &&
          Math.abs(prev.width - next.width) < 1 &&
          Math.abs(prev.height - next.height) < 1 &&
          Math.abs((prev.rail || 0) - (next.rail || 0)) < 1 &&
          Math.abs((prev.log || 0) - (next.log || 0)) < 1
        ) {
          return prev;
        }
        return { width: next.width, height: next.height, rail: next.rail, log: next.log || 0 };
      });
    };
    const observer = new ResizeObserver(() => {
      if (typeof requestAnimationFrame === "function") {
        if (frame) cancelAnimationFrame(frame);
        frame = requestAnimationFrame(measure);
      } else {
        measure();
      }
    });
    observer.observe(stage);
    const body = typeof stage.closest === "function" ? stage.closest(".tos-body") : null;
    if (body) observer.observe(body);
    const pane = typeof stage.closest === "function" ? stage.closest(".tos-pane") : null;
    if (pane && pane.parentElement) observer.observe(pane.parentElement);
    measure();
    return () => {
      if (frame && typeof cancelAnimationFrame === "function") cancelAnimationFrame(frame);
      observer.disconnect();
    };
  }, [companionHidden, status.companion && status.companion.enabled]);

  function chooseFit() {
    setScreenPref((prev) => ({ mode: "fit", width: prev.width || 0 }));
  }

  function onResizePointerDown(event) {
    if (event && event.button != null && event.button !== 0) return;
    if (event && event.preventDefault) event.preventDefault();
    if (event && event.stopPropagation) event.stopPropagation();
    const startX = Number(event && event.clientX) || 0;
    const guest = sizeRef.current;
    const startWidth = scaledRef.current.width || guest.width;
    function move(ev) {
      const dx = (Number(ev && ev.clientX) || 0) - startX;
      const space = spaceRef.current || { width: 0, height: 0, rail: 0, log: 0 };
      const fit = fitGuestDisplay({ width: space.width, height: space.height }, guest, space.rail, 12, space.log);
      const known = fit.availableWidth > 0 && fit.availableHeight > 0;
      const max = known
        ? maxScreenWidth(fit.availableWidth, fit.availableHeight, guest.width, guest.height)
        : Math.max(guest.width, startWidth);
      const width = clampScreenWidth(startWidth + dx, guest.width, max);
      setScreenPref({ mode: "manual", width: width });
    }
    function detach() {
      if (typeof window === "undefined") return;
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", detach);
      window.removeEventListener("pointercancel", detach);
    }
    if (typeof window !== "undefined") {
      window.addEventListener("pointermove", move);
      window.addEventListener("pointerup", detach);
      window.addEventListener("pointercancel", detach);
    }
  }

  function run(label, work) {
    setBusy(label);
    setError("");
    setInfo("");
    return work()
      .then((body) => {
        applyStatus(body, setStatus);
        if (body && typeof body === "object") setStatusLoaded(true);
        setBusy("");
        if (body && Array.isArray(body.events)) refreshLog(body);
        return body;
      })
      .catch((err) => {
        setBusy("");
        noteError(err);
      });
  }

  function setMode(op) {
    return run("control", () => api.control({ op }));
  }

  function onSetup() {
    return run("setup", () => api.setup({ flavor: status.flavor || "tinkeros" }));
  }

  function onStart() {
    return run("start", () => api.start({ flavor: status.flavor || "tinkeros", name: status.snapshot || GOLDEN_SNAPSHOT }));
  }

  function onStop() {
    return run("stop", () => api.stop());
  }

  function onReset() {
    return run("reset", () => api.reset());
  }

  function onSave() {
    return run("save", () => api.saveSnapshot(GOLDEN_SNAPSHOT));
  }

  function onRestore() {
    return run("restore", () => api.restoreSnapshot(GOLDEN_SNAPSHOT));
  }

  function onCanvasClick(event) {
    if (!userMayInput(status.mode)) return;
    const size = guestSize(status.flavor, status);
    const box = event.currentTarget;
    const rect = box.getBoundingClientRect
      ? box.getBoundingClientRect()
      : { left: 0, top: 0, width: size.width, height: size.height };
    const point = mapPointerToGuest(event.clientX, event.clientY, rect, size.width, size.height);
    api
      .input({ type: "click", x: point.x, y: point.y, button: "left" })
      .then((body) => applyStatus(body, setStatus))
      .catch((err) => noteError(err));
  }

  function onKeyDown(event) {
    if (!focusedRef.current) return;
    const payload = keyEventToPayload(event);
    if (!payload) return;
    if (payload.hatch) {
      if (event.preventDefault) event.preventDefault();
      setFocused(false);
      if (event.currentTarget && event.currentTarget.blur) event.currentTarget.blur();
      setInfo("Keyboard released. Click the screen to capture keys again.");
      return;
    }
    if (!userMayInput(statusRef.current.mode)) return;
    if (event.preventDefault) event.preventDefault();
    api
      .input(payload)
      .then((body) => applyStatus(body, setStatus))
      .catch((err) => noteError(err));
  }

  const size = guestSize(status.flavor, status);
  const forced = initial && initial.scale;
  const scaled = screenDisplay(screenPref, box, size, box.rail, 12, forced, box.log);
  sizeRef.current = size;
  scaledRef.current = scaled;
  spaceRef.current = box;
  const chip = statusSummary(status);
  const drive = drivingChip(status);
  const vmChip = vmStateChip(status, statusLoaded);
  const bbs = bbsChip(status, statusLoaded);
  const guest = guestVersionChip(status, statusLoaded);
  const filteredLog = filterLogEvents(log, logFilter);
  const layoutMode = paneLayoutMode(
    (box && box.width) || (initial && initial.viewport && initial.viewport.width) || 0
  );
  const onboarding = needsOnboarding(status);
  const flavor = flavorLabel(status.flavor, status.flavor_name);
  const accel = accelLabel(status.accel, status.kvm);
  const running = !!status.running;
  const disabled = !!busy;

  return jsxs("div", {
    className: "tos-pane",
    "data-testid": "pane",
    "data-mode": status.mode,
    "data-running": running ? "1" : "0",
    "data-theme": theme,
    "data-layout": layoutMode,
    style: themeStyle(theme),
    children: [
      jsxs("header", {
        className: "tos-top",
        children: [
          jsxs("div", {
            className: "tos-brand",
            children: [
              jsx("span", { className: "tos-mark", "aria-hidden": "true" }),
              jsxs("div", {
                children: [
                  jsx("strong", { children: "TempleOS" }),
                  jsx("em", { children: theme === "hermes" ? "Temple of Hermes" : "Shared guest" }),
                ],
              }),
            ],
          }),
          jsxs("div", {
            className: "tos-chips",
            role: "group",
            "aria-label": "Guest status",
            children: [
              jsx("span", { className: "tos-badge", "data-testid": "flavor-badge", title: "Guest flavour", children: flavor }),
              jsx("span", { className: "tos-badge tos-badge-accel", "data-testid": "accel-badge", title: "Hardware acceleration", children: accel }),
              jsx("span", { className: "tos-badge", "data-testid": "snapshot-badge", title: "Active snapshot", children: status.snapshot || "no snapshot" }),
              stateChip("vm-state-chip", vmChip),
              stateChip("bbs-status-chip", bbs),
              stateChip("guest-version-chip", guest),
              jsx("span", {
                className: "tos-chip",
                "data-testid": "status-chip",
                "data-mode": status.mode,
                "data-paused": status.agent_paused ? "1" : "0",
                "data-state": vmChip.state,
                children: chip,
              }),
            ],
          }),
          jsx("button", {
            type: "button",
            className: "tos-btn tos-theme",
            "data-testid": "theme-toggle",
            "aria-label": "Switch pane theme",
            title: theme === "hermes" ? "Switch to VGA chrome" : "Switch to Temple of Hermes theme",
            onClick: () => setTheme(nextTheme(theme)),
            children: [
              jsx(Icon, { name: "gear" }),
              jsx("span", { className: "tos-btn-label", children: theme === "hermes" ? "Temple" : "VGA" }),
            ],
          }),
        ],
      }),
      jsxs("div", {
        className: "tos-toolbar",
        children: [
          jsxs("div", {
            className: "tos-bar",
            role: "toolbar",
            "aria-label": "TempleOS controls",
            children: [
              jsxs("div", {
                className: "tos-group",
                role: "group",
                "aria-label": "VM power",
                children: [
                  jsx("span", { className: "tos-group-label", children: "Power" }),
                  actionButton({ testid: "start", label: busy === "start" ? "Starting…" : "Start", icon: "power", primary: true, disabled: disabled || running, onClick: onStart, title: "Start the guest" }),
                  actionButton({ testid: "stop", label: "Stop", icon: "stop", disabled: disabled || !running, onClick: onStop, title: "Stop the guest" }),
                  actionButton({ testid: "reset", label: "Reset", icon: "reset", disabled: disabled || !running, onClick: onReset, title: "Reset the guest" }),
                ],
              }),
              jsxs("div", {
                className: "tos-group",
                role: "group",
                "aria-label": "Snapshots",
                children: [
                  jsx("span", { className: "tos-group-label", children: "Snapshots" }),
                  actionButton({ testid: "snapshot-save", label: busy === "save" ? "Saving…" : "Save", icon: "save", disabled: disabled || !running, onClick: onSave, title: "Save the golden snapshot" }),
                  actionButton({ testid: "snapshot-restore", label: busy === "restore" ? "Restoring…" : "Restore", icon: "restore", disabled: disabled, onClick: onRestore, title: "Restore the golden snapshot" }),
                ],
              }),
              jsxs("div", {
                className: "tos-group",
                role: "group",
                "aria-label": "Input mode",
                children: [
                  jsx("span", { className: "tos-group-label", children: "Input" }),
                  jsxs("div", {
                    className: "tos-modes",
                    role: "group",
                    "aria-label": "Control mode",
                    children: [
                      modeButton("watch", "Watch", status.mode, disabled, setMode),
                      modeButton("shared", "Shared", status.mode, disabled, setMode),
                      modeButton("user", "You drive", status.mode, disabled, setMode),
                    ],
                  }),
                  actionButton({ testid: "take-control", label: "Take control", icon: "hand", primary: true, disabled: disabled || status.mode === "user", onClick: () => setMode("take"), title: "Take the keyboard from the agent" }),
                  actionButton({ testid: "hand-back", label: "Hand back", icon: "users", disabled: disabled || status.mode === "shared", onClick: () => setMode("handback"), title: "Hand the keyboard back to the agent" }),
                ],
              }),
              jsxs("div", {
                className: "tos-group",
                role: "group",
                "aria-label": "View",
                children: [
                  jsx("span", { className: "tos-group-label", children: "View" }),
                  actionButton({ testid: "screen-fit", label: "Fit", icon: "fit", pressed: screenPref.mode === "fit", onClick: chooseFit, title: "Fit the guest to the pane (double-click the corner handle too)" }),
                ],
              }),
              jsxs("div", {
                className: "tos-group tos-group-terry",
                role: "group",
                "aria-label": "Terry companion",
                children: [
                  jsx("span", { className: "tos-group-label", children: "Terry" }),
                  jsx(CompanionControls, {
                    hidden: companionHidden,
                    enabled: !(status.companion && status.companion.enabled === false),
                    costume: companionCostume,
                    costumes: (status.companion && status.companion.costumes) || ["base", "cowboy", "wizard", "chef"],
                    muted: quotesMuted,
                    onToggleMuted: toggleQuotesMuted,
                    onToggleHidden: () => {
                      setCompanionHidden((prev) => {
                        const next = !prev;
                        api.companionSet({ hidden: next }).catch(() => {});
                        return next;
                      });
                    },
                    onCostume: (name) => {
                      setCompanionCostume(name);
                      api.companionSet({ costume: name }).catch(() => {});
                    },
                  }),
                ],
              }),
            ],
          }),
        ],
      }),
      jsx("div", {
        className: "tos-drive tos-drive-" + drive.kind,
        "data-testid": "agent-paused",
        "data-kind": drive.kind,
        children: drive.label,
      }),
      onboarding
        ? jsxs("section", {
            className: "tos-onboard",
            "data-testid": "onboarding",
            children: [
              jsx("h2", { children: "Set up the guest" }),
              jsx("p", { children: "TempleOS runs in a local QEMU VM. QEMU and the pinned ISO stay on this machine and are never bundled with the plugin. Networking stays off." }),
              jsxs("ul", {
                className: "tos-checks",
                children: [
                  checkRow("QEMU", firstCheck(status.checks, ["qemu", "qemu_present"])),
                  checkRow("ISO", firstCheck(status.checks, ["iso", "iso_ok", "iso_present"])),
                  checkRow("KVM", status.kvm === true ? true : firstCheck(status.checks, ["kvm"])),
                ],
              }),
              jsx("button", { type: "button", className: "tos-btn tos-primary", "data-testid": "setup", disabled: disabled, onClick: onSetup, children: busy === "setup" ? "Setting up…" : "Set up" }),
              jsx("p", { className: "tos-hint", children: "Set up fetches the official pin, verifies SHA-256, and reports whether /dev/kvm can be opened. Then press Start." }),
            ],
          })
        : null,
      jsxs("div", {
        className: "tos-body",
        children: [
          jsxs("div", {
            className: "tos-stage-row",
            "data-testid": "stage-row",
            children: [
          jsxs("div", {
            className: "tos-stage",
            ref: stageRef,
            children: [
              jsxs("div", {
                className: "tos-screen-stack",
                style: { width: scaled.width },
                children: [
              jsxs("div", {
                className: "tos-screen" + (focused ? " is-focused" : ""),
                "data-testid": "screen",
                "data-focused": focused ? "1" : "0",
                "data-screen-mode": scaled.mode,
                "data-scale": String(Math.round(scaled.scale * 1000) / 1000),
                ref: screenRef,
                tabIndex: 0,
                role: "application",
                "aria-label": "TempleOS guest screen",
                style: { width: scaled.width, height: scaled.height },
                onClick: (event) => {
                  setFocused(true);
                  onCanvasClick(event);
                },
                onFocus: () => setFocused(true),
                onBlur: () => setFocused(false),
                onKeyDown: onKeyDown,
                children: [
                  frameUrl
                    ? jsx("img", {
                        alt: "TempleOS guest",
                        src: frameUrl,
                        draggable: false,
                        style: { width: "100%", height: "100%", imageRendering: "pixelated" },
                      })
                    : jsx("div", {
                        className: "tos-placeholder",
                        "data-testid": "placeholder",
                        children: running ? "Waiting for a frame…" : "VM stopped. Press Start, or ask the agent to start it.",
                      }),
                  jsx("button", {
                    type: "button",
                    className: "tos-resize-handle",
                    "data-testid": "screen-resize",
                    "aria-label": "Resize guest screen",
                    title: "Drag to resize. Double-click to fit.",
                    onPointerDown: onResizePointerDown,
                    onClick: (event) => {
                      if (event.preventDefault) event.preventDefault();
                      if (event.stopPropagation) event.stopPropagation();
                    },
                    onDoubleClick: (event) => {
                      if (event.preventDefault) event.preventDefault();
                      if (event.stopPropagation) event.stopPropagation();
                      chooseFit();
                    },
                  }),
                ],
              }),
              focused
                ? jsx("p", { className: "tos-hatch", "data-testid": "keyboard-hatch", children: "Keyboard captured. Press Esc to release." })
                : jsx("p", { className: "tos-hatch tos-hatch-idle", "data-testid": "keyboard-hatch", children: "Click the screen to type. Esc releases the keyboard." }),
              jsxs("section", {
                className: "tos-log",
                "data-testid": "agent-log",
                "data-filter": logFilter,
                "data-follow": logFollow ? "1" : "0",
                children: [
                  jsxs("div", {
                    className: "tos-log-head",
                    children: [
                      jsxs("h2", {
                        children: [
                          jsx(Icon, { name: "terminal", size: 13 }),
                          jsx("span", { children: "Agent log" }),
                        ],
                      }),
                      jsxs("div", {
                        className: "tos-log-filters",
                        role: "group",
                        "aria-label": "Filter the Agent Log",
                        children: ["all", "tools", "user", "errors"].map((name) =>
                          jsx(
                            "button",
                            {
                              type: "button",
                              className: "tos-log-filter" + (logFilter === name ? " is-on" : ""),
                              "data-testid": "log-filter-" + name,
                              "aria-pressed": logFilter === name ? "true" : "false",
                              title: "Show " + name,
                              onClick: () => setLogFilter(name),
                              children: name === "user" ? "You" : name.charAt(0).toUpperCase() + name.slice(1),
                            },
                            name
                          )
                        ),
                      }),
                      jsx("button", {
                        type: "button",
                        className: "tos-log-follow" + (logFollow ? " is-on" : ""),
                        "data-testid": "log-follow",
                        "aria-pressed": logFollow ? "true" : "false",
                        title: logFollow ? "Auto-follow is locked on. Click to stop following." : "Follow new Agent Log events again.",
                        onClick: () => setLogFollow((prev) => !prev),
                        children: [
                          jsx(Icon, { name: logFollow ? "lock" : "unlock", size: 13 }),
                          jsx("span", { children: logFollow ? "Following" : "Follow" }),
                        ],
                      }),
                    ],
                  }),
                  jsx("div", {
                    className: "tos-log-scroll",
                    ref: logScrollRef,
                    onScroll: onLogScroll,
                    tabIndex: 0,
                    "aria-live": "polite",
                    "aria-label": "Agent Log events",
                    children: filteredLog.length
                      ? filteredLog.map((event, i) => logRow(event, i))
                      : jsx("p", {
                          className: "tos-log-empty",
                          children:
                            logFilter === "tools"
                              ? "No tool calls yet."
                              : logFilter === "user"
                                ? "No user actions yet."
                                : logFilter === "errors"
                                  ? "No errors. Quiet and healthy."
                                  : "The agent has not injected input yet.",
                        }),
                  }),
                ],
              }),
                ],
              }),
            ],
          }),
              jsx(TerryCompanionOverlay, {
                api: api,
                animation: (status.companion && status.companion.animation) || "idle",
                costume: companionCostume,
                hidden: companionHidden,
                enabled: !(status.companion && status.companion.enabled === false),
                speech: (status.companion && status.companion.speech) || null,
                sprite: (initial && initial.companionSprite) || "",
                spriteRow: (initial && initial.companionSpriteRow) || 0,
              }),
            ],
          }),
        ],
      }),
      error ? jsx("div", { className: "tos-error", "data-testid": "error", children: error }) : null,
      info ? jsx("div", { className: "tos-info", "data-testid": "info", children: info }) : null,
    ],
  });
}

const POLL_TICK = 100;

function modeButton(mode, label, current, disabled, setMode) {
  const op = mode === "user" ? "take" : mode === "shared" ? "handback" : "watch";
  const icon = mode === "watch" ? "eye" : mode === "user" ? "keyboard" : "users";
  return jsx("button", {
    type: "button",
    className: "tos-btn" + (current === mode ? " is-on" : ""),
    "data-testid": "mode-" + mode,
    "aria-pressed": current === mode ? "true" : "false",
    title: "Set control mode to " + label,
    disabled: disabled,
    onClick: () => setMode(op),
    children: [
      jsx(Icon, { name: icon }),
      jsx("span", { className: "tos-btn-label", children: label }),
    ],
  }, mode);
}

function checkRow(label, value) {
  const state = checkState(value);
  const mark = state === "ok" ? "ok" : state === "no" ? "missing" : "unknown";
  return jsxs("li", {
    className: "tos-check tos-check-" + state,
    "data-testid": "check-" + label.toLowerCase(),
    children: [jsxs("span", { children: [label, " — ", mark] })],
  });
}

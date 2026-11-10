import { jsx, jsxs } from "react/jsx-runtime";
import { useEffect, useMemo, useRef, useState } from "react";
import { createApi, blobUrlFromBase64, revokeUrl, errorText, isAbortError } from "./api.js";
import { getHostTransport } from "./host.js";
import { CompanionControls, TerryCompanionOverlay } from "./companion.js";
import { HERMES_ASSETS, nextTheme } from "./theme.js";
import {
  GOLDEN_SNAPSHOT,
  accelLabel,
  drivingChip,
  clampScreenWidth,
  fitGuestDisplay,
  flavorLabel,
  guestSize,
  keyEventToPayload,
  logLine,
  mapPointerToGuest,
  maxScreenWidth,
  measureScreenSpace,
  checkState,
  firstCheck,
  needsOnboarding,
  pollIntervalMs,
  readStoredScreenPref,
  screenDisplay,
  statusSummary,
  userMayInput,
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
          jsx("span", { className: "tos-badge", "data-testid": "flavor-badge", children: flavor }),
          jsx("span", { className: "tos-badge tos-badge-accel", "data-testid": "accel-badge", children: accel }),
          jsx("span", { className: "tos-badge", "data-testid": "snapshot-badge", children: status.snapshot || "no snapshot" }),
          jsx("span", {
            className: "tos-chip",
            "data-testid": "status-chip",
            "data-mode": status.mode,
            "data-paused": status.agent_paused ? "1" : "0",
            children: chip,
          }),
          jsx("button", {
            type: "button",
            className: "tos-btn tos-theme",
            "data-testid": "theme-toggle",
            "aria-label": "Switch pane theme",
            title: theme === "hermes" ? "Switch to VGA chrome" : "Switch to Temple of Hermes theme",
            onClick: () => setTheme(nextTheme(theme)),
            children: theme === "hermes" ? "Temple" : "VGA",
          }),
        ],
      }),
      jsxs("div", {
        className: "tos-bar",
        children: [
          jsx("button", { type: "button", className: "tos-btn tos-primary", "data-testid": "start", disabled: disabled || running, onClick: onStart, children: busy === "start" ? "Starting…" : "Start" }),
          jsx("button", { type: "button", className: "tos-btn", "data-testid": "stop", disabled: disabled || !running, onClick: onStop, children: "Stop" }),
          jsx("button", { type: "button", className: "tos-btn", "data-testid": "reset", disabled: disabled || !running, onClick: onReset, children: "Reset" }),
          jsx("button", { type: "button", className: "tos-btn", "data-testid": "snapshot-save", disabled: disabled || !running, onClick: onSave, children: "Snapshot golden" }),
          jsx("button", { type: "button", className: "tos-btn", "data-testid": "snapshot-restore", disabled: disabled, onClick: onRestore, children: "Restore golden" }),
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
          jsx("button", { type: "button", className: "tos-btn tos-primary", "data-testid": "take-control", disabled: disabled || status.mode === "user", onClick: () => setMode("take"), children: "Take control" }),
          jsx("button", { type: "button", className: "tos-btn", "data-testid": "hand-back", disabled: disabled || status.mode === "shared", onClick: () => setMode("handback"), children: "Hand back" }),
          jsx("button", {
            type: "button",
            className: "tos-btn" + (screenPref.mode === "fit" ? " is-on" : ""),
            "data-testid": "screen-fit",
            "aria-pressed": screenPref.mode === "fit" ? "true" : "false",
            title: "Fit the guest to the pane",
            onClick: chooseFit,
            children: "Fit",
          }),
          jsx(CompanionControls, {
            hidden: companionHidden,
            enabled: !(status.companion && status.companion.enabled === false),
            costume: companionCostume,
            costumes: (status.companion && status.companion.costumes) || ["base", "cowboy", "wizard", "chef"],
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
                children: [
                  jsx("h2", { children: "Agent log" }),
                  log.length
                    ? log.map((event, i) =>
                        jsx(
                          "p",
                          {
                            className: "tos-log-line tos-log-" + (event.source || "agent") + (event.ok === false ? " is-failed" : ""),
                            children: typeof event === "string" ? event : logLine(event),
                          },
                          String((event && event.id) || i)
                        )
                      )
                    : jsx("p", { className: "tos-log-empty", children: "The agent has not injected input yet." }),
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
  return jsx("button", {
    type: "button",
    className: "tos-btn" + (current === mode ? " is-on" : ""),
    "data-testid": "mode-" + mode,
    "aria-pressed": current === mode ? "true" : "false",
    disabled: disabled,
    onClick: () => setMode(op),
    children: label,
  });
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

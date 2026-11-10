/** Pure helpers for the TempleOS pane. */

export const DEFAULT_WIDTH = 640;
export const DEFAULT_HEIGHT = 480;
export const ZEALOS_WIDTH = 1024;
export const ZEALOS_HEIGHT = 768;
export const CONTROL_MODES = ["watch", "shared", "user"];
export const GOLDEN_SNAPSHOT = "golden";

export const FLAVOR_LABELS = {
  tinkeros: "TinkerOS 5.20-rc10",
  templeos: "TempleOS 5.03",
  zealos: "ZealOS",
};

/** Cap pane polls so /frame never starves the Hermes gateway (≤5 fps). */
export const POLL_VISIBLE_MS = 250;
export const POLL_FOCUSED_MS = 200;
export const POLL_IDLE_MS = 1000;
export const POLL_STOPPED_MS = 1500;
export const POLL_HIDDEN_MS = 5000;
export const POLL_SLOW_MS = 2000;

export function guestSize(flavor, status) {
  if (status && Number(status.width) > 0 && Number(status.height) > 0) {
    return { width: Number(status.width), height: Number(status.height) };
  }
  if (flavor === "zealos") return { width: ZEALOS_WIDTH, height: ZEALOS_HEIGHT };
  return { width: DEFAULT_WIDTH, height: DEFAULT_HEIGHT };
}

export function flavorLabel(flavor, flavorName) {
  if (flavorName) return String(flavorName);
  return FLAVOR_LABELS[flavor] || flavor || "TinkerOS";
}

export function integerScale(innerWidth, innerHeight, guestWidth, guestHeight) {
  const w = Number(innerWidth) || 0;
  const h = Number(innerHeight) || 0;
  const gw = Number(guestWidth) || DEFAULT_WIDTH;
  const gh = Number(guestHeight) || DEFAULT_HEIGHT;
  const raw = Math.min(w / gw, h / gh);
  const scale = Math.max(1, Math.floor(raw || 1));
  return { scale, width: gw * scale, height: gh * scale };
}

export const SCREEN_SIZE_KEY = "templeos.screenSize";

function positive(value, fallback) {
  const number = Number(value);
  if (Number.isFinite(number) && number > 0) return number;
  return fallback;
}

/** Largest aspect-preserving scale that fits beside Terry and above the log.
 *  railWidth is Terry's column only. logHeight comes out of the vertical space.
 *  Fractional CSS scales are allowed. A zero measurement falls back to 1x. */
export function fitGuestDisplay(viewport, guest, railWidth, gap = 12, logHeight = 0) {
  const gw = positive(guest && guest.width, DEFAULT_WIDTH);
  const gh = positive(guest && guest.height, DEFAULT_HEIGHT);
  const rail = Math.max(0, Number(railWidth) || 0);
  const gutter = Math.max(0, Number(gap) || 0);
  const log = Math.max(0, Number(logHeight) || 0);
  const availableWidth = Math.max(0, (Number(viewport && viewport.width) || 0) - rail - gutter);
  const availableHeight = Math.max(0, (Number(viewport && viewport.height) || 0) - log);
  if (availableWidth <= 0 || availableHeight <= 0) {
    return { scale: 1, width: gw, height: gh, availableWidth: availableWidth, availableHeight: availableHeight };
  }
  const scale = Math.min(availableWidth / gw, availableHeight / gh);
  return { scale: scale, width: gw * scale, height: gh * scale, availableWidth: availableWidth, availableHeight: availableHeight };
}

/** Decide whether the rail sits beside the stage. A stacked layout must not
 *  subtract the rail width from the screen. */
export function measureScreenSpace(metrics, gap = 12) {
  const gutter = Math.max(0, Number(gap) || 0);
  const hatch = Math.max(0, Number(metrics && metrics.hatchHeight) || 0);
  const log = Math.max(0, Number(metrics && metrics.logHeight) || 0);
  const height = Math.max(0, (Number(metrics && metrics.stageHeight) || 0) - hatch);
  const railW = Math.max(0, Number(metrics && metrics.railWidth) || 0);
  const railLeft = metrics ? metrics.railLeft : null;
  const stageRight = metrics ? metrics.stageRight : null;
  const sideBySide =
    railW > 0 &&
    railLeft != null &&
    stageRight != null &&
    Number.isFinite(Number(railLeft)) &&
    Number.isFinite(Number(stageRight)) &&
    Number(railLeft) + 1 >= Number(stageRight);
  if (sideBySide) {
    const body = Number(metrics && metrics.bodyWidth) || 0;
    const stage = Number(metrics && metrics.stageWidth) || 0;
    const width = body > 0 ? body : stage + railW + gutter;
    return { width: width, height: height, rail: railW, gap: gutter, log: log };
  }
  const stage = Number(metrics && metrics.stageWidth) || 0;
  const body = Number(metrics && metrics.bodyWidth) || 0;
  return { width: stage > 0 ? stage : body, height: height, rail: 0, gap: gutter, log: log };
}

export function maxScreenWidth(availableWidth, availableHeight, guestWidth, guestHeight) {
  const gw = positive(guestWidth, DEFAULT_WIDTH);
  const gh = positive(guestHeight, DEFAULT_HEIGHT);
  const byW = Number(availableWidth) || 0;
  const byH = Number(availableHeight) || 0;
  if (byW <= 0 || byH <= 0) return Math.max(gw, byW, (byH / gh) * gw);
  return Math.max(gw, Math.min(byW, (byH / gh) * gw));
}

export function clampScreenWidth(width, guestWidth, maxWidth) {
  const min = positive(guestWidth, DEFAULT_WIDTH);
  let max = Number(maxWidth);
  if (!Number.isFinite(max) || max <= 0) max = min;
  max = Math.max(min, max);
  const next = Number(width);
  if (!Number.isFinite(next)) return min;
  return Math.min(max, Math.max(min, next));
}

export function parseScreenPref(raw) {
  const fallback = { mode: "fit", width: 0 };
  if (raw == null || raw === "") return fallback;
  let parsed = raw;
  if (typeof raw === "string") {
    try {
      parsed = JSON.parse(raw);
    } catch (err) {
      return fallback;
    }
  }
  if (!parsed || typeof parsed !== "object") return fallback;
  const width = Number(parsed.width);
  return {
    mode: parsed.mode === "manual" ? "manual" : "fit",
    width: Number.isFinite(width) && width > 0 ? width : 0,
  };
}

export function serializeScreenPref(pref) {
  const mode = pref && pref.mode === "manual" ? "manual" : "fit";
  const width = Math.max(0, Math.round(Number(pref && pref.width) || 0));
  return JSON.stringify({ mode: mode, width: width });
}

export function screenDisplay(pref, viewport, guest, railWidth, gap = 12, forcedScale, logHeight = 0) {
  const gw = positive(guest && guest.width, DEFAULT_WIDTH);
  const gh = positive(guest && guest.height, DEFAULT_HEIGHT);
  const mode = pref && pref.mode === "manual" ? "manual" : "fit";
  if (Number(forcedScale) > 0) {
    const scale = Number(forcedScale);
    return {
      mode: mode,
      scale: scale,
      width: gw * scale,
      height: gh * scale,
      availableWidth: gw * scale,
      availableHeight: gh * scale,
    };
  }
  const fit = fitGuestDisplay(viewport, { width: gw, height: gh }, railWidth, gap, logHeight);
  if (mode !== "manual") return { mode: "fit", ...fit };
  const known = fit.availableWidth > 0 && fit.availableHeight > 0;
  const max = known
    ? maxScreenWidth(fit.availableWidth, fit.availableHeight, gw, gh)
    : Math.max(gw, Number(pref && pref.width) || gw);
  const width = clampScreenWidth(pref && pref.width, gw, max);
  const scale = width / gw;
  return {
    mode: "manual",
    scale: scale,
    width: width,
    height: gh * scale,
    availableWidth: fit.availableWidth,
    availableHeight: fit.availableHeight,
  };
}

function browserStorage() {
  try {
    if (typeof localStorage === "undefined" || !localStorage) return null;
    return localStorage;
  } catch (err) {
    return null;
  }
}

export function readStoredScreenPref(storage) {
  const box = storage || browserStorage();
  if (!box || typeof box.getItem !== "function") return { mode: "fit", width: 0 };
  try {
    return parseScreenPref(box.getItem(SCREEN_SIZE_KEY));
  } catch (err) {
    return { mode: "fit", width: 0 };
  }
}

export function writeStoredScreenPref(pref, storage) {
  const box = storage || browserStorage();
  if (!box || typeof box.setItem !== "function") return false;
  try {
    box.setItem(SCREEN_SIZE_KEY, serializeScreenPref(pref));
    return true;
  } catch (err) {
    return false;
  }
}

export function mapPointerToGuest(clientX, clientY, rect, guestWidth, guestHeight) {
  const gw = Number(guestWidth) || DEFAULT_WIDTH;
  const gh = Number(guestHeight) || DEFAULT_HEIGHT;
  const left = rect && Number(rect.left) ? Number(rect.left) : 0;
  const top = rect && Number(rect.top) ? Number(rect.top) : 0;
  const width = rect && Number(rect.width) ? Number(rect.width) : gw;
  const height = rect && Number(rect.height) ? Number(rect.height) : gh;
  const x = Math.floor(((Number(clientX) - left) / (width || 1)) * gw);
  const y = Math.floor(((Number(clientY) - top) / (height || 1)) * gh);
  return {
    x: Math.max(0, Math.min(gw - 1, x)),
    y: Math.max(0, Math.min(gh - 1, y)),
  };
}

export function modeLabel(mode, agentPaused) {
  if (mode === "user") return "You drive";
  if (mode === "watch") return "Watch";
  if (agentPaused) return "Agent paused";
  return "Shared";
}

export function accelLabel(accel, kvm) {
  if (accel === "kvm" || kvm) return "kvm";
  if (accel === "tcg") return "tcg";
  return "off";
}

export function statusSummary(status) {
  const mode = modeLabel(status && status.mode, status && status.agent_paused);
  const running = status && status.running ? "running" : "stopped";
  const snap = (status && status.snapshot) || "none";
  const accel = accelLabel(status && status.accel, status && status.kvm);
  return `${running} · ${snap} · ${accel} · ${mode}`;
}

export function drivingChip(status) {
  const mode = status && status.mode;
  const paused = !!(status && status.agent_paused);
  const busy = !!(status && status.agent_busy);
  if (mode === "user") {
    return { kind: "user", label: "Agent paused, you're driving" };
  }
  if (mode === "shared" && paused) {
    return { kind: "user", label: "Agent paused, you're driving" };
  }
  if (busy && mode !== "user") {
    return { kind: "agent", label: "Agent is typing" };
  }
  if (mode === "watch") {
    return { kind: "watch", label: "Watching — agent can type" };
  }
  return { kind: "shared", label: "Shared — you or the agent can type" };
}

export function firstCheck(checks, names) {
  if (!checks) return undefined;
  for (const name of names) {
    if (Object.prototype.hasOwnProperty.call(checks, name) && checks[name] !== undefined) {
      return checks[name];
    }
  }
  return undefined;
}

export function checkState(value) {
  if (value === true || value === "ok" || value === "present" || value === "ready") return "ok";
  if (value === false) return "no";
  if (typeof value === "string") {
    const lower = value.toLowerCase();
    if (lower === "missing" || lower === "false" || lower === "error" || lower === "absent" || lower === "no") return "no";
    return "unknown";
  }
  if (value && typeof value === "object") {
    if (value.ok === false) return "no";
    if (value.ok === true) return "ok";
  }
  return "unknown";
}

export function checkMissing(value) {
  return checkState(value) === "no";
}

export function needsOnboarding(status) {
  if (!status) return true;
  if (status.running) return false;
  if (status.setup_needed) return true;
  const code = status.code;
  if (code === "qemu_missing" || code === "iso_missing" || code === "iso_hash_mismatch" || code === "doctor_failed") {
    return true;
  }
  const checks = status.checks || {};
  if (checkMissing(checks.qemu) || checkMissing(checks.iso) || checkMissing(checks.iso_ok) || checkMissing(checks.iso_present)) {
    return true;
  }
  return false;
}

export function pollIntervalMs(state) {
  const hidden = !!(state && (state.hidden || state.documentHidden));
  const running = !!(state && state.running);
  const unchanged = !!(state && state.unchanged);
  const focused = !!(state && state.focused);
  const slow = !!(state && state.slow);
  if (hidden) return POLL_HIDDEN_MS;
  if (!running) return POLL_STOPPED_MS;
  if (slow) return Math.max(POLL_SLOW_MS, POLL_IDLE_MS);
  if (unchanged && !focused) return POLL_IDLE_MS;
  if (focused) return POLL_FOCUSED_MS;
  return POLL_VISIBLE_MS;
}

export function isReleaseHatch(event) {
  if (!event) return false;
  return event.key === "Escape" && !event.shiftKey && !event.altKey && !event.ctrlKey && !event.metaKey;
}

const CODE_QCODES = {
  Enter: "ret",
  Escape: "esc",
  Backspace: "backspace",
  Tab: "tab",
  " ": "spc",
  Space: "spc",
  ArrowUp: "up",
  ArrowDown: "down",
  ArrowLeft: "left",
  ArrowRight: "right",
  Delete: "delete",
  Home: "home",
  End: "end",
  PageUp: "pgup",
  PageDown: "pgdn",
  Insert: "insert",
  Shift: "shift",
  Control: "ctrl",
  Alt: "alt",
  Meta: "meta_l",
  CapsLock: "caps_lock",
  ContextMenu: "menu",
  Minus: "minus",
  Equal: "equal",
  BracketLeft: "bracket_left",
  BracketRight: "bracket_right",
  Backslash: "backslash",
  Semicolon: "semicolon",
  Quote: "apostrophe",
  Comma: "comma",
  Period: "dot",
  Slash: "slash",
  Backquote: "grave_accent",
  IntlBackslash: "backslash",
};

const PHYSICAL_CODES = {
  Minus: "minus",
  Equal: "equal",
  BracketLeft: "bracket_left",
  BracketRight: "bracket_right",
  Backslash: "backslash",
  Semicolon: "semicolon",
  Quote: "apostrophe",
  Comma: "comma",
  Period: "dot",
  Slash: "slash",
  Backquote: "grave_accent",
  Space: "spc",
};

export function qcodeFor(event) {
  if (!event) return "";
  const key = event.key;
  if (key && CODE_QCODES[key]) return CODE_QCODES[key];
  const code = event.code || "";
  if (PHYSICAL_CODES[code]) return PHYSICAL_CODES[code];
  const fn = /^F([1-9]|1[0-2])$/.exec(key) || /^F([1-9]|1[0-2])$/.exec(code);
  if (fn) return "f" + fn[1];
  const digit = /^Digit([0-9])$/.exec(code);
  if (digit) return digit[1];
  const letter = /^Key([A-Z])$/.exec(code);
  if (letter) return letter[1].toLowerCase();
  if (key && /^[a-z0-9]$/i.test(key) && key.length === 1) return key.toLowerCase();
  return "";
}

export function keyEventToPayload(event) {
  if (!event) return null;
  if (isReleaseHatch(event)) return { hatch: true };
  if (event.key && event.key.length === 1 && !event.ctrlKey && !event.altKey && !event.metaKey) {
    return { type: "type", text: event.key };
  }
  const qcode = qcodeFor(event);
  if (!qcode) return null;
  const keys = [];
  if (event.ctrlKey) keys.push("ctrl");
  if (event.altKey) keys.push("alt");
  if (event.shiftKey && event.key && event.key.length !== 1) keys.push("shift");
  if (qcode !== "ctrl" && qcode !== "alt" && qcode !== "shift") keys.push(qcode);
  if (!keys.length) return null;
  return { type: "keys", keys };
}

export function nextMode(op, current) {
  const token = String(op || "").toLowerCase().replace("-", "_");
  if (token === "take" || token === "take_control" || token === "user") return "user";
  if (token === "handback" || token === "hand_back" || token === "shared") return "shared";
  if (token === "watch") return "watch";
  return current || "shared";
}

export function userMayInput(mode) {
  return mode !== "watch";
}

export function formatLogTime(event) {
  if (!event) return "";
  const raw = event.at || event.ts;
  if (typeof raw === "number") {
    const date = new Date(raw * (raw < 1e12 ? 1000 : 1));
    if (!Number.isNaN(date.getTime())) {
      return date.toLocaleTimeString("en-CA", { hour12: false, timeZone: "America/Toronto" });
    }
  }
  if (typeof raw === "string" && raw.length >= 19) {
    const date = new Date(raw);
    if (!Number.isNaN(date.getTime())) {
      return date.toLocaleTimeString("en-CA", { hour12: false, timeZone: "America/Toronto" });
    }
    return raw.slice(11, 19);
  }
  return "";
}

export function logLine(event) {
  if (!event) return "";
  const time = formatLogTime(event);
  const who = event.source === "user" ? "You" : "Agent";
  const summary = event.summary || [event.tool, event.op].filter(Boolean).join(" ");
  const suffix = event.ok === false ? " (failed)" : "";
  return (time ? time + "  " : "") + who + "  " + summary + suffix;
}

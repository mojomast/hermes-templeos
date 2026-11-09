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

/** Visible running: ~10–15 fps. Idle or hidden backs off. */
export const POLL_VISIBLE_MS = 80;
export const POLL_FOCUSED_MS = 70;
export const POLL_IDLE_MS = 400;
export const POLL_STOPPED_MS = 800;
export const POLL_HIDDEN_MS = 2000;

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
  if (hidden) return POLL_HIDDEN_MS;
  if (!running) return POLL_STOPPED_MS;
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

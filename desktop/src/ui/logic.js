/** Pure helpers for the TempleOS pane. */

export const DEFAULT_WIDTH = 640;
export const DEFAULT_HEIGHT = 480;
export const ZEALOS_WIDTH = 1024;
export const ZEALOS_HEIGHT = 768;
export const CONTROL_MODES = ["watch", "shared", "user"];

export function guestSize(flavor) {
  if (flavor === "zealos") return { width: ZEALOS_WIDTH, height: ZEALOS_HEIGHT };
  return { width: DEFAULT_WIDTH, height: DEFAULT_HEIGHT };
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

/** High-resolution Terry v4 rig renderer.
 *
 * Fan tribute to Terry A. Davis — not affiliated with TempleOS or his estate.
 * The v4 part bundle is stored at desktop/assets/companion/terry/v4/ and is
 * LANCZOS-downsampled to slot_size * 3.5. Draw those parts at their original
 * slot size inside the rig coordinate space, then let the canvas backing
 * store scale the whole figure smoothly. Never use the 192x208 atlas here.
 */

export const STUB_SLOTS = Object.freeze([
  "ear_l",
  "ear_r",
  "hair",
  "brow_l",
  "brow_r",
  "eye_l",
  "eye_r",
  "nose",
  "mouth",
]);

export const COSTUME_VARIANTS = Object.freeze({
  base: Object.freeze({}),
  cowboy: Object.freeze({ cap: "cowboy", torso_overlay: "cowboy_vest" }),
  wizard: Object.freeze({ cap: "wizard", torso_overlay: "wizard_robe" }),
  chef: Object.freeze({ cap: "chef", torso_overlay: "chef_apron" }),
});

const STUB_SET = new Set(STUB_SLOTS);
const RIG_CENTER_X = 96;
const RIG_HEIGHT = 193;
const RIG_WIDTH = 150;
const RIG_BOTTOM = 199;

export function sampleClip(clip, time) {
  if (!clip || !clip.frames || !clip.frames.length) return null;
  const count = clip.frames.length;
  const duration = Number(clip.duration_ms) || 1;
  const phase =
    clip.loop === false
      ? Math.max(0, Math.min(1, time / duration)) * (count - 1)
      : ((((time % duration) + duration) % duration) / duration) * count;
  const index = Math.min(count - 1, Math.max(0, Math.floor(phase)));
  const frame = clip.frames[index];
  return { ...frame, parts: { ...(frame.parts || {}) }, variants: { ...(frame.variants || {}) } };
}

export function speechPlate(events, time, fallback = "neutral") {
  let chosen = fallback;
  for (const event of events || []) {
    if (Number(event.time_ms) > time) break;
    if (event.plate) chosen = event.plate;
  }
  return chosen;
}

function variantPath(spec, variant) {
  if (!spec || !spec.variants) return "";
  return spec.variants[variant] || spec.variants.default || "";
}

export function drawFrame(ctx, frame, registry, images, costume = "base", options = {}) {
  if (!frame || !registry || !registry.slots) return;
  const parts = { ...(frame.parts || {}) };
  const variants = { ...(frame.variants || {}) };
  const costumeMap = COSTUME_VARIANTS[costume] || COSTUME_VARIANTS.base;

  if (costumeMap.torso_overlay && !parts.torso_overlay && parts.torso) {
    parts.torso_overlay = { ...parts.torso };
  }
  Object.assign(variants, costumeMap);
  if (options.headPlate) variants.head_base = options.headPlate;

  const hidden = new Set(frame.hidden_slots || []);
  const list = Object.entries(parts).filter(([slot, pose]) => {
    if (!registry.slots[slot] || !pose || pose.alpha === 0) return false;
    if (STUB_SET.has(slot) || hidden.has(slot)) return false;
    // The package has no high-res master for the split cigarette front.
    if (slot === "cigarette_front") return false;
    return true;
  });
  list.sort(([a, pa], [b, pb]) => {
    const la = registry.slots[a].layer + (pa.layer_boost || 0);
    const lb = registry.slots[b].layer + (pb.layer_boost || 0);
    return la - lb || a.localeCompare(b);
  });

  for (const [slot, pose] of list) {
    if (pose.visible === false) continue;
    if (frame.visibility && frame.visibility[slot] === false) continue;
    if (frame.props && frame.props[slot] === false) continue;
    const spec = registry.slots[slot];
    let variant = variants[slot] || pose.variant || "default";
    let path = variantPath(spec, variant);
    let image = path ? images.get(path) : null;
    if (!image) {
      path = spec.variants && spec.variants.default;
      image = path ? images.get(path) : null;
    }
    if (!image) continue;
    const pivot = pose.pivot || spec.pivot || [0, 0];
    const size = spec.size || [image.width || 1, image.height || 1];
    ctx.save();
    ctx.globalAlpha = pose.alpha == null ? 1 : pose.alpha;
    ctx.translate(pose.x || 0, pose.y || 0);
    ctx.rotate(((pose.rot || 0) * Math.PI) / 180);
    ctx.scale((pose.flip ? -1 : 1) * (pose.sx == null ? 1 : pose.sx), pose.sy == null ? 1 : pose.sy);
    ctx.drawImage(image, -pivot[0], -pivot[1], size[0], size[1]);
    ctx.restore();
  }
}

function drawSmoke(ctx, frame, data, images, time) {
  const emitter = frame && frame.emitter;
  if (!emitter || !emitter.active || !data.smoke || !data.smoke.presets) return;
  const preset = data.smoke.presets[emitter.type];
  if (!preset || !preset.textures || !preset.textures.length) return;
  const joints = frame.joints || {};
  const origin = joints[emitter.origin_joint] || [96, 82];
  const offset = emitter.start_offset || [0, 0];
  const direction = emitter.direction || [1, -0.12];
  const start = preset.scale_start || [0.2, 0.2];
  const end = preset.scale_end == null ? 0.4 : preset.scale_end;
  const seconds = Math.max(0, Number(time) || 0) / 1000;
  for (let i = 0; i < 4; i += 1) {
    const key = preset.textures[i % preset.textures.length];
    const asset = data.smoke.assets && data.smoke.assets[key];
    if (!asset) continue;
    const image = images.get(asset.path);
    if (!image) continue;
    const life = 1.4;
    const u = ((seconds + i * 0.37) % life) / life;
    const scale = start[0] + (end - start[0]) * u;
    const x = origin[0] + offset[0] + direction[0] * u * 14 + Math.sin(seconds * 2 + i) * 2;
    const y = origin[1] + offset[1] + direction[1] * u * 14 - u * 10;
    ctx.save();
    ctx.globalAlpha = (preset.opacity == null ? 0.3 : preset.opacity) * (1 - u);
    ctx.translate(x, y);
    ctx.rotate((i - 1.5) * 0.12 + u * 0.2);
    ctx.scale(scale, scale);
    ctx.drawImage(image, -asset.anchor[0], -asset.anchor[1], asset.size[0], asset.size[1]);
    ctx.restore();
  }
}

/** Smooth, DPR-aware canvas fit. The rig is 192x208; the visible figure is
 * about 175px tall, so a 750px dock maps to a ~660px figure. */
export function renderScene(canvas, data, images, frame, costume = "base", options = {}) {
  if (!canvas || !canvas.getContext) return null;
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;
  const rect = typeof canvas.getBoundingClientRect === "function" ? canvas.getBoundingClientRect() : null;
  const cssW = Math.max(1, (rect && rect.width) || canvas.clientWidth || 600);
  const cssH = Math.max(1, (rect && rect.height) || canvas.clientHeight || 750);
  const dpr = (typeof window !== "undefined" && Number(window.devicePixelRatio)) || 1;
  const width = Math.max(1, Math.round(cssW * dpr));
  const height = Math.max(1, Math.round(cssH * dpr));
  if (canvas.width !== width) canvas.width = width;
  if (canvas.height !== height) canvas.height = height;

  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, cssW, cssH);
  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = "high";

  const scale = Math.min(cssH / RIG_HEIGHT, cssW / RIG_WIDTH);
  ctx.save();
  ctx.translate(cssW / 2 - RIG_CENTER_X * scale, cssH - RIG_BOTTOM * scale);
  ctx.scale(scale, scale);
  if (options.smoke) drawSmoke(ctx, frame, data, images, options.time);
  drawFrame(ctx, frame, data.registry, images, costume, options);
  ctx.restore();
  return { cssW, cssH, dpr, scale };
}

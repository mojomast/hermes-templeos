/** Terry companion atlas overlay for the TempleOS pane.
 *
 * Fan tribute to Terry A. Davis — not affiliated with TempleOS or his estate.
 * Loads atlas PNG+JSON through ctx.rest (/companion/atlas) into a Blob URL.
 * Hide / costume preferences persist through the plugin backend (plugin data dir).
 */

import { useEffect, useRef, useState } from "react";
import { jsx, jsxs } from "react/jsx-runtime";
import { blobUrlFromBase64, revokeUrl } from "./api.js";

function rowFor(atlas, name) {
  const rows = (atlas && atlas.rows) || [];
  for (let i = 0; i < rows.length; i += 1) {
    if (rows[i] && rows[i].name === name) return rows[i];
  }
  return rows[0] || null;
}

/** Canvas sprite that plays the named atlas row via requestAnimationFrame. */
export function TerryCompanionOverlay({ api, animation, costume, hidden, enabled }) {
  const canvasRef = useRef(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");
  const packRef = useRef(null);
  const animRef = useRef(animation || "idle");
  const rafRef = useRef(0);
  const startRef = useRef(0);

  animRef.current = animation || "idle";

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
    const ctx = canvas.getContext("2d");
    if (!ctx) return undefined;
    startRef.current = performance.now();

    const tick = (now) => {
      const pack = packRef.current;
      if (!pack || !pack.image || !pack.atlas) {
        rafRef.current = requestAnimationFrame(tick);
        return;
      }
      const row = rowFor(pack.atlas, animRef.current);
      const cell = pack.atlas.cell || [192, 208];
      const cw = cell[0] || 192;
      const ch = cell[1] || 208;
      if (canvas.width !== cw) canvas.width = cw;
      if (canvas.height !== ch) canvas.height = ch;
      ctx.clearRect(0, 0, cw, ch);
      if (row && row.frames && row.frames.length) {
        const frameMs = Number(row.frame_ms) || Number(pack.atlas.loop_ms) / row.frames.length || 183;
        const elapsed = Math.max(0, now - startRef.current);
        const index = Math.floor(elapsed / frameMs) % row.frames.length;
        const frame = row.frames[index];
        ctx.drawImage(pack.image, frame.x, frame.y, frame.w, frame.h, 0, 0, cw, ch);
      }
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      rafRef.current = 0;
    };
  }, [ready, hidden, enabled, animation]);

  if (enabled === false) return null;
  if (hidden) return null;

  return jsxs("div", {
    className: "tos-companion",
    "data-testid": "companion",
    "data-animation": animation || "idle",
    "data-costume": costume || "base",
    title: "Terry companion — fan tribute to Terry A. Davis",
    children: [
      ready
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
            children: options.map((name) =>
              jsx("option", { value: name, children: name }, name)
            ),
          }),
        ],
      }),
    ],
  });
}

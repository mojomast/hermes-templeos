import { jsx, jsxs, useEffect, useRef, useState } from "react/jsx-runtime";
import { createApi, blobUrlFromBase64, revokeUrl, errorText } from "./api.js";
import { getHostTransport } from "./host.js";
import { guestSize, integerScale, modeLabel, statusSummary } from "./logic.js";

export function TempleOSPane() {
  const transport = getHostTransport() || {};
  const api = createApi(transport.rest);
  const [status, setStatus] = useState({
    running: false,
    mode: "shared",
    agent_paused: false,
    accel: null,
    snapshot: null,
    flavor: "tinkeros",
    kvm: false,
  });
  const [error, setError] = useState("");
  const [log, setLog] = useState([]);
  const [frameUrl, setFrameUrl] = useState("");
  const prevUrl = useRef("");

  function note(line) {
    setLog((rows) => [line, ...rows].slice(0, 20));
  }

  function applyStatus(body) {
    if (!body || typeof body !== "object") return;
    setStatus((prev) => ({ ...prev, ...body }));
  }

  useEffect(() => {
    let cancelled = false;
    const tick = () => {
      api
        .status()
        .then((body) => {
          if (!cancelled) applyStatus(body);
        })
        .catch((err) => {
          if (!cancelled) setError(errorText(err));
        });
      api
        .frame()
        .then((body) => {
          if (cancelled) return;
          const next = blobUrlFromBase64(body && body.data, body && body.mime);
          if (!next) return;
          revokeUrl(prevUrl.current);
          prevUrl.current = next;
          setFrameUrl(next);
        })
        .catch(() => {
          /* look may be not_implemented; status still drives the chip */
        });
    };
    tick();
    const intervalFn =
      typeof transport.setInterval === "function" ? transport.setInterval : null;
    const handle = intervalFn ? intervalFn(tick, 200) : null;
    return () => {
      cancelled = true;
      if (handle && typeof transport.clearInterval === "function") {
        transport.clearInterval(handle);
      }
      revokeUrl(prevUrl.current);
      prevUrl.current = "";
    };
  }, []);

  function setMode(op) {
    api
      .control({ op })
      .then((body) => {
        applyStatus(body);
        setError("");
        note(op === "take" ? "You took control." : op === "watch" ? "Watch only." : "Handed back to shared.");
      })
      .catch((err) => setError(errorText(err)));
  }

  function onCanvasClick(event) {
    if (status.mode === "watch") return;
    const size = guestSize(status.flavor);
    const box = event.currentTarget;
    const rect = box.getBoundingClientRect ? box.getBoundingClientRect() : { left: 0, top: 0, width: size.width, height: size.height };
    const x = Math.floor(((event.clientX - rect.left) / (rect.width || 1)) * size.width);
    const y = Math.floor(((event.clientY - rect.top) / (rect.height || 1)) * size.height);
    api
      .input({ type: "click", x, y, button: "left" })
      .then((body) => applyStatus(body))
      .catch((err) => setError(errorText(err)));
  }

  const size = guestSize(status.flavor);
  const scaled = integerScale(size.width * 2, size.height * 2, size.width, size.height);
  const chip = statusSummary(status);

  return jsxs("div", {
    className: "tos-pane",
    "data-testid": "pane",
    children: [
      jsxs("header", {
        className: "tos-bar",
        children: [
          jsx("div", {
            className: "tos-chip",
            "data-testid": "status-chip",
            "data-mode": status.mode,
            "data-paused": status.agent_paused ? "1" : "0",
            children: chip,
          }),
          jsx("button", {
            type: "button",
            className: "tos-btn",
            "data-testid": "take-control",
            onClick: () => setMode("take"),
            children: "Take control",
          }),
          jsx("button", {
            type: "button",
            className: "tos-btn",
            "data-testid": "hand-back",
            onClick: () => setMode("handback"),
            children: "Hand back",
          }),
        ],
      }),
      jsx("div", {
        className: "tos-screen",
        "data-testid": "screen",
        style: { width: scaled.width, height: scaled.height },
        onClick: onCanvasClick,
        children: frameUrl
          ? jsx("img", {
              alt: "TempleOS guest",
              src: frameUrl,
              width: scaled.width,
              height: scaled.height,
            })
          : jsx("div", {
              className: "tos-placeholder",
              "data-testid": "placeholder",
              children: status.running ? "Waiting for a frame…" : "VM stopped. Ask the agent to start it.",
            }),
      }),
      status.agent_paused
        ? jsx("div", { className: "tos-paused", "data-testid": "agent-paused", children: modeLabel(status.mode, true) })
        : null,
      error ? jsx("div", { className: "tos-error", "data-testid": "error", children: error }) : null,
      jsxs("section", {
        className: "tos-log",
        "data-testid": "agent-log",
        children: [
          jsx("h2", { children: "Agent log" }),
          log.length
            ? log.map((line, i) => jsx("p", { children: line }, String(i)))
            : jsx("p", { children: "The agent has not injected input yet." }),
        ],
      }),
    ],
  });
}

import { jsx } from "react/jsx-runtime";
import { setHostTransport } from "./host.js";
import { TempleOSPane } from "./pane.js";

export const PANE_ID = "templeos";
export const PANE_TITLE = "TempleOS";

export function createPaneContribution() {
  return {
    id: PANE_ID,
    title: PANE_TITLE,
    area: "panes",
    order: 45,
    data: { placement: "right", width: "920px" },
    render: function renderTempleOS() {
      return jsx(TempleOSPane, {});
    },
  };
}

/**
 * Desktop entry. The pane talks only through ctx.rest (plugin routes).
 * Hermes >= 0.23.0. No token reads, no loopback from the iframe.
 */
export function registerTempleOSPane(ctx) {
  if (!ctx || typeof ctx.register !== "function") return false;
  const rest =
    typeof ctx.rest === "function"
      ? function templeosRest(path, opts) {
          return ctx.rest(path, opts);
        }
      : null;
  setHostTransport({
    rest,
    setInterval: typeof ctx.setInterval === "function" ? ctx.setInterval.bind(ctx) : null,
    clearInterval: typeof ctx.clearInterval === "function" ? ctx.clearInterval.bind(ctx) : null,
  });
  ctx.register(createPaneContribution());
  return true;
}

export function createDesktopPlugin() {
  return {
    id: "templeos",
    name: PANE_TITLE,
    defaultEnabled: true,
    register: registerTempleOSPane,
  };
}

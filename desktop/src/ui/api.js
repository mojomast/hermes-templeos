/** ctx.rest client. Paths stay inside this plugin's namespace. Never dial loopback from the iframe. */

const SOFT_CODES = {
  not_implemented: true,
  vm_not_running: true,
};

function joinPath(path, query) {
  if (!query) return path;
  const parts = [];
  Object.keys(query).forEach((key) => {
    const value = query[key];
    if (value == null || value === "") return;
    parts.push(encodeURIComponent(key) + "=" + encodeURIComponent(String(value)));
  });
  if (!parts.length) return path;
  return path + "?" + parts.join("&");
}

export function createApi(rest) {
  function call(path, options) {
    if (typeof rest !== "function") {
      return Promise.reject(
        new Error("TempleOS backend is not connected. Enable the plugin, then Rescan.")
      );
    }
    const opts = options ? { ...options } : {};
    // Host authentication belongs to ctx.rest. Never attach grants or headers.
    if (opts.headers) delete opts.headers;
    return Promise.resolve(rest(path, opts)).then((body) => {
      if (!body || typeof body !== "object") {
        throw new Error("TempleOS returned an empty response.");
      }
      if (body.ok === false && !SOFT_CODES[body.code]) {
        const error = new Error(body.error || "TempleOS could not finish that.");
        error.fix = body.fix || "";
        error.code = body.code || "";
        throw error;
      }
      return body;
    });
  }

  return {
    health: () => call("/health"),
    status: () => call("/status"),
    frame: (opts) => call(joinPath("/frame", opts && opts.since ? { since: opts.since } : null)),
    control: (body) => call("/control", { method: "POST", body }),
    input: (body) => call("/input", { method: "POST", body }),
    vm: (body) => call("/vm", { method: "POST", body }),
    start: (body) => call("/vm", { method: "POST", body: { ...(body || {}), op: "start" } }),
    stop: () => call("/vm", { method: "POST", body: { op: "stop" } }),
    reset: () => call("/vm", { method: "POST", body: { op: "reset" } }),
    snapshots: () => call("/snapshots"),
    saveSnapshot: (name) => call("/snapshots", { method: "POST", body: { op: "save", name: name || "golden" } }),
    restoreSnapshot: (name) => call("/snapshots", { method: "POST", body: { op: "restore", name: name || "golden" } }),
    log: () => call("/log"),
    doctor: () => call("/doctor"),
    setup: (body) => call("/setup", { method: "POST", body: body || {} }),
    companion: () => call("/companion"),
    companionSet: (body) => call("/companion", { method: "POST", body: body || {} }),
    companionAtlas: (opts) =>
      call(joinPath("/companion/atlas", opts && opts.costume ? { costume: opts.costume } : null)),
  };
}

export function blobUrlFromBase64(data, mime) {
  if (typeof data !== "string" || !data) return "";
  if (
    typeof atob !== "function" ||
    typeof Blob === "undefined" ||
    typeof URL === "undefined" ||
    !URL.createObjectURL
  ) {
    return "";
  }
  const binary = atob(data);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  const url = URL.createObjectURL(new Blob([bytes], { type: mime || "image/png" }));
  return url;
}

export function revokeUrl(url) {
  if (url && typeof url === "string" && url.slice(0, 5) === "blob:" && typeof URL !== "undefined" && URL.revokeObjectURL) {
    URL.revokeObjectURL(url);
  }
}

export function isAbortError(error) {
  if (!error) return false;
  if (error.name === "AbortError") return true;
  if (error.code === "ABORT_ERR" || error.code === 20) return true;
  const message = String(error.message || error || "");
  return /signal is aborted|aborted without reason|The operation was aborted|AbortError/i.test(message);
}

export function errorText(error) {
  if (isAbortError(error)) return "";
  const message = (error && error.message) || "Something went wrong.";
  const fix = error && error.fix;
  return fix ? message + " " + fix : message;
}

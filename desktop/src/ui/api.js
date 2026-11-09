/** ctx.rest client. Paths stay inside this plugin's namespace. Never dial loopback from the iframe. */

export function createApi(rest) {
  function call(path, options) {
    if (typeof rest !== "function") {
      return Promise.reject(
        new Error("TempleOS backend is not connected. Enable the plugin, then Rescan.")
      );
    }
    return Promise.resolve(rest(path, options || {})).then((body) => {
      if (!body || typeof body !== "object") {
        throw new Error("TempleOS returned an empty response.");
      }
      if (body.ok === false && body.code !== "not_implemented") {
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
    frame: () => call("/frame"),
    control: (body) => call("/control", { method: "POST", body }),
    input: (body) => call("/input", { method: "POST", body }),
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
  if (url && typeof URL !== "undefined" && URL.revokeObjectURL) {
    URL.revokeObjectURL(url);
  }
}

export function errorText(error) {
  const message = (error && error.message) || "Something went wrong.";
  const fix = error && error.fix;
  return fix ? message + " " + fix : message;
}

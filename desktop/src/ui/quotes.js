/** Approved Terry quote picker.
 *
 * The production list lives in desktop/terry-quotes.json and is supplied by
 * the coordinator. Nothing here invents, scrapes, or recalls a quote: the
 * picker only ever returns entries that were supplied by the caller's data
 * file.
 *
 * Schema: [{ text: str, source_title: str, source_url: str, date?: str }]
 */

export const TERRY_IDLE_INTERVAL_MS = 45000;
export const QUOTE_EVENT_KINDS = Object.freeze(["boot", "tool_success", "idle"]);

function text(value) {
  return typeof value === "string" ? value : "";
}

/** Validate one entry. Malformed entries return null and are skipped.
 *  Approved quote text is preserved verbatim; the bubble wraps/scrolls it. */
export function normalizeQuote(entry) {
  if (!entry || typeof entry !== "object" || Array.isArray(entry)) return null;
  const body = text(entry.text);
  const title = text(entry.source_title);
  const url = text(entry.source_url);
  if (!body.trim() || !title.trim() || !url.trim()) return null;
  if (entry.date != null && typeof entry.date !== "string") return null;
  return {
    text: body,
    source_title: title,
    source_url: url,
    ...(entry.date != null ? { date: entry.date } : {}),
  };
}

/** Load an array of schema entries, ignoring everything malformed. */
export function loadQuotes(raw) {
  if (!Array.isArray(raw)) return [];
  const out = [];
  for (const entry of raw) {
    const quote = normalizeQuote(entry);
    if (quote) out.push(quote);
  }
  return out;
}

function randomIndex(length, random, avoid) {
  if (length <= 0) return -1;
  const roll = Number(random());
  const safe = Number.isFinite(roll) ? Math.min(0.999999, Math.max(0, roll)) : 0;
  let index = Math.floor(safe * length);
  if (length > 1 && index === avoid) index = (index + 1) % length;
  return index;
}

/** Pick a random approved quote, or null when empty/malformed/muted. */
export function pickQuote(raw, options = {}) {
  const quotes = loadQuotes(raw);
  if (!quotes.length) return null;
  if (options.muted) return null;
  const index = randomIndex(quotes.length, options.random || Math.random, options.avoid);
  if (index < 0) return null;
  return { ...quotes[index] };
}

export function quoteKindForLogEvent(event) {
  if (!event || typeof event !== "object") return null;
  if (event.source !== "agent") return null;
  if (!event.tool) return null;
  if (event.ok === false) return null;
  return "tool_success";
}

export function quoteKindForBoot(previousRunning, nextRunning) {
  if (previousRunning === true) return null;
  if (nextRunning !== true) return null;
  return "boot";
}

/** Stateful, injectable wrapper used by the pane and by unit tests. */
export function createQuotePicker(raw, options = {}) {
  let quotes = loadQuotes(raw);
  let muted = !!options.muted;
  let lastIndex = -1;
  let timer = null;
  let idleClear = null;
  const random = typeof options.random === "function" ? options.random : Math.random;
  const idleIntervalMs = Math.max(
    1000,
    Number(options.idleIntervalMs) || TERRY_IDLE_INTERVAL_MS
  );

  function stopIdle() {
    if (timer == null) return;
    const clear =
      idleClear ||
      options.clearIntervalFn ||
      (typeof clearInterval === "function" ? clearInterval : null);
    if (typeof clear === "function") clear(timer);
    timer = null;
    idleClear = null;
  }

  return {
    get size() {
      return quotes.length;
    },
    quotes() {
      return quotes.map((quote) => ({ ...quote }));
    },
    isMuted() {
      return muted;
    },
    setMuted(next) {
      muted = !!next;
      return muted;
    },
    toggleMuted() {
      muted = !muted;
      return muted;
    },
    pick(kind) {
      if (muted || !quotes.length) return null;
      const index = randomIndex(quotes.length, random, lastIndex);
      if (index < 0) return null;
      lastIndex = index;
      return { ...quotes[index], kind: kind || "idle" };
    },
    say(sayFn, kind) {
      if (typeof sayFn !== "function") return null;
      const quote = this.pick(kind || "idle");
      if (!quote) return null;
      const opts = { kind: quote.kind, quote: { ...quote }, hold_s: 6 };
      sayFn(quote.text, opts);
      return quote;
    },
    startIdle(sayFn, idleOptions = {}) {
      stopIdle();
      if (typeof sayFn !== "function" || muted || !quotes.length) return null;
      const set =
        idleOptions.setIntervalFn ||
        (typeof setInterval === "function" ? setInterval : null);
      if (typeof set !== "function") return null;
      const interval = Math.max(
        1000,
        Number(idleOptions.intervalMs) || idleIntervalMs
      );
      idleClear =
        idleOptions.clearIntervalFn ||
        options.clearIntervalFn ||
        (typeof clearInterval === "function" ? clearInterval : null);
      timer = set(() => this.say(sayFn, "idle"), interval);
      if (timer && typeof timer.unref === "function") timer.unref();
      return timer;
    },
    stopIdle,
    idleIntervalMs,
    replace(rawQuotes) {
      quotes = loadQuotes(rawQuotes);
      lastIndex = -1;
      return quotes.length;
    },
  };
}

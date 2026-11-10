/** Tiny React stand-in for node:test. One fiber, hooks in call order. */

let fiber = null;

function ensure() {
  if (!fiber) fiber = { hooks: [], cursor: 0, effectCursor: 0, effects: [], effectSlots: [], rendering: false };
  return fiber;
}

export function useState(init) {
  const current = ensure();
  const index = current.cursor;
  current.cursor += 1;
  if (current.hooks.length <= index) {
    current.hooks.push(typeof init === "function" ? init() : init);
  }
  const set = (value) => {
    const prev = current.hooks[index];
    current.hooks[index] = typeof value === "function" ? value(prev) : value;
  };
  return [current.hooks[index], set];
}

export function useRef(init) {
  const current = ensure();
  const index = current.cursor;
  current.cursor += 1;
  if (current.hooks.length <= index) current.hooks.push({ current: init });
  return current.hooks[index];
}

function sameDeps(a, b) {
  if (!Array.isArray(a) || !Array.isArray(b)) return false;
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i += 1) {
    if (!Object.is(a[i], b[i])) return false;
  }
  return true;
}

export function useMemo(factory, deps) {
  const current = ensure();
  const index = current.cursor;
  current.cursor += 1;
  const prev = current.hooks[index];
  if (prev && prev.__memo && sameDeps(prev.deps, deps)) return prev.value;
  const value = factory();
  current.hooks[index] = { __memo: true, deps: deps, value: value };
  return value;
}

export function useEffect(fn, deps) {
  const current = ensure();
  const index = current.effectCursor;
  current.effectCursor += 1;
  current.effects.push({ index: index, fn: fn, deps: deps });
}

export function jsx(type, props, key) {
  const next = Object.assign({}, props || {});
  if (key !== undefined) next.key = key;
  if (typeof type === "function") {
    const current = ensure();
    const root = !current.rendering;
    if (root) {
      current.cursor = 0;
      current.effectCursor = 0;
      current.effects = [];
      current.rendering = true;
    }
    try {
      return type(next);
    } finally {
      if (root) current.rendering = false;
    }
  }
  return { type, props: next };
}

export const jsxs = jsx;
export const Fragment = "fragment";

export function resetFiber() {
  fiber = null;
}

export function rerender(type, props) {
  return jsx(type, props);
}

export function flushEffects() {
  const current = ensure();
  const pending = current.effects.splice(0);
  if (!current.effectSlots) current.effectSlots = [];
  const cleanups = [];
  for (const effect of pending) {
    const prev = current.effectSlots[effect.index];
    if (prev && sameDeps(prev.deps, effect.deps)) continue;
    if (prev && typeof prev.cleanup === "function") prev.cleanup();
    const cleanup = effect.fn();
    current.effectSlots[effect.index] = {
      deps: effect.deps,
      cleanup: typeof cleanup === "function" ? cleanup : null,
    };
    if (typeof cleanup === "function") cleanups.push(cleanup);
  }
  return cleanups;
}

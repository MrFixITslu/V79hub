/**
 * Single-process Sentinel maintenance fence. Register middleware first, then
 * install handler tracking before registering any other middleware or routes.
 * Persistence revision checks remain required for multiple Hub processes.
 */
export class SentinelWriteFenceError extends Error {
  constructor(message) {
    super(message);
    this.name = "SentinelWriteFenceError";
    this.code = "SENTINEL_WRITE_FENCE";
  }
}

export function createSentinelWriteFence() {
  const activeHttpWrites = new Map();
  let activeSentinelRequest = null;
  let activeStoreWrites = 0;

  function isStateChangingRequest(req) {
    if (!["GET","HEAD","OPTIONS"].includes(req.method)) return true;
    if (req.method === "OPTIONS") return false;
    // Express dispatches HEAD to GET and matches route paths case-insensitively.
    return /^\/api\/apps\/[^/]+\/launch\/?$/i.test(req.path) ||
      /^\/api\/billing\/wipay\/return\/?$/i.test(req.path) ||
      /^\/api\/ecosystem\/apps\/?$/i.test(req.path);
  }

  function retire(req, state) {
    if (state.transportEnded && state.handlers === 0) activeHttpWrites.delete(req);
  }

  function middleware(req,res,next) {
    if (!isStateChangingRequest(req)) return next();
    const sentinelRoute = /^\/api\/admin\/sentinel-qa\/organizations(?:\/|$)/i.test(req.path);
    if (activeSentinelRequest && req !== activeSentinelRequest && !sentinelRoute) {
      res.setHeader("Cache-Control","no-store");
      return res.status(423).json({error:"Hub write temporarily unavailable during Sentinel QA maintenance"});
    }
    const state = {transportEnded:false, handlers:0};
    activeHttpWrites.set(req,state);
    res.once("finish",() => { state.transportEnded=true; retire(req,state); });
    res.once("close",() => {
      state.transportEnded=true;
      retire(req,state);
    });
    // Retain the state on the request even after retirement: delayed callback
    // middleware must not resume dispatch after a disconnected request retires.
    req[sentinelState] = state;
    return next();
  }

  const sentinelState = Symbol("sentinelWriteState");
  const wrappedHandlers = new WeakMap();
  function trackHandler(handler) {
    if (wrappedHandlers.has(handler)) return wrappedHandlers.get(handler);
    function invoke(context, req, res, next, error, isError) {
      const state = req[sentinelState];
      if (!state) return isError ? handler.call(context,error,req,res,next) : handler.call(context,req,res,next);
      if (state.transportEnded) return;
      state.handlers++;
      let nextCalled = false;
      const guardedNext = (...args) => {
        if (!state.transportEnded && !nextCalled) { nextCalled=true; return next(...args); }
      };
      const settled = () => { state.handlers--; retire(req,state); };
      let result;
      try {
        result = isError ? handler.call(context,error,req,res,guardedNext) : handler.call(context,req,res,guardedNext);
      } catch (err) {
        settled();
        throw err;
      }
      if (result && typeof result.then === "function") {
        // Express 4 does not observe promises; deliver rejection to its error
        // pipeline and keep the write tracked until the handler has settled.
        return Promise.resolve(result).then(
          value => { settled(); return value; },
          err => { try { guardedNext(err); } finally { settled(); } },
        );
      }
      settled();
      return result;
    }
    const wrapped = handler.length === 4
      ? function(error,req,res,next) { return invoke(this,req,res,next,error,true); }
      : function(req,res,next) { return invoke(this,req,res,next,undefined,false); };
    wrappedHandlers.set(handler,wrapped);
    wrappedHandlers.set(wrapped,wrapped);
    return wrapped;
  }

  // Current Hub writes register directly on app. A mounted Router with writes
  // must install its own handler tracking before its internal registrations.
  function installHandlerTracking(app) {
    const wrap = value => Array.isArray(value) ? value.map(wrap) : typeof value === "function" ? trackHandler(value) : value;
    for (const method of ["use","all","get","head","post","put","patch","delete","options"]) {
      const register = app[method];
      app[method] = function(...args) { return register.apply(this,args.map(wrap)); };
    }
  }

  function beginExclusive(req) {
    if (!req || !activeHttpWrites.has(req)) {
      throw new SentinelWriteFenceError("Tracked HTTP write request required");
    }
    if (activeSentinelRequest || activeHttpWrites.size !== 1 || activeStoreWrites !== 0) {
      throw new SentinelWriteFenceError("Hub has another active state-changing operation");
    }
    activeSentinelRequest = req;
    let released = false;
    return () => {
      if (released) return;
      released = true;
      if (activeSentinelRequest === req) activeSentinelRequest = null;
    };
  }

  function beginStoreSave({sentinel = false}={}) {
    if (activeSentinelRequest && !sentinel) {
      throw new SentinelWriteFenceError("Non-Sentinel store save blocked during exclusive QA mutation");
    }
    if (sentinel && !activeSentinelRequest) {
      throw new SentinelWriteFenceError("Sentinel write attempted outside exclusive maintenance window");
    }
    activeStoreWrites++;
    let released=false;
    return () => {
      if (released) return;
      released=true;
      activeStoreWrites=Math.max(0,activeStoreWrites-1);
    };
  }

  function snapshot() {
    return {activeHttpWrites:activeHttpWrites.size,activeStoreWrites,exclusive:activeSentinelRequest !== null};
  }
  return {middleware,installHandlerTracking,trackHandler,beginExclusive,beginStoreSave,snapshot};
}

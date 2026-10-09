/**
 * Sentinel test-tenant mutation window.
 *
 * A short-lived, single-process fence for coordinated Hub HTTP mutations.
 * This does not replace multi-process PostgreSQL revision checks.
 * Register middleware before all routes and wrap every Hub store save.
 */
export class SentinelWriteFenceError extends Error {
  constructor(message) {
    super(message);
    this.name = "SentinelWriteFenceError";
    this.code = "SENTINEL_WRITE_FENCE";
  }
}

export function createSentinelWriteFence() {
  const activeHttpWrites = new Set();
  let activeSentinelRequest = null;
  let activeStoreWrites = 0;

  function isStateChangingRequest(req) {
    if (!["GET","HEAD","OPTIONS"].includes(req.method)) return true;
    if (req.method === "OPTIONS") return false;
    // Express may dispatch HEAD to a GET handler. These GET routes can create
    // external identities, persist payment events or initialize the catalog.
    return /^\/api\/apps\/[^/]+\/launch\/?$/i.test(req.path) ||
      /^\/api\/billing\/wipay\/return\/?$/i.test(req.path) ||
      /^\/api\/ecosystem\/apps\/?$/i.test(req.path);
  }

  function middleware(req,res,next) {
    if (!isStateChangingRequest(req)) return next();
    const sentinelRoute = req.path.startsWith("/api/admin/sentinel-qa/organizations");
    if (activeSentinelRequest && req !== activeSentinelRequest && !sentinelRoute) {
      res.setHeader("Cache-Control","no-store");
      return res.status(423).json({error:"Hub write temporarily unavailable during Sentinel QA maintenance"});
    }
    activeHttpWrites.add(req);
    let ended = false;
    const finished = () => {
      if (ended) return;
      ended = true;
      activeHttpWrites.delete(req);
    };
    res.once("finish",finished);
    res.once("close",finished);
    return next();
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
    return {
      activeHttpWrites: activeHttpWrites.size,
      activeStoreWrites,
      exclusive: activeSentinelRequest !== null,
    };
  }
  return {middleware,beginExclusive,beginStoreSave,snapshot};
}

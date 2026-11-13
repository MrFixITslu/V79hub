import { createOrganizationNameDeliveryWorker } from "./organization-name-delivery.mjs";

const DEFAULT_INTERVAL_MS = 30_000;

function explicitEndpoint(url, secret) {
  if (typeof url !== "string" || !url || typeof secret !== "string" || secret.length < 32) {
    throw new Error("Organisation-name delivery endpoint and 32+ character secret are required.");
  }
  let value;
  try { value = new URL(url); }
  catch { throw new Error("Organisation-name delivery endpoint URL is invalid."); }
  if (!["https:", "http:"].includes(value.protocol) || !value.hostname ||
      value.username || value.password || value.search || value.hash || value.pathname !== "/") {
    throw new Error("Organisation-name delivery endpoint must be a plain HTTP(S) origin.");
  }
  return { baseUrl: value.toString(), secret };
}

// Explicit opt-in only. The shared Hub store remains authoritative; a failed
// destination delivery never rewrites Hub state or blocks the other destination.
export function createOrganizationNameDeliveryLifecycle({
  persistence = /** @type {{mode: string, deliveryRepository: object | null} | null} */ (null),
  env = process.env,
  createWorker = createOrganizationNameDeliveryWorker,
  schedule = setInterval,
  unschedule = clearInterval,
  intervalMs = DEFAULT_INTERVAL_MS,
  logger = console,
} = {}) {
  const enabled = env.V79_ORG_NAME_DELIVERY_ENABLED || "0";
  if (!["0", "1"].includes(enabled)) {
    throw new Error("V79_ORG_NAME_DELIVERY_ENABLED must be 0 or 1.");
  }
  if (enabled === "0") {
    return {
      enabled: false,
      start() {},
      stop() {},
      async poll() { return { status: "disabled" }; },
    };
  }
  if (persistence?.mode !== "postgres" || !persistence?.deliveryRepository) {
    throw new Error("Organisation-name delivery requires Hub PostgreSQL persistence and repository.");
  }
  if (!Number.isInteger(intervalMs) || intervalMs < 5000 || intervalMs > 300_000) {
    throw new Error("Invalid organisation-name delivery polling interval.");
  }

  // Mandatory explicit origins avoid ambiguous Tiquet 3000/3050 defaults.
  const endpoints = {
    tiquet: explicitEndpoint(env.V79_ORG_NAME_TIQ_URL, env.V79_ORG_NAME_TIQ_SECRET),
    pos: explicitEndpoint(env.V79_ORG_NAME_POS_URL, env.V79_ORG_NAME_POS_SECRET),
  };
  const worker = createWorker({ repository: persistence.deliveryRepository, endpoints });
  let timer = null;
  let inFlight = false;
  let started = false;
  let stopped = false;

  async function poll() {
    if (!started || stopped) return { status: "stopped" };
    if (inFlight) return { status: "busy" };
    inFlight = true;
    try {
      const result = await worker.runOnce();
      for (const destination of ["tiquet", "pos"]) {
        const status = result?.[destination]?.status || "unknown";
        if (["worker_error", "dead_letter"].includes(status)) {
          logger.warn?.(`[Hub organisation-name delivery] ${destination}: ${status}`);
        }
      }
      return result;
    } catch {
      logger.error?.("[Hub organisation-name delivery] polling failed; retry scheduled.");
      return { status: "worker_error" };
    } finally {
      inFlight = false;
    }
  }

  function start() {
    if (started || stopped) return;
    started = true;
    timer = schedule(() => { void poll(); }, intervalMs);
    timer?.unref?.();
    void poll();
  }

  function stop() {
    if (stopped) return;
    stopped = true;
    if (timer !== null) unschedule(timer);
    timer = null;
  }

  return { enabled: true, start, stop, poll };
}

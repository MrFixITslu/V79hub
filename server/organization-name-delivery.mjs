import { signPlatformRequest } from "./platform-contract.mjs";

export const ORGANIZATION_NAME_SYNC_PATH =
  "/api/platform/organization/name/sync";

const destinations = ["tiquet", "pos"];

function deliveryUrl(config) {
  if (
    !config ||
    typeof config.baseUrl !== "string" ||
    typeof config.secret !== "string" ||
    config.secret.length < 32
  ) {
    throw new Error("Destination configuration or signing secret is missing.");
  }

  const base = new URL(config.baseUrl);
  if (
    !["http:", "https:"].includes(base.protocol) ||
    base.username || base.password ||
    base.search || base.hash ||
    base.pathname !== "/"
  ) {
    throw new Error("Invalid destination base URL.");
  }

  return new URL(ORGANIZATION_NAME_SYNC_PATH, base).toString();
}

export function createOrganizationNameDeliveryWorker({
  repository,
  endpoints,
  fetchImpl = fetch,
  timeoutMs = 8000,
}) {
  if (!Number.isInteger(timeoutMs) ||
      timeoutMs < 1000 || timeoutMs > 30000) {
    throw new Error("Invalid delivery timeout.");
  }

  async function deliverOnce(destination) {
    if (!destinations.includes(destination)) {
      throw new Error("Invalid destination.");
    }

    // Validate configuration before claiming a database lease.
    const config = endpoints?.[destination];
    const url = deliveryUrl(config);

    const job = await repository.claimOrganizationNameDelivery(destination);
    if (!job) return { destination, status: "idle" };

    if (job.destination !== destination) {
      throw new Error("Claimed delivery destination mismatch.");
    }

    const payload = {
      eventId: job.eventId,
      organizationId: job.organizationId,
      destination,
      name: job.name,
      nameRevision: job.nameRevision,
    };

    const body = JSON.stringify(payload);
    const timestamp = String(Date.now());

    try {
      const signature = signPlatformRequest({
        method: "POST",
        pathname: ORGANIZATION_NAME_SYNC_PATH,
        timestamp,
        body,
        secret: config.secret,
      });

      const response = await fetchImpl(url, {
        method: "POST",
        redirect: "error",
        signal: AbortSignal.timeout(timeoutMs),
        headers: {
          "content-type": "application/json",
          "x-v79-service-id": "v79-hub",
          "x-v79-timestamp": timestamp,
          "x-v79-signature": signature,
        },
        body,
      });

      if (!response.ok) {
        throw new Error(`Destination returned HTTP ${response.status}`);
      }

      const ack = await response.json();

      if (
        ack?.accepted !== true ||
        ack.eventId !== job.eventId ||
        ack.organizationId !== job.organizationId ||
        ack.destination !== destination ||
        ack.name !== job.name ||
        ack.nameRevision !== job.nameRevision
      ) {
        throw new Error("Destination acknowledgement mismatch.");
      }
    } catch (error) {
      const status = await repository.markOrganizationNameFailed({
        id: job.id,
        leaseToken: job.leaseToken,
        attempts: job.attempts,
        error,
      });

      return { destination, status, eventId: job.eventId };
    }

    // Only an exact persisted acknowledgement permits this transition.
    await repository.markOrganizationNameDelivered({
      id: job.id,
      leaseToken: job.leaseToken,
    });

    return {
      destination,
      status: "delivered",
      eventId: job.eventId,
    };
  }

  async function runOnce() {
    const results = await Promise.allSettled(
      destinations.map(deliverOnce),
    );

    return Object.fromEntries(results.map((result, i) => [
      destinations[i],
      result.status === "fulfilled"
        ? result.value
        : {
            destination: destinations[i],
            status: "worker_error",
            error: String(result.reason?.message || result.reason),
          },
    ]));
  }

  return { deliverOnce, runOnce };
}

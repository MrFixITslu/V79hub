/** G2.16: Command Center evidence-state presentation, NOT a runtime adapter.
 *
 * This pure transformation deliberately cannot render a trusted/live device.
 * Source self-reported "live" is NEVER proof of independent Edge attestation.
 * Historical operator TCP pilot results are never continuous uptime.
 *
 * Intended for a future native NOC UI integration after separate security
 * review. No HTTP requests, no session data, no secrets, no cookies, no writes.
 */
export type SentinelEvidenceDisplay = Readonly<{
  schemaVersion: 1;
  collectorLabel: "Simulated only" | "Self-reported; unverified" | "Unavailable";
  collectorState: "simulation_confirmed" | "unattested_claim" | "unknown";
  verifiedEdgeCollectors: 0;
  continuousMonitoringVerified: false;
  trustedForExecutiveUse: false;
  reportedServices: number | null;
  reportedServicesLabel: "Reported only; not verified devices" | "No reliable report";
  tcpPilotLabel: "Historical operator-reported TCP checks" | "No verified pilot log";
  tcpPilotChecks: number | null;
  tcpPilotSuccesses: number | null;
  tcpPilotMeanMs: number | null;
  tcpPilotIdentityVerified: false;
  customerReady: false;
}>;

type ObjectValue = Record<string, unknown>;
const obj = (v: unknown): v is ObjectValue => typeof v === "object" && v !== null && !Array.isArray(v);
const fields = (v: ObjectValue, keys: string[]) =>
  Object.keys(v).length === keys.length && keys.every(k => Object.hasOwn(v, k));

const READINESS = ["ready", "collector", "integrations"];
const PILOT_KEYS = [
  "status", "attemptsExecuted", "maxAttempts", "scheduledSlotsSkipped",
  "outcomes", "meanTcpConnectMs", "additionalProbesAuthorized",
  "continuousMonitoringEnabled", "independentlyAuthenticatedCollector",
  "trustedForExecutiveUse", "productionReady",
];

/** Accepts already redacted local evidence, never a raw packet/HTTP response.
 * Pilot summary shape intentionally narrower than raw operator terminal log.
 * The actual Acer observation itself is not cryptographically attested.
 */
export function deriveSentinelEvidenceDisplay(input: {
  readiness: unknown;
  reportedServiceCount: unknown;
  historicalPilot: unknown;
}): SentinelEvidenceDisplay {
  let collectorState: SentinelEvidenceDisplay["collectorState"] = "unknown";
  if (obj(input.readiness) && fields(input.readiness, READINESS) &&
      input.readiness.ready === true) {
    if (input.readiness.collector === "simulated-only" &&
        input.readiness.integrations === "disabled") {
      collectorState = "simulation_confirmed";
    } else if (
      typeof input.readiness.collector === "string" &&
      (input.readiness.collector === "live" || input.readiness.collector === "active")
    ) {
      collectorState = "unattested_claim";
    }
  }
  const reported = input.reportedServiceCount;
  const reportedServices = typeof reported === "number" &&
    Number.isSafeInteger(reported) && reported >= 0 && reported <= 24 ? reported : null;

  let tcpPilotChecks: number | null = null;
  let tcpPilotSuccesses: number | null = null;
  let tcpPilotMeanMs: number | null = null;
  const p = input.historicalPilot;
  if (obj(p) && fields(p, PILOT_KEYS) &&
      p.status === "bounded_one_time_pilot_finished" &&
      p.maxAttempts === 15 && p.scheduledSlotsSkipped === 0 &&
      p.attemptsExecuted === 15 &&
      p.additionalProbesAuthorized === false &&
      p.continuousMonitoringEnabled === false &&
      p.independentlyAuthenticatedCollector === false &&
      p.trustedForExecutiveUse === false &&
      p.productionReady === false &&
      obj(p.outcomes) && fields(p.outcomes, [
        "connection-failed", "refused", "tcp-open", "timeout",
      ]) &&
      Object.values(p.outcomes).every(v => typeof v === "number" && Number.isSafeInteger(v) && v >= 0) &&
      (p.outcomes["tcp-open"] as number) + (p.outcomes["connection-failed"] as number) +
      (p.outcomes.refused as number) + (p.outcomes.timeout as number) === 15 &&
      typeof p.meanTcpConnectMs === "number" && Number.isFinite(p.meanTcpConnectMs) &&
      p.meanTcpConnectMs >= 0 && p.meanTcpConnectMs <= 3000) {
    tcpPilotChecks = 15;
    tcpPilotSuccesses = p.outcomes["tcp-open"] as number;
    tcpPilotMeanMs = p.meanTcpConnectMs;
  }

  return {
    schemaVersion: 1,
    collectorLabel: collectorState === "simulation_confirmed" ? "Simulated only"
      : collectorState === "unattested_claim" ? "Self-reported; unverified" : "Unavailable",
    collectorState,
    verifiedEdgeCollectors: 0,
    continuousMonitoringVerified: false,
    trustedForExecutiveUse: false,
    reportedServices,
    reportedServicesLabel: reportedServices !== null
      ? "Reported only; not verified devices" : "No reliable report",
    tcpPilotLabel: tcpPilotChecks !== null
      ? "Historical operator-reported TCP checks" : "No verified pilot log",
    tcpPilotChecks,
    tcpPilotSuccesses,
    tcpPilotMeanMs,
    tcpPilotIdentityVerified: false,
    customerReady: false,
  };
}

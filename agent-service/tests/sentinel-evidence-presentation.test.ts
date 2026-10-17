import test from "node:test";
import assert from "node:assert/strict";
import { deriveSentinelEvidenceDisplay } from "../src/sentinel-evidence-presentation.js";

const readiness = () => ({ ready: true, collector: "simulated-only", integrations: "disabled" });
const pilot = () => ({
  status: "bounded_one_time_pilot_finished",
  attemptsExecuted: 15, maxAttempts: 15, scheduledSlotsSkipped: 0,
  outcomes: { "connection-failed": 0, refused: 0, "tcp-open": 15, timeout: 0 },
  meanTcpConnectMs: 5.1,
  additionalProbesAuthorized: false, continuousMonitoringEnabled: false,
  independentlyAuthenticatedCollector: false, trustedForExecutiveUse: false,
  productionReady: false,
});
const result = (overrides: Record<string, unknown> = {}) =>
  deriveSentinelEvidenceDisplay({
    readiness: readiness(), reportedServiceCount: 7, historicalPilot: pilot(),
    ...overrides,
  });

test("actual Acer pilot is historical and NOC is explicitly simulated-only", () => {
  const displayed = result();
  assert.equal(displayed.collectorState, "simulation_confirmed");
  assert.equal(displayed.collectorLabel, "Simulated only");
  assert.equal(displayed.reportedServices, 7);
  assert.equal(displayed.reportedServicesLabel, "Reported only; not verified devices");
  assert.equal(displayed.tcpPilotChecks, 15);
  assert.equal(displayed.tcpPilotSuccesses, 15);
  assert.equal(displayed.tcpPilotMeanMs, 5.1);
  assert.equal(displayed.tcpPilotLabel, "Historical operator-reported TCP checks");
  assert.equal(displayed.verifiedEdgeCollectors, 0);
  assert.equal(displayed.continuousMonitoringVerified, false);
  assert.equal(displayed.trustedForExecutiveUse, false);
  assert.equal(displayed.tcpPilotIdentityVerified, false);
  assert.equal(displayed.customerReady, false);
});

test("unauthenticated NOC live claim remains unverified", () => {
  for (const collector of ["live", "active"]) {
    const displayed = result({ readiness: {ready:true, collector, integrations:"active"} });
    assert.equal(displayed.collectorState, "unattested_claim");
    assert.equal(displayed.collectorLabel, "Self-reported; unverified");
    assert.equal(displayed.verifiedEdgeCollectors, 0);
    assert.equal(displayed.customerReady, false);
  }
});

test("readiness private extras never become a status or private response", () => {
  const bad = { ...readiness(), endpoint: "10.20.30.40", password: "secret_value" };
  const displayed = result({readiness:bad});
  assert.equal(displayed.collectorState, "unknown");
  assert.ok(!JSON.stringify(displayed).includes("10.20"));
  assert.ok(!JSON.stringify(displayed).includes("secret_value"));
});

test("unreliable service counts never become verified device numbers", () => {
  for(const count of [-1, 100, 2.5, "7", true, null, NaN]) {
    const displayed = result({reportedServiceCount:count});
    assert.equal(displayed.reportedServices, null);
    assert.equal(displayed.reportedServicesLabel, "No reliable report");
  }
});

test("pilot record cannot turn on streaming, source trust, or more tests", () => {
  for (const field of [
    "additionalProbesAuthorized", "continuousMonitoringEnabled",
    "independentlyAuthenticatedCollector", "trustedForExecutiveUse", "productionReady",
  ]) {
    const displayed = result({historicalPilot:{...pilot(), [field]:true}});
    assert.equal(displayed.tcpPilotChecks, null);
    assert.equal(displayed.tcpPilotLabel, "No verified pilot log");
    assert.equal(displayed.continuousMonitoringVerified, false);
  }
});

test("pilot must match one 15-attempt summary, no arbitrary extra fields", () => {
  const variants = [
    {...pilot(), attemptsExecuted:14},
    {...pilot(), maxAttempts:100},
    {...pilot(), scheduledSlotsSkipped:1},
    {...pilot(), secret:"192.168.100.163"},
    {...pilot(), meanTcpConnectMs:Infinity},
    {...pilot(), outcomes:{...pilot().outcomes, "tcp-open":14}},
    {...pilot(), outcomes:{...pilot().outcomes, timeout:1}},
  ];
  for (const historicalPilot of variants) {
    const displayed = result({historicalPilot});
    assert.equal(displayed.tcpPilotChecks, null);
    assert.equal(displayed.trustedForExecutiveUse, false);
  }
});

test("without trustworthy input, rendering is unknown, never green", () => {
  const displayed = deriveSentinelEvidenceDisplay({
    readiness:null, reportedServiceCount:null, historicalPilot:null,
  });
  assert.equal(displayed.collectorState, "unknown");
  assert.equal(displayed.reportedServices, null);
  assert.equal(displayed.tcpPilotChecks, null);
  assert.equal(displayed.verifiedEdgeCollectors, 0);
});

test("private source text cannot leak into browser-facing view model", () => {
  const displayed = result({
    historicalPilot:{...pilot(), patientNote:"PRIVATE", accessKey:"secret"},
    readiness:{...readiness(), credentials:"SECRET"},
  });
  assert.ok(!JSON.stringify(displayed).includes("SECRET"));
  assert.equal(displayed.tcpPilotChecks, null);
  assert.equal(displayed.collectorState, "unknown");
});

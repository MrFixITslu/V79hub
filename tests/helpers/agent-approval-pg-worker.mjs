import { createHubStorePersistence } from "../../server/runtime-store.mjs";
import { createAgentProposal, decideAgentProposal, appendAgentProposalAudit } from "../../server/agent-approval-ledger.mjs";
import { createAgentApprovalAuditChain, verifyAgentApprovalAuditLinkage } from "../../server/agent-approval-audit-chain.mjs";

// CI-only child process: never point this worker at a production database.
const connection = String(process.env.V79_APPROVAL_TEST_PG_URL || "");
let parsed;
try { parsed = new URL(connection); } catch { throw new Error("Isolated test database connection missing."); }
if (parsed.hostname !== "127.0.0.1" || parsed.port !== "5432" ||
    parsed.pathname !== "/v79_ci_approval" || parsed.username !== "v79_ci_agent") {
  throw new Error("Refusing any non-isolated PostgreSQL target.");
}

const ownership = { organizationId: "ci-owner-org", actorUserId: "ci-founder" };
const audit = createAgentApprovalAuditChain("ci-only-owner-approval-hmac-key-1234567890");
const normalize = raw => ({
  users: Array.isArray(raw.users) ? raw.users : [],
  agentActionProposals: Array.isArray(raw.agentActionProposals) ? raw.agentActionProposals : [],
  agentProposalAuditTrail: Array.isArray(raw.agentProposalAuditTrail) ? raw.agentProposalAuditTrail : [],
  auditEvents: Array.isArray(raw.auditEvents) ? raw.auditEvents : [],
});
const persistence = createHubStorePersistence({
  backend: "postgres", databaseUrl: connection, storeFile: "/tmp/unused-v79-ci-postgres.json",
});

async function stop() {
  try { await persistence.close(); } catch { /* test-only cleanup */ }
  process.exit(0);
}

try {
  const data = await persistence.load(normalize, () => { throw new Error("Cannot seed an empty real PostgreSQL store."); });
  if (!audit.verify(data.agentProposalAuditTrail) ||
      !verifyAgentApprovalAuditLinkage(data.agentProposalAuditTrail, data.agentActionProposals)) {
    throw new Error("Loaded approval state audit verification failed.");
  }
  if (typeof process.send !== "function") throw new Error("IPC is required for the concurrency barrier.");
  process.send({ type: "ready", revision: persistence.revision() });

  process.on("message", async message => {
    if (message?.type !== "go") return;
    const task = message.task;
    try {
      let result;
      if (task?.type === "create") {
        result = createAgentProposal(data.agentActionProposals, {
          operation: "draft_operational_report", targetSystem: "hub",
          summary: task.summary,
          rationale: "Examine safe aggregate indicators before preparing a human-only plan.",
          idempotencyKey: task.key,
        }, ownership);
      } else if (task?.type === "decision") {
        result = decideAgentProposal(data.agentActionProposals, {
          id: task.id, organizationId: ownership.organizationId, actorUserId: ownership.actorUserId,
          expectedRevision: 1, decision: task.decision,
        });
      } else {
        throw new Error("Unexpected isolated worker operation.");
      }
      if (!["created", "decided"].includes(result.kind)) {
        process.send({ type: "result", outcome: result.kind });
        return;
      }
      appendAgentProposalAudit(data.auditEvents, result.proposal,
        result.kind === "created" ? "agent.proposal.created" : "agent.proposal." + result.proposal.status,
        ownership.actorUserId);
      audit.append(data.agentProposalAuditTrail, result.proposal, ownership.actorUserId);
      await persistence.save(data);
      process.send({ type: "result", outcome: "saved", proposalId: result.proposal.id });
    } catch (error) {
      process.send({ type: "result", outcome: error?.name === "StoreRevisionConflictError" ? "stale" : "error",
        errorName: String(error?.name || "Error").slice(0,50) });
    } finally {
      await stop();
    }
  });
} catch (error) {
  process.send?.({ type: "fatal", errorName: String(error?.name || "Error").slice(0,50) });
  await stop();
}

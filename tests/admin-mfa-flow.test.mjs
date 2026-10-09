import test from "node:test";
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdtemp, rm } from "node:fs/promises";
import { createServer } from "node:http";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { totpCode } from "../server/security-contract.mjs";

async function listen(server) {
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  return `http://127.0.0.1:${server.address().port}`;
}

test("production platform admin enrolls mandatory MFA before a session is issued", { timeout: 45000 }, async t => {
  const dir = await mkdtemp(join(tmpdir(), "v79-admin-mfa-"));
  const probe = createServer();
  const origin = await listen(probe);
  await new Promise(resolve => probe.close(resolve));

  const downstreamMethods = [];
  const downstream = createServer((req, res) => {
    downstreamMethods.push(String(req.method || ""));
    res.writeHead(503, { "content-type": "application/json" });
    res.end(JSON.stringify({ available: false }));
  });
  const downstreamUrl = await listen(downstream);
  t.after(async () => {
    downstream.closeAllConnections();
    await new Promise(resolve => downstream.close(resolve));
  });

  const child = spawn(process.execPath, ["--import", "tsx", "server.ts"], {
    cwd: process.cwd(),
    env: {
      ...process.env,
      NODE_ENV: "production",
      DATA_DIR: dir,
      PORT: new URL(origin).port,
      APP_URL: origin,
      V79_HUB_ADMIN_PASSWORD: "a-unique-admin-password-1234",
      V79_HUB_ADMIN_EMAIL: "vision79slu@gmail.com",
      V79_REQUIRE_ADMIN_MFA: "1",
      V79_PLATFORM_SHARED_SECRET: "platform-test-secret-12345678901234567890",
      POS_BASE_URL: downstreamUrl,
      FFPRO_INTERNAL_URL: downstreamUrl,
      TIQUET_INTERNAL_URL: downstreamUrl,
      MARKETING_INTERNAL_URL: downstreamUrl,
      ACADEMY_INTERNAL_URL: downstreamUrl,
      LASERTAG_INTERNAL_URL: downstreamUrl,
    },
    stdio: ["ignore", "pipe", "pipe"],
  });

  let output = "";
  child.stdout.on("data", chunk => output += chunk);
  child.stderr.on("data", chunk => output += chunk);
  t.after(async () => {
    if (child.exitCode === null) {
      const exited = new Promise(resolve => child.once("exit", resolve));
      child.kill();
      await Promise.race([exited, new Promise(resolve => setTimeout(resolve, 1200))]);
    }
    await rm(dir, { recursive: true, force: true });
  });

  const request = (path, options = {}) => fetch(origin + path, { redirect: "manual", ...options });
  let ready = false;
  for (let i = 0; i < 250; i++) {
    if (child.exitCode !== null) break;
    try {
      if ((await request("/api/health")).ok) {
        ready = true;
        break;
      }
    } catch {}
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  assert.ok(ready, `Isolated MFA test server did not become ready: ${output.slice(-1200)}`);

  const login = await request("/api/auth/login", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ username: "admin", password: "a-unique-admin-password-1234" }),
  });
  assert.equal(login.status, 202, output);
  assert.equal(login.headers.get("set-cookie"), null);
  const challenge = await login.json();
  assert.equal(challenge.mfaRequired, true);
  assert.equal(challenge.setupRequired, true);
  assert.match(challenge.secret, /^[A-Z2-7]+$/);

  const retryLogin = await request("/api/auth/login", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ username: "admin", password: "a-unique-admin-password-1234" }),
  });
  assert.equal(retryLogin.status, 202, output);
  const retryChallenge = await retryLogin.json();
  assert.equal(retryChallenge.setupRequired, true);
  assert.equal(retryChallenge.secret, challenge.secret, "pending MFA enrollment must reuse the same setup secret");

  // A pending MFA challenge never creates an authenticated approval session.
  assert.equal((await request("/api/agent/proposals", {
    headers: { cookie: "v79_hub_session=not-verified" },
  })).status, 401);
  const validCode = totpCode(challenge.secret);
  const invalidCode = validCode === "000000" ? "000001" : "000000";
  const denied = await request("/api/auth/mfa/complete-login", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ challengeId: challenge.challengeId, code: invalidCode }),
  });
  assert.equal(denied.status, 401);
  assert.equal(denied.headers.get("set-cookie"), null);

  const complete = await request("/api/auth/mfa/complete-login", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ challengeId: challenge.challengeId, code: totpCode(challenge.secret) }),
  });
  assert.equal(complete.status, 200, output);
  assert.match(complete.headers.get("set-cookie") || "", /v79_hub_session=/);
  const identity = await complete.json();
  assert.equal(identity.user.platformOperator, true);
  assert.equal(identity.user.mfaEnabled, true);

  // Phase 3 approval inbox is accessible only after the owner completes MFA.
  const cookie = String(complete.headers.get("set-cookie") || "").split(";")[0];
  assert.equal((await request("/api/agent/proposals")).status, 401);
  const listing = await request("/api/agent/proposals", { headers: { cookie } });
  assert.equal(listing.status, 200);
  assert.equal((await listing.json()).executionEnabled, false);
  const proposal = {
    operation: "draft_finance_review", targetSystem: "ffpro",
    summary: "Review monthly cashflow planning",
    rationale: "Review aggregate financial trends in FFPRO without executing any payments.",
    idempotencyKey: "mfa-owner-decision-test-0001", evidenceRef: "ffpro:currentMonthNet",
  };
  const withOrigin = { "content-type": "application/json", cookie, origin };
  assert.equal((await request("/api/agent/proposals", {
    method: "POST", headers: { ...withOrigin, origin: "https://invalid.invalid" },
    body: JSON.stringify(proposal),
  })).status, 403);
  const draftResponse = await request("/api/agent/proposals", {
    method: "POST", headers: withOrigin, body: JSON.stringify(proposal),
  });
  assert.equal(draftResponse.status, 201);
  const draft = await draftResponse.json();
  assert.equal(draft.proposal.executionStatus, "disabled");
  assert.equal(draft.proposal.evidenceVerification, "unverified");
  // Simulate repeated clicks/retries during a single in-process owner session.
  // They must resolve to one ledger record, never another action or dispatch.
  const retries = await Promise.all(Array.from({ length: 5 }, () => request("/api/agent/proposals", {
    method: "POST", headers: withOrigin, body: JSON.stringify(proposal),
  })));
  for (const retry of retries) {
    assert.equal(retry.status, 200);
    const body = await retry.json();
    assert.equal(body.duplicate, true);
    assert.equal(body.proposal.id, draft.proposal.id);
    assert.equal(body.proposal.executionStatus, "disabled");
  }
  const listAfterRetries = await request("/api/agent/proposals", { headers: { cookie } });
  assert.equal(listAfterRetries.status, 200);
  assert.equal((await listAfterRetries.json()).proposals.length, 1);
  assert.equal((await request("/api/agent/proposals", {
    method: "POST", headers: withOrigin,
    body: JSON.stringify({ ...proposal, execute: true }),
  })).status, 400);
  const decisionResponse = await request("/api/agent/proposals/" + draft.proposal.id + "/decision", {
    method: "POST", headers: withOrigin,
    body: JSON.stringify({ decision: "reject", expectedRevision: 1 }),
  });
  assert.equal(decisionResponse.status, 200);
  const decision = await decisionResponse.json();
  assert.equal(decision.proposal.status, "rejected");
  assert.equal(decision.proposal.executionStatus, "disabled");
  assert.equal(decision.executionEnabled, false);

  // An MFA-verified founder can approve the plan, but never dispatch a write.
  const approvalDraft = { ...proposal, summary: "Review forecast assumptions manually",
    idempotencyKey: "mfa-owner-decision-test-0002" };
  const approvalCreate = await request("/api/agent/proposals", {
    method: "POST", headers: withOrigin, body: JSON.stringify(approvalDraft),
  });
  assert.equal(approvalCreate.status, 201);
  const approvalCreated = await approvalCreate.json();
  const approvalDecision = await request("/api/agent/proposals/" + approvalCreated.proposal.id + "/decision", {
    method: "POST", headers: withOrigin,
    body: JSON.stringify({ decision: "approve", expectedRevision: 1 }),
  });
  assert.equal(approvalDecision.status, 200);
  const approved = await approvalDecision.json();
  assert.equal(approved.proposal.status, "approved");
  assert.equal(approved.proposal.executionStatus, "disabled");
  assert.equal(approved.proposal.evidenceVerification, "unverified");
  const finalList = await request("/api/agent/proposals", { headers: { cookie } });
  assert.equal(finalList.status, 200);
  const finalBody = await finalList.json();
  assert.equal(finalBody.totalProposals, 2);
  assert.equal(finalBody.proposals.every(item => item.executionStatus === "disabled"), true);
  const olderPage = await request("/api/agent/proposals?offset=1", { headers: { cookie } });
  assert.equal(olderPage.status, 200);
  const olderPageBody = await olderPage.json();
  assert.equal(olderPageBody.offset, 1);
  assert.equal(olderPageBody.pageSize, 100);
  assert.equal(olderPageBody.proposals.length, 1);
  assert.equal(olderPageBody.proposals[0].executionStatus, "disabled");
  assert.equal((await request("/api/agent/proposals?offset=-1", { headers: { cookie } })).status, 400);
  assert.equal((await request("/api/agent/proposals?offset=501", { headers: { cookie } })).status, 400);
  assert.deepEqual(downstreamMethods.filter(method => !["GET", "HEAD"].includes(method)), [],
    "the isolated configured app endpoints must never receive a write from decision routes");

  const secondLogin = await request("/api/auth/login", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ username: "vision79slu@gmail.com", password: "a-unique-admin-password-1234" }),
  });
  assert.equal(secondLogin.status, 202, output);
  const verifyChallenge = await secondLogin.json();
  assert.equal(verifyChallenge.setupRequired, false);
  assert.equal("secret" in verifyChallenge, false);
});

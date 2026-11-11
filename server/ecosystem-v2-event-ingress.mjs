import { createHash } from "node:crypto";
import { verifyPlatformRequest } from "./platform-contract.mjs";

/**
 * Ecosystem v2 signed Tiquet ingestion.
 * The Hub receives a MINIMAL read-only audit projection. No customer details,
 * payment settlement, ticket closure, inventory changes or outbound actions.
 * Disabled by default and not a substitute for browser/staging acceptance.
 */
const TYPES = Object.freeze({
  "job.created": ["status", "priority", "origin"],
  "job.status_changed": ["status", "previousStatus"],
  "job.paid": ["status"],
  "customer.created": ["origin"],
  "payment.recorded": ["currency", "method", "provider"],
  "customer.feedback_submitted": ["rating", "contactAllowed"],
  "job.scope_acknowledged": ["version"],
});
const ID = /^[A-Za-z0-9._:@-]{4,180}$/;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const SAFE = /^[A-Za-z0-9_ .:-]{1,64}$/;
const WINDOW_MS = 90 * 86400_000;
const MAX_FUTURE_MS = 2 * 60_000;
const MAX_STORED = 2048;

function reject(reason) {
  const e = new Error("Ecosystem event rejected");
  e.reason = reason;
  return e;
}

export function mapTiquetAccount(store, organizationRef, accountRef) {
  if (!ID.test(organizationRef || "") || !ID.test(accountRef || "")) throw reject("invalid_mapping_identity");
  const org = (store?.organizations || []).find(v => v.id === organizationRef && v.status === "active");
  const mapping = (store?.appTenantMappings || []).find(v =>
    v.organizationId === organizationRef && v.appId === "app-tiquet" &&
    v.status === "active" && v.externalTenantId === accountRef
  );
  const granted = (store?.appEntitlements || []).some(v =>
    v.organizationId === organizationRef && v.appId === "app-tiquet" && v.enabled === true);
  if (!org || !mapping || !granted) throw reject("organization_not_mapped");
  return { organizationId: org.id, externalAccountId: mapping.externalTenantId };
}

/** Reject PII rather than silently copying arbitrary payload fields into Hub. */
export function projectTiquetEvent(input, verifiedOrg, nowMs = Date.now()) {
  if (!input || typeof input !== "object" || Array.isArray(input) ||
      !UUID.test(input.id || "") || input.version !== 1 ||
      !Object.hasOwn(TYPES, input.type) ||
      input.organizationRef !== verifiedOrg.organizationId ||
      input.accountRef !== verifiedOrg.externalAccountId ||
      !ID.test(input.subjectId || "") ||
      typeof input.occurredAt !== "string") throw reject("invalid_event_envelope");
  const occurred = Date.parse(input.occurredAt);
  if (!Number.isFinite(occurred) || occurred > nowMs + MAX_FUTURE_MS || occurred < nowMs - WINDOW_MS)
    throw reject("event_time_out_of_range");
  const raw = input.payload;
  if (!raw || typeof raw !== "object" || Array.isArray(raw) ||
      Buffer.byteLength(JSON.stringify(raw), "utf8") > MAX_STORED) throw reject("invalid_payload");
  const allowed = TYPES[input.type];
  if (Object.keys(raw).some(k => !allowed.includes(k))) throw reject("unapproved_event_fields");
  const payload = {};
  for (const [key, value] of Object.entries(raw)) {
    if (typeof value !== "string" || !SAFE.test(value) || /@|https?:|bearer|token|secret/i.test(value)) throw reject("unsafe_event_value");
    payload[key] = value;
  }
  if (input.type === "customer.feedback_submitted" &&
      (!/^[1-5]$/.test(payload.rating || "") ||
       !["yes","no"].includes(payload.contactAllowed)))
    throw reject("invalid_feedback_category");
  if (input.type === "job.scope_acknowledged" &&
      !/^[1-9][0-9]{0,6}$/.test(payload.version || ""))
    throw reject("invalid_scope_version");
  if (payload.currency && !/^[A-Z]{3}$/.test(payload.currency)) throw reject("invalid_currency");
  return Object.freeze({
    id: input.id, source: "tiquet", type: input.type,
    organizationId: verifiedOrg.organizationId,
    accountRef: verifiedOrg.externalAccountId,
    subjectId: input.subjectId, occurredAt: new Date(occurred).toISOString(),
    correlationId: input.correlationId == null ? null :
      (UUID.test(input.correlationId) ? input.correlationId : null),
    payload: Object.freeze(payload),
  });
}

/**
 * Separate append-only PostgreSQL inbox, not the Hub JSON document.
 * ON CONFLICT + comparison makes duplicates safe and conflicting replays fail.
 */
/**
 * Website only reports opaque lead IDs and attribution. The contact details,
 * consent records and messages remain in the Website CRM.
 */
export function projectWebsiteLeadEvent(input, trustedOwnerOrgId, store, nowMs = Date.now()) {
  if (!input || typeof input !== "object" || Array.isArray(input) ||
      !UUID.test(input.id || "") || input.type !== "lead.created" ||
      input.version !== 1 || !ID.test(trustedOwnerOrgId || "") ||
      input.organizationRef !== trustedOwnerOrgId ||
      !/^[1-9][0-9]{0,12}$/.test(input.subjectId || "") ||
      !(store?.organizations || []).some(o => o.id === trustedOwnerOrgId && o.status === "active"))
    throw reject("invalid_website_lead");
  const t = Date.parse(input.occurredAt);
  if (!Number.isFinite(t) || t > nowMs + MAX_FUTURE_MS || t < nowMs - WINDOW_MS)
    throw reject("invalid_website_event_time");
  if (!input.payload || typeof input.payload !== "object" || Array.isArray(input.payload) ||
      JSON.stringify(input.payload).length > MAX_STORED ||
      !Object.keys(input.payload).every(k => ["leadId","interest","leadSource","pageOrigin","employeesBand"].includes(k)))
    throw reject("invalid_website_payload");
  if (String(input.payload.leadId) !== input.subjectId)
    throw reject("lead_id_mismatch");
  const referral = input.payload.leadSource;
  const safeReferral = typeof referral === "string" &&
    /^[A-Za-z0-9 _.-]{1,60}$/.test(referral) ? referral : "unclassified";
  return Object.freeze({
    id:input.id,source:"website",type:"lead.created",
    organizationId:trustedOwnerOrgId, accountRef:"website",
    subjectId:"lead:"+input.subjectId,
    correlationId:UUID.test(input.correlationId || "") ? input.correlationId : null,
    occurredAt:new Date(t).toISOString(),
    payload:Object.freeze({source:safeReferral}),
  });
}

export function createWebsiteEventHandler({
  enabled=false, secret, ownerOrganizationId, getStore, inbox, now=Date.now
}) {
  return async function handle(req,res) {
    res.setHeader("Cache-Control","no-store");
    if (!enabled) return res.status(404).json({error:"Not available"});
    if (typeof secret !== "string" || secret.length < 32 || !inbox ||
        typeof getStore !== "function" || !Buffer.isBuffer(req.rawBody))
      return res.status(503).json({error:"Integration unavailable"});
    const body=req.rawBody.toString("utf8");
    if(req.get("x-v79-service-id")!=="website" ||
       !verifyPlatformRequest({method:"POST",pathname:"/api/platform/events",
         timestamp:req.get("x-v79-timestamp")||"",
         signature:req.get("x-v79-signature")||"",body,secret}))
      return res.status(401).json({error:"Invalid service signature"});
    try {
      const event=projectWebsiteLeadEvent(req.body,ownerOrganizationId,getStore(),now());
      const status=await inbox.write(event);
      return res.status(status==="duplicate"?200:202).json({status,eventId:event.id});
    }catch(err){
      if(err?.reason==="event_replay_conflict")
        return res.status(409).json({error:"Event conflict"});
      if(err?.reason) return res.status(422).json({error:"Invalid event contract"});
      return res.status(503).json({error:"Event acceptance unavailable"});
    }
  };
}

export function createEcosystemEventInbox(pool) {
  if (!pool || typeof pool.query !== "function") throw new Error("PostgreSQL pool required");
  let schemaReady;
  async function ensureSchema() {
    if (!schemaReady) {
      schemaReady = pool.query(`CREATE TABLE IF NOT EXISTS v79_ecosystem_events_v2 (
        source TEXT NOT NULL,
        event_id UUID NOT NULL,
        organization_id TEXT NOT NULL,
        account_ref TEXT NOT NULL,
        event_type TEXT NOT NULL,
        subject_id TEXT NOT NULL,
        correlation_id TEXT,
        occurred_at TIMESTAMPTZ NOT NULL,
        payload JSONB NOT NULL,
        digest CHAR(64) NOT NULL,
        received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (source, event_id)
      )`).catch(err => { schemaReady = null; throw err; });
    }
    return schemaReady;
  }
  async function write(event) {
    await ensureSchema();
    const digest = createHash("sha256").update(JSON.stringify(event)).digest("hex");
    const inserted = await pool.query(
      `INSERT INTO v79_ecosystem_events_v2
         (source,event_id,organization_id,account_ref,event_type,subject_id,correlation_id,occurred_at,payload,digest)
       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb,$10)
       ON CONFLICT (source,event_id) DO NOTHING RETURNING event_id`,
      [event.source,event.id,event.organizationId,event.accountRef,event.type,event.subjectId,
       event.correlationId || null,event.occurredAt,JSON.stringify(event.payload),digest],
    );
    if (inserted.rowCount === 1) return "accepted";
    const prior = await pool.query(
      `SELECT organization_id, account_ref, digest
         FROM v79_ecosystem_events_v2 WHERE source=$1 AND event_id=$2`,
      [event.source,event.id],
    );
    if (prior.rowCount !== 1 || prior.rows[0].digest !== digest ||
        prior.rows[0].organization_id !== event.organizationId ||
        prior.rows[0].account_ref !== event.accountRef) throw reject("event_replay_conflict");
    return "duplicate";
  }
  /**
   * @param {string} organizationId
   * @param {number} [limit]
   * @param {string | null} [correlationId]
   */
  async function latest(organizationId, limit = 30, correlationId = null) {
    if (!ID.test(organizationId || "") || !Number.isSafeInteger(limit) ||
        limit < 1 || limit > 100 ||
        (correlationId !== null && !UUID.test(correlationId)))
      throw reject("invalid_read_scope");
    await ensureSchema();
    // Every query requires an authenticated organisation; correlation IDs
    // alone never grant access to another tenant's event history.
    const query = correlationId === null
      ? `SELECT source,event_id,event_type,subject_id,correlation_id,occurred_at,received_at,payload
         FROM v79_ecosystem_events_v2
         WHERE organization_id=$1 ORDER BY received_at DESC,event_id DESC LIMIT $2`
      : `SELECT source,event_id,event_type,subject_id,correlation_id,occurred_at,received_at,payload
         FROM v79_ecosystem_events_v2
         WHERE organization_id=$1 AND correlation_id=$2
         ORDER BY occurred_at,event_id LIMIT $3`;
    const params = correlationId === null ? [organizationId,limit] :
      [organizationId,correlationId,limit];
    const data = await pool.query(query,params);
    return data.rows;
  }
  async function hasTiquetJob(organizationId,jobId) {
    if(!ID.test(organizationId||"")||!UUID.test(jobId||""))
      throw reject("invalid_job_scope");
    await ensureSchema();
    const result=await pool.query(`
      SELECT 1 FROM v79_ecosystem_events_v2
      WHERE organization_id=$1 AND source='tiquet'
        AND event_type='job.created' AND subject_id=$2 LIMIT 1
    `,[organizationId,jobId]);
    return result.rowCount===1;
  }
  return Object.freeze({ write, latest, hasTiquetJob, ensureSchema });
}

export function createTiquetEventHandler({ enabled = false, secret, getStore, inbox, now = Date.now }) {
  return async function handle(req, res) {
    res.setHeader("Cache-Control", "no-store");
    if (!enabled) return res.status(404).json({ error: "Not available" });
    // No private data in error responses; no fallback to login/SSO secrets.
    if (typeof secret !== "string" || secret.length < 32 || !inbox ||
        typeof getStore !== "function" || !Buffer.isBuffer(req.rawBody))
      return res.status(503).json({ error: "Integration unavailable" });
    const body = req.rawBody.toString("utf8");
    if (req.get("x-v79-service-id") !== "tiquet" ||
        !verifyPlatformRequest({ method:"POST", pathname:"/api/platform/events",
          timestamp:req.get("x-v79-timestamp") || "", signature:req.get("x-v79-signature") || "",
          body, secret }))
      return res.status(401).json({ error: "Invalid service signature" });
    try {
      const input = req.body;
      const mapping = mapTiquetAccount(getStore(), input?.organizationRef, input?.accountRef);
      const event = projectTiquetEvent(input, mapping, now());
      const status = await inbox.write(event);
      return res.status(status === "duplicate" ? 200 : 202).json({ status, eventId: event.id });
    } catch (err) {
      if (err?.reason === "event_replay_conflict") return res.status(409).json({ error: "Event conflict" });
      if (err?.reason === "organization_not_mapped") return res.status(409).json({ error: "Organisation mapping inactive" });
      if (err?.reason) return res.status(422).json({ error: "Invalid event contract" });
      return res.status(503).json({ error: "Event acceptance unavailable" });
    }
  };
}

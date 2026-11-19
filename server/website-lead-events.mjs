import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { verifyPlatformRequest } from './platform-contract.mjs';

export const WEBSITE_EVENT_PATH = '/api/platform/events';
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const fields = ['leadId', 'interest', 'leadSource', 'pageOrigin', 'employeesBand'];

function parseEvent(raw) {
  const e = JSON.parse(raw);
  if (!e || Array.isArray(e) || !uuid.test(e.id || '') || e.type !== 'lead.created' ||
      e.version !== 1 || typeof e.organizationRef !== 'string' ||
      !/^\d{1,16}$/.test(e.subjectId || '') || typeof e.occurredAt !== 'string' ||
      !Number.isFinite(Date.parse(e.occurredAt)) ||
      (e.correlationId !== undefined && !uuid.test(e.correlationId)) ||
      !e.payload || Array.isArray(e.payload) || typeof e.payload !== 'object' ||
      !Number.isSafeInteger(e.payload.leadId) || e.payload.leadId < 1 ||
      String(e.payload.leadId) !== e.subjectId ||
      Object.keys(e.payload).some(k => !fields.includes(k)) ||
      fields.slice(1).some(k => e.payload[k] !== undefined &&
        (typeof e.payload[k] !== 'string' || e.payload[k].length > 4000)) ||
      Object.keys(e).some(k => !['id','type','version','occurredAt','organizationRef',
        'subjectId','correlationId','payload'].includes(k))) throw Error('INVALID_EVENT');
  return e;
}

// Each immutable receipt is published with an exclusive hard link. A replay
// cannot overwrite a receipt, even across processes. fsync precedes HTTP 2xx.
// Kept under the existing DATA_DIR mount, separate from the Hub account store.
export function createWebsiteLeadEventReceiver({dataDir, env = process.env,
  organizationAllowed, beginWrite = () => () => {}}) {
  const directory = path.join(dataDir, 'website-lead-events');
  function config() {
    return {
      enabled: env.V79_WEBSITE_EVENTS_ENABLED === '1',
      secret: String(env.V79_WEBSITE_EVENT_SECRET || '').trim(),
      organization: String(env.V79_WEBSITE_ORGANIZATION_REF || '').trim(),
    };
  }
  function syncDirectory() {
    const fd = fs.openSync(directory, 'r');
    try { fs.fsyncSync(fd); } finally { fs.closeSync(fd); }
  }
  function read(file, expected) {
    const record = JSON.parse(fs.readFileSync(file, 'utf8'));
    if (!record || typeof record.event?.id !== 'string' ||
        record.event.id.toLowerCase() !== expected.toLowerCase()) throw Error('INVALID_RECEIPT');
    return record;
  }
  function receive(req, res) {
    res.setHeader('Cache-Control', 'no-store');
    const c = config();
    if (!c.enabled || c.secret.length < 32 || !c.organization ||
        !organizationAllowed(c.organization))
      return res.status(503).json({error:'Website events are not configured'});
    const raw = req.rawBody?.toString('utf8');
    if (typeof raw !== 'string' || Buffer.byteLength(raw) > 16384)
      return res.status(400).json({error:'Invalid event body'});
    const signature = req.get('x-v79-signature') || '';
    if (req.get('x-v79-service-id') !== 'website' || !/^[a-f0-9]{64}$/i.test(signature) ||
        !verifyPlatformRequest({method:'POST', pathname:WEBSITE_EVENT_PATH, body:raw,
          timestamp:req.get('x-v79-timestamp'), signature, secret:c.secret}))
      return res.status(401).json({error:'Invalid event signature'});
    let event;
    try { event = parseEvent(raw); }
    catch { return res.status(400).json({error:'Invalid lead event'}); }
    if (event.organizationRef !== c.organization)
      return res.status(403).json({error:'Event workspace is not permitted'});
    const digest = crypto.createHash('sha256').update(raw).digest('hex');
    const file = path.join(directory, event.id.toLowerCase() + '.json');
    let temporary;
    const endWrite = beginWrite();
    try {
      fs.mkdirSync(directory, {recursive:true, mode:0o700});
      const parent = fs.openSync(dataDir, 'r');
      try { fs.fsyncSync(parent); } finally { fs.closeSync(parent); }
      fs.chmodSync(directory, 0o700);
      let duplicate = fs.existsSync(file);
      if (!duplicate) {
        temporary = path.join(directory, '.' + crypto.randomUUID() + '.tmp');
        const fd = fs.openSync(temporary, 'wx', 0o600);
        try {
          fs.writeFileSync(fd, JSON.stringify({digest, receivedAt:new Date().toISOString(),
            state:'received', event}));
          fs.fsyncSync(fd);
        } finally { fs.closeSync(fd); }
        try { fs.linkSync(temporary, file); }
        catch (error) { if (error.code !== 'EEXIST') throw error; duplicate = true; }
      }
      const record = read(file, event.id);
      if (record.digest !== digest)
        return res.status(409).json({error:'Event identity already used'});
      syncDirectory();
      return res.status(duplicate ? 200 : 201).json({
        id:event.id, state:'received', duplicate,
        // Receipt only: no account, task, email, payment or entitlement action.
        executionEnabled:false,
      });
    } catch {
      return res.status(503).json({error:'Event persistence unavailable'});
    } finally {
      if (temporary) {
        try { fs.unlinkSync(temporary); } catch {}
      }
      endWrite();
    }
  }
  function receipt(req, res) {
    res.setHeader('Cache-Control', 'no-store');
    const id = String(req.params.eventId || '');
    if (!uuid.test(id)) return res.status(400).json({error:'Invalid event ID'});
    try {
      const record = read(path.join(directory, id.toLowerCase() + '.json'), id);
      const c = config();
      if (record.event.organizationRef !== c.organization ||
          !organizationAllowed(record.event.organizationRef))
        return res.status(403).json({error:'Event workspace is not permitted'});
      return res.json({id, state:record.state, receivedAt:record.receivedAt,
        organizationRef:record.event.organizationRef, subjectId:record.event.subjectId,
        correlationId:record.event.correlationId, executionEnabled:false});
    } catch (error) {
      return res.status(error.code === 'ENOENT' ? 404 : 503)
        .json({error:'Event receipt unavailable'});
    }
  }
  return {receive, receipt};
}

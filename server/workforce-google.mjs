/** Google boundary for the owner workforce. Never expose a general URL/tool executor. */
import { createHash } from 'node:crypto';

export const GOOGLE_OPERATIONS = Object.freeze(['create_email_draft', 'create_calendar_event', 'update_calendar_event', 'delete_calendar_event']);
export const GOOGLE_OWNER = 'vision79slu@gmail.com';
export const GOOGLE_TIMEZONE = 'America/St_Lucia';
const ID = /^[A-Za-z0-9_-]{1,200}$/;
const validId = value => typeof value === 'string' && ID.test(value);
const EMAIL = /^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$/;
function exact(v, keys) {
  return v && typeof v === 'object' && !Array.isArray(v) && Object.keys(v).sort().join() === [...keys].sort().join();
}
function string(v, max, multiline = false) {
  return typeof v === 'string' && v.trim() === v && v.length > 0 && v.length <= max &&
    !(multiline ? /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/ : /[\u0000-\u001f\u007f]/).test(v);
}
function reject() { throw new Error('Invalid Google workforce request'); }
function iso(v) {
  return typeof v === 'string' && /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.000Z$/.test(v) &&
    Number.isFinite(Date.parse(v)) && new Date(v).toISOString() === v;
}
export function validateGooglePayload(operation, system, p) {
  if (!GOOGLE_OPERATIONS.includes(operation)) reject();
  if (operation === 'create_email_draft') {
    if (system !== 'gmail' || !exact(p, ['threadId','messageId','to','subject','body']) ||
      !validId(p.threadId) || !validId(p.messageId) || !EMAIL.test(p.to) || p.to.length > 254 ||
      !string(p.subject, 200) || !string(p.body, 20000, true)) reject();
  } else {
    if (system !== 'calendar') reject();
    const fields = operation === 'create_calendar_event' ? ['summary','start','end','attendees'] :
      operation === 'update_calendar_event' ? ['eventId','etag','summary','start','end','attendees'] : ['eventId','etag'];
    if (!exact(p, fields)) reject();
    if (operation !== 'create_calendar_event' && (!validId(p.eventId) || !string(p.etag, 200))) reject();
    if (operation !== 'delete_calendar_event') {
      if (!string(p.summary, 200) || !iso(p.start) || !iso(p.end) || Date.parse(p.end) <= Date.parse(p.start) ||
        Date.parse(p.end) - Date.parse(p.start) > 24 * 3600000 || !Array.isArray(p.attendees) || p.attendees.length > 20 ||
        p.attendees.some(e => typeof e !== 'string' || e.length > 254 || !EMAIL.test(e)) ||
        new Set(p.attendees.map(e=>e.toLowerCase())).size !== p.attendees.length) reject();
    }
  }
  return structuredClone(p);
}

export class GoogleWorkforceError extends Error {
  constructor(code, uncertain = false) { super(code); this.code = code; this.uncertain = uncertain; }
}

/** getAccessToken must use a server-owned secret store. ChatGPT connector tokens are not portable. */
export function googleWorkforceClient({ getAccessToken, fetchImpl = fetch }) {
  async function request(service, path, { method = 'GET', body, etag } = {}) {
    const token = await getAccessToken(service);
    if (typeof token !== 'string' || !token || /[\r\n]/.test(token)) throw new GoogleWorkforceError('GOOGLE_AUTH_REQUIRED');
    const base = service === 'gmail' ? 'https://gmail.googleapis.com/gmail/v1/users/me' : 'https://www.googleapis.com/calendar/v3';
    let response;
    try {
      response = await fetchImpl(base + path, {
        method, redirect: 'error', signal: AbortSignal.timeout(15000),
        headers: { Authorization: `Bearer ${token}`, ...(body ? {'Content-Type':'application/json'} : {}), ...(etag ? {'If-Match':etag} : {}) },
        ...(body ? { body: JSON.stringify(body) } : {}),
      });
    } catch { throw new GoogleWorkforceError('GOOGLE_OUTCOME_UNKNOWN', method !== 'GET'); }
    if (!response.ok) {
      const code = response.status === 401 ? 'GOOGLE_AUTH_REQUIRED' : response.status === 412 ? 'GOOGLE_EVENT_CHANGED' :
        response.status === 429 ? 'GOOGLE_RATE_LIMITED' : 'GOOGLE_REQUEST_FAILED';
      throw new GoogleWorkforceError(code, method !== 'GET' && response.status >= 500);
    }
    if (response.status === 204) return {};
    try { return await response.json(); }
    catch { throw new GoogleWorkforceError('GOOGLE_RESPONSE_INVALID', method !== 'GET'); }
  }
  async function assertAccount(service) {
    const p = await request(service, service === 'gmail' ? '/profile' : '/calendars/primary');
    if (String(service === 'gmail' ? p.emailAddress : p.id).toLowerCase() !== GOOGLE_OWNER) throw new GoogleWorkforceError('GOOGLE_ACCOUNT_MISMATCH');
  }
  async function readEvent(id) {
    if (!validId(id)) reject();
    return request('calendar', `/calendars/primary/events/${encodeURIComponent(id)}`);
  }
  async function free(start, end) {
    const result = await request('calendar', '/freeBusy', {method:'POST',body:{timeMin:start,timeMax:end,timeZone:GOOGLE_TIMEZONE,items:[{id:GOOGLE_OWNER}]}});
    const calendar = result.calendars?.[GOOGLE_OWNER];
    if (!calendar || calendar.errors?.length || !Array.isArray(calendar.busy)) throw new GoogleWorkforceError('GOOGLE_AVAILABILITY_UNKNOWN');
    return calendar.busy;
  }
  return Object.freeze({
    async status() { await assertAccount('gmail'); await assertAccount('calendar'); return { account: GOOGLE_OWNER, timezone: GOOGLE_TIMEZONE, sendEnabled: false }; },
    async listEmails(query = 'in:inbox newer_than:7d', pageToken = '') {
      if (!string(query, 300) || typeof pageToken !== 'string' || pageToken.length > 2000) reject();
      await assertAccount('gmail');
      return request('gmail', `/messages?${new URLSearchParams({q:query,maxResults:'25',...(pageToken?{pageToken}:{})})}`);
    },
    async readThread(threadId) {
      if (!validId(threadId)) reject();
      await assertAccount('gmail');
      const data = await request('gmail', `/threads/${threadId}?format=full`);
      return { ...data, trust:'untrusted-email-content' };
    },
    async listAppointments(start, end, pageToken = '') {
      if (!iso(start) || !iso(end) || Date.parse(end) <= Date.parse(start) || Date.parse(end)-Date.parse(start)>31*86400000 || typeof pageToken !== 'string' || pageToken.length>2000) reject();
      await assertAccount('calendar');
      return request('calendar', `/calendars/primary/events?${new URLSearchParams({timeMin:start,timeMax:end,timeZone:GOOGLE_TIMEZONE,singleEvents:'true',orderBy:'startTime',maxResults:'100',...(pageToken?{pageToken}:{})})}`);
    },
    async execute(job) {
      const p = validateGooglePayload(job.operation, job.system, job.payload);
      const service = job.system === 'gmail' ? 'gmail' : 'calendar';
      await assertAccount(service);
      if (service === 'gmail') {
        const message = await request('gmail', `/messages/${p.messageId}?format=metadata&metadataHeaders=Message-ID`);
        const messageId = message.payload?.headers?.find(h=>h.name.toLowerCase()==='message-id')?.value;
        if (message.threadId !== p.threadId || typeof messageId !== 'string' || !/^<[^<>\s\r\n]{1,500}>$/.test(messageId)) throw new GoogleWorkforceError('GOOGLE_THREAD_CHANGED');
        // Encoded subject and base64 body prevent CRLF/header injection; recipient is a single validated mailbox.
        const raw = [`To: ${p.to}`,`Subject: =?UTF-8?B?${Buffer.from(p.subject).toString('base64')}?=`,
          `In-Reply-To: ${messageId}`,`References: ${messageId}`,'MIME-Version: 1.0',
          'Content-Type: text/plain; charset=UTF-8','Content-Transfer-Encoding: base64','',
          Buffer.from(p.body).toString('base64').match(/.{1,76}/g).join('\r\n')].join('\r\n');
        const draft = await request('gmail', '/drafts', {method:'POST',body:{message:{threadId:p.threadId,raw:Buffer.from(raw).toString('base64url')}}});
        if (!draft.id) throw new GoogleWorkforceError('GOOGLE_RECEIPT_MISSING', true);
        return { providerId:draft.id, effect:'draft-created', sent:false };
      }
      let current;
      if (job.operation !== 'create_calendar_event') {
        current = await readEvent(p.eventId);
        if (current.etag !== p.etag || current.recurringEventId || current.recurrence || current.eventType && current.eventType !== 'default' ||
            current.organizer?.email?.toLowerCase() !== GOOGLE_OWNER || current.status === 'cancelled') throw new GoogleWorkforceError('GOOGLE_EVENT_CHANGED');
      }
      if (job.operation === 'delete_calendar_event') {
        await request('calendar', `/calendars/primary/events/${p.eventId}?sendUpdates=all`, {method:'DELETE',etag:p.etag});
        return { providerId:p.eventId, effect:'event-deleted' };
      }
      const busy = await free(p.start, p.end);
      // Updates use event listings to exclude only this event from overlap checks.
      if (job.operation === 'create_calendar_event' && busy.length) throw new GoogleWorkforceError('GOOGLE_CALENDAR_CONFLICT');
      if (job.operation === 'update_calendar_event') {
        const conflicts = await request('calendar', `/calendars/primary/events?${new URLSearchParams({timeMin:p.start,timeMax:p.end,singleEvents:'true',maxResults:'2500'})}`);
        if (!Array.isArray(conflicts.items) || conflicts.nextPageToken || conflicts.items.some(e=>e.id!==p.eventId && e.status!=='cancelled' && e.transparency!=='transparent')) throw new GoogleWorkforceError('GOOGLE_CALENDAR_CONFLICT');
      }
      const body = { summary:p.summary,start:{dateTime:p.start,timeZone:GOOGLE_TIMEZONE},end:{dateTime:p.end,timeZone:GOOGLE_TIMEZONE},attendees:p.attendees.map(email=>({email})) };
      if (job.operation === 'create_calendar_event') {
        // Google-valid deterministic ID protects against duplicate creation across ambiguous outcomes.
        body.id = 'v79' + createHash('sha256').update(job.organizationId + ':' + job.id).digest('hex');
      }
      const result = await request('calendar', `/calendars/primary/events${current?'/'+p.eventId:''}?sendUpdates=all`,
        {method:current?'PATCH':'POST',body,...(current?{etag:p.etag}:{})});
      if (!result.id || !result.etag) throw new GoogleWorkforceError('GOOGLE_RECEIPT_MISSING', true);
      return { providerId:result.id, etag:result.etag, effect:current?'event-updated':'event-created' };
    },
  });
}

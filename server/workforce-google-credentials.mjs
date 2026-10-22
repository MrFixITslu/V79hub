/** Trusted Hub-side credential broker. Never import into the agent/model service. */
import fs from 'node:fs/promises';
import { constants } from 'node:fs';
import { GOOGLE_OWNER, GoogleWorkforceError } from './workforce-google.mjs';

export const GOOGLE_SCOPES = Object.freeze([
  'https://www.googleapis.com/auth/gmail.readonly',
  'https://www.googleapis.com/auth/gmail.compose',
  'https://www.googleapis.com/auth/calendar.readonly',
  'https://www.googleapis.com/auth/calendar.events.owned',
]);
const sameScopes = value => Array.isArray(value) && value.length === GOOGLE_SCOPES.length &&
  [...value].sort().join(' ') === [...GOOGLE_SCOPES].sort().join(' ');

export function googleCredentialBroker({ file, enabled, fetchImpl = fetch, now = Date.now }) {
  let cached = null, refresh = null;
  async function credentials() {
    let handle;
    try {
      handle = await fs.open(file, constants.O_RDONLY | constants.O_NOFOLLOW);
      const info = await handle.stat();
      if (!info.isFile() || info.size > 16384 || (info.mode & 0o077) !== 0 || info.uid !== process.getuid()) throw new Error();
      const data = JSON.parse(await handle.readFile('utf8'));
      if (data.schema !== 1 || data.owner !== GOOGLE_OWNER || !sameScopes(data.scopes) ||
          !['client_id','client_secret','refresh_token'].every(k=>typeof data[k]==='string' && data[k].length>0 && data[k].length<=8192 && !/[\r\n]/.test(data[k]))) throw new Error();
      return data;
    } catch { throw new GoogleWorkforceError('GOOGLE_CREDENTIALS_UNAVAILABLE'); }
    finally { await handle?.close(); }
  }
  async function obtain() {
    // Re-read the protected file even while cached: local removal, permissions and owner revocation fail closed.
    const c = await credentials();
    if (cached && cached.expiresAt > now()+60000 && cached.refreshToken===c.refresh_token) return cached.token;
    let response;
    try {
      response = await fetchImpl('https://oauth2.googleapis.com/token', {
        method:'POST',redirect:'error',signal:AbortSignal.timeout(15000),
        headers:{'Content-Type':'application/x-www-form-urlencoded'},
        body:new URLSearchParams({client_id:c.client_id,client_secret:c.client_secret,refresh_token:c.refresh_token,grant_type:'refresh_token'}).toString(),
      });
    } catch { cached=null; throw new GoogleWorkforceError('GOOGLE_AUTH_UNAVAILABLE'); }
    if (!response.ok) { cached=null; throw new GoogleWorkforceError('GOOGLE_REAUTH_REQUIRED'); }
    let token;
    try { token=await response.json(); }
    catch { throw new GoogleWorkforceError('GOOGLE_AUTH_UNAVAILABLE'); }
    if (typeof token.access_token!=='string' || !token.access_token || /[\r\n]/.test(token.access_token) ||
        token.token_type?.toLowerCase()!=='bearer' || !Number.isFinite(token.expires_in) || token.expires_in<120 || token.expires_in>86400 ||
        (token.scope && !sameScopes(token.scope.split(' '))) ||
        (token.refresh_token && token.refresh_token!==c.refresh_token)) throw new GoogleWorkforceError('GOOGLE_REAUTH_REQUIRED');
    if (!enabled()) throw new GoogleWorkforceError('GOOGLE_INTEGRATION_DISABLED');
    cached={token:token.access_token,refreshToken:c.refresh_token,expiresAt:now()+token.expires_in*1000};
    return cached.token;
  }
  return Object.freeze({
    async getAccessToken(service) {
      if (!enabled() || !['gmail','calendar'].includes(service)) throw new GoogleWorkforceError('GOOGLE_INTEGRATION_DISABLED');
      refresh ??= obtain().finally(()=>{refresh=null});
      return refresh;
    },
    clear() { cached=null; },
  });
}


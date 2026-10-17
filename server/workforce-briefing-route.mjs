// Staged owner report reader. No scheduler startup, collection, queue or execution.
export function createOwnerBriefingReader({ ownerMfaContext, enabled, readStatus }) {
  if ([ownerMfaContext, enabled, readStatus].some(fn => typeof fn !== 'function')) {
    throw Error('Missing briefing reader dependencies');
  }
  return async function ownerBriefingReader(req, res) {
    res.setHeader('Cache-Control', 'no-store');
    if (!ownerMfaContext(req)) return res.status(403).json({ error: 'MFA-verified owner access required.' });
    if (!enabled()) return res.status(503).json({ error: 'Workforce report access is disabled.' });
    if (req.method !== 'GET') return res.status(405).json({ error: 'Read-only endpoint.' });
    try {
      // Must be the validated status reader, never raw file or agent output.
      const status = await readStatus();
      if (!status || status.mode !== 'read-only' || !Array.isArray(status.reports) ||
          status.reports.length > 12 ||
          !['disabled','report_available','incomplete','stale_or_unavailable','unavailable'].includes(status.status)) {
        throw Error('Invalid report reader contract');
      }
      return res.status(200).json(status);
    } catch {
      return res.status(503).json({ error: 'Workforce reports are unavailable.' });
    }
  };
}

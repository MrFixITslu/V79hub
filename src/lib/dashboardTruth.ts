/**
 * Display-only dashboard trust helpers.
 * Never replace missing source observations with invented zeroes, currency or health.
 * Product authorization stays on the existing Hub server.
 */
export type MetricRecord = Record<string, unknown>;

export function numericMetric(value: unknown): number | null {
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  if (!/^-?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?$/i.test(trimmed)) return null;
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? parsed : null;
}

export function countMetric(value: unknown): string {
  const number = numericMetric(value);
  if (number === null || !Number.isSafeInteger(number) || number < 0) return "—";
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(number);
}

export function percentMetric(value: unknown): string {
  const number = numericMetric(value);
  if (number === null || number < 0 || number > 100) return "—";
  return `${new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 }).format(number)}%`;
}

export function summaryCurrency(metrics: MetricRecord): string | null {
  for (const input of [metrics.currencyCode, metrics.currency, metrics.currency_code]) {
    if (typeof input !== "string") continue;
    const code = input.trim().toUpperCase();
    if (!/^[A-Z]{3}$/.test(code)) continue;
    try {
      new Intl.NumberFormat("en-US", { style: "currency", currency: code });
      return code;
    } catch {
      // Invalid/unsupported currency: require explicit reliable source data.
    }
  }
  return null;
}

export function moneyMetric(value: unknown, metrics: MetricRecord): string {
  const amount = numericMetric(value);
  const currency = summaryCurrency(metrics);
  if (amount === null || !currency) return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency", currency, minimumFractionDigits: 2, maximumFractionDigits: 2,
  }).format(amount);
}

export function openJobsMetric(jobsByStatus: unknown): number | null {
  if (!jobsByStatus || typeof jobsByStatus !== "object" || Array.isArray(jobsByStatus)) return null;
  const entries = Object.entries(jobsByStatus);
  if (entries.length === 0) return null;
  let total = 0;
  for (const [status, value] of entries) {
    const count = numericMetric(value);
    if (count === null || !Number.isSafeInteger(count) || count < 0) return null;
    if (!/resolved|closed|complete/i.test(status)) total += count;
  }
  return Number.isSafeInteger(total) ? total : null;
}

export function hasUsableSummary(summary: { status: string; metrics?: MetricRecord } | undefined): boolean {
  if (!summary || summary.status !== "ok" || !summary.metrics) return false;
  return Object.entries(summary.metrics).some(([key, value]) => {
    if (/^(currency|currencycode|currency_code|generatedat|updatedat|sourcereportedat)$/i.test(key)) return false;
    if (numericMetric(value) !== null) return true;
    if (!value || typeof value !== "object" || Array.isArray(value)) return false;
    return Object.values(value).some(item => numericMetric(item) !== null);
  });
}

export function connectionCopy(
  visibleCount: number, usableCount: number, hasDashboard: boolean, hasError: boolean,
): string {
  if (hasError) return "Dashboard check failed. Current app data availability is unknown.";
  if (!hasDashboard) return "Checking authorized application data.";
  if (visibleCount === 0) return "No applications are enabled for this workspace.";
  if (usableCount === 0) return "No enabled application returned a usable data summary.";
  if (usableCount === visibleCount) return "All enabled app data summaries responded. This does not confirm service uptime.";
  return `${usableCount} of ${visibleCount} enabled apps returned usable data summaries. This is not an uptime check.`;
}

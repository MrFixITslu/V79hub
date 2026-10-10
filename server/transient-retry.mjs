export async function retryTransient(
  operation,
  { attempts = 2, delayMs = 150, onRetry = null } = {},
) {
  if (typeof operation !== "function") {
    throw new TypeError("retryTransient requires an operation function.");
  }

  const maxAttempts = Math.max(1, Math.trunc(Number(attempts) || 1));
  const waitMs = Math.max(0, Math.trunc(Number(delayMs) || 0));
  let lastError;

  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    try {
      return await operation(attempt);
    } catch (error) {
      lastError = error;
      if (attempt >= maxAttempts) throw error;
      if (typeof onRetry === "function") onRetry(error, attempt);
      if (waitMs > 0) {
        await new Promise(resolve => setTimeout(resolve, waitMs));
      }
    }
  }

  throw lastError;
}
import { resolveOllamaNativeRuntime } from "./ollama-native.js";
import type { ExecutiveRankingRequest, ExecutiveSelector } from "./executive-cycle.js";

/**
 * Optional local-only model ranking. No tools, no app URLs, no side effects.
 * The caller must have already enforced internal-token and founder ownership.
 * Returned text is untrusted: executive-cycle validates exact allowed IDs.
 */
export function createLocalExecutiveSelector(
  options: { env?: NodeJS.ProcessEnv; fetchImpl?: typeof fetch } = {},
): ExecutiveSelector {
  const runtime = resolveOllamaNativeRuntime(options.env);
  const fetchImpl = options.fetchImpl || fetch;
  return async (request: ExecutiveRankingRequest) => {
    if (request.candidates.length > 10) throw new Error("Too many findings");
    const prompt = JSON.stringify({
      goal: request.stage === "coo"
        ? "Rank verified operational findings for investigation."
        : "Review the COO ranking against commercial and customer impact.",
      findings: request.candidates,
      ...(request.stage === "ceo" ? { cooOrder: request.cooOrder || [] } : {}),
    });
    if (prompt.length > 6000) throw new Error("Executive preview input too large");
    const response = await fetchImpl(`${runtime.baseURL}/api/chat`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        model: runtime.model,
        stream: false,
        keep_alive: runtime.keepAlive,
        format: "json",
        options: {
          temperature: 0,
          num_predict: Math.min(runtime.maxTokens > 0 ? runtime.maxTokens : 120, 180),
          num_ctx: Math.min(runtime.contextSize, 3072),
        },
        messages: [
          {
            role: "system",
            content: request.stage === "coo"
              ? "You are V79 Digital's COO reviewer. You do not have tools or authority to approve, send, or change anything. Respond ONLY in JSON: {\"findingIds\":[\"existing-id\", ...]}. Include only IDs from the input. Prioritize urgent issues. Do not invent information."
              : "You are V79 Digital's CEO reviewer. You do not have tools or authority to approve, send, or change anything. Respond ONLY in JSON: {\"findingIds\":[\"existing-id\", ...]}. Include only IDs from the input; review COO ordering for customer and business risk. Do not invent information.",
          },
          { role: "user", content: prompt },
        ],
      }),
      signal: AbortSignal.timeout(Math.min(runtime.timeoutMs, 30_000)),
    });
    if (!response.ok) throw new Error("Local executive model unavailable");
    const payload: unknown = await response.json();
    if (typeof payload !== "object" || payload === null) throw new Error("Invalid model response");
    const raw = (payload as { message?: { content?: unknown } }).message?.content;
    if (typeof raw !== "string" || raw.length > 4096) throw new Error("Invalid model response");
    return raw;
  };
}

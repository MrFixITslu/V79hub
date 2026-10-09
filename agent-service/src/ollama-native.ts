export type OllamaNativeRuntime = {
  baseURL: string;
  model: string;
  timeoutMs: number;
  keepAlive: string | number;
  maxTokens: number;
  contextSize: number;
};

function positiveInteger(value: string | undefined, fallback: number) {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : fallback;
}

function parseKeepAlive(value: string | undefined): string | number {
  const normalized = String(value || "-1").trim();
  if (/^-?\d+$/.test(normalized)) return Number(normalized);
  return normalized || -1;
}

export function resolveOllamaNativeRuntime(env: NodeJS.ProcessEnv = process.env): OllamaNativeRuntime {
  return {
    baseURL: String(env.OLLAMA_BASE_URL || "http://ollama:11434").trim().replace(/\/+$/, ""),
    model: String(env.OLLAMA_AGENT_MODEL || "qwen2.5:1.5b").trim(),
    timeoutMs: positiveInteger(env.OLLAMA_REQUEST_TIMEOUT_MS, 90_000),
    keepAlive: parseKeepAlive(env.OLLAMA_KEEP_ALIVE),
    maxTokens: positiveInteger(env.OLLAMA_MAX_TOKENS, 80),
    contextSize: positiveInteger(env.OLLAMA_CONTEXT_SIZE, 2048),
  };
}

type OllamaChatResponse = {
  message?: { role?: string; content?: string };
  error?: string;
};

export async function prewarmOllamaOwnerAssistant(
  options: {
    env?: NodeJS.ProcessEnv;
    fetchImpl?: typeof fetch;
  } = {},
) {
  const env = options.env || process.env;
  const runtime = resolveOllamaNativeRuntime(env);
  const fetchImpl = options.fetchImpl || fetch;
  const timeoutMs = positiveInteger(env.OLLAMA_PREWARM_TIMEOUT_MS, 120_000);
  const response = await fetchImpl(`${runtime.baseURL}/api/generate`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      model: runtime.model,
      prompt: "",
      stream: false,
      keep_alive: runtime.keepAlive,
    }),
    signal: AbortSignal.timeout(timeoutMs),
  });

  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(`Ollama prewarm returned HTTP ${response.status}: ${JSON.stringify(payload).slice(0, 300)}`);
  }
  return { model: runtime.model, keepAlive: runtime.keepAlive };
}

export async function runOllamaOwnerAssistant(
  groundedMessage: string,
  options: {
    env?: NodeJS.ProcessEnv;
    fetchImpl?: typeof fetch;
    specialistInstructions?: string;
  } = {},
) {
  const runtime = resolveOllamaNativeRuntime(options.env);
  const fetchImpl = options.fetchImpl || fetch;
  const response = await fetchImpl(`${runtime.baseURL}/api/chat`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      model: runtime.model,
      stream: false,
      keep_alive: runtime.keepAlive,
      options: {
        temperature: 0,
        num_predict: runtime.maxTokens,
        num_ctx: runtime.contextSize,
      },
      messages: [
        {
          role: "system",
          content: [
            "You are the private Vision79 Owner Assistant for V79 Digital.",
            "You are in READ-ONLY mode.",
            "Use only the trusted business snapshot supplied in the user message for current facts.",
            "Never invent missing values.",
            "Prioritize exceptions, risks, overdue work, cashflow, customer impact, operational issues, and practical next actions.",
            "When PRIORITY SIGNALS are present, follow their severity order: high before medium before info. Never rank a generic zero-activity observation above a high-severity signal.",
            "Do not claim you changed, sent, deployed, refunded, booked, or edited anything.",
            "Keep answers concise and professional. Prefer at most five short bullets unless the owner asks for more detail.",
            options.specialistInstructions || "",
          ].join(" "),
        },
        { role: "user", content: groundedMessage },
      ],
    }),
    signal: AbortSignal.timeout(runtime.timeoutMs),
  });

  const payload = (await response.json().catch(() => ({}))) as OllamaChatResponse;
  if (!response.ok) {
    throw new Error(payload.error || `Ollama returned HTTP ${response.status}.`);
  }
  const output = String(payload.message?.content || "").trim();
  if (!output) throw new Error("Ollama returned an empty response.");
  return {
    output,
    model: runtime.model,
    provider: "ollama" as const,
  };
}
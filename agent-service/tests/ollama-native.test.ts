import test from "node:test";
import assert from "node:assert/strict";
import { prewarmOllamaOwnerAssistant, resolveOllamaNativeRuntime, runOllamaOwnerAssistant } from "../src/ollama-native.js";

test("native Ollama defaults to the responsive local model", () => {
  assert.deepEqual(resolveOllamaNativeRuntime({}), {
    baseURL: "http://ollama:11434",
    model: "qwen2.5:1.5b",
    timeoutMs: 90000,
    keepAlive: -1,
    maxTokens: 80,
    contextSize: 2048,
  });
});

test("native Ollama prewarms and retains the configured model", async () => {
  let requestUrl = "";
  let requestBody: any;
  const fetchImpl = async (url: string | URL | Request, init?: RequestInit) => {
    requestUrl = String(url);
    requestBody = JSON.parse(String(init?.body || "{}"));
    return new Response(JSON.stringify({ done: true }), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  };

  const result = await prewarmOllamaOwnerAssistant({
    env: {
      OLLAMA_BASE_URL: "http://ollama:11434/",
      OLLAMA_AGENT_MODEL: "qwen2.5:1.5b",
      OLLAMA_KEEP_ALIVE: "-1",
      OLLAMA_PREWARM_TIMEOUT_MS: "45000",
    },
    fetchImpl: fetchImpl as typeof fetch,
  });

  assert.equal(requestUrl, "http://ollama:11434/api/generate");
  assert.equal(requestBody.model, "qwen2.5:1.5b");
  assert.equal(requestBody.prompt, "");
  assert.equal(requestBody.stream, false);
  assert.equal(requestBody.keep_alive, -1);
  assert.deepEqual(result, { model: "qwen2.5:1.5b", keepAlive: -1 });
});

test("native Ollama returns assistant content without requiring an OpenAI key", async () => {
  let requestBody: any;
  const fetchImpl = async (_url: string | URL | Request, init?: RequestInit) => {
    requestBody = JSON.parse(String(init?.body || "{}"));
    return new Response(JSON.stringify({
      message: { role: "assistant", content: "1. Check stockout risk.\n2. Review open tickets." },
    }), { status: 200, headers: { "content-type": "application/json" } });
  };

  const result = await runOllamaOwnerAssistant("trusted snapshot", {
    env: {
      OLLAMA_BASE_URL: "http://ollama:11434/",
      OLLAMA_AGENT_MODEL: "qwen2.5:3b",
      OLLAMA_REQUEST_TIMEOUT_MS: "30000",
      OLLAMA_KEEP_ALIVE: "1h",
      OLLAMA_MAX_TOKENS: "120",
      OLLAMA_CONTEXT_SIZE: "1536",
    },
    fetchImpl: fetchImpl as typeof fetch,
  });

  assert.equal(result.provider, "ollama");
  assert.equal(result.model, "qwen2.5:3b");
  assert.match(result.output, /stockout risk/);
  assert.equal(requestBody.model, "qwen2.5:3b");
  assert.equal(requestBody.stream, false);
  assert.equal(requestBody.options.temperature, 0);
  assert.equal(requestBody.options.num_predict, 120);
  assert.equal(requestBody.options.num_ctx, 1536);
  assert.equal(requestBody.keep_alive, "1h");
});

test("native Ollama fails closed on empty model responses", async () => {
  const fetchImpl = async () =>
    new Response(JSON.stringify({ message: { role: "assistant", content: "" } }), {
      status: 200,
      headers: { "content-type": "application/json" },
    });

  await assert.rejects(
    runOllamaOwnerAssistant("trusted snapshot", { fetchImpl: fetchImpl as typeof fetch }),
    /empty response/i,
  );
});
test("native Ollama keeps specialist instructions in a system role rather than relying on tool calls", async () => {
  let sentBody: any;
  const fetchImpl = async (_url: string | URL | Request, init?: RequestInit) => {
    sentBody = JSON.parse(String(init?.body || "{}"));
    return new Response(JSON.stringify({ message: { role: "assistant", content: "Draft recommendations only." } }), {
      status: 200, headers: { "content-type": "application/json" },
    });
  };
  const result = await runOllamaOwnerAssistant("Owner question with scoped snapshot", {
    specialistInstructions: "You are V79 Finance. Never execute payments.",
    fetchImpl: fetchImpl as typeof fetch,
  });
  assert.equal(result.output, "Draft recommendations only.");
  assert.equal(sentBody.messages[0].role, "system");
  assert.match(sentBody.messages[0].content, /V79 Finance/);
  assert.match(sentBody.messages[0].content, /Never execute payments/);
  assert.equal(sentBody.messages[1].role, "user");
  assert.equal(sentBody.messages[1].content, "Owner question with scoped snapshot");
  assert.equal(sentBody.tools, undefined);
});

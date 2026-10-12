import test from "node:test";
import assert from "node:assert/strict";
import { createLocalDevelopmentProposer } from "../src/ollama-development.js";

const order = {
  repository: "MrFixITslu/V79hub" as const,
  baseCommit: "75291868e9392d82fdb31cfbc59ffb80b7d41d86",
  taskId: "G1-DEV-002",
  objective: "Draft a regression test only.",
  files: [{
    path: "agent-service/tests/example.test.ts",
    sourceBlob: "1234567890abcdef1234567890abcdef12345678",
    excerpt: "test('demo', () => {});",
  }],
};

test("development model refuses nonlocal endpoints before making any request", () => {
  for (const baseURL of [
    "https://api.openai.com",
    "http://evil.example.com",
    "https://ollama:11434",
  ]) {
    assert.throws(
      () => createLocalDevelopmentProposer({
        env: { OLLAMA_BASE_URL: baseURL },
        fetchImpl: async () => { throw new Error("Must not call network."); },
      }),
      /must be local/,
    );
  }
});

test("development model sends bounded no-tool request to local Ollama only", async () => {
  let called = 0;
  const fakeFetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    called++;
    assert.equal(String(input), "http://ollama:11434/api/chat");
    const payload = JSON.parse(String(init?.body));
    assert.equal(payload.format, "json");
    assert.equal(payload.stream, false);
    assert.equal(payload.tools, undefined);
    assert.equal(payload.messages[1].role, "user");
    assert.match(payload.messages[1].content, /G1-DEV-002/);
    return new Response(JSON.stringify({
      message: { content: '{"summary":"review-only","changes":[],"testIdeas":[],"risks":[]}' },
    }), { status: 200 });
  };
  const selector = createLocalDevelopmentProposer({
    env: { OLLAMA_BASE_URL: "http://ollama:11434", OLLAMA_AGENT_MODEL: "synthetic-local" },
    fetchImpl: fakeFetch,
  });
  const response = await selector(order);
  assert.equal(called, 1);
  assert.equal(typeof response, "string");
});

test("local model HTTP failure is a rejected draft, not a silent approval", async () => {
  const selector = createLocalDevelopmentProposer({
    env: { OLLAMA_BASE_URL: "http://127.0.0.1:11434" },
    fetchImpl: async () => new Response("unavailable", { status: 503 }),
  });
  await assert.rejects(selector(order), /unavailable/);
});

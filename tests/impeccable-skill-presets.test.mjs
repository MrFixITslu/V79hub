import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {test} from "node:test";
import {fileURLToPath} from "node:url";
import {resolve, dirname} from "node:path";
const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const preset = readFileSync(resolve(root, "src/lib/impeccablePreset.ts"), "utf8");
const ui = readFileSync(resolve(root, "src/components/WorkforceSkillManager.tsx"), "utf8");

test("Impeccable preset is bounded, review-only, and non-executable", () => {
  const match = /content: `([\s\S]*?)`,\s*\} as const/.exec(preset);
  assert.ok(match, "expected template literal without interpolation");
  const content = match[1];
  assert.ok(Buffer.byteLength(content, "utf8") > 1000);
  assert.ok(Buffer.byteLength(content, "utf8") <= 6000);
  assert.match(preset, /sourceVersion: "4\.8\.0"/);
  assert.match(content, /lower-trust advice/);
  assert.match(content, /cannot read local skill scripts, run a shell/);
  assert.match(content, /desktop, tablet and mobile/);
  assert.match(content, /three genuinely different approaches/);
  assert.doesNotMatch(content, /<script|fetch\(|eval\(|child_process|https?:\/\//i);
});

test("UI offers reviewed manual load with existing fresh-MFA activation", () => {
  assert.match(ui, /import \{IMPECCABLE_PRESET\}/);
  assert.match(ui, /const loadImpeccablePreset = \(\) =>/);
  assert.match(ui, /setWorkers\(\["technical-security"\]\)/);
  assert.match(ui, /onClick=\{loadImpeccablePreset\}/);
  assert.match(ui, /onClick=\{apply\}/);
  assert.match(ui, /Activation or pausing requires a founder session with MFA/);
  assert.doesNotMatch(ui, /dangerouslySetInnerHTML/);
});

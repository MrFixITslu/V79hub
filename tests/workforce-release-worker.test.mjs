import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import os from "node:os";
import { createHash } from "node:crypto";
import { validateReleaseManifest, assertImageOnlyChange, executeRelease } from "../scripts/workforce-release-worker.mjs";
const old = "sha256:" + "a".repeat(64), target = "sha256:" + "b".repeat(64), validation = "sha256:" + "c".repeat(64), commit = "d".repeat(40);
async function setup(t) {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), "v79-release-worker-test-")); t.after(() => fs.rm(dir, { recursive: true, force: true }));
  const file = async (name, body) => { const bytes = Buffer.from(JSON.stringify(body)); const f = path.join(dir, name); await fs.writeFile(f, bytes, { mode: 0o600 }); return { path: f, sha256: createHash("sha256").update(bytes).digest("hex") }; };
  const m = { version: 1, system: "hub", project: "v79-hub", commitSha: commit,
    validationImage: validation, validationScripts: ["lint", "test", "build"],
    services: [{ container: "v79-hub", service: "v79-hub", expectedImage: old, targetImage: target, rollbackImage: old }],
    compose: [await file("base.json", {}), await file("wipay.pinned.json", {})],
    releaseOverlay: await file("release.json", {}),
    backupReceipt: await file("recovery.json", { restoreVerified: true, rollbackVerified: true, capturedAt: new Date().toISOString(), runtimeImages: { "v79-hub": old } }) };
  const job = { operation: "validate_release", system: "hub", payload: { commitSha: commit, manifestSha256: "e".repeat(64) } };
  const calls = []; let runtime = old, failUp = false;
  const before = { name: "v79-hub", services: { "v79-hub": { image: old, environment: { WIPAY_MODE: "sandbox" }, volumes: ["data:/app/data"] } } };
  const after = structuredClone(before); after.services["v79-hub"].image = target;
  const docker = async args => {
    calls.push(args);
    if (args[0] === "image") return JSON.stringify([{ Id: args[2], Config: { Labels: { "org.opencontainers.image.revision": commit } } }]);
    if (args[0] === "inspect") return JSON.stringify([{ Image: runtime, Config: { Labels: { "com.docker.compose.project": "v79-hub", "com.docker.compose.service": "v79-hub",
      "com.docker.compose.project.config_files": [...m.compose.map(f => f.path), ...(runtime === target ? [m.releaseOverlay.path] : [])].join(",") } }, State: { Health: { Status: "healthy" } } }]);
    if (args.includes("config")) return JSON.stringify(args.includes(m.releaseOverlay.path) ? after : before);
    if (args.includes("up")) { if (failUp) throw new Error("synthetic failed recreation"); runtime = args.includes(m.releaseOverlay.path) ? target : old; }
    return "";
  };
  return { m, job, calls, docker, before, after, setRuntime: image => { runtime = image; }, failUp: () => { failUp = true; } };
}
test("validation uses exact images, no network, no host mounts or Docker socket, non-root bounded containers", async t => {
  const h = await setup(t); let authorizations = 0;
  const result = await executeRelease(h.job, h.m, { docker: h.docker, authorize: async () => { authorizations++; } });
  assert.equal(result.status, "succeeded"); assert.equal(authorizations, 4);
  const runs = h.calls.filter(a => a[0] === "run"); assert.equal(runs.length, 3);
  for (const a of runs) {
    assert.equal(a[a.indexOf("--network") + 1], "none"); assert.equal(a[a.indexOf("--user") + 1], "1000:1000");
    assert.ok(a.includes("--read-only")); assert.ok(a.includes("--cap-drop")); assert.ok(a.includes("--memory"));
    assert.ok(!a.includes("-v") && !a.includes("--volume") && !a.includes("--mount"));
    assert.ok(a.includes(validation));
  }
  assert.equal(h.calls.filter(a => a.includes("up")).length, 0);
});
test("deploy changes only approved application image; rollback restores exact original pinned overlays", async t => {
  const h = await setup(t);
  assert.equal((await executeRelease({ ...h.job, operation: "deploy_release" }, h.m, { docker: h.docker, authorize: async () => {} })).status, "succeeded");
  let up = h.calls.find(a => a.includes("up")); assert.ok(up.includes("--no-deps") && up.includes("--no-build") && up.includes("never"));
  assert.equal(up.at(-1), "v79-hub"); assert.ok(!up.includes("v79-hub-postgres"));
  h.calls.length = 0;
  assert.equal((await executeRelease({ ...h.job, operation: "rollback_release" }, h.m, { docker: h.docker, authorize: async () => {} })).status, "succeeded");
  up = h.calls.find(a => a.includes("up")); assert.ok(!up.includes(h.m.releaseOverlay.path));
  assert.ok(h.m.compose.every(f => up.includes(f.path)));
});
test("unverified recovery, runtime drift, changed environment and revoked approval stop before mutation", async t => {
  const h = await setup(t), deploy = { ...h.job, operation: "deploy_release" };
  await assert.rejects(executeRelease(deploy, h.m, { docker: h.docker, authorize: async () => { throw new Error("paused"); } }));
  assert.equal(h.calls.filter(a => a.includes("up")).length, 0);
  h.setRuntime(target); await assert.rejects(executeRelease(deploy, h.m, { docker: h.docker, authorize: async () => {} }), /Runtime/); h.setRuntime(old);
  h.after.services["v79-hub"].environment.WIPAY_MODE = "live";
  assert.throws(() => assertImageOnlyChange(h.before, h.after, h.m.services), /only approved images/);
  h.after.services["v79-hub"].environment.WIPAY_MODE = "sandbox";
  await fs.writeFile(h.m.backupReceipt.path, JSON.stringify({ restoreVerified: false }));
  await assert.rejects(executeRelease(deploy, h.m, { docker: h.docker, authorize: async () => {} }), /changed/);
  assert.equal(h.calls.filter(a => a.includes("up")).length, 0);
});
test("failure after deployment starts is uncertain and performs no automatic retry or rollback", async t => {
  const h = await setup(t); h.failUp();
  const result = await executeRelease({ ...h.job, operation: "deploy_release" }, h.m, { docker: h.docker, authorize: async () => {} });
  assert.equal(result.status, "uncertain"); assert.equal(h.calls.filter(a => a.includes("up")).length, 1);
});
test("manifest registry rejects databases, mutable image tags, arbitrary scripts and mismatched commit", async t => {
  const h = await setup(t);
  for (const m of [{ ...h.m, validationImage: "node:latest" }, { ...h.m, commitSha: "0".repeat(40) },
    { ...h.m, validationScripts: ["test", "start"] },
    { ...h.m, services: [{ ...h.m.services[0], container: "v79-hub-postgres" }] },
    { ...h.m, services: [{ ...h.m.services[0], targetImage: "hub:latest" }] }]) assert.throws(() => validateReleaseManifest(m, h.job));
});

test("twelve ordered pinned Compose inputs are preserved while oversized and duplicate stacks reject", async t => {
  const h = await setup(t);
  const original = h.m.compose;
  h.m.compose = Array.from({length:12}, (_,i) => ({path:path.join(path.dirname(original[0].path),`layer-${i}.json`),sha256:"a".repeat(64)}));
  assert.equal(validateReleaseManifest(h.m,h.job).compose.length,12);
  const paths=h.m.compose.map(f=>f.path);
  assert.deepEqual(validateReleaseManifest(h.m,h.job).compose.map(f=>f.path),paths);
  assert.throws(()=>validateReleaseManifest({...h.m,compose:[...h.m.compose,...h.m.compose.slice(0,5)]},h.job));
  assert.throws(()=>validateReleaseManifest({...h.m,compose:[...h.m.compose.slice(0,11),h.m.compose[0]]},h.job));
});

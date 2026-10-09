import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, mkdir, readFile, readdir, rm, stat, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import {
  safeAuditCheckpoint, compareAuditCheckpointToAnchor, retainAuditCheckpoint,
} from "../server/agent-approval-checkpoint-retention.mjs";

const schema = "v79-agent-approval-audit-checkpoint-v1";
const genesis = "0".repeat(64);
const checkpoint = (count, headMac = count ? "a".repeat(64) : genesis) =>
  ({ schema, count, headMac });

async function privateDirectories(t) {
  const base = await mkdtemp(path.join(tmpdir(), "v79-offstore-anchor-test-"));
  t.after(() => rm(base, { recursive:true, force:true }));
  const directory = path.join(base, "checkpoint-vault");
  const hubDataDirectory = path.join(base, "hub-state-data");
  await mkdir(directory, { mode:0o700 });
  await mkdir(hubDataDirectory, { mode:0o700 });
  return { base, directory, hubDataDirectory, epoch:"epoch1" };
}

test("checkpoint accepts only redacted non-executing valid metadata and preserves exact counts", () => {
  assert.deepEqual(safeAuditCheckpoint({
    ...checkpoint(1), executionEnabled:false, independentRetentionConfigured:false,
  }),checkpoint(1));
  for (const invalid of [
    {...checkpoint(1), tenantId:"synthetic-owner"},
    {...checkpoint(1), executionEnabled:true},
    {...checkpoint(1), independentRetentionConfigured:true},
    checkpoint(-1),
    checkpoint(10001),
    checkpoint(1,genesis),
    checkpoint(0,"a".repeat(64)),
    checkpoint(1,"g".repeat(64)),
    {...checkpoint(1), count:1.1},
    {},
    null,
  ]) assert.throws(() => safeAuditCheckpoint(invalid), /Invalid/);
});

test("independent checkpoint comparison distinguishes exact match, rollbacks, forks and unanchored growth", () => {
  assert.equal(compareAuditCheckpointToAnchor(checkpoint(2),checkpoint(2)), "match");
  assert.equal(compareAuditCheckpointToAnchor(checkpoint(2),checkpoint(1)), "rollback-detected");
  assert.equal(compareAuditCheckpointToAnchor(checkpoint(2),checkpoint(2,"b".repeat(64))), "fork-detected");
  assert.equal(compareAuditCheckpointToAnchor(checkpoint(1),checkpoint(2)), "unanchored-growth");
  assert.equal(compareAuditCheckpointToAnchor(checkpoint(1),{...checkpoint(1),contacts:["x"]}), "invalid");
});

test("operator-only private external vault records immutable-count checkpoints without overwrites", async t => {
  const input=await privateDirectories(t);
  const first=await retainAuditCheckpoint({...input,checkpoint:checkpoint(1)});
  assert.equal(first.status,"retained-locally");
  assert.equal(first.count,1);
  assert.equal(await stat(path.join(input.directory,"epoch1-00000001.json")).then(s=>s.mode&0o077),0);
  const stored=JSON.parse(await readFile(path.join(input.directory,"epoch1-00000001.json"),"utf8"));
  assert.deepEqual(stored,{epoch:"epoch1",...checkpoint(1)});
  assert.equal("organizationId" in stored,false);
  assert.equal("signingKey" in stored,false);
  const same=await retainAuditCheckpoint({...input,checkpoint:checkpoint(1)});
  assert.equal(same.status,"already-retained");
  const second=await retainAuditCheckpoint({...input,checkpoint:checkpoint(2,"b".repeat(64))});
  assert.equal(second.status,"retained-locally");
  const retained=(await readdir(input.directory)).sort();
  assert.deepEqual(retained,["epoch1-00000001.json","epoch1-00000002.json"]);
  assert.throws(()=>safeAuditCheckpoint({...checkpoint(1),password:"never"}),/Invalid/);
  await assert.rejects(
    retainAuditCheckpoint({...input,checkpoint:checkpoint(1)}),/rollback/,
  );
  await assert.rejects(
    retainAuditCheckpoint({...input,checkpoint:checkpoint(2,"c".repeat(64))}),/fork/,
  );
  assert.deepEqual(await readdir(input.directory),["epoch1-00000001.json","epoch1-00000002.json"]);
});

test("vault forbids paths inside Hub data, overly broad permissions, invalid epochs and symbolic links", async t => {
  const input=await privateDirectories(t);
  await assert.rejects(retainAuditCheckpoint({
    ...input, directory:input.hubDataDirectory, checkpoint:checkpoint(1),
  }),/outside Hub/);
  const inside = path.join(input.hubDataDirectory,"anchors");
  await mkdir(inside,{mode:0o700});
  await assert.rejects(retainAuditCheckpoint({
    ...input,directory:inside,checkpoint:checkpoint(1),
  }),/outside Hub/);
  const outside = path.join(input.base,"symbolic");
  await symlink(input.directory,outside);
  await assert.rejects(retainAuditCheckpoint({
    ...input,directory:outside,checkpoint:checkpoint(1),
  }),/owner-only/);
  await assert.rejects(retainAuditCheckpoint({
    ...input,epoch:"../bad-epoch",checkpoint:checkpoint(1),
  }),/Explicit private/);
  await assert.rejects(retainAuditCheckpoint({
    ...input,directory:"./relative",checkpoint:checkpoint(1),
  }),/Explicit private/);
  await assert.rejects(retainAuditCheckpoint({
    ...input,hubDataDirectory:input.directory,checkpoint:checkpoint(1),
  }),/outside Hub/);
});

test("vault rejects corrupted existing records, unsafe file permissions, injected filenames and held locks", async t => {
  const input=await privateDirectories(t);
  await retainAuditCheckpoint({...input,checkpoint:checkpoint(1)});
  const original = path.join(input.directory,"epoch1-00000001.json");
  await writeFile(original,"{bad json", {mode:0o600});
  await assert.rejects(retainAuditCheckpoint({
    ...input,checkpoint:checkpoint(2,"b".repeat(64)),
  }),/unreadable/);
  await writeFile(original,JSON.stringify({epoch:"epoch1",...checkpoint(1)}),{mode:0o600});
  const injected = path.join(input.directory,"epoch1-ignored.json");
  await writeFile(injected,"{}",{mode:0o600});
  await assert.rejects(retainAuditCheckpoint({
    ...input,checkpoint:checkpoint(2,"b".repeat(64)),
  }),/unexpected archive filename/);
  await rm(injected);
  const lock = path.join(input.directory,".agent-audit-lock");
  await mkdir(lock,{mode:0o700});
  await assert.rejects(retainAuditCheckpoint({
    ...input,checkpoint:checkpoint(2,"b".repeat(64)),
  }));
  assert.deepEqual((await readdir(input.directory)).sort(),[".agent-audit-lock","epoch1-00000001.json"]);
});

test("different audit key epochs never silently overwrite an existing chain", async t => {
  const input=await privateDirectories(t);
  assert.equal((await retainAuditCheckpoint({...input,checkpoint:checkpoint(3)})).status,"retained-locally");
  const rotated=await retainAuditCheckpoint({
    ...input,epoch:"epoch2",checkpoint:checkpoint(3,"b".repeat(64)),
  });
  assert.equal(rotated.status,"retained-locally");
  assert.deepEqual((await readdir(input.directory)).sort(),
    ["epoch1-00000003.json","epoch2-00000003.json"]);
});

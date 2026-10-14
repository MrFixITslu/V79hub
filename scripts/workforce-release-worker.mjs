#!/usr/bin/env node
import fs from "node:fs/promises";
import path from "node:path";
import { createHash, randomUUID } from "node:crypto";
import { spawn } from "node:child_process";
import { pathToFileURL } from "node:url";
import { isDeepStrictEqual } from "node:util";
import { WORK_SYSTEMS } from "../server/workforce-actions.mjs";

const sha = bytes => createHash("sha256").update(bytes).digest("hex");
const IMAGE = /^sha256:[a-f0-9]{64}$/;
const HASH = /^[a-f0-9]{64}$/;
const IDS = {
  hub: ["v79-hub", "v79-business-agent"], tiquet: ["v79-tiquet-manager"],
  marketing: ["v79marketing-app"], ffpro: ["fire-finance-app"],
  pos: ["v79-pos-api", "v79-pos-worker"], academy: ["v79_course_builder"],
  website: ["V79website"], games: ["gaming-studio-j"], sentinel: ["v79-sentinel"], lasertag: ["lasertag"],
};
// New container names require a reviewed registry change, never model guessing.
export function validateReleaseManifest(m, job) {
  if (!m || m.version !== 1 || m.system !== job.system || m.commitSha !== job.payload.commitSha ||
      !WORK_SYSTEMS.includes(m.system) || !/^[a-zA-Z0-9_-]{1,80}$/.test(m.project) ||
      !IMAGE.test(m.validationImage) || !Array.isArray(m.services) || m.services.length < 1 || m.services.length > 2 ||
      !Array.isArray(m.compose) || !m.compose.length || m.compose.length > 5 ||
      !Array.isArray(m.validationScripts) || !m.validationScripts.length ||
      !m.validationScripts.includes("test") || !m.validationScripts.every(s => ["lint", "test", "build"].includes(s))) throw new Error("Invalid release manifest");
  const names = new Set(), services = new Set();
  for (const s of m.services) {
    if (!IDS[m.system].includes(s.container) || names.has(s.container) || services.has(s.service) ||
        !/^[A-Za-z0-9_-]{1,80}$/.test(s.service) || !IMAGE.test(s.expectedImage) ||
        !IMAGE.test(s.targetImage) || s.targetImage === s.expectedImage || s.rollbackImage !== s.expectedImage) throw new Error("Invalid release service");
    names.add(s.container); services.add(s.service);
  }
  for (const f of [...m.compose, m.releaseOverlay, m.backupReceipt]) {
    if (!f || typeof f.path !== "string" || !path.isAbsolute(f.path) ||
        path.normalize(f.path) !== f.path || !HASH.test(f.sha256)) throw new Error("Invalid pinned release file");
  }
  if (new Set(m.compose.map(f => f.path)).size !== m.compose.length ||
      m.compose.some(f => f.path === m.releaseOverlay.path)) throw new Error("Duplicate compose file");
  return m;
}
export function assertImageOnlyChange(before, after, services, target = true) {
  const a = structuredClone(before), b = structuredClone(after);
  for (const s of services) {
    if (!a.services?.[s.service] || !b.services?.[s.service] ||
        b.services[s.service].image !== (target ? s.targetImage : s.expectedImage)) throw new Error("Effective image differs from approval");
    // No environment, mounts, ports, networks, secrets or commands may change.
    a.services[s.service].image = b.services[s.service].image;
  }
  if (!isDeepStrictEqual(a, b)) throw new Error("Release must change only approved images");
}
export async function dockerCommand(args, { timeout = 120000, maxBytes = 4 * 1024 * 1024 } = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn("docker", args, { stdio: ["ignore", "pipe", "pipe"], env: { ...process.env } });
    let out = "", size = 0, stopped = false;
    const timer = setTimeout(() => { stopped = true; child.kill("SIGKILL"); }, timeout);
    child.stdout.on("data", d => { size += d.length; if (size > maxBytes) { stopped = true; child.kill("SIGKILL"); } else out += d; });
    // Docker errors can include resolved secrets: never retain or print stderr.
    child.stderr.on("data", () => {});
    child.on("error", () => { clearTimeout(timer); reject(new Error("Docker unavailable")); });
    child.on("close", code => {
      clearTimeout(timer);
      if (stopped || code !== 0) reject(new Error("Docker operation failed or timed out")); else resolve(out);
    });
  });
}
async function verifiedFile(f) {
  const stat = await fs.lstat(f.path);
  if (!stat.isFile() || stat.isSymbolicLink() || (stat.mode & 0o022)) throw new Error("Pinned file must be a protected regular file");
  const bytes = await fs.readFile(f.path);
  if (sha(bytes) !== f.sha256) throw new Error("Pinned file changed");
  return bytes;
}
export async function executeRelease(job, manifest, { docker = dockerCommand, authorize, now = Date.now } = {}) {
  if (!["validate_release", "deploy_release", "rollback_release"].includes(job.operation)) throw new Error("Unsupported release operation");
  const m = validateReleaseManifest(manifest, job);
  const compose = ["compose", "--project-name", m.project, ...m.compose.flatMap(f => ["-f", f.path])];
  const target = [...compose, "-f", m.releaseOverlay.path];
  const inspected = async container => JSON.parse(await docker(["inspect", container]))[0];
  const files = async () => {
    for (const f of [...m.compose, m.releaseOverlay, m.backupReceipt]) await verifiedFile(f);
  };
  await files();
  const inspectedBaseline = new Map();
  for (const s of m.services) {
    const current = await inspected(s.container);
    const allowedImages = job.operation === "rollback_release" ? [s.targetImage, s.expectedImage] : [s.expectedImage];
    const labels = current.Config?.Labels || {};
    if (!allowedImages.includes(current.Image) || labels["com.docker.compose.project"] !== m.project ||
        labels["com.docker.compose.service"] !== s.service) throw new Error("Runtime differs from approved baseline");
    const expectedFiles = current.Image === s.targetImage ? [...m.compose.map(f => f.path), m.releaseOverlay.path] : m.compose.map(f => f.path);
    if (labels["com.docker.compose.project.config_files"] !== expectedFiles.join(",")) throw new Error("Live pinned overlay set differs from manifest");
    inspectedBaseline.set(s.container, current.Image);
  }
  for (const image of new Set([m.validationImage, ...m.services.flatMap(s => [s.targetImage, s.expectedImage])])) {
    const info = JSON.parse(await docker(["image", "inspect", image]))[0];
    if (info.Id !== image) throw new Error("Immutable image unavailable");
    if ((image === m.validationImage || m.services.some(s => s.targetImage === image)) &&
        info.Config?.Labels?.["org.opencontainers.image.revision"] !== m.commitSha) throw new Error("Image source commit unverified");
  }
  const before = JSON.parse(await docker([...compose, "config", "--format", "json"]));
  const after = JSON.parse(await docker([...target, "config", "--format", "json"]));
  assertImageOnlyChange(before, after, m.services);
  for (const s of m.services) if (before.services[s.service].image !== s.expectedImage) throw new Error("Rollback config is not exactly pinned");
  await authorize();
  if (job.operation === "validate_release") {
    for (const script of m.validationScripts) {
      await authorize();
      const name = "v79-approved-check-" + randomUUID();
      try {
        await docker(["run", "--rm", "--name", name, "--network", "none", "--read-only", "--cap-drop", "ALL",
          "--security-opt", "no-new-privileges", "--user", "1000:1000", "--pids-limit", "256",
          "--memory", "1g", "--cpus", "1", "--tmpfs", "/tmp:rw,noexec,nosuid,size=256m",
          "--entrypoint", "npm", m.validationImage, "run", script], { timeout: 900000 });
      } finally {
        // Remove only this random synthetic test container on timeout/crash.
        await docker(["rm", "-f", name]).catch(() => {});
      }
    }
    return { status: "succeeded", commitSha: m.commitSha, system: m.system, tests: m.validationScripts };
  }
  if (!["deploy_release", "rollback_release"].includes(job.operation)) throw new Error("Unsupported release operation");
  const recovery = JSON.parse(await verifiedFile(m.backupReceipt));
  if (recovery.restoreVerified !== true || recovery.rollbackVerified !== true ||
      !Number.isFinite(Date.parse(recovery.capturedAt)) || now() - Date.parse(recovery.capturedAt) < 0 ||
      now() - Date.parse(recovery.capturedAt) > 86400000 ||
      !m.services.every(s => recovery.runtimeImages?.[s.container] === s.expectedImage)) throw new Error("Current restore/rollback recovery proof required");
  await files(); await authorize();
  // Tests or an operator may have changed runtime during preflight.
  for (const s of m.services) {
    const current = await inspected(s.container);
    if (current.Image !== inspectedBaseline.get(s.container)) throw new Error("Runtime changed during preflight");
  }
  // No build/pull, no databases, no dependencies, no config synchronization.
  // A failure after recreation starts is uncertain; never retry automatically.
  try {
    await docker([...(job.operation === "deploy_release" ? target : compose),
      "up", "-d", "--no-deps", "--no-build", "--pull", "never", "--force-recreate", "--wait", "--wait-timeout", "120",
      ...m.services.map(s => s.service)], { timeout: 180000 });
    for (const s of m.services) {
      const running = await inspected(s.container);
      if (running.Image !== (job.operation === "deploy_release" ? s.targetImage : s.expectedImage) ||
          running.State?.Health?.Status !== "healthy") throw new Error("Release health verification failed");
    }
    return { status: "succeeded", commitSha: m.commitSha, system: m.system, images: m.services.map(s => s.container) };
  } catch { return { status: "uncertain", commitSha: m.commitSha, system: m.system, reason: "Inspect exact runtime before approving rollback" }; }
}

export async function runWorkerOnce({ hubUrl, tokenFile, manifestDirectory, receiptDirectory, systems }) {
  const url = new URL(hubUrl);
  if (!["http:", "https:"].includes(url.protocol) || url.username || url.password || url.pathname !== "/" || url.search || url.hash ||
      (url.protocol === "http:" && !["127.0.0.1", "localhost"].includes(url.hostname))) throw new Error("Trusted HTTPS or localhost Hub URL required");
  const token = (await fs.readFile(tokenFile, "utf8")).trim();
  if (token.length < 32) throw new Error("Separate workforce token required");
  const call = async (endpoint, body, extra = {}) => {
    const response = await fetch(new URL("/internal/workforce/" + endpoint, url), {
      method: body === undefined ? "GET" : "POST", redirect: "error", signal: AbortSignal.timeout(15000),
      headers: { "content-type": "application/json", "x-v79-workforce-token": token, ...extra },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
    if (!response.ok) throw new Error("Hub rejected worker request");
    return response.json();
  };
  const item = await call("execute-work-item", {});
  if (item.job) return { state: "succeeded", jobId: item.job.id, taskId: item.job.result.taskId };
  const { job } = await call("claim", { worker: "v79-release-worker", operations: ["validate_release", "deploy_release", "rollback_release"], systems });
  if (!job) return { state: "idle" };
  let receipt;
  try {
    const manifestPath = path.join(manifestDirectory, job.payload.manifestSha256 + ".json");
    const bytes = await verifiedFile({ path: manifestPath, sha256: job.payload.manifestSha256 });
    const authorize = async () => {
      const answer = await call(job.id + "/authorization", undefined, { "x-v79-workforce-claim": job.claim.token });
      if (answer.authorized !== true) throw new Error("Approval is paused or expired");
    };
    receipt = await executeRelease(job, JSON.parse(bytes), { authorize });
  } catch { receipt = { status: "failed", reason: "Release preflight or isolated validation failed" }; }
  const result = { jobId: job.id, digest: job.digest, ...receipt, completedAt: new Date().toISOString() };
  const bytes = Buffer.from(JSON.stringify(result));
  await fs.mkdir(receiptDirectory, { recursive: true, mode: 0o700 });
  const receiptSha256 = sha(bytes);
  await fs.writeFile(path.join(receiptDirectory, receiptSha256 + ".json"), bytes, { mode: 0o600, flag: "wx" });
  await call(job.id + "/receipt", { claimToken: job.claim.token, digest: job.digest, status: receipt.status, receiptSha256 });
  return { state: receipt.status, jobId: job.id, receiptSha256 };
}
if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  try {
    const result = await runWorkerOnce({ hubUrl: process.env.V79_WORKFORCE_HUB_URL,
      tokenFile: process.env.V79_WORKFORCE_TOKEN_FILE,
      manifestDirectory: process.env.V79_WORKFORCE_MANIFEST_DIR,
      receiptDirectory: process.env.V79_WORKFORCE_RECEIPT_DIR,
      systems: String(process.env.V79_WORKFORCE_SYSTEMS || "hub,tiquet").split(",") });
    console.log(JSON.stringify(result));
  } catch { console.error("STOP: worker unavailable; reconcile claimed jobs before retrying"); process.exitCode = 1; }
}

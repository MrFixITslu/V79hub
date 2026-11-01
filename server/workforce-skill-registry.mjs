import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";

// Owner-only instruction registry. Skills are TEXT, not executable plugins/tools.
// An existing pinned built-in specialist prompt is never replaced by this registry.
export const SKILL_WORKERS = Object.freeze([
  "ceo", "coo", "finance", "strategy", "marketing", "customer-service", "technical-security", "sales"
]);
export const SKILL_MAX_CONTENT = 6000;
export const SKILL_MAX_PER_WORKER = 2;
const MAX_SKILLS = 100;
const MAX_VERSIONS = 30;
const MAX_AUDIT = 1000;
const digest = text => crypto.createHash("sha256").update(text, "utf8").digest("hex");
const exactKeys = (obj, keys) => obj && typeof obj === "object" && !Array.isArray(obj) &&
  Object.keys(obj).sort().join("|") === [...keys].sort().join("|");
const fail = (reason, status = 400) => Object.assign(new Error(reason), { status });
const emptyState = () => ({ schema: 1, revision: 0, skills: [], audit: [] });
const validRevision = rev => Number.isSafeInteger(rev) && rev >= 0;
const validWorker = worker => SKILL_WORKERS.includes(worker);

export function validateSkillDraft(input) {
  if (!exactKeys(input, ["name", "content"])) throw fail("Only name and content are accepted");
  const name = input.name;
  const content = input.content;
  if (typeof name !== "string" || name.trim().length < 3 || name.trim().length > 80 ||
      /[\u0000-\u001f\u007f]/.test(name)) throw fail("Skill name must be 3–80 plain-text characters");
  if (typeof content !== "string" || !content.trim() || Buffer.byteLength(content, "utf8") > SKILL_MAX_CONTENT ||
      /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/.test(content))
    throw fail("Skill must be plain UTF-8 text of 1–6000 bytes, without control characters");
  // Best-effort warnings only: no static scanner can establish that a prompt is safe.
  const warnings = [];
  if (/ignore (all |any )?(previous|system|developer) instructions|override (system|developer) instructions/i.test(content))
    warnings.push("Instruction-override language detected; inspect before activation");
  if (/(?:api key|access token|password|secret).{0,70}(?:send|publish|disclose|reveal|upload)/i.test(content))
    warnings.push("Potential credential-disclosure instructions; inspect before activation");
  if (/\b(?:curl|wget|sudo|chmod|rm -rf|subprocess|exec\()\b/i.test(content))
    warnings.push("Command-like text detected; skills are never executable");
  return { name: name.trim(), content, sha256: digest(content), bytes: Buffer.byteLength(content, "utf8"), warnings };
}

export function createSkillRegistry({ file, secret, now = () => Date.now() }) {
  if (typeof file !== "string" || !path.isAbsolute(file)) throw Error("Absolute registry file required");
  if (typeof secret !== "string" || Buffer.byteLength(secret, "utf8") < 32) throw Error("Independent 32+ byte skill registry key required");
  const dir = path.dirname(file), lockPath = file + ".lock";
  let pending = Promise.resolve();
  const sign = state => crypto.createHmac("sha256", secret).update(JSON.stringify(state)).digest("hex");
  const sealed = state => ({ state, mac: sign(state) });
  function load() {
    let fd;
    try {
      fd = fs.openSync(file, fs.constants.O_RDONLY | fs.constants.O_NOFOLLOW);
    } catch (e) {
      if (e.code === "ENOENT") return emptyState();
      throw e;
    }
    try {
      if (fs.fstatSync(fd).size > 24 * 1024 * 1024) throw fail("Skill registry too large", 503);
      const envelope = JSON.parse(fs.readFileSync(fd, "utf8"));
      if (!envelope || !envelope.state || typeof envelope.mac !== "string" ||
          !/^[a-f0-9]{64}$/.test(envelope.mac)) throw fail("Skill registry envelope invalid", 503);
      const expected = Buffer.from(sign(envelope.state), "hex"), actual = Buffer.from(envelope.mac, "hex");
      if (!crypto.timingSafeEqual(expected, actual)) throw fail("Skill registry integrity check failed", 503);
      const state = envelope.state;
      if (state.schema !== 1 || !validRevision(state.revision) ||
          !Array.isArray(state.skills) || !Array.isArray(state.audit) || state.skills.length > MAX_SKILLS)
        throw fail("Skill registry schema invalid", 503);
      // Detect a corrupted record before returning even read-only metadata.
      for (const skill of state.skills) {
        if (!/^skill-[a-f0-9]{16}$/.test(skill.id) ||
            !Array.isArray(skill.versions) || !skill.versions.length || skill.versions.length > MAX_VERSIONS ||
            !Array.isArray(skill.workers) || !skill.workers.every(validWorker) ||
            !validRevision(skill.revision)) throw fail("Skill registry record invalid", 503);
        for (const ver of skill.versions) {
          if (!Number.isSafeInteger(ver.version) || ver.version < 1 ||
              typeof ver.name !== "string" || ver.name.length < 3 || ver.name.length > 80 ||
              typeof ver.content !== "string" || Buffer.byteLength(ver.content) > SKILL_MAX_CONTENT ||
              ver.sha256 !== digest(ver.content)) throw fail("Skill version integrity check failed", 503);
        }
        if (skill.activeVersion !== null &&
            !skill.versions.some(v => v.version === skill.activeVersion)) throw fail("Active skill version missing", 503);
      }
      return state;
    } catch (e) {
      if (e instanceof SyntaxError) throw fail("Skill registry unreadable", 503);
      throw e;
    } finally {
      fs.closeSync(fd);
    }
  }
  function persist(state) {
    fs.mkdirSync(dir, { recursive: true, mode: 0o700 });
    // Caller holds the cross-process exclusive write lock.
    const tmp = path.join(dir, "." + path.basename(file) + "." + crypto.randomBytes(12).toString("hex") + ".tmp");
    try {
      const fd = fs.openSync(tmp, fs.constants.O_CREAT | fs.constants.O_EXCL | fs.constants.O_WRONLY | fs.constants.O_NOFOLLOW, 0o600);
      try {
        fs.writeFileSync(fd, JSON.stringify(sealed(state)), "utf8");
        fs.fsyncSync(fd);
      } finally { fs.closeSync(fd); }
      fs.renameSync(tmp, file);
      const dirFd = fs.openSync(dir, fs.constants.O_RDONLY);
      try { fs.fsyncSync(dirFd); } finally { fs.closeSync(dirFd); }
    } finally {
      try { fs.unlinkSync(tmp); } catch (e) { if (e.code !== "ENOENT") throw e; }

    }
  }
  // Read and write under one exclusive local queue; a separate process writer
  // must not silently overwrite us. Re-load under the lock for CAS correctness.
  async function transact(update) {
    const run = pending.catch(() => {}).then(() => {
      fs.mkdirSync(dir, { recursive: true, mode: 0o700 });
      // Lock BEFORE reading: otherwise a second process can replay a stale read.
      // An abandoned lock fails closed for operator review rather than guessing.
      fs.mkdirSync(lockPath, { mode: 0o700 });
      try {
        const before = load();
        const state = structuredClone(before);
        const result = update(state);
        state.revision++;
        persist(state);
        return result;
      } finally {
        fs.rmdirSync(lockPath);
      }
    });
    pending = run;
    return run;
  }
  const metadata = item => ({
    id: item.id, name: item.name, revision: item.revision, activeVersion: item.activeVersion,
    latestVersion: item.versions.at(-1).version, workers: [...item.workers],
    status: item.activeVersion === null ? "draft" : item.workers.length ? "active" : "paused",
    updatedAt: item.updatedAt,
  });
  const locate = (state, id) => {
    const skill = state.skills.find(s => s.id === id);
    if (!skill) throw fail("Skill not found", 404);
    return skill;
  };
  const audit = (state, action, skill, actor) => {
    state.audit.push({ at: new Date(now()).toISOString(), action, id: skill.id,
      revision: skill.revision, version: skill.versions.at(-1).version, actor });
    if (state.audit.length > MAX_AUDIT) state.audit = state.audit.slice(-MAX_AUDIT);
  };
  const assertRevision = (skill, revision) => {
    if (!validRevision(revision) || revision !== skill.revision) throw fail("Stale skill revision. Refresh before editing.", 409);
  };
  return Object.freeze({
    list() {
      const state = load();
      return { skills: state.skills.map(metadata), audit: state.audit.slice(-100).reverse(),
        limits: { maxContentBytes: SKILL_MAX_CONTENT, maxPerWorker: SKILL_MAX_PER_WORKER } };
    },
    get(id) {
      const item = locate(load(), id);
      return { ...metadata(item), versions: item.versions.map(v => ({ ...v })) };
    },
    create(input, actor) {
      const checked = validateSkillDraft(input);
      return transact(state => {
        if (state.skills.length >= MAX_SKILLS) throw fail("Skill library is full", 409);
        const timestamp = new Date(now()).toISOString();
        const item = { id: "skill-" + crypto.randomBytes(8).toString("hex"), name: checked.name,
          revision: 1, activeVersion: null, workers: [], updatedAt: timestamp,
          versions: [{ version: 1, name: checked.name, content: checked.content, sha256: checked.sha256, createdAt: timestamp }] };
        state.skills.push(item);
        audit(state, "create-draft", item, actor);
        return metadata(item);
      });
    },
    revise(id, input, expectedRevision, actor) {
      const checked = validateSkillDraft(input);
      return transact(state => {
        const item = locate(state, id);
        assertRevision(item, expectedRevision);
        if (item.versions.length >= MAX_VERSIONS) throw fail("Skill version limit reached; archive this skill and create a new one", 409);
        const timestamp = new Date(now()).toISOString();
        item.name = checked.name;
        item.revision++;
        item.updatedAt = timestamp;
        item.versions.push({ version: item.versions.at(-1).version + 1, name: checked.name, content: checked.content,
          sha256: checked.sha256, createdAt: timestamp });
        audit(state, "new-draft-version", item, actor);
        return metadata(item);
      });
    },
    activate(id, version, workers, expectedRevision, actor) {
      if (!Array.isArray(workers) || workers.length < 1 || workers.length > SKILL_WORKERS.length ||
          new Set(workers).size !== workers.length || !workers.every(validWorker) ||
          !Number.isSafeInteger(version)) throw fail("Select one or more known workers and an exact skill version");
      return transact(state => {
        const item = locate(state, id);
        assertRevision(item, expectedRevision);
        if (version !== item.versions.at(-1).version) throw fail("Restore historical versions to a new draft before activation", 409);
        for (const role of workers) {
          const other = state.skills.filter(s => s.id !== id && s.activeVersion !== null && s.workers.includes(role));
          if (other.length >= SKILL_MAX_PER_WORKER) throw fail("Worker already has the maximum active skills: " + role, 409);
        }
        item.activeVersion = version;
        item.workers = [...workers];
        item.revision++;
        item.updatedAt = new Date(now()).toISOString();
        audit(state, "activate", item, actor);
        return metadata(item);
      });
    },
    pause(id, expectedRevision, actor) {
      return transact(state => {
        const item = locate(state, id);
        assertRevision(item, expectedRevision);
        item.workers = [];
        item.revision++;
        item.updatedAt = new Date(now()).toISOString();
        audit(state, "pause", item, actor);
        return metadata(item);
      });
    },
    restore(id, version, expectedRevision, actor) {
      if (!Number.isSafeInteger(version)) throw fail("Invalid version");
      return transact(state => {
        const item = locate(state, id);
        assertRevision(item, expectedRevision);
        const historic = item.versions.find(v => v.version === version);
        if (!historic) throw fail("Historical version not found", 404);
        if (item.versions.length >= MAX_VERSIONS) throw fail("Version limit reached", 409);
        item.name = historic.name;
        item.versions.push({ version: item.versions.at(-1).version + 1, name: historic.name, content: historic.content,
          sha256: historic.sha256, createdAt: new Date(now()).toISOString(), restoredFrom: version });
        item.revision++;
        item.updatedAt = new Date(now()).toISOString();
        audit(state, "restore-as-draft", item, actor);
        return metadata(item);
      });
    },
    assignedSkills() {
      const state = load(), result = Object.fromEntries(SKILL_WORKERS.map(role => [role, []]));
      for (const item of state.skills) {
        if (item.activeVersion === null) continue;
        const version = item.versions.find(v => v.version === item.activeVersion);
        for (const role of item.workers) {
          result[role].push({ id: item.id, name: version.name, version: version.version,
            sha256: version.sha256, content: version.content });
          if (result[role].length > SKILL_MAX_PER_WORKER) throw fail("Worker assignment integrity error", 503);
        }
      }
      return result;
    }
  });
}

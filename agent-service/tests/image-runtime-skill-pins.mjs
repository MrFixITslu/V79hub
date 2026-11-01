import fs from "node:fs";
import { createHash } from "node:crypto";

const roles = ["ceo","coo","finance","strategy","marketing","customer-service","technical-security","sales"];
const roleDefinitions = fs.readFileSync(new URL("../src/chat-roles.ts", import.meta.url), "utf8");
for (const role of roles) {
  const escaped = role.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const re = new RegExp("id:'" + escaped + "'[^\\n]*skillSha:'([a-f0-9]{40})'");
  const expected = re.exec(roleDefinitions)?.[1];
  if (!expected) throw Error("Missing pinned role SHA: " + role);
  const bytes = fs.readFileSync(new URL("../workforce/skills/" + role + "/SKILL.md", import.meta.url));
  const actual = createHash("sha1").update("blob " + bytes.length + "\\0").update(bytes).digest("hex");
  if (actual !== expected) throw Error("Runtime built-in skill SHA mismatch: " + role);
}
console.log("PINNED_ROLE_SKILLS_IN_IMAGE=8/8_PASS");

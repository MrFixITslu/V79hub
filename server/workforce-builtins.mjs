import {readFileSync} from "node:fs";
import {createHash} from "node:crypto";

// Build-time pinned skills. The registry may add advisory guidance but NEVER
// overwrite these trusted originals or replace the agent's runtime pins.
const ROLES = Object.freeze([
  {id:"ceo", name:"CEO", focus:"Strategic decisions, portfolio risk and founder priorities", sha:"29108d06d5fa30ad491dec022331811df134b376"},
  {id:"coo", name:"COO", focus:"Daily operations, service delivery and tracked blockers", sha:"46f5e0fe40c328aa4b66ad137e9b58b7bab703e1"},
  {id:"finance", name:"Finance", focus:"Verified finance signals, budgets and risk without transactions", sha:"be38136760e41013f0106d5a244807726d7999a5"},
  {id:"strategy", name:"Strategy", focus:"Roadmaps, trade-offs, partnerships and go/no-go decisions", sha:"5ec7c3214bc29bba8fe8e83eb2a5589790154dee"},
  {id:"marketing", name:"Marketing", focus:"Evidence-based campaign planning and consent-aware promotion", sha:"5265265024fe382d199043f4e70c3536730b21a6"},
  {id:"customer-service", name:"Customer Service", focus:"Tiquet support quality and responsible customer communication", sha:"9b98a8adf527784a69e9927b829e39f9cf44f0a8"},
  {id:"technical-security", name:"Technical & Security", focus:"System health, change reviews, security and restoration coverage", sha:"4dfdff55fc274fab3af00223f49cf42b267119b5"},
  {id:"sales", name:"Sales", focus:"Lead qualification, consent and evidence-based sales planning", sha:"0a3024ef6f2f612fc44fe07fa6a7110f709a08c8"},
]);
const verified = role => {
  if (!role) throw Object.assign(new Error("Unknown built-in specialist"),{status:404});
  // One fixed, repo-controlled path per known role. No untrusted path input.
  const bytes=readFileSync(new URL("../workforce/skills/"+role.id+"/SKILL.md",import.meta.url));
  const prefix=Buffer.from("blob "+bytes.length+"\0");
  const sha=createHash("sha1").update(prefix).update(bytes).digest("hex");
  if (sha !== role.sha) throw Object.assign(new Error("Built-in skill integrity failure"),{status:503});
  return {id:role.id,name:role.name,focus:role.focus,skillSha:sha,
    bytes:bytes.length,protected:true,content:bytes.toString("utf8")};
};
export function builtinSkillCatalog() {
  // Validate every source before returning ANY metadata; fail closed on tampering.
  return ROLES.map(role => {
    const {content,...meta}=verified(role);
    return meta;
  });
}
export function builtinSkillDetail(id) {
  if (typeof id!=="string") throw Object.assign(new Error("Invalid role"),{status:404});
  return verified(ROLES.find(role=>role.id===id));
}

#!/usr/bin/env node
// Read-only preview: no database connection and no writes.
import fs from "node:fs";
import { planLegacySubscriptions } from "../server/legacy-plan-migration.mjs";
const flags = process.argv.slice(2);
const value = name => { const i = flags.indexOf(name); return i >= 0 ? flags[i+1] : ""; };
if (flags.some(x => ["--apply","--write","--commit"].includes(x))) {
  console.error("Migration preview refuses mutation."); process.exit(2);
}
const file=value("--snapshot"), owner=value("--owner-organization-id");
if (!file || !owner || !fs.existsSync(file)) {
  console.error("Usage: node scripts/preview-trial-migration.mjs --snapshot <staging-json-copy> --owner-organization-id <verified-id>");
  process.exit(2);
}
try {
  const result = planLegacySubscriptions(JSON.parse(fs.readFileSync(file,"utf8")),owner);
  console.log(JSON.stringify({mode:"DRY_RUN_ONLY",...result.summary,requiresFounderApproval:true,productionDataTouched:false},null,2));
  if (result.summary.allowCustomerAccessWithoutVerifiedPolicy) process.exitCode=1;
} catch (e) { console.error("Preview failed:", e instanceof Error ? e.message : "invalid input"); process.exitCode=1; }

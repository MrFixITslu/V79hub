import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { resolve, dirname } from "node:path";

const root=resolve(dirname(fileURLToPath(import.meta.url)),"..");
const files=[
  "server.ts","docker-compose.yml",
  "src/components/AppSwitcher.tsx",
  "src/components/HubOverview.tsx",
];

test("Hub code, deployment defaults and both UI launchers use the canonical Academy hostname",()=>{
  for(const name of files){
    const text=readFileSync(resolve(root,name),"utf8");
    assert.ok(text.includes("https://academy.v79sl.com"),name+" must specify live Academy URL");
    assert.equal(text.includes("https://v79academy.v79sl.com"),false,
      name+" must not reference obsolete Academy domain");
    assert.equal(text.includes("https://academy.v79sl.com/academy"),false,
      name+" must not append obsolete /academy path");
  }
});

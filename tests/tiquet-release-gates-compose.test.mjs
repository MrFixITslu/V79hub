// No production access. Test the exact isolated Hub Compose source and server flag.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
const read=f=>fs.readFileSync(new URL(f,import.meta.url),"utf8");
test("Hub-to-Tiquet session binding explicitly defaults OFF",()=>{
 const yaml=read("../docker-compose.yml");
 const server=read("../server.ts");
 assert.equal((yaml.match(/^\s+V79_HUB_TIQUET_SESSION_BINDING:\s*\$\{V79_HUB_TIQUET_SESSION_BINDING:-0\}\s*$/gm)||[]).length,1);
 assert.match(server,/process\.env\.V79_HUB_TIQUET_SESSION_BINDING === "1"/);
 assert.ok(yaml.includes("V79_TIQUET_LAUNCH_SECRET"));
 assert.ok(yaml.includes("TIQUET_PUBLIC_URL"));
 assert.ok(!/V79_HUB_TIQUET_SESSION_BINDING:\s*\$\{[^}]*:-1\}/.test(yaml));
});
test("a safe source diff never changes service topology, image, DB or mail config",()=>{
 const yaml=read("../docker-compose.yml");
 assert.match(yaml,/^\s*v79-hub:/m);
 assert.match(yaml,/^\s*v79-hub-postgres:/m);
 assert.match(yaml,/WIPAY_ENABLED/);
 assert.match(yaml,/RESEND_API_KEY/);
 assert.match(yaml,/V79_HUB_STORE_BACKEND/);
 assert.match(yaml,/V79_PLATFORM_SHARED_SECRET/);
 assert.match(yaml,/V79_TIQUET_LAUNCH_SECRET/);
 assert.match(yaml,/V79_HUB_TIQUET_SESSION_BINDING/);
});

import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { spawnSync } from "node:child_process";

const filename=new URL("../scripts/v79-v2-readonly-baseline.sh",import.meta.url);
const contents=readFileSync(filename,"utf8");
test("live-baseline collection is syntactically valid and strictly read-only",()=>{
 const syntax=spawnSync("bash",["-n",filename.pathname],{encoding:"utf8"});
 assert.equal(syntax.status,0,syntax.stderr||"bash parser failed");
 assert.match(contents,/docker ps -a --no-trunc/);
 assert.match(contents,/docker inspect --type=container/);
 assert.match(contents,/IMMUTABLE_IMAGE_ID/);
 for(const pattern of [
   /docker (?:stop|start|restart|rm|rmi|run|exec|pull|push|build)/,
   /docker compose (?:up|down|pull|push|build)/,
   /--format.*\.Config\.Env/,
   /cat .*\.env/,
   /curl |wget |ssh |scp |rsync /,
   /delete|truncate|drop database|update .+ set/i,
 ])assert.doesNotMatch(contents,pattern);
});

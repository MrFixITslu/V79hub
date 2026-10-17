#!/usr/bin/env python3
"""Read-only G3 release inventory. Never print credentials or customer content."""
import hashlib
import json
import pathlib
import subprocess
import sys


def command(args, stdin=None):
    result = subprocess.run(args, input=stdin, capture_output=True, timeout=30)
    if result.returncode:
        raise RuntimeError("Inventory command failed; sensitive output withheld")
    return result.stdout


def inspect(name):
    return json.loads(command(["docker", "inspect", name]))[0]


def snapshot(info):
    state = info.get("State", {})
    return {"id": info["Id"], "image": info["Image"],
            "started_at": state.get("StartedAt"), "running": state.get("Running")}


NODE = r"""
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {createRequire} from 'node:module';
const hash=b=>crypto.createHash('sha256').update(b).digest('hex');
const out={source_files:[],runtime_source_hashes:{},database:{inspected:false},
  production_enabled:process.env.V79_MARKETING_PRODUCTION_ENABLED==='1',
  production_publish_enabled:process.env.V79_MARKETING_PRODUCTION_PUBLISH_ENABLED==='1',
  local_model_configured:Boolean(process.env.OLLAMA_BASE_URL)};
for(const name of ['/app/server.ts','/app/dist/server.cjs','/app/dist/server.cjs.map']){
  if(!fs.existsSync(name))continue;
  const b=fs.readFileSync(name);out.source_files.push({path:name,bytes:b.length,sha256:hash(b)});
  if(name.endsWith('.map')){
    const map=JSON.parse(b.toString('utf8'));
    for(let i=0;i<(map.sources||[]).length;i++){
      const p=path.posix.normalize(map.sources[i]);
      if(p.includes('node_modules')||typeof map.sourcesContent?.[i]!=='string')continue;
      out.runtime_source_hashes[p]=hash(Buffer.from(map.sourcesContent[i],'utf8'));
    }
  }
}
const dbPath=process.env.DATABASE_PATH||path.join(process.cwd(),'data','v79_marketing.sqlite');
out.database.path=dbPath;
if(fs.existsSync(dbPath)){
  let db;
  try{
    const require=createRequire(path.join(process.cwd(),'package.json'));
    const Database=require('better-sqlite3');
    db=new Database(dbPath,{readonly:true,fileMustExist:true});
    db.pragma('query_only = ON');
    const tables=new Set(db.prepare("SELECT name FROM sqlite_master WHERE type='table'").all().map(x=>x.name));
    out.database.counts={};
    for(const table of ['businesses','users','social_accounts','posts','post_deliveries','campaigns'])
      if(tables.has(table))out.database.counts[table]=db.prepare(`SELECT COUNT(*) AS n FROM ${table}`).get().n;
    if(tables.has('social_accounts'))out.database.connected_by_platform=db.prepare(
      'SELECT platform,COUNT(*) AS count FROM social_accounts WHERE connected=1 GROUP BY platform').all();
    if(tables.has('posts'))out.database.posts_by_status=db.prepare(
      'SELECT status,COUNT(*) AS count FROM posts GROUP BY status').all();
    if(tables.has('users')&&tables.has('businesses'))out.database.founder_links=db.prepare(
      "SELECT b.id AS business_id,b.hub_organization_id AS organization_id,u.hub_user_id AS scoped_hub_user_id FROM businesses b JOIN users u ON u.business_id=b.id WHERE u.email=? AND u.role='BUSINESS_OWNER' LIMIT 5").all('vision79slu@gmail.com');
    out.database.inspected=true;
  }catch{out.database.error='Read-only SQLite inspection unavailable; no raw error disclosed';}
  finally{db?.close();}
}
console.log(JSON.stringify(out));
"""


def main():
    names = ("v79marketing-app", "v79-hub", "v79-business-agent",
             "v79-hub-postgres", "v79-tiquet-manager", "tiquet-postgres")
    before = {name: inspect(name) for name in names}
    result = {"mode": "read-only", "deployment_performed": False,
              "containers": {}, "marketing_compose_files": []}
    for name, info in before.items():
        labels = info.get("Config", {}).get("Labels") or {}
        image = json.loads(command(["docker", "image", "inspect", info["Image"]]))[0]
        result["containers"][name] = {
            **snapshot(info),
            "health": (info.get("State", {}).get("Health") or {}).get("Status"),
            "revision": (image.get("Config", {}).get("Labels") or {}).get("org.opencontainers.image.revision"),
            "project": labels.get("com.docker.compose.project"),
            "service": labels.get("com.docker.compose.service"),
            "compose_files": labels.get("com.docker.compose.project.config_files"),
            "working_directory": labels.get("com.docker.compose.project.working_dir"),
            "mounts": [{"source": m["Source"], "destination": m["Destination"],
                        "writable": m["RW"]} for m in info.get("Mounts", [])],
        }
    files = (before["v79marketing-app"].get("Config", {}).get("Labels") or {}).get(
        "com.docker.compose.project.config_files", "")
    for name in files.split(","):
        if not name:
            continue
        p = pathlib.Path(name)
        result["marketing_compose_files"].append({
            "path": name, "exists": p.is_file(),
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None,
        })
    result["marketing_runtime"] = json.loads(command(
        ["docker", "exec", "-i", "v79marketing-app", "node", "--input-type=module", "-"],
        NODE.encode()))
    after = {name: snapshot(inspect(name)) for name in names}
    result["live_container_identity_unchanged"] = all(
        snapshot(before[name]) == after[name] for name in names)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("STOP: read-only inventory could not complete; sensitive output withheld", file=sys.stderr)
        sys.exit(1)

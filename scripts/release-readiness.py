#!/usr/bin/env python3
"""Read-only release evidence collector. No apply/deploy/restore mode exists.

Never import either application or print inspect/config/log payloads. Docker
exec helpers use built-ins for hashes or a READ ONLY PostgreSQL transaction.
Raw environment, connection strings, credentials and customer rows stay private.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from datetime import datetime, timezone

APPS = {"hub": "v79-hub", "tiquet": "v79-tiquet-manager"}
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^sha256:[0-9a-f]{64}$")
SOURCE_ROOTS = ["server", "src", "scripts", ".github/workflows"]
SOURCE_FILES = ["server.ts", "package.json", "package-lock.json", "Dockerfile", "docker-compose.yml"]
FLAGS = ["V79_REQUIRE_ADMIN_MFA", "V79_SENTINEL_INGEST_ENABLED", "V79_ALLOW_LEGACY_AUTH",
         "V79_ALLOW_EMAIL_ACCOUNT_LINK", "V79_ENTITLEMENT_RECHECK_ENABLED",
         "V79_HUB_MANAGED_BILLING", "V79_SENTINEL_QA_CREATE_ENABLED", "V79_SENTINEL_QA_CLEANUP_ENABLED",
         "WIPAY_ENABLED"]

SOURCE_HELPER = r'''
const fs = require('node:fs'), path = require('node:path'), crypto = require('node:crypto');
const roots = ['server', 'src', 'scripts', '.github/workflows'];
const fixed = ['server.ts','package.json','package-lock.json','Dockerfile','docker-compose.yml'];
const files = {}, unreadable = [], symlinks = [];
function walk(rel, assets=false) {
  const p = path.join('/app', rel);
  let st; try { st=fs.lstatSync(p); } catch(e) { if(e.code !== 'ENOENT') unreadable.push(rel); return; }
  if(st.isSymbolicLink()) { symlinks.push(rel); return; }
  if(st.isDirectory()) { for(const n of fs.readdirSync(p).sort()) {
    if(n.startsWith('.env') || ['node_modules','data','uploads','logs','backups','.git'].includes(n)) continue;
    walk(path.posix.join(rel,n), assets);
  } return; }
  if(!st.isFile()) return;
  if(!assets && !/\.(?:mjs|cjs|js|ts|tsx|jsx|json|sql|sh|py|ya?ml)$/.test(rel) && !fixed.includes(rel)) return;
  if(st.size > 16*1024*1024) { unreadable.push(rel); return; }
  const b=fs.readFileSync(p), sha256=crypto.createHash('sha256').update(b).digest('hex');
  const git=crypto.createHash('sha1').update(Buffer.from('blob '+b.length+'\0')).update(b).digest('hex');
  files[rel]={git,sha256,mode:(st.mode & 0o777).toString(8)};
}
for(const r of [...roots,...fixed]) walk(r);
const source={...files}; walk('dist',true);
const assets=Object.fromEntries(Object.entries(files).filter(([p])=>p.startsWith('dist/')));
const fingerprint=o=>crypto.createHash('sha256').update(JSON.stringify(Object.entries(o).sort())).digest('hex');
const markers={};
for(const rel of ['data/tiquet.db','data/tiquet.db.migrated','data/data.db','data/data.db.migrated',
 'data/.jwt_secret','data/.sa_jwt_secret']) {
 try { const s=fs.lstatSync('/app/'+rel); markers[rel]={present:true,regular:s.isFile(),symlink:s.isSymbolicLink(),mode:(s.mode&0o777).toString(8)}; }
 catch(e) { markers[rel]={present:false}; }
}
console.log(JSON.stringify({source,unreadable,symlinks,dist_files:Object.keys(assets).length,
 dist_sha256:fingerprint(assets),markers,installed_dependencies_verified:false}));
'''

DB_HELPER = r'''
import pg from 'pg';
import crypto from 'node:crypto';
// dotenv config reads only files and alters only this short-lived audit process.
// Do not import server/db.js or server/index.js: both can run startup migrations.
try { const d=await import('dotenv'); d.config({path:'/app/.env',quiet:true}); } catch {}
const isHub=process.env.V79_AUDIT_APP === 'hub';
if(isHub && process.env.V79_HUB_STORE_BACKEND !== 'postgres') {
 console.log(JSON.stringify({backend:'not-confirmed-postgres',migration_applied:'UNVERIFIED'}));
} else {
 const options={connectionTimeoutMillis:4000,query_timeout:5000,
   options:'-c default_transaction_read_only=on -c statement_timeout=5000 -c lock_timeout=1000'};
 if(process.env.DATABASE_URL) options.connectionString=process.env.DATABASE_URL;
 else Object.assign(options,{host:process.env.DB_HOST||'tiquet-postgres',port:Number(process.env.DB_PORT||5432),
   database:process.env.DB_NAME||'tiquet',user:process.env.DB_USER||'tiquet_app',password:process.env.DB_PASSWORD,
   ssl:process.env.DB_SSL==='true'?{rejectUnauthorized:false}:false});
 const client=new pg.Client(options);
 try {
  await client.connect(); await client.query('BEGIN READ ONLY');
  const version=(await client.query('SHOW server_version')).rows[0].server_version;
  const ro=(await client.query('SHOW transaction_read_only')).rows[0].transaction_read_only;
  const cols=(await client.query(`SELECT table_name,column_name,data_type,is_nullable,column_default
    FROM information_schema.columns WHERE table_schema='public' ORDER BY table_name,ordinal_position`)).rows;
  const indexes=(await client.query(`SELECT tablename,indexname,indexdef FROM pg_indexes
    WHERE schemaname='public' ORDER BY tablename,indexname`)).rows;
  const schema_sha256=crypto.createHash('sha256').update(JSON.stringify({cols,indexes})).digest('hex');
  const has=(t,c)=>cols.some(r=>r.table_name===t&&(!c||r.column_name===c));
  const ledgers=['schema_migrations','migrations','knex_migrations','_prisma_migrations'].filter(t=>has(t));
  const checks=isHub?{state_table:has('v79_hub_state'),revision_column:has('v79_hub_state','revision'),
    state_column:has('v79_hub_state','state')}:{accounts:has('accounts'),users:has('users'),jobs:has('jobs'),
    hub_account_link:has('accounts','huborganizationid'),hub_user_link:has('users','hubuserid')};
  console.log(JSON.stringify({backend:'postgres',server_version:version,transaction_read_only:ro,
   schema_sha256,checks,migration_ledger_tables:ledgers,migration_applied:'UNVERIFIED',customer_rows_read:0}));
  await client.query('ROLLBACK');
 } catch { console.log(JSON.stringify({backend:'postgres',status:'READ_ONLY_QUERY_UNAVAILABLE',migration_applied:'UNVERIFIED'})); }
 finally { await client.end().catch(()=>{}); }
}
'''

def run(args, input_text=None, timeout=25):
    """Capture all diagnostics privately; never return command/error payloads."""
    try:
        r = subprocess.run(args, input=input_text, capture_output=True, text=True,
                           timeout=timeout, env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"})
        return r.stdout if r.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None

def parsed(raw):
    try:
        return json.loads(raw) if raw else None
    except (ValueError, TypeError):
        return None

def metadata(path):
    p = Path(path)
    try:
        st = p.lstat()
        return {"present": True, "mode": oct(st.st_mode & 0o777), "uid": st.st_uid,
                "gid": st.st_gid, "symlink": p.is_symlink(), "regular": p.is_file()}
    except OSError:
        return {"present": False}

def config_metadata(path):
    result = metadata(path)
    p = Path(path)
    # Hash complete Compose source files, never .env or individual secrets.
    if result.get('regular') and not result.get('symlink') and p.suffix in ('.yml', '.yaml'):
        try:
            if p.stat().st_size <= 1024*1024:
                result['sha256'] = hashlib.sha256(p.read_bytes()).hexdigest()
        except OSError:
            result['hash'] = 'UNAVAILABLE'
    return result

def source_path(path):
    return path in SOURCE_FILES or any(path.startswith(r + "/") for r in SOURCE_ROOTS)

def repo_evidence(path):
    head = run(["git", "-C", str(path), "rev-parse", "HEAD"])
    if not head or not HEX40.fullmatch(head.strip()):
        return {"path": str(path), "repository": False}
    commit = head.strip()
    raw = run(["git", "-C", str(path), "ls-tree", "-rz", commit])
    files = {}
    for item in (raw or "").split("\0"):
        if "\t" in item:
            info, name = item.split("\t", 1)
            mode, kind, sha = info.split()
            if kind == "blob" and source_path(name):
                files[name] = sha
    # Status only reports the number of changed source paths, not names of
    # untracked private files. It never refreshes the index (optional locks off).
    status = run(["git", "-C", str(path), "status", "--porcelain=v1", "-z", "--untracked-files=no"])
    dirty = None if status is None else sum(bool(v) for v in status.split("\0"))
    tree = run(["git", "-C", str(path), "rev-parse", commit + "^{tree}"])
    return {"path": str(path), "repository": True, "commit": commit,
            "tree": tree.strip() if tree else None, "tracked_status_entries": dirty, "files": files}

def compare(runtime, reference, packaged_only=False):
    expected = {p: h for p, h in reference.items()
                if not packaged_only or p.startswith(("server/", "scripts/")) or p in ("package.json", "package-lock.json")}
    got = {p: v["git"] for p, v in runtime.items() if p in expected}
    missing = sorted(set(expected) - set(runtime))
    different = sorted(p for p in got if got[p] != expected[p])
    extra = sorted(p for p in runtime if p not in reference)
    return {"compared": len(got), "matching": sum(got[p] == expected[p] for p in got),
            "missing": missing, "different": different, "extra_runtime_source": extra,
            "coverage": "packaged server/scripts/packages" if packaged_only else "source inventory",
            "build_attestation_verified": False}

def image_evidence(image_id):
    raw = parsed(run(["docker", "image", "inspect", image_id]))
    if not raw:
        return {"inspection": "UNAVAILABLE"}
    i = raw[0]
    revision = i.get("Config", {}).get("Labels", {}) or {}
    return {"id": i.get("Id"), "repo_digests": i.get("RepoDigests") or [],
            "revision": {k: v for k, v in revision.items()
                         if k in ("org.opencontainers.image.revision", "v79.commit") and HEX40.fullmatch(str(v))},
            "created": i.get("Created"), "os": i.get("Os"), "architecture": i.get("Architecture")}

def audit(references):
    report = {"collected_utc": datetime.now(timezone.utc).isoformat(), "production": "NO-GO",
              "read_only": True, "live_restore_test_performed": False, "apps": {}}
    for app, name in APPS.items():
        containers = parsed(run(["docker", "inspect", name]))
        if not containers:
            report["apps"][app] = {"inspection": "UNAVAILABLE"}
            continue
        c = containers[0]
        config, hc = c["Config"], c.get("HostConfig", {})
        env = dict(v.split("=", 1) for v in config.get("Env", []) if "=" in v)
        labels = config.get("Labels") or {}
        mounts = [{k: m.get(k) for k in ("Type", "Name", "Source", "Destination", "RW")}
                  for m in c.get("Mounts", [])]
        shape = {"User": config.get("User"), "WorkingDir": config.get("WorkingDir"),
                 "Entrypoint": config.get("Entrypoint"), "Cmd": config.get("Cmd")}
        item = {"container_id": c["Id"], "image": image_evidence(c["Image"]),
                "image_tag_at_creation": config.get("Image"),
                "status": c["State"]["Status"], "health": c["State"].get("Health", {}).get("Status", "UNAVAILABLE"),
                "started": c["State"].get("StartedAt"), "mounts": mounts,
                "networks": sorted(c.get("NetworkSettings", {}).get("Networks", {})),
                "restart_policy": hc.get("RestartPolicy", {}).get("Name"), "privileged": hc.get("Privileged"),
                "readonly_rootfs": hc.get("ReadonlyRootfs"), "security_opt": hc.get("SecurityOpt"),
                "startup_config_sha256": hashlib.sha256(json.dumps(shape, sort_keys=True).encode()).hexdigest(),
                "user": config.get("User"), "environment_key_count": len(env),
                "flags_at_container_creation": {k: ("ON" if env[k] == "1" else "OFF" if env[k] == "0" else "UNSET_OR_OTHER")
                                                 if k in env else "UNSET_OR_OTHER" for k in FLAGS},
                "application_dotenv_overlay_verified": False,
                "compose": {"project": labels.get("com.docker.compose.project"),
                            "service": labels.get("com.docker.compose.service"),
                            "config_files": labels.get("com.docker.compose.project.config_files"),
                            "working_dir": labels.get("com.docker.compose.project.working_dir")}}
        paths = (item["compose"]["config_files"] or "").split(",")
        item["protected_host_files"] = {p: config_metadata(p) for p in paths if p}
        wd = item["compose"]["working_dir"]
        if wd:
            for fname in (".env", ".deployed_sha", "docker-compose.override.yml"):
                item["protected_host_files"][str(Path(wd) / fname)] = config_metadata(Path(wd) / fname)
            try:
                stamp_path = Path(wd) / '.deployed_sha'
                stamp = stamp_path.read_text().strip() if not stamp_path.is_symlink() else ''
                item['deployed_sha_stamp'] = stamp if HEX40.fullmatch(stamp) else 'INVALID_OR_UNAVAILABLE'
            except OSError:
                item['deployed_sha_stamp'] = 'UNAVAILABLE'
        inventory = parsed(run(["docker", "exec", "-i", name, "node", "-e", SOURCE_HELPER], timeout=45))
        if inventory:
            item["runtime_inventory"] = inventory
            item["github_comparison"] = {}
            for label, ref in references.items():
                if ref["repo"] == ("V79hub" if app == "hub" else "V79Tiquet"):
                    item["github_comparison"][label] = {"commit": ref["commit"], **compare(inventory["source"], ref["files"], app == "tiquet")}
        else:
            item["runtime_inventory"] = "UNAVAILABLE"
        dirs = {Path.home() / ("v79hub" if app == "hub" else "V79Tiquet")}
        if wd:
            dirs.add(Path(wd))
        item["repositories"] = []
        for path in sorted(dirs):
            evidence = repo_evidence(path)
            if evidence.get('files'):
                evidence['github_vs_local_commit'] = {}
                for label, ref in references.items():
                    if ref['repo'] == ('V79hub' if app == 'hub' else 'V79Tiquet'):
                        local = {p: {'git': sha} for p, sha in evidence['files'].items()}
                        evidence['github_vs_local_commit'][label] = compare(local, ref['files'])
            if evidence.get("files") and inventory:
                evidence["runtime_vs_commit"] = compare(inventory["source"], evidence.pop("files"), app == "tiquet")
            else:
                evidence.pop("files", None)
            item["repositories"].append(evidence)
        item["database_read_only_metadata"] = parsed(run(["docker", "exec", "-i", "-e", "V79_AUDIT_APP=" + app,
               name, "node", "--input-type=module", "-"], DB_HELPER, timeout=20)) or "UNAVAILABLE"
        health_url = 'http://127.0.0.1:' + ('3040/api/health' if app == 'hub' else '3050/health')
        health_code = "fetch(" + json.dumps(health_url) + ", {signal:AbortSignal.timeout(4000)}).then(r=>" + \
            "console.log(JSON.stringify({http_status:r.status,ok:r.ok}))).catch(()=>" + \
            "console.log(JSON.stringify({status:'UNAVAILABLE'})))"
        item['local_http_health'] = parsed(run(['docker','exec',name,'node','-e',health_code],timeout=8)) or 'UNAVAILABLE'
        report["apps"][app] = item
    # Container identities only: no env, labels, ports, logs or customer records.
    rows = run(["docker", "ps", "-a", "--format", "{{.ID}} {{.Names}} {{.Status}}"])
    report["existing_service_inventory"] = rows.splitlines() if rows else "UNAVAILABLE"
    report['database_containers'] = {}
    for name in ('v79-hub-postgres', 'tiquet-postgres'):
        raw = parsed(run(['docker','inspect',name]))
        if not raw:
            report['database_containers'][name] = {'inspection':'UNAVAILABLE','application_mapping_verified':False}
            continue
        db = raw[0]
        labels = db.get('Config',{}).get('Labels') or {}
        report['database_containers'][name] = {
            'container_id':db['Id'],'image':image_evidence(db['Image']),
            'status':db['State']['Status'],'health':db['State'].get('Health',{}).get('Status','UNAVAILABLE'),
            'mounts':[{k:m.get(k) for k in ('Type','Name','Source','Destination','RW')} for m in db.get('Mounts',[])],
            'networks':sorted(db.get('NetworkSettings',{}).get('Networks',{})),
            'compose_project':labels.get('com.docker.compose.project'),
            'compose_service':labels.get('com.docker.compose.service'),
            'application_mapping_verified':False}
    report['backup_candidates'] = {}
    for root in [Path('/opt/v79/hub/backups'), Path.home()/'v79hub/backups', Path.home()/'backups']:
        files = []
        try:
            for p in sorted(root.iterdir(), key=lambda p: p.lstat().st_mtime, reverse=True)[:10]:
                s = p.lstat()
                files.append({'name': p.name, 'size': s.st_size, 'mode': oct(s.st_mode & 0o777),
                              'symlink': p.is_symlink(), 'regular': p.is_file(), 'mtime': s.st_mtime})
        except OSError:
            pass
        report['backup_candidates'][str(root)] = {'entries': files, 'recoverability_verified': False}
    return report

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["audit"])
    parser.add_argument("--references", type=Path, help="Pinned public Git blob reference inventory")
    args = parser.parse_args(argv)
    references = {}
    if args.references:
        references = json.loads(args.references.read_text())
    else:
        # A separately generated, literal public manifest can be inserted here
        # for stdin execution. No file download or network call occurs in audit.
        references = EMBEDDED_REFERENCES
    print(json.dumps(audit(references), indent=2, sort_keys=True))
    return 0

EMBEDDED_REFERENCES = json.loads(r'''{"hub_main":{"repo":"V79hub","commit":"c45d305b98d6080c07a5d2e35f7941a8ef15f4ce","tree":"2c4272d399ecbe12056ae47329a3dfb61f83b6ed","files":{".github/workflows/deploy-ecosystem.yml":"eae7749e4dbef99a6eba76924eb6789cfc29b12b",".github/workflows/v79-01-ephemeral-staging.yml":"39c9d275b8fad2643502dc2a821b9a5c3e60d0de",".github/workflows/v79-ci-cd.yml":"8dd7b429647443983dedcd2ec5bfef99e16e2443","Dockerfile":"16e222c8252efbb12d5643fcd9913d8c11e11547","docker-compose.yml":"556c8412e12af6f2f59ac3d52efe3d4f2283a788","package-lock.json":"11215761d6d66d6d46fdac5398eeb75e1549ca5b","package.json":"8dbe55e032f26f5288ee9d70a1c2cb9ac148aade","scripts/agent-staging-preflight.mjs":"14335bcc9417a7b4272b8cf680aa41a2aef3a324","scripts/approved-production-cutover.mjs":"825b069a9552e7bc5160bd00279b683e3d2d1eb0","scripts/check-integrations.mjs":"048cc2e1ae317b05e3b5d319807fe632d6ab9d2b","scripts/convert-pos-account.mjs":"c1726eaf611a2d27593db212faaf13537982dcc6","scripts/deploy-ecosystem-release.sh":"2c827c2bd426830107535661f349fcd39cba650a","scripts/deploy-server.sh":"4fa420a4adc081f3505f61fa61ee684f762302e9","scripts/migrate-store-to-postgres.mjs":"61bce13d02a3211e342067321c9a70edf53b118b","scripts/preview-trial-migration.mjs":"cd2f1c1877801f3a9d27cdaf91c79b01acc519ad","scripts/read-only-live-cutover-preflight.mjs":"7fe119e6075eb11c110612dd083f7035d2e5866f","scripts/recover-owner.mjs":"fe16a3af5fcd4686cee85a3d9c3b90266b9c2cd1","scripts/rehearse-approved-cutover.mjs":"c8e94386ee69f6a492f8bae88600b32762191faf","scripts/release-config-audit.mjs":"d51e052b3e6193330f6b1e612334358a8292ed69","scripts/resend-authoritative-dns.mjs":"95621ce15e775cb77b6ed71c930c9960e9f61916","scripts/resend-dns-preflight.mjs":"5d347dca941190df0de2e6d4f9697fc2ba3e558d","scripts/reset-admin-password.mjs":"ddef95fc111e8fcce77734d07527271fc1af2fac","scripts/smoke-launches.mjs":"3ba02322bc82e7ee8b8e1ee055520f09facf7d6a","scripts/staging-resend-smoke.mjs":"77ac98d50b8b42931492f0c5136f39e466f44ea4","scripts/verify-sentinel-preservation.sh":"33f557d068e207437da47bf9361fa04b8f2a5443","server.ts":"699389a0b854df595e4cac0918445d5196307dd3","server/agent-access.mjs":"8d7fb14a5b8e95b8320d93becfe4ef4db1bfa907","server/agent-approval-audit-chain.mjs":"62db000a5ffbc6ee7138adc4f0d0bcdbc71fe95a","server/agent-approval-checkpoint-retention.mjs":"2770faaebddf0e7c8f8acfdb51b456954723e463","server/agent-approval-ledger.mjs":"87961e5fcd925495b0d9474e3b3d287677147e59","server/agent-evidence-attestation.mjs":"907f4da5edee6a1d0377245023f7190a7c244afa","server/agent-proposal-inbox.mjs":"914620fded08002ff85e260df81c6ab034c11e69","server/agent-proposals.mjs":"d0cf9e1f654606b0e67b4fdb498aa03b6c9c3e99","server/agent-reviewed-handoff.mjs":"5ba448e7b1256a07175c73e30dd15b28c744a37d","server/agent-supervised-marketing.mjs":"31ff2a72fe3519a6d31ff08750778038505d585d","server/agent-supervised-tiquet.mjs":"0eec3d1e9f2219d91bd390c7728aeb3e7a2dc2e6","server/billing-contract.mjs":"777ef93b5132e54ee6ace7bb88ba2a43e10d6eb1","server/entitlement-validation.mjs":"8c957d262e1fca5c7939684a150e3279061a4f3a","server/ffpro-provisioning.mjs":"5270e768abbbc196acbe4e26ec80610625343899","server/legacy-cutover.mjs":"e1d51ff0926971cda89cba15bc436024632c5411","server/legacy-plan-migration.mjs":"dc95c8b5d9310c9a34eddc9792e26c873fbba850","server/marketing-provisioning.mjs":"0c039bb18773012f7bb94d5636124fd9da24105e","server/onboarding-store.mjs":"5f6342e8cfa2871bda643efaa3c02b2ddc846805","server/organization-access.mjs":"3cd3b315974886df22ebaf75b9aac97580eb2d2d","server/organization-store.mjs":"fa26340afb861f20df39b4a558285c3150e8aaec","server/platform-contract.mjs":"d7c85a149f9b053314cb085d0874690ed7452e87","server/pos-provisioning.mjs":"355b1bc8bf5839aa5c5f9d3d1188675d4c38ce8b","server/postgres-store.mjs":"d3244d28c63077ad8a257f2e5444a5ef208d0ecc","server/resend-transactional.mjs":"bc2a61af623554aed5d61c6a49bef761cf1ea3f9","server/runtime-store.mjs":"e96405b9527cecbe36d5db50d268561816fee5d8","server/security-contract.mjs":"a2d13478cddad88971996608d644b7d2c093c50b","server/sentinel-audit-retention.mjs":"624e9ec7e28311f0a1e122169ba6208565d1e6ea","server/sentinel-qa-cleanup.mjs":"ef4a648dc410dd84b8a32b99faec960e0b4863ae","server/sentinel-qa-create.mjs":"34521d93a2ea93ffeb2f43befe434a0495ca37fa","server/sentinel-qa-routes.mjs":"96476be32773799b473220cfd51bea54c2b4e9ed","server/sentinel-write-fence.mjs":"b60bb6a1ad381074c7faf85734b3febe4f1b5795","server/source-metric-signature.mjs":"0e898cc9b38eac557892cd7162b6b5193c97029a","server/subscription-access.mjs":"c135b5710978f2fa862b3489d685aad6b2dc0994","server/team-invitation-store.mjs":"8fd442e64782e8454cbd1f826331df29147cd889","server/tiquet-provisioning.mjs":"2a834b164c3f15e4dd2be30d660b04840c9c6451","server/tiquet-signed-source-reader.mjs":"32e369e4c2bac83c33a3bb8add69ee35a522895e","server/transient-retry.mjs":"15205e90c5c66f643c4067096b1ab59e69587910","server/trial-reminder-dispatch.mjs":"578c1b786699be3c2c58c231f3ae7493e2491690","server/trial-reminders.mjs":"cc3c780cb8209f6990117e219bd8acda09ba5194","server/wipay-provider.mjs":"d24a1f82e224d260afa1f77279296ba4eb6846b7","src/App.tsx":"3785ca8e74b8b19c37a6d8509d57ac77726bfd6e","src/components/AcademyImport.tsx":"a1451c0233b7eb682b26aa76c427bee5d68745e3","src/components/AcademyJuniorAdmin.tsx":"df7c5794859b0f6375f30939e79e798d6fb06deb","src/components/AcademyLearners.tsx":"d55e88296ad22c33764c8563c18ccb4900cc1e7f","src/components/AcademyPublishing.tsx":"86ac06566a6da81f84fbfedfb5bd54576852cde0","src/components/AdminConsole.tsx":"25b03202ea9ae1c3a6fee02b25f510132307ff7e","src/components/AgentApprovalInbox.tsx":"939915d001f35f7fab4ee5daf0bb6c08fcc71b55","src/components/AppSwitcher.tsx":"4244527374358e011af6c6d36c802835e7c83b20","src/components/CustomerOnboardingAdmin.tsx":"5818dac50f56ecb9bbe99111e4b5a3b2679b8d20","src/components/FFPROPlatformAdmin.tsx":"3b710aca082eb45e049cbd29418e5d8c3df06010","src/components/HubOverview.tsx":"af7e752eb1fb258860c38cdc5bebc0869b015f82","src/components/InviteAcceptance.tsx":"29d3c5ee381e737defda823579d11f1dca5ff29b","src/components/Login.tsx":"f15357fc958065e369fda5a4e68c713539ad3543","src/components/MarketingPlatformAdmin.tsx":"bfc2a82af7dff4f5effce2a60365e467b9271d68","src/components/OwnerAssistant.tsx":"1255183ac3c8f275efd5a8fedd1404877bf504b1","src/components/POSPlatformAdmin.tsx":"c5fd7fc63ad3b7ae91e03c4315e0c1a1c4242b65","src/components/PlatformAdminOverview.tsx":"c066cda031d3b6bccc59e0e415ce066be3247be8","src/components/PlatformAuditAdmin.tsx":"26768b712f6f254be15a8fd5501d551759d5bb6c","src/components/PlatformCustomersAdmin.tsx":"ef40bf2074da7ed16290435626ac9ec15ea31e7f","src/components/PlatformPlansAdmin.tsx":"5fbf2cb4456c97609d2a3a048fca9946e72b5ef8","src/components/SentinelQaAdmin.tsx":"8dabd7cebf03e8360c6221e80b2d4be306419772","src/components/Sidebar.tsx":"b6486870f11497832a0eab561d755acbaf391209","src/components/SignedTiquetEvidencePanel.tsx":"cbb5db4dcff596cf41171001054b798f0a87e9bd","src/components/SupervisedTiquetTicketPicker.tsx":"99ec1724890861f9df6a9094f229c2752f52ea24","src/components/TeamInviteAcceptance.tsx":"5edd73106da8e5dac32801f210e21f5f896a5ba8","src/components/TiquetPlatformAdmin.tsx":"4b92c720fddb334c7a28d467206edd72fed8fd4b","src/components/UserManagement.tsx":"4ea5e8677238f58284559a09aaf45807b29608eb","src/components/WorkspaceBilling.tsx":"febce7908fc2eec8a3eaf9c8bb0ae6e78e0397d8","src/components/WorkspaceConnections.tsx":"98a26686fb474f10a1b134e923d1e70d2abf3833","src/components/WorkspaceSecurity.tsx":"7826ad3dbff9085dcb2215701aa1b9a5e4d2ab1c","src/components/WorkspaceTeam.tsx":"e494eaba5722dbe2868ab0cc76b6bc37ec51f6bb","src/index.css":"87723c1a8ea62d53da53d507878e2ca127a51009","src/lib/academyAdmin.ts":"a1eeaa59a7101cab4e49cf345e956f1ac162ee41","src/lib/appLaunch.ts":"e9341a55efb5e343e6cfffaa112361f8ccae78c8","src/lib/sentinel-qa-client.mjs":"5b03e610f5b3223e889794f95a35e116f092998b","src/main.tsx":"080dac371e6d8ba952c0c9a6f668e7195d77091e","src/types.ts":"0db05e2d5e31d0a7809b4f3b6c8787c8c395a679"}},"hub_pr129":{"repo":"V79hub","commit":"40e7d4fb0306299f82811d9591384934b2937862","tree":"ba2e9ec3fd90674ed1fbd73c4c55433c1842b95b","files":{".github/workflows/deploy-ecosystem.yml":"eae7749e4dbef99a6eba76924eb6789cfc29b12b",".github/workflows/v79-01-ephemeral-staging.yml":"39c9d275b8fad2643502dc2a821b9a5c3e60d0de",".github/workflows/v79-ci-cd.yml":"8dd7b429647443983dedcd2ec5bfef99e16e2443","Dockerfile":"16e222c8252efbb12d5643fcd9913d8c11e11547","docker-compose.yml":"556c8412e12af6f2f59ac3d52efe3d4f2283a788","package-lock.json":"11215761d6d66d6d46fdac5398eeb75e1549ca5b","package.json":"8dbe55e032f26f5288ee9d70a1c2cb9ac148aade","scripts/agent-staging-preflight.mjs":"14335bcc9417a7b4272b8cf680aa41a2aef3a324","scripts/approved-production-cutover.mjs":"825b069a9552e7bc5160bd00279b683e3d2d1eb0","scripts/check-integrations.mjs":"048cc2e1ae317b05e3b5d319807fe632d6ab9d2b","scripts/convert-pos-account.mjs":"c1726eaf611a2d27593db212faaf13537982dcc6","scripts/deploy-ecosystem-release.sh":"2c827c2bd426830107535661f349fcd39cba650a","scripts/deploy-server.sh":"251f1c57f57555ffa6d32794d2de47dac5b68a0b","scripts/migrate-store-to-postgres.mjs":"61bce13d02a3211e342067321c9a70edf53b118b","scripts/preview-trial-migration.mjs":"cd2f1c1877801f3a9d27cdaf91c79b01acc519ad","scripts/read-only-live-cutover-preflight.mjs":"7fe119e6075eb11c110612dd083f7035d2e5866f","scripts/recover-owner.mjs":"fe16a3af5fcd4686cee85a3d9c3b90266b9c2cd1","scripts/rehearse-approved-cutover.mjs":"c8e94386ee69f6a492f8bae88600b32762191faf","scripts/release-config-audit.mjs":"d51e052b3e6193330f6b1e612334358a8292ed69","scripts/resend-authoritative-dns.mjs":"95621ce15e775cb77b6ed71c930c9960e9f61916","scripts/resend-dns-preflight.mjs":"5d347dca941190df0de2e6d4f9697fc2ba3e558d","scripts/reset-admin-password.mjs":"ddef95fc111e8fcce77734d07527271fc1af2fac","scripts/smoke-launches.mjs":"3ba02322bc82e7ee8b8e1ee055520f09facf7d6a","scripts/staging-resend-smoke.mjs":"77ac98d50b8b42931492f0c5136f39e466f44ea4","scripts/verify-sentinel-preservation.sh":"5c71b552a662b5f75e112d44205b7d6e4192cc48","server.ts":"699389a0b854df595e4cac0918445d5196307dd3","server/agent-access.mjs":"8d7fb14a5b8e95b8320d93becfe4ef4db1bfa907","server/agent-approval-audit-chain.mjs":"62db000a5ffbc6ee7138adc4f0d0bcdbc71fe95a","server/agent-approval-checkpoint-retention.mjs":"2770faaebddf0e7c8f8acfdb51b456954723e463","server/agent-approval-ledger.mjs":"87961e5fcd925495b0d9474e3b3d287677147e59","server/agent-evidence-attestation.mjs":"907f4da5edee6a1d0377245023f7190a7c244afa","server/agent-proposal-inbox.mjs":"914620fded08002ff85e260df81c6ab034c11e69","server/agent-proposals.mjs":"d0cf9e1f654606b0e67b4fdb498aa03b6c9c3e99","server/agent-reviewed-handoff.mjs":"5ba448e7b1256a07175c73e30dd15b28c744a37d","server/agent-supervised-marketing.mjs":"31ff2a72fe3519a6d31ff08750778038505d585d","server/agent-supervised-tiquet.mjs":"0eec3d1e9f2219d91bd390c7728aeb3e7a2dc2e6","server/billing-contract.mjs":"777ef93b5132e54ee6ace7bb88ba2a43e10d6eb1","server/entitlement-validation.mjs":"8c957d262e1fca5c7939684a150e3279061a4f3a","server/ffpro-provisioning.mjs":"5270e768abbbc196acbe4e26ec80610625343899","server/legacy-cutover.mjs":"e1d51ff0926971cda89cba15bc436024632c5411","server/legacy-plan-migration.mjs":"dc95c8b5d9310c9a34eddc9792e26c873fbba850","server/marketing-provisioning.mjs":"0c039bb18773012f7bb94d5636124fd9da24105e","server/onboarding-store.mjs":"5f6342e8cfa2871bda643efaa3c02b2ddc846805","server/organization-access.mjs":"3cd3b315974886df22ebaf75b9aac97580eb2d2d","server/organization-store.mjs":"fa26340afb861f20df39b4a558285c3150e8aaec","server/platform-contract.mjs":"d7c85a149f9b053314cb085d0874690ed7452e87","server/pos-provisioning.mjs":"355b1bc8bf5839aa5c5f9d3d1188675d4c38ce8b","server/postgres-store.mjs":"d3244d28c63077ad8a257f2e5444a5ef208d0ecc","server/resend-transactional.mjs":"bc2a61af623554aed5d61c6a49bef761cf1ea3f9","server/runtime-store.mjs":"e96405b9527cecbe36d5db50d268561816fee5d8","server/security-contract.mjs":"a2d13478cddad88971996608d644b7d2c093c50b","server/sentinel-audit-retention.mjs":"624e9ec7e28311f0a1e122169ba6208565d1e6ea","server/sentinel-qa-cleanup.mjs":"ef4a648dc410dd84b8a32b99faec960e0b4863ae","server/sentinel-qa-create.mjs":"34521d93a2ea93ffeb2f43befe434a0495ca37fa","server/sentinel-qa-routes.mjs":"96476be32773799b473220cfd51bea54c2b4e9ed","server/sentinel-write-fence.mjs":"b60bb6a1ad381074c7faf85734b3febe4f1b5795","server/source-metric-signature.mjs":"0e898cc9b38eac557892cd7162b6b5193c97029a","server/subscription-access.mjs":"c135b5710978f2fa862b3489d685aad6b2dc0994","server/team-invitation-store.mjs":"8fd442e64782e8454cbd1f826331df29147cd889","server/tiquet-provisioning.mjs":"2a834b164c3f15e4dd2be30d660b04840c9c6451","server/tiquet-signed-source-reader.mjs":"32e369e4c2bac83c33a3bb8add69ee35a522895e","server/transient-retry.mjs":"15205e90c5c66f643c4067096b1ab59e69587910","server/trial-reminder-dispatch.mjs":"578c1b786699be3c2c58c231f3ae7493e2491690","server/trial-reminders.mjs":"cc3c780cb8209f6990117e219bd8acda09ba5194","server/wipay-provider.mjs":"d24a1f82e224d260afa1f77279296ba4eb6846b7","src/App.tsx":"3785ca8e74b8b19c37a6d8509d57ac77726bfd6e","src/components/AcademyImport.tsx":"a1451c0233b7eb682b26aa76c427bee5d68745e3","src/components/AcademyJuniorAdmin.tsx":"df7c5794859b0f6375f30939e79e798d6fb06deb","src/components/AcademyLearners.tsx":"d55e88296ad22c33764c8563c18ccb4900cc1e7f","src/components/AcademyPublishing.tsx":"86ac06566a6da81f84fbfedfb5bd54576852cde0","src/components/AdminConsole.tsx":"25b03202ea9ae1c3a6fee02b25f510132307ff7e","src/components/AgentApprovalInbox.tsx":"939915d001f35f7fab4ee5daf0bb6c08fcc71b55","src/components/AppSwitcher.tsx":"4244527374358e011af6c6d36c802835e7c83b20","src/components/CustomerOnboardingAdmin.tsx":"5818dac50f56ecb9bbe99111e4b5a3b2679b8d20","src/components/FFPROPlatformAdmin.tsx":"3b710aca082eb45e049cbd29418e5d8c3df06010","src/components/HubOverview.tsx":"af7e752eb1fb258860c38cdc5bebc0869b015f82","src/components/InviteAcceptance.tsx":"29d3c5ee381e737defda823579d11f1dca5ff29b","src/components/Login.tsx":"f15357fc958065e369fda5a4e68c713539ad3543","src/components/MarketingPlatformAdmin.tsx":"bfc2a82af7dff4f5effce2a60365e467b9271d68","src/components/OwnerAssistant.tsx":"1255183ac3c8f275efd5a8fedd1404877bf504b1","src/components/POSPlatformAdmin.tsx":"c5fd7fc63ad3b7ae91e03c4315e0c1a1c4242b65","src/components/PlatformAdminOverview.tsx":"c066cda031d3b6bccc59e0e415ce066be3247be8","src/components/PlatformAuditAdmin.tsx":"26768b712f6f254be15a8fd5501d551759d5bb6c","src/components/PlatformCustomersAdmin.tsx":"ef40bf2074da7ed16290435626ac9ec15ea31e7f","src/components/PlatformPlansAdmin.tsx":"5fbf2cb4456c97609d2a3a048fca9946e72b5ef8","src/components/SentinelQaAdmin.tsx":"8dabd7cebf03e8360c6221e80b2d4be306419772","src/components/Sidebar.tsx":"b6486870f11497832a0eab561d755acbaf391209","src/components/SignedTiquetEvidencePanel.tsx":"cbb5db4dcff596cf41171001054b798f0a87e9bd","src/components/SupervisedTiquetTicketPicker.tsx":"99ec1724890861f9df6a9094f229c2752f52ea24","src/components/TeamInviteAcceptance.tsx":"5edd73106da8e5dac32801f210e21f5f896a5ba8","src/components/TiquetPlatformAdmin.tsx":"4b92c720fddb334c7a28d467206edd72fed8fd4b","src/components/UserManagement.tsx":"4ea5e8677238f58284559a09aaf45807b29608eb","src/components/WorkspaceBilling.tsx":"febce7908fc2eec8a3eaf9c8bb0ae6e78e0397d8","src/components/WorkspaceConnections.tsx":"98a26686fb474f10a1b134e923d1e70d2abf3833","src/components/WorkspaceSecurity.tsx":"7826ad3dbff9085dcb2215701aa1b9a5e4d2ab1c","src/components/WorkspaceTeam.tsx":"e494eaba5722dbe2868ab0cc76b6bc37ec51f6bb","src/index.css":"87723c1a8ea62d53da53d507878e2ca127a51009","src/lib/academyAdmin.ts":"a1eeaa59a7101cab4e49cf345e956f1ac162ee41","src/lib/appLaunch.ts":"e9341a55efb5e343e6cfffaa112361f8ccae78c8","src/lib/sentinel-qa-client.mjs":"5b03e610f5b3223e889794f95a35e116f092998b","src/main.tsx":"080dac371e6d8ba952c0c9a6f668e7195d77091e","src/types.ts":"0db05e2d5e31d0a7809b4f3b6c8787c8c395a679"}},"tiquet_main":{"repo":"V79Tiquet","commit":"1edae1033d349d0dc99e7cb5fadaf84c39018a33","tree":"76d439ace4f744790dee1cfe10ca9554323a8a8e","files":{".github/workflows/v79-ci-cd.yml":"46f69e9422a42a1a34d7f7ae19aa8c272e3dd3ee","Dockerfile":"60976fe617bd1e3df380d4f13f2d5d6a3e2b49af","docker-compose.yml":"81139e79a2090a18b409214f5e9d508c22fc8dcc","package-lock.json":"0e94ae8fa9795f4655e4eff3d08f7eead586c929","package.json":"cf2a8dc0cf4f9f9a15d75a7a40bf1c32f2d0365f","scripts/backup-and-inventory.js":"6db5e89ad8c789141346cf8788443d8f426f34dc","scripts/backup-db.js":"38cdabc1cb680b25e2e172e9b02bc6947da206e2","scripts/deploy-server.sh":"77b9fa2eb9ab6e7b8a14ee01fa57d2a4a1e65439","scripts/generate-secrets.js":"066f3dfe88c4447b05ab880ae36dba3fdd769954","scripts/migrate-sqlite-to-pg.js":"c7d1e6032a37f0edc4eea313506b5e4fa9abffc6","server/agentReplyDrafts.js":"a69af9d107687147d1814434722acdb472550485","server/billingClient.js":"67f5cdde957a2a4d62183e657568b7d21c98a9d9","server/billingClient.test.js":"cd0865792d0d60e4ae7b9b0bdf23537bf3b1e8ba","server/db.js":"7c912ffaed39c536421b82b1674eb6fc6d7f756d","server/email.js":"a923f0e8d464142d838187d02ff4b89b19ed379b","server/gatewayClient.js":"a673a9bdc7ae681cf37aba05d397439715c82b1f","server/healthcheck.js":"2f9ca6a0e90a6520eb0f90ae1bff9c41bccba4a7","server/hubAccess.js":"4fc68aaa72c87c89d35d67b4cd0000fed23b5b0d","server/hubAwareAuthentication.js":"e0cb6b3a83adf9e5c34cd602bb88090e003cbd82","server/hubEntitlementRevalidation.js":"ce2ecdaa69784d9c8ab67e2ab6b7953a5a394ce4","server/hubManagedLink.js":"d6cef2e82401783e432938cb43ab117e641613ab","server/hubProvisioning.js":"09f29fc4e1995ffdf26652ce5ff3cdc17d4b86b2","server/hubTeamAccess.js":"140710abbed8b17adb4803e58fdd26795bb005a8","server/hubTeamAccess.test.js":"18067c3c63ab775093b7f22b51b101acc45b38ca","server/index.js":"9e456276bca557bfd2acdba94c6fd9af0f738b53","server/legacyAccountLink.js":"1ca8d3a129b884f5a3f64b4b98405b3c4aca5aa6","server/logger.js":"213ccbe9d1f86ee41dba72f4f578209f0ecdd999","server/oauth.js":"008145c7f0e84235261ab08e6cef0d64f623279d","server/platform.js":"713b1459cce890c7ff144f9f03c8d2002ef5d8ff","server/platformEvents.js":"3db583c359a5a16078a545d8c3c95e66b059e615","server/schema.sql":"21a038bca544b21a7fa92d71983e38334956c7a6","server/security.js":"a9788f6ed5fc1ac17f11e922af4dfa86be743ad0","server/stripe.js":"0e874a71734015c52fa5ccd1deaea7878537f40a","server/tiquetSocketAccess.js":"161496bdf3b17a436c43b33b587d72deaa7702d2","src/App.tsx":"5ac1a6e56adee9162477c6b47c79f4123bd0c6c2","src/api.ts":"2b77b648781bedae46dd3b527b6dd921d8f00fbe","src/components/AgentReplyDraftPanel.tsx":"5d5b83d9f935ea3c7d581c5ea03b9efc3e89da85","src/components/AuthGate.tsx":"7f7b60c5f51f5694030acb872ec084fde06cfb6c","src/components/ClientPortal.tsx":"c1c037566e8af9e2ed23a224c3f2ddca92c6670e","src/components/Clients.tsx":"5a3c1a0c0274583d3023f67d51e4f97d603840fb","src/components/CommandPalette.tsx":"18f8586ea5412d974aeb93ee741e4977e08c5fda","src/components/D3PieChartWidget.tsx":"8ca25e0a946de183990c73f8cd9a1a2bdb124532","src/components/Dashboard.tsx":"a6184e69ca2509d60a536117f230ce850cde5dc8","src/components/FileRepository.tsx":"3d4ca2ba8246ae627d6c5b362e8e811a3cb7bcc5","src/components/GoogleAuthButton.tsx":"1105f5dfb6d0df60895fd4dfdad869437565a246","src/components/Invoices.tsx":"c9424085fe1642543039eb80b0dde9a67739fb24","src/components/JobBoard.tsx":"0b054f0897642d17ad7455831d5e281ad76d26eb","src/components/JobDetailModal.tsx":"889fccb614adb63808ff68a7ff9cd1698161a273","src/components/JobModal.tsx":"b85ae2c1df1e26c2afb68d2f81a54f93223382dd","src/components/JobRequestForm.tsx":"a4ebadefa6786aa20f794ad068175f8d8d94acb3","src/components/Payroll.tsx":"d93096e0b83b6fe0438f5c6b33061afac67fe589","src/components/ResetPasswordPage.tsx":"eb69d13ff378c191c1a8db83e3679bd2ca59ae60","src/components/Settings.tsx":"8f3453a6f8b5554f10235d0d6eb2d6b6bbe2b0fd","src/components/Sidebar.tsx":"aa97215b2d6ade7ccb26e4c86b473a512a8ccf70","src/components/UserManagement.tsx":"57142293dfc5d399daeb9b7ea5569a3c680bce62","src/currency.ts":"40ff2497759625d3a47e5b362516e10924a8e256","src/index.css":"3b6dc88b12b13c1482df0a744e6e2d4211a90d91","src/main.tsx":"ef474bf64cfb4374e19484541cdec71a6d13c6dd","src/navigationState.js":"4574bec1247dfd7b106d542c6c971e8ef511d7a0","src/types.ts":"86cf88523c33ed969471b4e65a1b91209779fdc8","src/useSyncedCollection.ts":"9372bed90549f5b059ac3741605fd71012e8bf13"}},"tiquet_pr31":{"repo":"V79Tiquet","commit":"0d74bee6d1ab92b1aebbb46016b378dc0a989322","tree":"30ccf88e8683bfd08afebd5c56fe900eee8af8f7","files":{".github/workflows/v79-ci-cd.yml":"6e9b648429750a91b789f4d826fe7604a59ecf55","Dockerfile":"60976fe617bd1e3df380d4f13f2d5d6a3e2b49af","docker-compose.yml":"81139e79a2090a18b409214f5e9d508c22fc8dcc","package-lock.json":"0e94ae8fa9795f4655e4eff3d08f7eead586c929","package.json":"cf2a8dc0cf4f9f9a15d75a7a40bf1c32f2d0365f","scripts/backup-and-inventory.js":"6db5e89ad8c789141346cf8788443d8f426f34dc","scripts/backup-db.js":"38cdabc1cb680b25e2e172e9b02bc6947da206e2","scripts/deploy-server.sh":"77b9fa2eb9ab6e7b8a14ee01fa57d2a4a1e65439","scripts/generate-secrets.js":"066f3dfe88c4447b05ab880ae36dba3fdd769954","scripts/migrate-sqlite-to-pg.js":"c7d1e6032a37f0edc4eea313506b5e4fa9abffc6","server/agentReplyDrafts.js":"a69af9d107687147d1814434722acdb472550485","server/billingClient.js":"67f5cdde957a2a4d62183e657568b7d21c98a9d9","server/billingClient.test.js":"cd0865792d0d60e4ae7b9b0bdf23537bf3b1e8ba","server/db.js":"7c912ffaed39c536421b82b1674eb6fc6d7f756d","server/email.js":"a923f0e8d464142d838187d02ff4b89b19ed379b","server/gatewayClient.js":"a673a9bdc7ae681cf37aba05d397439715c82b1f","server/healthcheck.js":"2f9ca6a0e90a6520eb0f90ae1bff9c41bccba4a7","server/hubAccess.js":"4fc68aaa72c87c89d35d67b4cd0000fed23b5b0d","server/hubAwareAuthentication.js":"e0cb6b3a83adf9e5c34cd602bb88090e003cbd82","server/hubEntitlementRevalidation.js":"ce2ecdaa69784d9c8ab67e2ab6b7953a5a394ce4","server/hubManagedLink.js":"d6cef2e82401783e432938cb43ab117e641613ab","server/hubProvisioning.js":"09f29fc4e1995ffdf26652ce5ff3cdc17d4b86b2","server/hubTeamAccess.js":"140710abbed8b17adb4803e58fdd26795bb005a8","server/hubTeamAccess.test.js":"18067c3c63ab775093b7f22b51b101acc45b38ca","server/index.js":"9e456276bca557bfd2acdba94c6fd9af0f738b53","server/legacyAccountLink.js":"1ca8d3a129b884f5a3f64b4b98405b3c4aca5aa6","server/logger.js":"213ccbe9d1f86ee41dba72f4f578209f0ecdd999","server/oauth.js":"008145c7f0e84235261ab08e6cef0d64f623279d","server/platform.js":"713b1459cce890c7ff144f9f03c8d2002ef5d8ff","server/platformEvents.js":"3db583c359a5a16078a545d8c3c95e66b059e615","server/schema.sql":"21a038bca544b21a7fa92d71983e38334956c7a6","server/security.js":"a9788f6ed5fc1ac17f11e922af4dfa86be743ad0","server/stripe.js":"0e874a71734015c52fa5ccd1deaea7878537f40a","server/tiquetSocketAccess.js":"161496bdf3b17a436c43b33b587d72deaa7702d2","src/App.tsx":"5ac1a6e56adee9162477c6b47c79f4123bd0c6c2","src/api.ts":"2b77b648781bedae46dd3b527b6dd921d8f00fbe","src/components/AgentReplyDraftPanel.tsx":"5d5b83d9f935ea3c7d581c5ea03b9efc3e89da85","src/components/AuthGate.tsx":"7f7b60c5f51f5694030acb872ec084fde06cfb6c","src/components/ClientPortal.tsx":"c1c037566e8af9e2ed23a224c3f2ddca92c6670e","src/components/Clients.tsx":"5a3c1a0c0274583d3023f67d51e4f97d603840fb","src/components/CommandPalette.tsx":"18f8586ea5412d974aeb93ee741e4977e08c5fda","src/components/D3PieChartWidget.tsx":"8ca25e0a946de183990c73f8cd9a1a2bdb124532","src/components/Dashboard.tsx":"a6184e69ca2509d60a536117f230ce850cde5dc8","src/components/FileRepository.tsx":"3d4ca2ba8246ae627d6c5b362e8e811a3cb7bcc5","src/components/GoogleAuthButton.tsx":"1105f5dfb6d0df60895fd4dfdad869437565a246","src/components/Invoices.tsx":"c9424085fe1642543039eb80b0dde9a67739fb24","src/components/JobBoard.tsx":"0b054f0897642d17ad7455831d5e281ad76d26eb","src/components/JobDetailModal.tsx":"889fccb614adb63808ff68a7ff9cd1698161a273","src/components/JobModal.tsx":"b85ae2c1df1e26c2afb68d2f81a54f93223382dd","src/components/JobRequestForm.tsx":"a4ebadefa6786aa20f794ad068175f8d8d94acb3","src/components/Payroll.tsx":"d93096e0b83b6fe0438f5c6b33061afac67fe589","src/components/ResetPasswordPage.tsx":"eb69d13ff378c191c1a8db83e3679bd2ca59ae60","src/components/Settings.tsx":"8f3453a6f8b5554f10235d0d6eb2d6b6bbe2b0fd","src/components/Sidebar.tsx":"aa97215b2d6ade7ccb26e4c86b473a512a8ccf70","src/components/UserManagement.tsx":"57142293dfc5d399daeb9b7ea5569a3c680bce62","src/currency.ts":"40ff2497759625d3a47e5b362516e10924a8e256","src/index.css":"3b6dc88b12b13c1482df0a744e6e2d4211a90d91","src/main.tsx":"ef474bf64cfb4374e19484541cdec71a6d13c6dd","src/navigationState.js":"4574bec1247dfd7b106d542c6c971e8ef511d7a0","src/types.ts":"86cf88523c33ed969471b4e65a1b91209779fdc8","src/useSyncedCollection.ts":"9372bed90549f5b059ac3741605fd71012e8bf13"}}}''')
if __name__ == "__main__":
    raise SystemExit(main())

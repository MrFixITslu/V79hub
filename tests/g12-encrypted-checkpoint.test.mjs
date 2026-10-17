import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { spawnSync } from "node:child_process";

const url = new URL("../scripts/g12-encrypted-checkpoint.sh", import.meta.url);
const script = fs.readFileSync(url, "utf8");

test("encrypted checkpoint syntax and default-off plan guard", () => {
  const syntax=spawnSync("bash",["-n"],{input:script,encoding:"utf8"});
  assert.equal(syntax.status,0,syntax.stderr);
  const invalid=spawnSync("bash",[url.pathname,"--execute"],{encoding:"utf8",timeout:3000});
  assert.equal(invalid.status,2);
  assert.match(invalid.stderr,/Usage/);
});

test("backup refuses host/image/volume drift before any archive writes",()=>{
  const prerequisites=[
    'set -euo pipefail',
    'umask 077',
    '"$(hostname -s)" == v79sl',
    "wipay-return-585f701.pinned.yml",
    "8aa57bba2c6955ab5affe5394ed7bec2b9b2693bc05556db3bef0420bcc04b74",
    "sha256:7876715a44166c1cbeb6b5070a774efb4d69fe36427bda1c4dee4fc637c67e30",
    "sha256:ff64a76651a2b784474f5d7430d0d78515bc7b46b2d0d1f81c51c79958ef417b",
    "v79-hub_v79_hub_postgres_data",
    "v79tiquet_tiquet_pg_data",
    "v79tiquet_tiquet_data",
    "v79tiquet_tiquet_uploads",
    "tiquet_workdir=/home/firelion/V79Tiquet",
    'tiquet_env="$tiquet_workdir/.env"',
    "Tiquet Compose working directory changed",
    "Tiquet Compose file list changed",
    '"$tiquet_env"',
    '"${tiquet_env#/}"',
    '[[ "$mode" == --plan ]]',
    'V79_G12_ENCRYPTED_BACKUP_APPROVED',
    "FOUNDER_APPROVED_ENCRYPTED_CHECKPOINT_ONLY",
    'PRIVATE KEY BLOCK',
    '"$fpr"',
    "pg_dump",
    "gpg --homedir",
    "--encrypt --output",
    "docker cp v79-hub:/app/data -",
    "docker cp v79-tiquet-manager:/app/uploads -",
    "docker image save",
    "docker inspect",
    "sha256sum -- *.gpg",
    "ENCRYPTED_CHECKPOINT_CREATED_RESTORE_NOT_TESTED",
    "database_snapshots_cross_service_atomic=NO",
    "restore_verified=NO",
    "release_approved=NO",
  ];
  for(const text of prerequisites)assert.ok(script.includes(text),"Required protection missing: "+text);
  const firstOutput=script.indexOf("base=/home/firelion/.v79-g12-encrypted-recovery");
  const guard=script.indexOf('V79_G12_ENCRYPTED_BACKUP_APPROVED');
  const pin=script.indexOf("expect_pin=8aa57");
  assert.ok(pin<guard&&guard<firstOutput);
});

test("checkpoint is encrypted on streaming boundaries with no plaintext snapshots or release operations",()=>{
  assert.doesNotMatch(script,/\bdocker\s+(?:run|start|stop|restart|rm|cp .*\/tmp|compose (?:up|down))\b/);
  assert.doesNotMatch(script,/\b(?:psql|DROP DATABASE|TRUNCATE|ALTER SYSTEM)\b/);
  // pg_restore may be checked for availability, but must never be executed.
  assert.doesNotMatch(script,/^(?!.*command -v)\s*pg_restore\b/m);
  assert.doesNotMatch(script,/docker\s+image\s+(?:rm|prune|tag|pull|push)/);
  assert.doesNotMatch(script,/tar -[a-z]*x/);
  assert.doesNotMatch(script,/--symmetric|--passphrase|--pinentry-mode loopback/);
  assert.doesNotMatch(script,/--output .*(?:\.sql|\.dump|\.tar)(?:\s|["']|$)/);
  assert.match(script,/if "\$@" \| gpg /);
  assert.match(script,/--encrypt --output "\$output\.partial"/);
  assert.match(script,/mv -- "\$output\.partial" "\$output"/);
  assert.match(script,/if \[\[ "\$mode" == --plan \]\]/);
});

test("off-host plan cannot do anything to infrastructure",()=>{
  if(process.env.HOSTNAME==="v79sl")return;
  const r=spawnSync("bash",[url.pathname,"--plan"],{encoding:"utf8",timeout:4000});
  assert.equal(r.status,2);
  assert.doesNotMatch(r.stdout, /ENCRYPTED CHECKPOINT CREATED|PLAN ONLY/);
});
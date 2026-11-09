import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { spawnSync } from 'node:child_process';

const compose = readFileSync('staging/pos-hubqa/hub-compose.yml', 'utf8');
const helper = readFileSync('staging/pos-hubqa/prepare.py', 'utf8');

test('Hub staging has private network, MFA, loopback-only port and disabled outbound writes', () => {
  assert.match(compose, /^name: v79-hub-pos-hubqa-20261109/m);
  assert.match(compose, /container_name: v79-hub-pos-hubqa/);
  assert.ok(compose.includes('user: "'));
  assert.ok(compose.includes('V79_HUB_STAGE_GID:?Set staging directory owner GID'));
  assert.ok(compose.includes('tmpfs:'));
  assert.ok(compose.includes('/app/node_modules/.vite-temp:uid='));
  assert.match(compose, /127\.0\.0\.1:18082:3040/);
  assert.match(compose, /external: true\s+name: v79pos-hubqa-20261109_stage_internal/);
  assert.match(compose, /POS_BASE_URL: http:\/\/v79-pos-hubqa-api:8080/);
  assert.match(compose, /POS_PUBLIC_URL: http:\/\/127\.0\.0\.1:18081/);
  assert.match(compose, /NODE_ENV: development/);
  assert.match(compose, /V79_REQUIRE_ADMIN_MFA: "1"/);
  assert.match(compose, /WIPAY_ENABLED: "0"/);
  assert.match(compose, /V79_WORKFORCE_ACTIONS_ENABLED: "0"/);
  assert.match(compose, /RESEND_API_KEY: ""/);
  assert.doesNotMatch(compose, /proxy_network|hub\.v79sl\.com|pos\.v79sl\.com|v79-commerce-api|v79-pos-db|v79-hub-postgres/);
  assert.doesNotMatch(compose, /0\.0\.0\.0:|restart: always|restart: unless-stopped/);
});

test('Stage bootstrap refuses a running stage and never changes production volumes', () => {
  assert.match(helper, /assert_stage_only\(args\.apply\)/);
  assert.match(helper, /if require_stopped and pos\["State"\]\["Running"\]/);
  assert.match(helper, /if not net\["Internal"\]/);
  assert.match(helper, /if stage_db_env\.get\("POSTGRES_DB"\) != "v79pos_hubqa"/);
  assert.match(helper, /pos\["Config"\]\["Image"\] != STAGE_POS_IMAGE/);
  assert.match(helper, /live\["Config"\]\["Image"\] != LIVE_POS_IMAGE/);
  assert.match(helper, /HostIp"\] != "127\.0\.0\.1"/);
  assert.match(helper, /V79_POS_PLATFORM_SHARED_SECRET"\] = secret/);
  assert.match(helper, /V79_PLATFORM_SHARED_SECRET"\] = secret/);
  assert.match(helper, /secrets\.token_hex\(48\)/);
  assert.match(helper, /os\.O_EXCL/);
  assert.match(helper, /--apply/);
  assert.doesNotMatch(helper, /docker compose down|docker stop v79-pos(?!-hubqa)|docker exec v79-pos-db/);
});

test('Python stage transformation removes the production Hub route and proxy network', () => {
  const script = [
    'import importlib.util',
    'from pathlib import Path',
    'import tempfile',
    'spec = importlib.util.spec_from_file_location("qa", "staging/pos-hubqa/prepare.py")',
    'qa = importlib.util.module_from_spec(spec)',
    'spec.loader.exec_module(qa)',
    'sample = """name: v79pos-hubqa-20261109',
    'services:',
    '  api:',
    '    image: v79pos:hubqa-2590623',
    '    environment:',
    '      HUB_INTERNAL_URL: http://v79-hub:3040',
    '      HUB_JWKS_URL: http://v79-hub:3040/.well-known/jwks.json',
    '      JWT_ISSUER: https://hub.v79sl.com',
    '    ports:',
    '      - 127.0.0.1:18081:8080',
    '    networks:',
    '      - stage_internal',
    '      - proxy_network',
    'networks:',
    '  stage_internal:',
    '    internal: true',
    '  proxy_network:',
    '    external: true',
    '    name: proxy_network',
    'volumes:',
    '  stage_db:',
    '    name: v79pos_hubqa_20261109_db',
    '"""',
    'with tempfile.TemporaryDirectory() as folder:',
    '    path = Path(folder) / "hubqa.compose.yml"',
    '    path.write_text(sample)',
    '    original, safe = qa.prepare_compose(path)',
    '    assert original == sample',
    '    assert "proxy_network" not in safe',
    '    assert "http://v79-hub:3040" not in safe',
    '    assert "http://v79-hub-pos-hubqa:3040" in safe',
    '    assert "JWT_ISSUER: http://127.0.0.1:18082" in safe',
    '    assert "127.0.0.1:18081:8080" in safe',
    '    assert "v79pos_hubqa_20261109_db" in safe',
    'print("ISOLATED_STAGE_TRANSFORMATION_TEST=PASS")',
  ].join('\n');
  const result = spawnSync('python3', ['-c', script], { encoding: 'utf8', timeout: 10000 });
  assert.equal(result.status, 0, result.stderr || result.stdout);
  assert.match(result.stdout, /ISOLATED_STAGE_TRANSFORMATION_TEST=PASS/);
});


test('Stage bootstrap accepts absent dedicated POS key, but rejects weak explicit key', () => {
  const script = [
    'import importlib.util',
    'from pathlib import Path',
    'import tempfile',
    'spec = importlib.util.spec_from_file_location("qa", "staging/pos-hubqa/prepare.py")',
    'qa = importlib.util.module_from_spec(spec)',
    'spec.loader.exec_module(qa)',
    'with tempfile.TemporaryDirectory() as folder:',
    '    path = Path(folder) / ".env"',
    '    values = {"STAGE_DB_PASSWORD":"d"*48,"ENCRYPTION_KEY":"e"*48,"GIFT_CARD_PEPPER":"g"*48,"V79_PLATFORM_SHARED_SECRET":"p"*48,"V79_POS_PLATFORM_SHARED_SECRET":""}',
    '    path.write_text("".join(k+"="+v+"\\n" for k,v in values.items()))',
    '    parsed = qa.read_env(path)',
    '    assert parsed["V79_POS_PLATFORM_SHARED_SECRET"] == ""',
    '    values["V79_POS_PLATFORM_SHARED_SECRET"] = "weak"',
    '    path.write_text("".join(k+"="+v+"\\n" for k,v in values.items()))',
    '    try:',
    '        qa.read_env(path)',
    '    except SystemExit as exc:',
    '        assert "Present but weak" in str(exc)',
    '    else:',
    '        raise AssertionError("Weak dedicated key was accepted")',
    'print("OPTIONAL_POS_KEY_FALLBACK_TEST=PASS")',
  ].join('\n');
  const result = spawnSync('python3', ['-c', script], { encoding: 'utf8', timeout: 10000 });
  assert.equal(result.status, 0, result.stderr || result.stdout);
  assert.match(result.stdout, /OPTIONAL_POS_KEY_FALLBACK_TEST=PASS/);
});

test('Stage recovery keeps 0700 private storage and never changes live containers or keys', () => {
  const script = readFileSync('staging/pos-hubqa/repair-permissions.py', 'utf8');
  for (const fragment of [
    'STAGE_PERMISSION_PREFLIGHT=PASS',
    'PRIVATE_DATA_DIRECTORY_PRESERVED=PASS',
    'EXISTING_STAGE_KEYS_PRESERVED=PASS',
    'stat.S_IMODE(s.st_mode) == 0o700',
    's.st_uid == os.getuid()',
    'STAGE_IMAGE = "v79hub:pos-hubqa-20261109"',
    'not hub["State"]["Running"]',
    '"127.0.0.1"',
    'atomic_save(env_file',
    'atomic_save(target'
  ]) assert.ok(script.includes(fragment), 'Missing guard: ' + fragment);
  for (const forbidden of ['0o777','docker compose down','docker stop v79-pos']) {
    assert.ok(!script.includes(forbidden), 'Unsafe stage repair code: ' + forbidden);
  }
  const compile = spawnSync('python3', ['-c',
    'import ast, pathlib; ast.parse(pathlib.Path("staging/pos-hubqa/repair-permissions.py").read_text()); print("STAGE_REPAIR_SYNTAX_PASS")'
  ], { encoding: 'utf8', timeout: 10000 });
  assert.equal(compile.status, 0, compile.stderr || compile.stdout);
  assert.ok(compile.stdout.includes('STAGE_REPAIR_SYNTAX_PASS'));
});

test('New staging bootstraps mount owner mapping rather than widening permissions', () => {
  assert.ok(helper.includes('"V79_HUB_STAGE_UID": str(os.getuid())'));
  assert.ok(helper.includes('"V79_HUB_STAGE_GID": str(os.getgid())'));
});

test('Stage pin tool is syntactically valid and preserves production and staging data', () => {
  const path = 'staging/pos-hubqa/sync-live-ui.py';
  const code = readFileSync(path, 'utf8');
  for (const phrase of [
    'STAGE_UI_SYNC_BLOCKED',
    'DRY_RUN_ONLY=PASS',
    'STAGING_KEYS_AND_DATA_PRESERVED=PASS',
    'PRODUCTION_CONTAINERS_NOT_RECREATED=PASS',
    'STAGING_HUB_EXACT_LIVE_IMAGE=PASS',
    'approved-live-image.json',
    'image_check(live)',
    'private_stage_store()',
    'make_checkpoint(ROOT / "data", compose, raw)',
    'run("docker", "tag", live["Image"], new_tag)',
    'up_stage()',
    'STAGE_PROMOTION_FAILED_ATTEMPTING_IMAGE_ONLY_ROLLBACK',
    'WIPAY_ENABLED',
    'V79_REQUIRE_ADMIN_MFA',
    'POS_BASE_URL: http://v79-pos-hubqa-api:8080',
    'health("http://" + stage_ip(stage) + ":3040/api/health")'
  ]) assert.ok(code.includes(phrase), 'Missing private stage safety check: ' + phrase);
  for (const forbidden of [
    'docker compose down',
    'docker stop v79-hub',
    'docker stop v79-pos',
    'docker rm v79-hub',
    'chmod 777',
    'docker exec v79-hub',
    'v79-pos-db',
    'pg_restore'
  ]) assert.ok(!code.includes(forbidden), 'Unexpected live-data operation: ' + forbidden);
  const syntax = spawnSync('python3', ['-c',
    'import ast,pathlib; ast.parse(pathlib.Path("staging/pos-hubqa/sync-live-ui.py").read_text()); print("LIVE_UI_SYNC_SYNTAX_PASS")'
  ], {encoding: 'utf8', timeout: 10000});
  assert.equal(syntax.status, 0, syntax.stderr || syntax.stdout);
  assert.ok(syntax.stdout.includes('LIVE_UI_SYNC_SYNTAX_PASS'));
});

test('Stage image verification supports an immutable live-image pin and private API checks', () => {
  const code = readFileSync('staging/pos-hubqa/check.py', 'utf8');
  for (const required of [
    'approved-live-image.json',
    'stage_hub["Image"] == image_id',
    'referenced["Id"] == image_id',
    '["HostConfig"].get("PortBindings")',
    'private_address(stage_hub)',
    'private_address(stage_pos)',
    'unauth_code == 401',
    'FULL_BROWSER_MFA_SSO=NOT_YET_VERIFIED'
  ]) assert.ok(code.includes(required), 'Missing stage acceptance condition: ' + required);
  const syntax = spawnSync('python3', ['-c',
    'import ast,pathlib; ast.parse(pathlib.Path("staging/pos-hubqa/check.py").read_text()); print("STAGE_ACCEPTANCE_SYNTAX_PASS")'
  ], {encoding:'utf8', timeout:10000});
  assert.equal(syntax.status, 0, syntax.stderr || syntax.stdout);
  assert.ok(syntax.stdout.includes('STAGE_ACCEPTANCE_SYNTAX_PASS'));
});

test('Live-image tag is derived from exact Docker image identity and refuses baked secrets', () => {
  const script = [
    'import importlib.util',
    'spec=importlib.util.spec_from_file_location("stage","staging/pos-hubqa/sync-live-ui.py")',
    'm=importlib.util.module_from_spec(spec)',
    'spec.loader.exec_module(m)',
    'id="sha256:"+"a"*64',
    'm.inspect=lambda n,kind="container":{"Id":id,"Config":{"Env":["NODE_ENV=production"]}}',
    'm.run=lambda *args,**kwargs:type("Result",(),{"returncode":0})()',
    'tag=m.image_check({"Image":id})',
    'assert tag=="v79hub:pos-hubqa-live-"+"a"*12',
    'm.inspect=lambda n,kind="container":{"Id":id,"Config":{"Env":["V79_PLATFORM_SHARED_SECRET=must-never-reuse"]}}',
    'try:',
    '    m.image_check({"Image":id})',
    'except RuntimeError as exc:',
    '    assert "baked-in" in str(exc)',
    'else:',
    '    raise AssertionError("Baked-in live signing secret accepted")',
    'print("STAGE_PIN_SECRETS_TEST_PASS")'
  ].join('\n');
  const result = spawnSync('python3', ['-c',script], {encoding:'utf8', timeout:10000});
  assert.equal(result.status, 0, result.stderr || result.stdout);
  assert.ok(result.stdout.includes('STAGE_PIN_SECRETS_TEST_PASS'));
});

test('Approved Connected Login uses a frontend-only overlay onto immutable stage backend', () => {
  const file = 'staging/pos-hubqa/overlay-approved-login.py';
  const script = readFileSync(file, 'utf8');
  for (const fragment of [
    'localhost/v79-hub-login-connected:20261109-r1',
    'localhost/v79-hub-sales-review:20261107-r1',
    'v79hub:pos-hubqa-20261109',
    'v79hub:pos-hubqa-ui-v3-20261109',
    'STAGING_LOGIN_OVERLAY=PASS',
    'DRY_RUN_ONLY=PASS',
    'STAGING_DATA_PRODUCTION_ISOLATION=PASS',
    'STAGE_UI_OVERLAY_FAILED_ATTEMPTING_STAGE_ONLY_ROLLBACK',
    'OLD_STAGE_HUB_IMAGE_RESTORED=PASS',
    'approved-login-overlay.json',
  ]) assert.ok(script.includes(fragment), 'Missing gate: ' + fragment);
  for (const forbidden of [
    'docker compose down',
    'docker stop v79-hub',
    'docker stop v79-pos',
    'docker rm v79-hub',
    'docker exec v79-hub',
    'pg_restore',
    'chmod 777',
    'docker build --build-arg',
  ]) assert.ok(!script.includes(forbidden), 'Unexpected stage overlay operation: ' + forbidden);
  for (const action of [
    'private_ip(stage_hub)',
    'healthcode("http://" + private_ip(pos) + ":8080/v1/me") == 401',
    'stage_build(files, scratch)',
    'checkpoint(original)',
    'atomic_write(ROOT / "compose.yml", original.replace(COMPOSE_OLD, COMPOSE_NEW, 1))',
    'current_prod["Id"] == prod["Id"]',
    'current_pos["Id"] == pos["Id"]',
    '"--network", "none"',
    '"--pull=false"',
    '"--no-deps"',
    '"--force-recreate"'
  ]) assert.ok(script.includes(action), 'Missing stage isolation gate: ' + action);
  const check = spawnSync('python3', ['-c',
    'import ast,pathlib; ast.parse(pathlib.Path("staging/pos-hubqa/overlay-approved-login.py").read_text()); print("OVERLAY_PYTHON_SYNTAX=PASS")'
  ], { encoding: 'utf8', timeout: 10000 });
  assert.equal(check.status, 0, check.stderr || check.stdout);
  assert.ok(check.stdout.includes('OVERLAY_PYTHON_SYNTAX=PASS'));
});

test('Frontend overlay image must be pinned to both built and 9 November source image', () => {
  const script = readFileSync('staging/pos-hubqa/check.py', 'utf8');
  for (const phrase of [
    'approved-login-overlay.json',
    'v79hub:pos-hubqa-ui-v3-20261109',
    'localhost/v79-hub-login-connected:20261109-r1',
    'record.get("base_stage_image") == "v79hub:pos-hubqa-20261109"',
    'built["Id"] == image_id and source["Id"] == source_id',
    'PRIVATE_STAGING_NETWORK=PASS',
    'FULL_BROWSER_MFA_SSO=NOT_YET_VERIFIED'
  ]) assert.ok(script.includes(phrase), 'Missing overlay pin check: ' + phrase);
});

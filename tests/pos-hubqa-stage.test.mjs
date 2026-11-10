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


test('9 Nov Connected Login presentation repair preserves stage backend and production', () => {
  const script = readFileSync('staging/pos-hubqa/repair-login-presentation.py', 'utf8');
  const required = [
    'PRIVATE_STAGING_AND_PRODUCTION_PREFLIGHT=PASS',
    'CANDIDATE_CSS_SHA256=',
    'DRY_RUN_ONLY=PASS',
    'STAGING_LOGIN_STYLE_AND_ASSETS=PASS',
    'V3_STAGING_STYLESHEET=PASS',
    'V3_STAGING_ASSETS=PASS',
    'STAGING_POS_ANONYMOUS_DENIAL=PASS',
    'PRODUCTION_UNCHANGED=PASS',
    'STAGE_CSS_FIX_FAILED_ATTEMPTING_STAGE_ONLY_ROLLBACK',
    'OLD_STAGE_HUB_IMAGE_RESTORED=PASS',
    'approved-login-style.json',
    'approved-login-overlay.json',
    'v79hub:pos-hubqa-ui-v3-styled-20261109',
    'v79hub:pos-hubqa-ui-v3-20261109',
    'localhost/v79-hub-login-connected:20261109-r1',
    'ea182c2656cea2979412e611bf1e704d4068512f72d6d2db5eba33f80d5c544c',
    'cb3417cc160bc3f8edcd3c444e22dd51af781918b065956182fa44d3b9907145',
    'cb250f00742c5bc3f40f119cbc51f626a1fb94f542f254e27b0d3c6884b4c49b',
    '"--network", "none"',
    '"--pull=false"',
    '"--no-deps"',
    '"--force-recreate"',
    'verify(image_id, live_hub, live_pos, stage_hub, stage_pos, paths)',
    'env_from(hub) == env_from(old_stage_hub)',
    'status != 200 or not media_type.startswith("image/")',
    'http_get(url + "/v1/me")[0] == 401'
  ];
  for (const fragment of required) {
    assert.ok(script.includes(fragment), 'Missing styling repair guard: ' + fragment);
  }
  for (const dangerous of [
    'docker compose down', 'docker stop v79-hub', 'docker stop v79-pos',
    'docker exec v79-hub', 'pg_restore', 'chmod 777',
    'docker rm v79-hub', 'docker rm v79-pos'
  ]) assert.ok(!script.includes(dangerous), 'Unsafe presentation repair instruction: ' + dangerous);
  const syntax = spawnSync('python3', ['-c',
    'import ast,pathlib; ast.parse(pathlib.Path("staging/pos-hubqa/repair-login-presentation.py").read_text()); print("STAGE_STYLE_PYTHON_SYNTAX=PASS")'
  ], { encoding: 'utf8', timeout: 10000 });
  assert.equal(syntax.status, 0, syntax.stderr || syntax.stdout);
  assert.match(syntax.stdout, /STAGE_STYLE_PYTHON_SYNTAX=PASS/);
});

test('Stage styled image acceptance must verify the exact overlay/source image and CSS fingerprint', () => {
  const script = readFileSync('staging/pos-hubqa/check.py', 'utf8');
  for (const fragment of [
    'approved-login-style.json',
    'approved-login-overlay.json',
    'v79hub:pos-hubqa-ui-v3-styled-20261109',
    'ea182c2656cea2979412e611bf1e704d4068512f72d6d2db5eba33f80d5c544c',
    'record.get("previous_image_id") == parent.get("overlay_image_id")',
    'record.get("source_image") == source_tag',
    'styled_image["Id"] == styled_id',
    'STAGING_HEALTH_AND_UNAUTH_DENIAL=PASS',
    'FULL_BROWSER_MFA_SSO=NOT_YET_VERIFIED'
  ]) assert.ok(script.includes(fragment), 'Missing immutable styled pin: ' + fragment);
});

test('Stylesheet asset discovery permits product icon paths without directory assumptions', () => {
  const script = [
    'import importlib.util',
    'p="staging/pos-hubqa/repair-login-presentation.py"',
    'spec=importlib.util.spec_from_file_location("stage_style",p)',
    'm=importlib.util.module_from_spec(spec)',
    'spec.loader.exec_module(m)',
    'sample="\\\"/app-icons/tiquet.svg\\\" \\\"/brand/favicon-32.png\\\" url(\\\'/assets/v79-login-earth.svg\\\')"',
    'assets={v.group() for v in m.ASSET_RE.finditer(sample)}',
    'assert assets == {"/app-icons/tiquet.svg","/brand/favicon-32.png","/assets/v79-login-earth.svg"},assets',
    'print("STAGE_STYLE_ASSET_DISCOVERY=PASS")'
  ].join('\n');
  const result = spawnSync('python3', ['-c', script],
    { encoding: 'utf8', timeout: 10000 });
  assert.equal(result.status, 0, result.stderr || result.stdout);
  assert.match(result.stdout, /STAGE_STYLE_ASSET_DISCOVERY=PASS/);
});


test('Private stage login image permission repair is fail-closed, nonroot-safe and rollback-capable', () => {
  const code = readFileSync('staging/pos-hubqa/recover-login-image-permissions.py', 'utf8');
  for (const guard of [
    'STAGE_ICON_PERMISSION_BLOCKED',
    'STAGING_SAFETY_PREFLIGHT=PASS',
    'DRY_RUN_ONLY=PASS',
    'ICON_DIRECTORY_FIX=0755 (only this directory)',
    'chmod 0755 /app/public/assets/login-products',
    'NONROOT_PRODUCT_IMAGE_READ=PASS',
    'STAGE_LOGIN_PRODUCT_PNG_HTTP=PASS',
    'STAGE_LOGIN_CSS=PASS',
    'STAGE_KEYS_MFA_AND_POS_BACKEND_PRESERVED=PASS',
    'PRODUCTION_CONTAINERS_UNCHANGED=PASS',
    'OLD_STAGE_HUB_IMAGE_RESTORED=PASS',
    'ICON_STAGE_FIX_FAILED_ATTEMPTING_STAGE_ONLY_ROLLBACK',
    'STAGING_LOGIN_ASSETS_FIXED=PASS',
    'STAGING_HUB_HEALTH=PASS',
    'VERSION3_VISUAL_AND_MFA_SSO=NOT_YET_VERIFIED',
    'approved-login-assets-perms.json',
    'before-product-icon-permissions-',
    'v79hub:pos-hubqa-ui-v3-styled-perms-20261109-r1',
    'v79hub:pos-hubqa-ui-v3-styled-20261109',
    'RootFS',
    'layers[:len(parents)] == parents',
    '"--read-only", "--user", "1000:1000"',
    '"--network", "none"',
    '"--pull=false"',
    '"--no-deps"',
    '"--force-recreate"',
    'r.read(8) == PNG',
    'inspect(LIVE)',
    'inspect(LIVE)["Id"] == live["Id"]'
  ]) assert.ok(code.includes(guard), 'Missing release guard: ' + guard);
  for (const forbidden of [
    'docker compose down', 'docker stop v79-hub',
    'docker stop v79-pos', 'docker rm v79-hub',
    'docker rm v79-pos', 'pg_restore',
    'chmod 777', 'docker exec v79-hub',
    'docker build --build-arg'
  ]) assert.ok(!code.includes(forbidden), 'Unsafe stage repair instruction: ' + forbidden);
  const syntax = spawnSync('python3', ['-c',
    'import ast,pathlib;ast.parse(pathlib.Path("staging/pos-hubqa/recover-login-image-permissions.py").read_text());print("STAGE_PRODUCT_ICON_REPAIR_SYNTAX=PASS")'
  ], { encoding: 'utf8', timeout: 10000 });
  assert.equal(syntax.status, 0, syntax.stderr || syntax.stdout);
  assert.match(syntax.stdout, /STAGE_PRODUCT_ICON_REPAIR_SYNTAX=PASS/);
});

test('Private stage acceptance pins exact fixed image and rejects HTML returned for product PNGs', () => {
  const script = readFileSync('staging/pos-hubqa/check.py', 'utf8');
  for (const text of [
    'approved-login-assets-perms.json',
    'v79hub:pos-hubqa-ui-v3-styled-perms-20261109-r1',
    'approved.get("derived_from") == source',
    'approved.get("previous_staging_image_id") ==',
    'built["Id"] == image_id and broken["Id"] == source_id',
    'STAGING_LOGIN_PRODUCT_IMAGES=PASS',
    'image_bytes.startswith(bytes.fromhex("89504e470d0a1a0a"))'
  ]) assert.ok(script.includes(text), 'Missing real PNG and image pin acceptance: ' + text);
});


test('Interrupted staging repair reuses only owner-observed immutable image after provenance and nonroot PNG checks', () => {
  const code = readFileSync('staging/pos-hubqa/recover-login-image-permissions.py', 'utf8');
  for (const item of [
    'def verify_prebuilt_image(broken):',
    'sha256:30ee063ae29b77ab09629ae09a361fa80ba78bd5e773c3d97064ed1a557706bf',
    'len(new_layers) == len(base_layers) + 1',
    'new_layers[:len(base_layers)] == base_layers',
    'for key in ("Env", "Entrypoint", "Cmd", "WorkingDir", "User")',
    'docker", "history", "--no-trunc"',
    'chmod 0755 /app/public/assets/login-products',
    'existing_id = verify_prebuilt_image(broken)',
    'EXISTING_CORRECTED_IMAGE_PROVENANCE=PASS',
    'EXISTING_NONROOT_PRODUCT_IMAGE_READ=PASS',
    'new_id = existing_id if existing_id else build()',
    'probe_nonroot_image()'
  ]) assert.ok(code.includes(item), 'Missing existing-image safety gate: ' + item);
  const syntax = spawnSync('python3', ['-c',
    'import ast,pathlib;ast.parse(pathlib.Path("staging/pos-hubqa/recover-login-image-permissions.py").read_text());print("STAGING_RESUME_SYNTAX=PASS")'
  ], {encoding: 'utf8', timeout: 10000});
  assert.equal(syntax.status, 0, syntax.stderr || syntax.stdout);
  assert.match(syntax.stdout, /STAGING_RESUME_SYNTAX=PASS/);
});


test('Private stage recreated Hub must preserve all effective auth environment values without leaking secrets', () => {
  const code = readFileSync('staging/pos-hubqa/recover-login-image-permissions.py', 'utf8');
  for (const part of [
    'def env_map(container):',
    'name, value = row.split("=", 1)',
    'name.isidentifier() and name not in result',
    'before_env = env_map(old)',
    'after_env = env_map(after)',
    'if before_env != after_env:',
    'if before_env.get(k) != after_env.get(k)',
    'values suppressed',
    'STAGE_AUTH_AND_SERVICE_ENV_SEMANTICALLY_IDENTICAL=PASS',
    'after["Config"]["User"] == "1000:1000"',
    'def verified_loopback_binding(container):',
    'set(bindings) == {"3040/tcp"}',
    'ports[0].get("HostIp") == "127.0.0.1"',
    'ports[0].get("HostPort") == "18082"',
    'verified_loopback_binding(old)',
    'verified_loopback_binding(after)',
    'STAGE_NONROOT_USER_AND_LOOPBACK_BINDING=PASS'
  ]) assert.ok(code.includes(part), 'Missing effective non-root stage security gate: ' + part);
  assert.ok(!code.includes('print(before_env)'), 'Secrets exposed through old environment dump');
  assert.ok(!code.includes('print(after_env)'), 'Secrets exposed through new environment dump');
  const syntax = spawnSync('python3', ['-c',
    'import ast,pathlib;ast.parse(pathlib.Path("staging/pos-hubqa/recover-login-image-permissions.py").read_text());print("RECREATED_STAGE_SEMANTIC_ENV_SYNTAX=PASS")'
  ], { encoding: 'utf8', timeout: 10000 });
  assert.equal(syntax.status, 0, syntax.stderr || syntax.stdout);
  assert.match(syntax.stdout, /RECREATED_STAGE_SEMANTIC_ENV_SYNTAX=PASS/);
});


test('Owner-approved dashboard alignment overlays only 3 matching live frontend files with strict stage-only rollback', () => {
  const script = readFileSync('staging/pos-hubqa/align-dashboard-ui.py', 'utf8');
  for (const guard of [
    'STAGING_DASHBOARD_ALIGNMENT_BLOCKED',
    'STAGING_DASHBOARD_DRY_RUN=PASS',
    'PRIVATE_STAGE_DASHBOARD_PREFLIGHT=PASS',
    'ALL_OTHER_IMPORTS_AND_LOGIN_UNCHANGED=PASS',
    'APPROVED_LIVE_DASHBOARD_COMPONENT=',
    'Unreviewed frontend dependencies:',
    'Latest dashboard source does not match running live frontend:',
    'v79hub:pos-hubqa-dashboard-aligned-20261109-r1',
    'approved-dashboard-alignment.json',
    'approved-login-assets-perms.json',
    'approved-login-overlay.json',
    'PRIVATE_DASHBOARD_CHECKPOINT=',
    'STAGING_UPDATED_DASHBOARD_FILES=PASS',
    'STAGING_LOGIN_ICONS_AND_CSS=PASS',
    'STAGING_MFA_AND_POS_RUNTIME_PRESERVED=PASS',
    'PRODUCTION_AND_STAGE_POS_UNCHANGED=PASS',
    'PRIVATE_STAGING_DASHBOARD_ALIGNED=PASS',
    'STAGING_DASHBOARD_FAILED_ROLLBACK_ATTEMPT',
    'PREVIOUS_HEALTHY_STAGE_RESTORED=PASS',
    'STAGING_MFA_AND_POS_BROWSER_RETEST=NOT_YET_VERIFIED',
    '"src/App.tsx"',
    '"src/components/HubOverview.tsx"',
    '"src/components/Sidebar.tsx"',
    '"src/components/Login.tsx"',
    '"src/index.css"',
    'docker", "cp"',
    'run("docker", "build", "--network", "none", "--pull=false"',
    '"--no-deps", "--force-recreate", "--wait", "hub"',
    'env_map(new) == env_map(stage)',
    'get(pos_url + "/v1/me")[0] == 401',
    'status == 200 and mime.startswith("image/png") and body == PNG'
  ]) assert.ok(script.includes(guard), 'Missing dashboard staging release guard: ' + guard);
  for (const forbidden of [
    'docker compose down', 'docker stop v79-hub',
    'docker stop v79-pos', 'docker rm v79-pos',
    'docker rm v79-hub', 'pg_restore', 'chmod -R', 'chmod 777'
  ]) assert.ok(!script.includes(forbidden), 'Unsafe stage alignment: ' + forbidden);
  const syntax = spawnSync('python3', ['-c',
    'import ast,pathlib;ast.parse(pathlib.Path("staging/pos-hubqa/align-dashboard-ui.py").read_text());print("STAGE_DASHBOARD_ALIGNMENT_SYNTAX=PASS")'
  ], { encoding: 'utf8', timeout: 10000 });
  assert.equal(syntax.status, 0, syntax.stderr || syntax.stdout);
  assert.match(syntax.stdout, /STAGE_DASHBOARD_ALIGNMENT_SYNTAX=PASS/);
});

test('Stage acceptance pins exact dashboard image, source and 3 file hashes', () => {
  const script = readFileSync('staging/pos-hubqa/check.py', 'utf8');
  for (const name of [
    'approved-dashboard-alignment.json',
    'v79hub:pos-hubqa-dashboard-aligned-20261109-r1',
    'record.get("base_stage_image_id") == parent.get("image_id")',
    'record.get("dashboard_source_image_id") == approved_source["Id"]',
    'stage_hub["Config"]["Image"] == tag',
    'actual_image["Id"] == identity',
    'set(sha_map) == set(files)',
    'src/components/HubOverview.tsx',
    'src/components/Sidebar.tsx',
    'STAGING_LOGIN_PRODUCT_IMAGES=PASS',
    'STAGING_HEALTH_AND_UNAUTH_DENIAL=PASS'
  ]) assert.ok(script.includes(name), 'Missing dashboard identity or regression check: ' + name);
});


test('Dashboard overlay accepts Docker legal names and identical repeated environment entries, rejects conflicts', () => {
  const source = [
    'import importlib.util',
    'spec=importlib.util.spec_from_file_location("stage_dashboard","staging/pos-hubqa/align-dashboard-ui.py")',
    'm=importlib.util.module_from_spec(spec)',
    'spec.loader.exec_module(m)',
    'make=lambda entries: {"Config":{"Env":entries}}',
    'good=make(["PATH=/usr/bin","SERVICE.MODE=stage","X-Name=allowed","V79_REQUIRE_ADMIN_MFA=1","REPEAT=one","REPEAT=one"])',
    'expected={"PATH":"/usr/bin","SERVICE.MODE":"stage","X-Name":"allowed","V79_REQUIRE_ADMIN_MFA":"1","REPEAT":"one"}',
    'assert m.env_map(good)==expected',
    'assert m.env_map(make(list(reversed(good["Config"]["Env"]))))==expected',
    'for malformed in (["REPEAT=one","REPEAT=two"],["=no-key"],["NO_EQUAL_SIGN"],[None]):',
    '  try:',
    '    m.env_map(make(malformed))',
    '  except RuntimeError as exc:',
    '    assert "STAGING_DASHBOARD_ALIGNMENT_BLOCKED" in str(exc)',
    '    assert "REPEAT=one" not in str(exc) and "REPEAT=two" not in str(exc)',
    '  else:',
    '    raise AssertionError("Conflicting/invalid environment entry accepted")',
    'print("DASHBOARD_DOCKER_ENV_SECURITY=PASS")'
  ].join('\n');
  const result = spawnSync('python3', ['-c', source],
    { encoding: 'utf8', timeout: 10000 });
  assert.equal(result.status, 0, result.stderr || result.stdout);
  assert.match(result.stdout, /DASHBOARD_DOCKER_ENV_SECURITY=PASS/);
});


test('Dashboard preflight inventories all unapproved frontend dependency differences before any stage write', () => {
  const source = readFileSync('staging/pos-hubqa/align-dashboard-ui.py', 'utf8');
  const start = source.indexOf('def verify_candidate_dependency_parity(scratch):');
  const end = source.indexOf('def build(scratch):', start);
  assert.ok(start >= 0 && end > start, 'Dependency scanner missing');
  const scanner = source.slice(start, end);
  for (const needed of [
    'mismatches = {}',
    'name = sorted(imported)[0]',
    'mismatches[actual] = (digest(stage_content), digest(contents))',
    'NON_DASHBOARD_DEPENDENCY_DIFFERENCES=',
    'DIFFERING_NON_DASHBOARD_DEPENDENCY=',
    'STAGE_SHA256=',
    'CANDIDATE_SHA256=',
    'for path, (stage_sha, candidate_sha) in sorted(mismatches.items()):',
    'ensure(not missing_stage and not missing_candidate and',
    'MISSING_STAGE_FRONTEND_DEPENDENCY=',
    'MISSING_CANDIDATE_FRONTEND_DEPENDENCY=',
    'DASHBOARD_DEPENDENCIES_SCANNED=',
    'no automatic broad copy',
    'ALL_OTHER_IMPORTS_AND_LOGIN_UNCHANGED=PASS'
  ]) assert.ok(scanner.includes(needed), 'Missing fail-closed dependency inventory: ' + needed);
  assert.ok(scanner.indexOf('ensure(not missing_stage and not missing_candidate and') < scanner.indexOf('for path in COMPONENTS:'),
    'Unapproved dependencies must block before writing overlay candidates');
  const check = spawnSync('python3', ['-c',
    'import ast,pathlib;ast.parse(pathlib.Path("staging/pos-hubqa/align-dashboard-ui.py").read_text());print("DASHBOARD_DIFFERENCE_INVENTORY_SYNTAX=PASS")'
  ], {encoding:'utf8', timeout: 10000});
  assert.equal(check.status, 0, check.stderr || check.stdout);
  assert.match(check.stdout, /DASHBOARD_DIFFERENCE_INVENTORY_SYNTAX=PASS/);
});


test('Dashboard candidate dependency resolver accepts explicit index.html without appending TypeScript suffixes', () => {
  const code = [
    'import importlib.util',
    'spec=importlib.util.spec_from_file_location("stage_dashboard","staging/pos-hubqa/align-dashboard-ui.py")',
    'module=importlib.util.module_from_spec(spec)',
    'spec.loader.exec_module(module)',
    'assert module.dependency_paths("index.html") == ("index.html",)',
    'assert module.dependency_paths("src/App.tsx") == ("src/App.tsx",)',
    'assert module.dependency_paths("src/index.css") == ("src/index.css",)',
    'assert module.dependency_paths("src/components/HubOverview")[0] == "src/components/HubOverview.ts"',
    'assert "src/components/HubOverview.tsx" in module.dependency_paths("src/components/HubOverview")',
    'assert not any(path.startswith("index.html.") for path in module.dependency_paths("index.html"))',
    'print("DASHBOARD_INDEX_HTML_PATH_RESOLUTION=PASS")'
  ].join('\n');
  const result = spawnSync('python3', ['-c', code], {encoding:'utf8', timeout:10000});
  assert.equal(result.status, 0, result.stderr || result.stdout);
  assert.match(result.stdout, /DASHBOARD_INDEX_HTML_PATH_RESOLUTION=PASS/);
});


test('Read-only dashboard scan inventories missing stage, missing candidate, and differing files in one pass', () => {
  const code = [
    'import importlib.util, io, tempfile, pathlib, contextlib',
    'p="staging/pos-hubqa/align-dashboard-ui.py"',
    'spec=importlib.util.spec_from_file_location("scan_stage",p)',
    'm=importlib.util.module_from_spec(spec)',
    'spec.loader.exec_module(m)',
    'm.COMPONENTS=("src/App.tsx",)',
    'm.COMPANIONS=()',
    'm.STAGE_NAME="stage"',
    'm.LIVE_NAME="live"',
    'm.candidate_container=lambda:"candidate"',
    'm.run=lambda *a,**kw:None',
    'app=\'import {OwnerToday} from "./components/OwnerToday";\\nimport {AdminConsole} from "./components/AdminConsole";\\nimport {Other} from "./components/Unlisted";\\nexport default function App() {}\'',
    'candidate={',
    ' "src/App.tsx":app,',
    ' "src/components/OwnerToday.tsx":"export const OwnerToday=1;",',
    ' "src/components/AdminConsole.tsx":"export const AdminConsole=2;"',
    '}',
    'stage={',
    ' "src/App.tsx":"export default function App() { return 1; }",',
    ' "src/components/AdminConsole.tsx":"export const AdminConsole=1;"',
    '}',
    'data={"candidate":candidate,"stage":stage,"live":{"src/App.tsx":app}}',
    'def extract(container,path,target):',
    ' value=data.get(container,{}).get(path)',
    ' if value is None: return False',
    ' target.parent.mkdir(parents=True,exist_ok=True)',
    ' target.write_bytes(value.encode())',
    ' return True',
    'm.extract=extract',
    'buf=io.StringIO()',
    'with tempfile.TemporaryDirectory() as tmp:',
    ' try:',
    '  with contextlib.redirect_stdout(buf): m.verify_candidate_dependency_parity(pathlib.Path(tmp))',
    ' except RuntimeError as e:',
    '  assert "Unreviewed frontend dependencies:" in str(e),str(e)',
    ' else: raise AssertionError("Unapproved frontend imports were accepted")',
    'text=buf.getvalue()',
    'assert "MISSING_STAGE_FRONTEND_DEPENDENCY=src/components/OwnerToday.tsx" in text,text',
    'assert "MISSING_CANDIDATE_FRONTEND_DEPENDENCY=src/components/Unlisted" in text,text',
    'assert "DIFFERING_NON_DASHBOARD_DEPENDENCY=src/components/AdminConsole.tsx" in text,text',
    'assert "MISSING_STAGE_FRONTEND_DEPENDENCIES=1" in text,text',
    'assert "MISSING_CANDIDATE_FRONTEND_DEPENDENCIES=1" in text,text',
    'assert "NON_DASHBOARD_DEPENDENCY_DIFFERENCES=1" in text,text',
    'assert text.count("APPROVED_LIVE_DASHBOARD_COMPONENT=src/App.tsx")==1,text',
    'print("DASHBOARD_ALL_GAPS_READONLY_INVENTORY=PASS")'
  ].join('\n');
  const result = spawnSync('python3', ['-c', code], {encoding:'utf8',timeout:10000});
  assert.equal(result.status, 0, result.stderr || result.stdout);
  assert.match(result.stdout, /DASHBOARD_ALL_GAPS_READONLY_INVENTORY=PASS/);
});


test('Dashboard dependency resolver records imports outside src and rejects traversal', () => {
  const python = [
    'import importlib.util',
    'spec=importlib.util.spec_from_file_location("stage_dashboard","staging/pos-hubqa/align-dashboard-ui.py")',
    'm=importlib.util.module_from_spec(spec)',
    'spec.loader.exec_module(m)',
    'source="src/components/OwnerToday.tsx"',
    'code="\\n".join(["import A from \\"../lib/dashboardTruth\\";","import B from \\"../../../secrets\\";","import C from \\"../../assets/global.svg\\";"])',
    'outside=set()',
    'imports=m.relative_imports(source,code,outside)',
    'assert imports=={"src/lib/dashboardTruth"},imports',
    'assert outside=={(source,"../../../secrets"),(source,"../../assets/global.svg")},outside',
    'try:',
    ' m.relative_imports(source,code)',
    'except RuntimeError as exc:',
    ' assert "STAGING_DASHBOARD_ALIGNMENT_BLOCKED" in str(exc),str(exc)',
    ' assert "Frontend import outside src" in str(exc),str(exc)',
    'else: raise AssertionError("Import escape not rejected")',
    'print("STAGE_DEPENDENCY_IMPORT_ESCAPE=PASS")'
  ].join('\n');
  const result = spawnSync('python3',['-c',python],{encoding:'utf8',timeout:10000});
  assert.equal(result.status,0,result.stderr||result.stdout);
  assert.match(result.stdout,/STAGE_DEPENDENCY_IMPORT_ESCAPE=PASS/);
  const script = readFileSync('staging/pos-hubqa/align-dashboard-ui.py','utf8');
  for(const check of [
    'outside_src = set()',
    'relative_imports(actual, contents.decode("utf-8"),',
    'FRONTEND_IMPORTS_OUTSIDE_SRC=',
    'FRONTEND_IMPORT_OUTSIDE_SRC=',
    'not mismatches and not outside_src',
    'imports outside src; no automatic broad copy'
  ]) assert.ok(script.includes(check),"Missing fail-closed import diagnostic: "+check);
});


test('Visual-only private dashboard overlay is limited to approved Overview/Sidebar and preserves App, Login, admin and MFA', () => {
  const source = readFileSync('staging/pos-hubqa/align-visual-dashboard.py','utf8');
  for (const guard of [
    'src/components/HubOverview.tsx',
    'src/components/Sidebar.tsx',
    'b00c05056dd7a8dfcfb6055425644d26ac6880472b714b17461995b16a381096',
    'c690df486b7f43d606ce50486bb94e077eccd33a8ed090e1009920537de5cce0',
    'src/App.tsx',
    'src/components/Login.tsx',
    'src/components/AdminConsole.tsx',
    'src/components/OwnerAssistant.tsx',
    'src/components/WorkforceActionPanel.tsx',
    'src/lib/appLaunch.ts',
    'src/lib/dashboardTruth.ts',
    'ea182c2656cea2979412e611bf1e704d4068512f72d6d2db5eba33f80d5c544c',
    'PRIVATE_VISUAL_DASHBOARD_DRY_RUN=PASS',
    'DIRECT_VISUAL_IMPORT_PARITY=PASS',
    'STAGE_APP_AUTH_NAVIGATION_PROPS=PASS',
    'APP_LOGIN_ADMIN_ROUTING_AND_WORKFORCE_SOURCES_UNCHANGED=PASS',
    'PRIVATE_VISUAL_DASHBOARD_CHECKPOINT=',
    'STAGING_VISUAL_DASHBOARD_ROLLBACK_ATTEMPT',
    'PREVIOUS_MFA_POS_STAGE_RESTORED=PASS',
    'PRIVATE_STAGING_VISUAL_DASHBOARD=PASS',
    'DASHBOARD_BROWSER_REVIEW_AND_MFA_POS_SSO=NOT_YET_VERIFIED',
    'guards.check_preflight()',
    'guards.build(scratch)',
    'guards.checkpoint(compose)',
    'guards.restart()',
    'guards.verify_after(',
    'verify_protected_sources(',
  ]) assert.ok(source.includes(guard), 'Visual staging code missing: '+guard);
  for(const term of ['docker compose down','docker rm v79-hub','chmod 777',
    'pg_restore','docker stop v79-pos','mcp__Remote_Desktop_Commander']) {
    assert.ok(!source.includes(term),'Unsafe visual stage instruction: '+term);
  }
  const syntax=spawnSync('python3',['-c',
    'import ast,pathlib;ast.parse(pathlib.Path("staging/pos-hubqa/align-visual-dashboard.py").read_text());print("VISUAL_STAGE_SCRIPT_SYNTAX=PASS")'
  ],{encoding:'utf8',timeout:10000});
  assert.equal(syntax.status,0,syntax.stderr||syntax.stdout);
  assert.match(syntax.stdout,/VISUAL_STAGE_SCRIPT_SYNTAX=PASS/);
});

test('Stage acceptance requires exact pinned visual image and unchanged App/Login/Admin source hashes', () => {
  const source=readFileSync('staging/pos-hubqa/check.py','utf8');
  for (const term of [
    'approved-dashboard-visual.json',
    'v79hub:pos-hubqa-dashboard-visual-20261109-r1',
    'pin.get("base_stage_image_id") == parent.get("image_id")',
    'pin.get("dashboard_source_image_id") == candidate["Id"]',
    'stage_hub["Config"]["Image"] == tag',
    'source_map == expected_visual',
    'set(protected_map) == set(expected_protected)',
    'src/components/Login.tsx',
    'src/components/AdminConsole.tsx',
    'src/components/WorkforceActionPanel.tsx',
    'STAGING_HEALTH_AND_UNAUTH_DENIAL=PASS',
    'STAGING_LOGIN_PRODUCT_IMAGES=PASS'
  ]) assert.ok(source.includes(term),'Missing exact visual stage read-back check: '+term);
});

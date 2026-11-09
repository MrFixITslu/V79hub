import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { spawnSync } from 'node:child_process';

const compose = readFileSync('staging/pos-hubqa/hub-compose.yml', 'utf8');
const helper = readFileSync('staging/pos-hubqa/prepare.py', 'utf8');

test('Hub staging has private network, MFA, loopback-only port and disabled outbound writes', () => {
  assert.match(compose, /^name: v79-hub-pos-hubqa-20261109/m);
  assert.match(compose, /container_name: v79-hub-pos-hubqa/);
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

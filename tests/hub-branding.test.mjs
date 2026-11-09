import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const base = process.cwd();
const read = (filename) => fs.readFileSync(path.join(base, filename));
test('Hub favicon assets use the distinct approved Hub identity', () => {
  const html = read('index.html').toString('utf8');
  assert.match(html, /\/brand\/favicon-32\.png\?v=v79-hub-approved-20261109/);
  assert.match(html, /\/brand-site\.webmanifest\?v=v79-hub-approved-20261109/);
  assert.doesNotMatch(html, /v79-symbol-20261108-r4/);
  for (const f of ['public/brand/favicon-16.png', 'public/brand/favicon-32.png',
      'public/brand/icon-transparent-512.png', 'public/brand/apple-touch-icon.png',
      'public/brand/android-chrome-192.png', 'public/brand/android-chrome-512.png',
      'public/brand/logo-full.png']) {
    assert.equal(read(f).subarray(0,8).toString('hex'), '89504e470d0a1a0a', f);
  }
  const ico = read('public/favicon.ico');
  assert.equal(ico.subarray(0,4).toString('hex'), '00000100');
  const svg = read('public/icon.svg').toString('utf8');
  assert.match(svg, /<svg /);
  assert.doesNotMatch(svg, /v79grad/);
  const manifest=JSON.parse(read('public/brand-site.webmanifest').toString('utf8'));
  assert.equal(manifest.name, 'V79 Hub');
  assert.equal(manifest.icons.length,2);
});

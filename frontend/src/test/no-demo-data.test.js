// Guards plan goal 3: demo data lives in backend/seed, never in frontend code.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';

const SRC = new URL('..', import.meta.url).pathname;
const FORBIDDEN = [/\bSH-[A-D]\b/, /\bB-0\d\d\b/, /\bR-0\d\d\b/, /\bSRC-[A-Z]/, /\+1-555/, /Lincoln|Jefferson|Example Ave/];

function files(dir) {
  return readdirSync(dir).flatMap(name => {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) return files(p);
    return /\.(jsx?|json)$/.test(name) && !/\.test\.jsx?$/.test(name) ? [p] : [];
  });
}

test('frontend source contains no seed IDs, phone numbers or venue names', () => {
  const hits = files(SRC).flatMap(f => {
    const text = readFileSync(f, 'utf8');
    return FORBIDDEN.filter(re => re.test(text)).map(re => `${f.replace(SRC, '')}: ${re}`);
  });
  assert.deepEqual(hits, []);
});

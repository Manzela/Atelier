/**
 * Unit test for SSEStreamParser (L07 / JAM-BUG-1 regression).
 *
 * No unit runner is wired into the dashboard yet (Playwright-only), so this runs
 * directly under Node's type-stripping loader:
 *   node --experimental-strip-types src/lib/sse-parser.test.mts
 * Wiring a vitest job into CI is tracked as a follow-up (audit L03 / missed vectors).
 */
import assert from 'node:assert/strict';

import { SSEStreamParser } from './sse-parser.ts';

let passed = 0;
function test(name: string, fn: () => void): void {
  fn();
  passed += 1;
  console.log(`  ok  ${name}`);
}

// The bug: event name and data line delivered in SEPARATE chunks.
test('preserves event name when event: and data: straddle a chunk boundary', () => {
  const p = new SSEStreamParser();
  const first = p.push('event: screen_converged\n');
  assert.deepEqual(first, [], 'no complete frame until the data line arrives');
  const second = p.push('data: {"screen":"welcome","html":"<x/>"}\n\n');
  assert.equal(second.length, 1);
  assert.equal(second[0].event, 'screen_converged', 'event name survived the boundary');
  assert.equal(second[0].data, '{"screen":"welcome","html":"<x/>"}');
});

// A large data payload split across many chunks reassembles, name intact.
test('reassembles a large data payload split across chunks', () => {
  const p = new SSEStreamParser();
  const big = 'A'.repeat(20000);
  p.push('event: specialist_trace\n');
  p.push('data: {"role":"UIDesigner","summary":"' + big.slice(0, 10000));
  const frames = p.push(big.slice(10000) + '"}\n\n');
  assert.equal(frames.length, 1);
  assert.equal(frames[0].event, 'specialist_trace');
  assert.ok(frames[0].data.includes(big), 'full payload reassembled');
});

// Multiple frames in one chunk each carry their own name; reset is intra-frame.
test('handles multiple frames in one chunk with correct per-frame names', () => {
  const p = new SSEStreamParser();
  const frames = p.push(
    'event: plan\ndata: {"a":1}\n\nevent: complete\ndata: {"b":2}\n\n'
  );
  assert.equal(frames.length, 2);
  assert.equal(frames[0].event, 'plan');
  assert.equal(frames[1].event, 'complete');
});

// A keep-alive comment line (": ping") carries no data and yields no frame.
test('ignores keep-alive comment lines', () => {
  const p = new SSEStreamParser();
  assert.deepEqual(p.push(': ping\n\n'), []);
});

console.log(`\n${passed} passed`);

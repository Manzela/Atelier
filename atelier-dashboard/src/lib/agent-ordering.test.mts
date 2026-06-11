/**
 * Unit test for the shared agent-ordering module (L08 regression).
 * Run: node --experimental-strip-types src/lib/agent-ordering.test.mts
 */
import assert from 'node:assert/strict';

import { CANONICAL_STAGE_ORDER, normalizeRole, stageIndex } from './agent-ordering.ts';

let passed = 0;
function test(name: string, fn: () => void): void {
  fn();
  passed += 1;
  console.log(`  ok  ${name}`);
}

test('normalizeRole accepts snake key, camelCase role, and roster id', () => {
  assert.equal(normalizeRole('ui_design'), 'ui_design');
  assert.equal(normalizeRole('UIDesigner'), 'ui_design');
  assert.equal(normalizeRole('specialist_uidesigner'), 'ui_design');
  assert.equal(normalizeRole('UXResearcher'), 'ux_research');
  assert.equal(normalizeRole('planner'), '');
  assert.equal(normalizeRole(''), '');
});

test('stageIndex orders the 6 specialists in canonical order', () => {
  const order = CANONICAL_STAGE_ORDER.map((k) => stageIndex(k));
  for (let i = 1; i < order.length; i += 1) {
    assert.ok(order[i] > order[i - 1], `${CANONICAL_STAGE_ORDER[i]} must sort after the prior`);
  }
});

test('camelCase and snake forms of the same role get the same index', () => {
  assert.equal(stageIndex('UIDesigner'), stageIndex('ui_design'));
});

test('intake leads, specialists middle, unknown last', () => {
  assert.ok(stageIndex('planner') < stageIndex('ux_research'));
  assert.ok(stageIndex('ux_research') < stageIndex('fixer'));
  assert.equal(stageIndex('judge_originality'), Number.MAX_SAFE_INTEGER);
});

test('the reporter symptom: UXResearcher sorts before UIDesigner', () => {
  // Jam bf309f9f: the trace showed UIDesigner before UXResearcher in one view.
  assert.ok(stageIndex('UXResearcher') < stageIndex('UIDesigner'));
});

console.log(`\n${passed} passed`);

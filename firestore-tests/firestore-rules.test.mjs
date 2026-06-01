/**
 * AT-084 — Firestore security-rules isolation test (PRD v2.2 §12 E8).
 *
 * SECURITY-SENSITIVE: proves the deny-by-default tenant/user isolation in
 * ../firestore.rules holds. Run against the Firestore emulator via:
 *
 *     npx firebase emulators:exec --only firestore \
 *       "node --test firestore-tests/firestore-rules.test.mjs"
 *
 * The test is NON-VACUOUS by construction: every collection has at least one
 * assertSucceeds (the legitimate owner/member) AND one assertFails (a foreign
 * principal). If the rules were loosened to `allow read: if true`, the
 * cross-tenant / cross-user / unauthenticated assertFails cases below would
 * start succeeding and the suite would FAIL — which is the property the gate
 * relies on. (Manually verified during authoring; see gaps.md.)
 *
 * Uses @firebase/rules-unit-testing (v5, peers firebase ^12). No production
 * Firebase project is touched — initializeTestEnvironment talks only to the
 * local emulator. The custom claim `atelier_tenant` mirrors the server-minted
 * claim read by atelier-core/src/atelier/auth/firebase.py's `_user_from_token`
 * (`decoded.get("atelier_tenant") or uid`). The rules derive tenant identity
 * via tenantOf(): the `atelier_tenant` claim when present + non-empty, else the
 * Firebase uid (B2C fallback). The B2C arm below proves a claimless user can
 * still reach /tenants/{theirUid}/... but no other uid's tenant subtree.
 */

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { after, before, describe, it } from 'node:test';

import {
  assertFails,
  assertSucceeds,
  initializeTestEnvironment,
} from '@firebase/rules-unit-testing';
import { doc, getDoc, setDoc } from 'firebase/firestore';

const __dirname = dirname(fileURLToPath(import.meta.url));
const RULES_PATH = join(__dirname, '..', 'firestore.rules');

// Stable identities used across the suite.
const UID_A = 'user-alice';
const UID_B = 'user-bob';
const TENANT_A = 'tenant-acme';
const TENANT_B = 'tenant-globex';
const PROJECT = 'redesign-2026-q3';
// B2C user: no atelier_tenant claim -> tenantOf() falls back to this uid, so the
// user's tenant subtree IS /tenants/{UID_B2C}/...
const UID_B2C = 'user-carol-b2c';

let testEnv;

/**
 * Authed context for a B2B Firebase user whose token carries an `atelier_tenant`
 * custom claim. Mirrors the server-minted claim read by firebase.py.
 */
function authedAs(uid, tenantId) {
  return testEnv.authenticatedContext(uid, { atelier_tenant: tenantId }).firestore();
}

/**
 * Authed context for a B2C Firebase user with NO `atelier_tenant` claim.
 * Per firebase.py (`decoded.get("atelier_tenant") or uid`) and the rules'
 * tenantOf() helper, such a user's tenant identity is their own uid, so they
 * operate under /tenants/{uid}/... only.
 */
function authedB2C(uid) {
  return testEnv.authenticatedContext(uid).firestore();
}

before(async () => {
  testEnv = await initializeTestEnvironment({
    projectId: 'atelier-rules-test',
    firestore: {
      rules: readFileSync(RULES_PATH, 'utf8'),
      // host/port are read from FIRESTORE_EMULATOR_HOST, set by
      // `firebase emulators:exec`. Default emulator port is 8080.
    },
  });

  // Seed documents with security rules disabled so the read/write assertions
  // below exercise the rules, not the absence of data.
  await testEnv.withSecurityRulesDisabled(async (ctx) => {
    const db = ctx.firestore();
    await setDoc(doc(db, `users/${UID_A}/usage/token-cap`), { used: 10 });
    await setDoc(doc(db, `users/${UID_B}/usage/token-cap`), { used: 20 });
    await setDoc(
      doc(db, `tenants/${TENANT_A}/projects/${PROJECT}/tasks/task-1`),
      { title: 'Acme task', status: 'todo', order: 1 }
    );
    await setDoc(
      doc(db, `tenants/${TENANT_B}/projects/${PROJECT}/tasks/task-1`),
      { title: 'Globex task', status: 'todo', order: 1 }
    );
    await setDoc(
      doc(db, `tenants/${TENANT_A}/projects/${PROJECT}/board/board-1`),
      { name: 'Acme board' }
    );
    // B2C user's own tenant subtree, keyed by their uid (no atelier_tenant claim).
    await setDoc(
      doc(db, `tenants/${UID_B2C}/projects/${PROJECT}/tasks/task-1`),
      { title: 'Carol task', status: 'todo', order: 1 }
    );
  });
});

after(async () => {
  if (testEnv) {
    await testEnv.cleanup();
  }
});

describe('per-user token-cap counter isolation (/users/{uid}/usage)', () => {
  it('owner CAN read its own counter', async () => {
    const db = authedAs(UID_A, TENANT_A);
    await assertSucceeds(getDoc(doc(db, `users/${UID_A}/usage/token-cap`)));
  });

  it('owner CAN write its own counter', async () => {
    const db = authedAs(UID_A, TENANT_A);
    await assertSucceeds(
      setDoc(doc(db, `users/${UID_A}/usage/token-cap`), { used: 11 })
    );
  });

  it('a different user CANNOT read another user counter', async () => {
    const db = authedAs(UID_B, TENANT_B);
    await assertFails(getDoc(doc(db, `users/${UID_A}/usage/token-cap`)));
  });

  it('a different user CANNOT write another user counter', async () => {
    const db = authedAs(UID_B, TENANT_B);
    await assertFails(
      setDoc(doc(db, `users/${UID_A}/usage/token-cap`), { used: 999 })
    );
  });

  it('unauthenticated CANNOT read a counter', async () => {
    const db = testEnv.unauthenticatedContext().firestore();
    await assertFails(getDoc(doc(db, `users/${UID_A}/usage/token-cap`)));
  });
});

describe('board/tasks tenant isolation (/tenants/{tenantId}/projects/.../tasks)', () => {
  it('tenant member CAN read its own task', async () => {
    const db = authedAs(UID_A, TENANT_A);
    await assertSucceeds(
      getDoc(doc(db, `tenants/${TENANT_A}/projects/${PROJECT}/tasks/task-1`))
    );
  });

  it('tenant member CAN read its own board doc', async () => {
    const db = authedAs(UID_A, TENANT_A);
    await assertSucceeds(
      getDoc(doc(db, `tenants/${TENANT_A}/projects/${PROJECT}/board/board-1`))
    );
  });

  it('tenant member CAN write within its own tenant', async () => {
    const db = authedAs(UID_A, TENANT_A);
    await assertSucceeds(
      setDoc(doc(db, `tenants/${TENANT_A}/projects/${PROJECT}/tasks/task-2`), {
        title: 'New Acme task',
        status: 'doing',
        order: 2,
      })
    );
  });

  it('tenant A member CANNOT read tenant B task (cross-tenant read denied)', async () => {
    const db = authedAs(UID_A, TENANT_A);
    await assertFails(
      getDoc(doc(db, `tenants/${TENANT_B}/projects/${PROJECT}/tasks/task-1`))
    );
  });

  it('tenant A member CANNOT write into tenant B (cross-tenant write denied)', async () => {
    const db = authedAs(UID_A, TENANT_A);
    await assertFails(
      setDoc(doc(db, `tenants/${TENANT_B}/projects/${PROJECT}/tasks/evil`), {
        title: 'injected',
      })
    );
  });

  it('a B2C user (NO atelier_tenant claim) CANNOT read a B2B tenant doc', async () => {
    // Authenticated, but no atelier_tenant claim -> tenantOf() == its own uid,
    // which is NOT TENANT_A, so the cross-tenant read is denied.
    const db = authedB2C('orphan-user');
    await assertFails(
      getDoc(doc(db, `tenants/${TENANT_A}/projects/${PROJECT}/tasks/task-1`))
    );
  });

  it('unauthenticated CANNOT read a tenant task', async () => {
    const db = testEnv.unauthenticatedContext().firestore();
    await assertFails(
      getDoc(doc(db, `tenants/${TENANT_A}/projects/${PROJECT}/tasks/task-1`))
    );
  });
});

describe('B2C uid-fallback tenant identity (no atelier_tenant claim)', () => {
  it('B2C user CAN read its own /tenants/{uid}/... subtree', async () => {
    const db = authedB2C(UID_B2C);
    await assertSucceeds(
      getDoc(doc(db, `tenants/${UID_B2C}/projects/${PROJECT}/tasks/task-1`))
    );
  });

  it('B2C user CAN write within its own /tenants/{uid}/... subtree', async () => {
    const db = authedB2C(UID_B2C);
    await assertSucceeds(
      setDoc(doc(db, `tenants/${UID_B2C}/projects/${PROJECT}/tasks/task-2`), {
        title: 'New Carol task',
        status: 'doing',
        order: 2,
      })
    );
  });

  it('B2C user CANNOT read another uid tenant subtree (cross-tenant denied)', async () => {
    const db = authedB2C(UID_B2C);
    await assertFails(
      getDoc(doc(db, `tenants/${TENANT_A}/projects/${PROJECT}/tasks/task-1`))
    );
  });

  it('B2C user CANNOT write into another uid tenant subtree', async () => {
    const db = authedB2C(UID_B2C);
    await assertFails(
      setDoc(doc(db, `tenants/${UID_A}/projects/${PROJECT}/tasks/evil`), {
        title: 'injected',
      })
    );
  });

  it('a B2B user CANNOT reach a B2C uid-keyed tenant subtree', async () => {
    // Defense-in-depth: a B2B caller's atelier_tenant claim (TENANT_A) is not
    // the B2C user's uid, so the B2C subtree is closed to them too.
    const db = authedAs(UID_A, TENANT_A);
    await assertFails(
      getDoc(doc(db, `tenants/${UID_B2C}/projects/${PROJECT}/tasks/task-1`))
    );
  });
});

describe('deny-by-default floor (unmatched collections)', () => {
  it('an authenticated user CANNOT read an arbitrary top-level collection', async () => {
    const db = authedAs(UID_A, TENANT_A);
    await assertFails(getDoc(doc(db, `secrets/super-secret`)));
  });

  it('an authenticated user CANNOT write an arbitrary top-level collection', async () => {
    const db = authedAs(UID_A, TENANT_A);
    await assertFails(setDoc(doc(db, `secrets/super-secret`), { x: 1 }));
  });
});

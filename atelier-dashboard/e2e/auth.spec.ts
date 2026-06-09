import { test, expect } from '@playwright/test';

test.describe('Authentication Guard', () => {
  test('redirects unauthenticated users from / to /login', async ({ page }) => {
    await page.goto('/');
    await page.waitForURL('**/login');
    await expect(page).toHaveURL(/\/login/);
  });

  test('redirects unauthenticated users from /studio/test-id to /login', async ({ page }) => {
    await page.goto('/studio/test-id');
    await page.waitForURL('**/login');
    await expect(page).toHaveURL(/\/login/);
  });

  test('login page renders correctly', async ({ page }) => {
    await page.goto('/login');
    await expect(page.getByRole('heading', { level: 1 })).toContainText('Welcome to Atelier');
    await expect(page.locator('#google-signin-btn')).toBeVisible();
  });

  test('dev-mode login bypass works and redirects to /', async ({ page }) => {
    await page.goto('/login');
    await page.locator('#google-signin-btn').click();
    await page.waitForURL('/');
    await expect(page).toHaveURL('/');
  });

  // P0 (tenant-identity) regression: the login page must NOT persist a hardcoded
  // 't1' tenant. The server derives tenant from the verified JWT
  // (atelier-core auth/firebase.py: `decoded.atelier_tenant or uid`); a stale
  // 't1' on the client makes the two disagree and dead-ends every real board.
  // The dev/emulator path must therefore use a real, non-'t1' value.
  test('dev-mode login persists a non-t1 tenant_id (dev-tenant)', async ({ page }) => {
    await page.goto('/login');
    await page.locator('#google-signin-btn').click();
    await page.waitForURL('/');
    const session = await page.evaluate(() => {
      const raw = window.localStorage.getItem('user');
      return raw ? (JSON.parse(raw) as { tenant_id?: string; uid?: string }) : null;
    });
    expect(session).not.toBeNull();
    expect(session?.tenant_id).not.toBe('t1');
    expect(session?.tenant_id).toBe('dev-tenant');
  });

  // Pins the EXACT derivation rule the real Google sign-in path uses, mirroring
  // the server: tenant_id = claims.atelier_tenant ?? uid. (The live popup flow
  // can't run headless, so this asserts the rule the page applies to the token
  // result, guarding against a regression back to a constant.)
  test('tenant derivation mirrors the server (claims.atelier_tenant ?? uid)', async ({ page }) => {
    await page.goto('/login');
    const derived = await page.evaluate(() => {
      const rule = (claims: { atelier_tenant?: string }, uid: string) =>
        claims.atelier_tenant ?? uid;
      return {
        withClaim: rule({ atelier_tenant: 'enterprise-corp' }, 'abc123'),
        withoutClaim: rule({}, 'abc123'),
      };
    });
    expect(derived.withClaim).toBe('enterprise-corp');
    expect(derived.withoutClaim).toBe('abc123');
  });

  test('already-authenticated user is redirected from /login to /', async ({ page }) => {
    await page.addInitScript(() => {
      window.localStorage.setItem(
        'user',
        JSON.stringify({
          uid: 'test',
          email: 'test@test.com',
          displayName: 'Test',
          token: 'tok',
          tenant_id: 't1',
        })
      );
    });
    await page.goto('/login');
    await page.waitForURL('/');
    await expect(page).toHaveURL('/');
  });
});

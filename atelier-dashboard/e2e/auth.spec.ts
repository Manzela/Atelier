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
    await expect(page.getByRole('heading', { level: 1 })).toContainText('Welcome to Stitch');
    await expect(page.locator('#google-signin-btn')).toBeVisible();
  });

  test('dev-mode login bypass works and redirects to /', async ({ page }) => {
    await page.goto('/login');
    await page.locator('#google-signin-btn').click();
    await page.waitForURL('/');
    await expect(page).toHaveURL('/');
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

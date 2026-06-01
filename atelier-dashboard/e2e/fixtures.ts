import { test as base, expect, Page } from '@playwright/test';

/**
 * Custom test fixture that seeds localStorage with a mock user session.
 * This simulates a logged-in user without going through the login UI,
 * enabling all tests to focus on their specific area rather than
 * re-testing auth flow.
 */
interface AuthFixtures {
  authenticatedPage: Page;
}

const MOCK_USER = {
  uid: 'e2e-test-user',
  email: 'e2e@atelier.test',
  displayName: 'E2E Tester',
  token: 'e2e-test-token',
  tenant_id: 't1',
};

export const test = base.extend<AuthFixtures>({
  authenticatedPage: async ({ page }, use) => {
    // Seed localStorage before navigating, so the auth guard passes
    await page.addInitScript((user) => {
      window.localStorage.setItem('user', JSON.stringify(user));
    }, MOCK_USER);
    await use(page);
  },
});

export { expect, MOCK_USER };

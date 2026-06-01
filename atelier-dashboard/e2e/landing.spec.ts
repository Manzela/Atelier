import { test, expect, MOCK_USER } from './fixtures';

test.describe('Landing Page (Stitch Shell)', () => {
  test('renders the Welcome heading', async ({ authenticatedPage: page }) => {
    await page.goto('/');
    await expect(page.getByRole('heading', { level: 1 })).toContainText('Welcome to Stitch.');
  });

  test('renders user initials from session', async ({ authenticatedPage: page }) => {
    await page.goto('/');
    const initials = MOCK_USER.displayName
      .split(' ')
      .map((n) => n[0])
      .join('')
      .toUpperCase();
    await expect(page.getByTitle(MOCK_USER.email)).toContainText(initials);
  });

  test('sidebar starts in Stitch mode with project tabs', async ({ authenticatedPage: page }) => {
    await page.goto('/');
    await expect(page.getByText('Stitch BETA')).toBeVisible();
    await expect(page.getByText('My projects')).toBeVisible();
    await expect(page.getByText('Last 30 days')).toBeVisible();
  });

  test('sidebar toggles to GCP Console mode', async ({ authenticatedPage: page }) => {
    await page.goto('/');
    await page.getByLabel('Toggle sidebar mode').click();
    await expect(page.getByText('GCP Console')).toBeVisible();
    await expect(page.getByText('IAM & Admin')).toBeVisible();
    await expect(page.getByText('Quotas & Billing')).toBeVisible();
    await expect(page.getByText('Model Registry')).toBeVisible();
  });

  test('sidebar toggles back to Stitch mode', async ({ authenticatedPage: page }) => {
    await page.goto('/');
    await page.getByLabel('Toggle sidebar mode').click();
    await expect(page.getByText('GCP Console')).toBeVisible();
    await page.getByLabel('Toggle sidebar mode').click();
    await expect(page.getByText('Stitch BETA')).toBeVisible();
  });

  test('prompt box is interactive and expands on focus', async ({ authenticatedPage: page }) => {
    await page.goto('/');
    const textarea = page.getByPlaceholder('What native mobile app shall we design?');
    await expect(textarea).toBeVisible();
    await textarea.focus();
    await textarea.fill('A fitness tracking app with social features');
    await expect(textarea).toHaveValue('A fitness tracking app with social features');
  });

  test('send button is disabled when prompt is empty', async ({ authenticatedPage: page }) => {
    await page.goto('/');
    const sendBtn = page.getByLabel('Generate');
    await expect(sendBtn).toBeDisabled();
  });

  test('send button enables when prompt has content', async ({ authenticatedPage: page }) => {
    await page.goto('/');
    const textarea = page.getByPlaceholder('What native mobile app shall we design?');
    await textarea.fill('test prompt');
    const sendBtn = page.getByLabel('Generate');
    await expect(sendBtn).toBeEnabled();
  });

  test('App/Web toggle switches device type', async ({ authenticatedPage: page }) => {
    await page.goto('/');
    const webBtn = page.getByText('Web', { exact: true });
    await webBtn.click();
    // Web button should now have the active styling (bg-[var(--g-outline)])
    await expect(webBtn).toBeVisible();
  });

  test('submit navigates to /studio/[id]', async ({ authenticatedPage: page }) => {
    await page.goto('/');
    const textarea = page.getByPlaceholder('What native mobile app shall we design?');
    await textarea.fill('A chat application');
    await page.getByLabel('Generate').click();
    await page.waitForURL('**/studio/**');
    await expect(page).toHaveURL(/\/studio\//);
  });

  test('Enter key submits the prompt', async ({ authenticatedPage: page }) => {
    await page.goto('/');
    const textarea = page.getByPlaceholder('What native mobile app shall we design?');
    await textarea.fill('Dashboard app');
    await textarea.press('Enter');
    await page.waitForURL('**/studio/**');
    await expect(page).toHaveURL(/\/studio\//);
  });
});

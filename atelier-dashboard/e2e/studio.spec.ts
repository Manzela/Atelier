import { test, expect } from './fixtures';

test.describe('Studio Workspace', () => {
  test('renders the studio header with project ID', async ({ authenticatedPage: page }) => {
    await page.goto('/studio/test-project-123');
    await expect(page.getByText('test-project-123')).toBeVisible();
  });

  test('back button navigates to landing page', async ({ authenticatedPage: page }) => {
    await page.goto('/studio/test-project-123');
    await page.getByLabel('Back to dashboard').click();
    await page.waitForURL('/');
    await expect(page).toHaveURL('/');
  });

  test('canvas shows idle state placeholder', async ({ authenticatedPage: page }) => {
    await page.goto('/studio/test-project-123');
    await expect(page.getByText(/Click.*Run.*to generate/)).toBeVisible();
  });

  test('layers panel renders all expected layers', async ({ authenticatedPage: page }) => {
    await page.goto('/studio/test-project-123');
    await expect(page.getByText('Hero Section')).toBeVisible();
    await expect(page.getByText('Feature Grid')).toBeVisible();
    await expect(page.getByText('Testimonials')).toBeVisible();
    await expect(page.getByText('Pricing Table')).toBeVisible();
    await expect(page.getByText('Footer')).toBeVisible();
  });

  test('Vertex AI settings panel renders sliders', async ({ authenticatedPage: page }) => {
    await page.goto('/studio/test-project-123');
    await expect(page.getByText('Vertex AI Settings')).toBeVisible();
    await expect(page.getByLabel('Temperature')).toBeVisible();
    await expect(page.getByLabel('Top-K')).toBeVisible();
    await expect(page.getByLabel('Max Tokens')).toBeVisible();
  });

  test('temperature slider is interactive', async ({ authenticatedPage: page }) => {
    await page.goto('/studio/test-project-123');
    const slider = page.getByLabel('Temperature');
    await slider.fill('0.8');
    await expect(page.getByText('0.80')).toBeVisible();
  });

  test('zoom controls work', async ({ authenticatedPage: page }) => {
    await page.goto('/studio/test-project-123');
    await expect(page.getByText('100%')).toBeVisible();
    await page.getByLabel('Zoom in').click();
    await expect(page.getByText('110%')).toBeVisible();
    await page.getByLabel('Zoom out').click();
    await expect(page.getByText('100%')).toBeVisible();
    await page.getByLabel('Reset zoom').click();
    await expect(page.getByText('100%')).toBeVisible();
  });

  test('log explorer toggle works', async ({ authenticatedPage: page }) => {
    await page.goto('/studio/test-project-123');
    await page.getByText('View Logs').click();
    await expect(page.getByText('Cloud Log Explorer')).toBeVisible();
    await page.getByLabel('Close log drawer').click();
    await expect(page.getByText('View Logs')).toBeVisible();
  });

  test('Run button triggers generation and eventually converges', async ({
    authenticatedPage: page,
  }) => {
    // Mock the SSE endpoint with a delayed response so React can render intermediate states
    await page.route('**/v1/generate/stream', async (route) => {
      // Delay 1 second to allow React to render "Generating..." state
      await new Promise((resolve) => setTimeout(resolve, 1000));
      await route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        body: 'event: complete\ndata: {"status":"done"}\n\n',
      });
    });

    await page.goto('/studio/test-project-123?brief=test');
    const runBtn = page.getByRole('button', { name: /Run/i });
    await runBtn.click();
    // The button text should change from "Run" to "Generating..." while in-flight
    await expect(page.getByText('Generating...')).toBeVisible({ timeout: 3000 });
  });

  test('D-O-R-A-V scorecard shows dashes when idle', async ({ authenticatedPage: page }) => {
    await page.goto('/studio/test-project-123');
    await expect(page.getByText('D-O-R-A-V Scorecard')).toBeVisible();
    const dashes = page.getByText('--');
    await expect(dashes.first()).toBeVisible();
  });
});

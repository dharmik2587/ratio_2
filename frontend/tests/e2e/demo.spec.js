import { test, expect } from '@playwright/test'

test.describe('SIH demo mode — judge view', () => {
  test('judge flow: select case, verify, inspect chain, ask WHY', async ({ page }) => {
    await page.goto('/')
    await page.getByText('SIH DEMO', { exact: true }).click()
    await expect(page.getByText('Judge view — one-click scenarios')).toBeVisible()
    await expect(page.locator('.demo-case')).toHaveCount(8)

    await page.locator('.demo-case', { hasText: 'Synthetic fake boulder' }).click()
    await page.getByRole('button', { name: /VERIFY SYNTHETIC FAKE BOULDER/ }).click()
    await expect(page.locator('.decision-banner strong').first()).toBeVisible({ timeout: 60_000 })
    await expect(page.locator('.decision-banner strong').first()).toContainText(/NOT.?SAFE|REVIEW.?REQUIRED/)
    await expect(page.locator('.blocked-chip')).toContainText('EXPORT BLOCKED')
    await expect(page.locator('.chain-step')).toHaveCount(8)
    await expect(page.locator('.chain-step').first()).toContainText('VISUAL CHANGE')
    await page.getByRole('button', { name: 'WHY WAS THIS DECIDED?' }).click()
    await expect(page.locator('.demo-navigator-result')).toBeVisible({ timeout: 60_000 })
    await expect(page.locator('.demo-navigator-result')).toContainText('RECOMMENDATION')
    await expect(page.locator('.demo-navigator-result')).toContainText(/NOT.?SAFE|REVIEW.?REQUIRED/)
  })

  test('fast-path and bad-registration cases render their recorded statuses', async ({ page }) => {
    await page.goto('/')
    await page.getByText('SIH DEMO', { exact: true }).click()

    // Case 1: legitimate enhancement → NO_SIGNIFICANT_CHANGE fast path
    await page.locator('.demo-case', { hasText: 'Legitimate enhancement' }).click()
    await page.getByRole('button', { name: /VERIFY LEGITIMATE ENHANCEMENT/ }).click()
    await expect(page.locator('.decision-banner strong').first()).toBeVisible({ timeout: 60_000 })
    await expect(page.locator('.decision-banner strong').first()).toContainText('NO SIGNIFICANT CHANGE')

    // Case 4: bad registration → UNRESOLVED (never CONTRADICTED)
    await page.locator('.demo-case', { hasText: 'Bad registration' }).click()
    await page.getByRole('button', { name: /VERIFY BAD REGISTRATION/ }).click()
    await expect(page.locator('.chain-title b')).toBeVisible({ timeout: 60_000 })
    await expect(page.locator('.chain-title b')).toContainText('UNRESOLVED')
    await expect(page.locator('.chain-title b')).not.toContainText('CONTRADICTED')
    // the independent validation point caught the bad fit
    await expect(page.locator('.chain-step').nth(2)).toContainText(/independent validation/)
  })

  test('coarse DEM case shows REFERENCE_INADEQUATE, never contradicted', async ({ page }) => {
    await page.goto('/')
    await page.getByText('SIH DEMO', { exact: true }).click()
    await page.locator('.demo-case', { hasText: 'Coarse reference' }).click()
    await page.getByRole('button', { name: /VERIFY COARSE REFERENCE/ }).click()
    await expect(page.locator('.chain-title b')).toBeVisible({ timeout: 60_000 })
    await expect(page.locator('.chain-title b')).toContainText(/REFERENCE.?INADEQUATE/)
    await expect(page.locator('.chain-title b')).not.toContainText('CONTRADICTED')
  })

  test('high-res case reports the 5 m/px local reference', async ({ page }) => {
    await page.goto('/')
    await page.getByText('SIH DEMO', { exact: true }).click()
    await page.locator('.demo-case', { hasText: 'Good registration + high-res reference' }).click()
    await page.getByRole('button', { name: /VERIFY GOOD REGISTRATION/ }).click()
    await expect(page.locator('.hi-res-banner')).toBeVisible({ timeout: 60_000 })
    await expect(page.locator('.hi-res-banner')).toContainText('5 m/pixel')
    await expect(page.locator('.chain-step').nth(3)).toContainText('REFERENCE_RESOLUTION_ADEQUATE')
  })

  test('Claude offline case falls back deterministically and keeps the decision', async ({ page }) => {
    await page.goto('/')
    await page.getByText('SIH DEMO', { exact: true }).click()
    await page.locator('.demo-case', { hasText: 'Claude offline' }).click()
    await page.getByRole('button', { name: /VERIFY CLAUDE OFFLINE/ }).click()
    await expect(page.locator('.demo-navigator-result')).toBeVisible({ timeout: 60_000 })
    await expect(page.locator('.demo-navigator-result')).toContainText('CLAUDE OFFLINE — FALLBACK ACTIVE')
    await expect(page.locator('.demo-navigator-result')).toContainText('POLICY DECISION')
  })
})

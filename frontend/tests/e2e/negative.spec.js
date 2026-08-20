import { test, expect } from '@playwright/test'
import { uploadPair, IMAGES, noiseFile } from './helpers'

test.describe('RATIO comparability gate and negative flows', () => {
  test('24: incompatible image flow stays in the comparison gate — no change metrics', async ({ page }) => {
    await page.goto('/')
    // upload a real lunar scene against pure noise: the pair is not comparable
    const cardInput = index => page.locator('.file-card').nth(index).locator('input[type="file"]')
    await cardInput(0).setInputFiles(IMAGES.original)
    await cardInput(1).setInputFiles(noiseFile())
    await page.getByRole('button', { name: /VERIFY IMAGE PAIR/ }).click()
    // Phase-3 comparison gate panel (the improved guardrail UI)
    await expect(page.getByText('RATIO stopped analysis here.')).toBeVisible()
    await expect(page.getByText('LOW VISUAL CORRESPONDENCE')).toBeVisible()
    await expect(page.getByText('No visual-change metrics were generated.')).toBeVisible()
    await expect(page.getByText('No terrain verification was attempted.')).toBeVisible()
    await expect(page.getByText('No mission-policy decision was produced.')).toBeVisible()
    // guidance for the operator
    await expect(page.getByText('Use an enhanced version derived from the original image')).toBeVisible()
    await expect(page.getByText('Use the same scene with a different resolution')).toBeVisible()
    await expect(page.getByText('Use a georegistered image pair')).toBeVisible()
    // no Phase-2 console for this input
    await expect(page.getByRole('button', { name: 'VERIFY PHYSICAL EVIDENCE' })).toHaveCount(0)
  })

  test('no-significant-change fast path: DEM verification not required', async ({ page }) => {
    await page.goto('/')
    await uploadPair(page, IMAGES.original, IMAGES.enhanced)
    await expect(page.getByText('Visual evidence workspace')).toBeVisible()
    // fast path: no reference required; the dataset select is disabled by design
    await page.getByRole('button', { name: 'VERIFY PHYSICAL EVIDENCE' }).click()
    await expect(page.locator('.fast-path')).toBeVisible({ timeout: 30_000 })
    await expect(page.locator('.fast-path')).toContainText('NO SIGNIFICANT CHANGE')
    await expect(page.locator('.fast-path')).toContainText('DEM verification was not required')
  })

  test('REAL / SYNTHETIC_DEMO labels are visible on the dataset strip', async ({ page }) => {
    await page.goto('/')
    await uploadPair(page, IMAGES.original, IMAGES.hazard)
    await expect(page.getByText('Visual evidence workspace')).toBeVisible()
    const options = await page.locator('.dataset-control select option').allTextContents()
    expect(options.some(t => t.includes('REAL ·'))).toBe(true)
    expect(options.some(t => t.includes('SYNTHETIC_DEMO ·'))).toBe(true)
    await page.locator('.dataset-control select').selectOption('NASA_SVS_LRO_SYNTHETIC_HAZARD')
    await expect(page.locator('.dataset-strip b').first()).toHaveText('SYNTHETIC_DEMO')
  })
})

import { test, expect } from '@playwright/test'
import { uploadPair } from './helpers'

test.describe('RATIO analysis flow', () => {
  test('1-6: open app, upload images, create analysis, select mission, reference, verify', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByText('RATIO', { exact: true }).first()).toBeVisible()
    await expect(page.getByText('EVIDENCE VERIFICATION CONSOLE')).toBeVisible()

    await uploadPair(page)

    const missionSelect = page.locator('.verification-controls select').first()
    await missionSelect.selectOption('HAZARD_ASSESSMENT')

    const datasetSelect = page.locator('.dataset-control select')
    await datasetSelect.selectOption('NASA_SVS_LRO_SYNTHETIC_HAZARD')

    await page.getByRole('button', { name: 'VERIFY PHYSICAL EVIDENCE' }).click()
    await expect(page.locator('.decision-banner')).toBeVisible({ timeout: 30_000 })
    await expect(page.locator('.decision-banner strong').first()).toContainText(/NOT SAFE|REVIEW REQUIRED/)
  })

  test('7-8: inspect feature and open the evidence panel (8-step evidence chain)', async ({ page }) => {
    await page.goto('/')
    await uploadPair(page)
    const datasetSelect = page.locator('.dataset-control select')
    await datasetSelect.selectOption('NASA_SVS_LRO_SYNTHETIC_HAZARD')
    await page.getByRole('button', { name: 'VERIFY PHYSICAL EVIDENCE' }).click()
    await expect(page.locator('.decision-banner')).toBeVisible({ timeout: 30_000 })

    const pills = page.locator('.feature-pills button')
    await expect(pills.first()).toBeVisible()
    await pills.first().click()

    const steps = page.locator('.chain-step')
    await expect(steps).toHaveCount(8)
    const titles = await steps.locator('.step-head b').allTextContents()
    expect(titles.join('|')).toContain('WHAT CHANGED?')
    expect(titles.join('|')).toContain('IS THE INPUT COMPARABLE?')
    expect(titles.join('|')).toContain('HOW WAS IT ALIGNED?')
    expect(titles.join('|')).toContain('WHAT DOES THE INDEPENDENT TERRAIN REFERENCE SHOW?')
    expect(titles.join('|')).toContain('HOW STRONG IS THE PHYSICAL SUPPORT?')
    expect(titles.join('|')).toContain('WHAT IS THE UNSUPPORTED RISK?')
    expect(titles.join('|')).toContain('WHAT DOES THE MISSION POLICY REQUIRE?')
    expect(titles.join('|')).toContain('FINAL DECISION')
    await expect(page.getByText('NOT A PROBABILITY').first()).toBeVisible()
  })

  test('13: Evidence Navigator answers from structured evidence (offline deterministic mode)', async ({ page }) => {
    await page.goto('/')
    await uploadPair(page)
    const datasetSelect = page.locator('.dataset-control select')
    await datasetSelect.selectOption('NASA_SVS_LRO_SYNTHETIC_HAZARD')
    await page.getByRole('button', { name: 'VERIFY PHYSICAL EVIDENCE' }).click()
    await expect(page.locator('.decision-banner')).toBeVisible({ timeout: 30_000 })

    await page.getByRole('button', { name: 'NAVIGATOR' }).click()
    await expect(page.getByText('EVIDENCE NAVIGATOR')).toBeVisible()
    await page.getByRole('button', { name: 'Why was this flagged?' }).click()
    await expect(page.locator('.nav-msg.assistant dl').first()).toBeVisible({ timeout: 30_000 })
    await expect(page.locator('.nav-meta code').first()).toContainText('get_feature_evidence')
    await expect(page.locator('.nav-meta code.decision')).toBeVisible()
  })

  test('14: graceful Claude-disabled mode — analysis works and falls back to deterministic explanation', async ({ page }) => {
    await page.goto('/')
    await expect(page.locator('.system')).toContainText(/CLAUDE OFFLINE|SYSTEM NOMINAL/)
    await uploadPair(page)
    const datasetSelect = page.locator('.dataset-control select')
    await datasetSelect.selectOption('NASA_SVS_LRO_SYNTHETIC_HAZARD')
    await page.getByRole('button', { name: 'VERIFY PHYSICAL EVIDENCE' }).click()
    await expect(page.locator('.decision-banner')).toBeVisible({ timeout: 30_000 })
    await page.getByRole('button', { name: 'EXPLAIN', exact: true }).click()
    await expect(page.locator('.explanation-panel')).toBeVisible({ timeout: 30_000 })
    await expect(page.locator('.explanation-panel')).toContainText('EXPLANATION REPORT')
    await expect(page.locator('.explain-policy')).toContainText('POLICY DECISION')
  })
})

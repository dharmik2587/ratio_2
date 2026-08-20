import { test, expect } from '@playwright/test'

// A report may already exist from earlier demo runs; these tests therefore
// verify that clicking RUN produces a FRESH report (new report id), not just
// that a previously rendered table is visible.

test.describe('RATIO benchmark and governance dashboards', () => {
  test('BENCHMARKS page: run the synthetic benchmark and inspect recorded per-class metrics', async ({ page }) => {
    await page.goto('/')
    await page.getByText('BENCHMARKS', { exact: true }).click()
    await expect(page.getByRole('heading', { name: /Synthetic benchmark/ })).toBeVisible()

    const strip = page.locator('.dataset-strip').first()
    const hadReport = await strip.isVisible().catch(() => false)
    const beforeText = hadReport ? await strip.textContent() : null

    await page.getByRole('button', { name: 'RUN BENCHMARK' }).click()
    if (beforeText) {
      await expect(strip).not.toHaveText(beforeText, { timeout: 120_000 })
    } else {
      await expect(strip).toBeVisible({ timeout: 120_000 })
    }
    await expect(page.locator('.bench-split').first()).toBeVisible({ timeout: 120_000 })

    // three scene-level splits, each with a recorded samples count
    await expect(page.locator('.bench-split')).toHaveCount(3)
    const splitTitles = await page.locator('.split-head b').allTextContents()
    expect(splitTitles.join('|')).toContain('DEVELOPMENT')
    expect(splitTitles.join('|')).toContain('VALIDATION')
    expect(splitTitles.join('|')).toContain('HELD OUT')

    // per-class table with the recorded columns (samples/detected/missed/false alarms/IoU)
    const header = await page.locator('.bench-split').first().locator('.tr.th').textContent()
    expect(header).toContain('HAZARD CLASS')
    expect(header).toContain('DETECTED')
    expect(header).toContain('AVG IOU')
    // false-positive controls: benign classes exist alongside hazard classes
    const firstSplitRows = await page.locator('.bench-split').first().locator('.table .tr:not(.th) span b').allTextContents()
    const classes = firstSplitRows.join(' ')
    expect(classes).toContain('fake boulder')
    expect(classes).toContain('mild sharpening')
  })

  test('MODEL GOVERNANCE page: run the drift monitor and see PASS/REVIEW/QUARANTINE per version', async ({ page }) => {
    await page.goto('/')
    await page.getByText('MODEL GOVERNANCE', { exact: true }).click()
    await expect(page.getByRole('heading', { name: 'Model governance' })).toBeVisible()

    const strip = page.locator('.dataset-strip').first()
    const hadReport = await strip.isVisible().catch(() => false)
    const beforeText = hadReport ? await strip.textContent() : null

    await page.getByRole('button', { name: 'RUN DRIFT MONITOR' }).click()
    if (beforeText) {
      await expect(strip).not.toHaveText(beforeText, { timeout: 120_000 })
    } else {
      await expect(strip).toBeVisible({ timeout: 120_000 })
    }
    await expect(page.locator('.drift-card').first()).toBeVisible({ timeout: 120_000 })

    // three enhancer versions, one baseline
    await expect(page.locator('.drift-card')).toHaveCount(3)
    const versions = await page.locator('.drift-head > div:first-child b').allTextContents()
    expect(versions).toEqual(['v1', 'v2', 'v3'])
    // baseline passes; the aggressive pipelines must not silently pass
    const decisions = await page.locator('.drift-decision b').allTextContents()
    expect(decisions[0]).toBe('PASS')
    expect(['REVIEW', 'QUARANTINE']).toContain(decisions[1])
    expect(['REVIEW', 'QUARANTINE']).toContain(decisions[2])
    // recorded reason codes are visible for the flagged versions
    await expect(page.locator('.drift-reasons em').last()).not.toHaveText('within configured thresholds')
  })
})

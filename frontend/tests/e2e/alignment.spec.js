import { test, expect } from '@playwright/test'
import { uploadPair } from './helpers'

test.describe('RATIO manual alignment with independent validation point', () => {
  test('9: manual 3-point alignment + independent 4th validation point', async ({ page }) => {
    await page.goto('/')
    await uploadPair(page)
    const datasetSelect = page.locator('.dataset-control select')
    await datasetSelect.selectOption('NASA_SVS_LRO_NEARSIDE_45')
    await page.getByRole('button', { name: 'MANUAL 3+1 POINT' }).click()
    await expect(page.locator('.alignment-modal')).toBeVisible()
    await expect(page.getByText('Three-point affine + independent validation point')).toBeVisible()

    const panes = page.locator('.alignment-panes > div')
    const imagePane = panes.nth(0)
    const referencePane = panes.nth(1)

    async function clickPane(pane, fx, fy) {
      const box = await pane.boundingBox()
      await pane.click({ position: { x: box.width * fx, y: box.height * fy } })
    }
    await clickPane(imagePane, 0.1, 0.1)
    await clickPane(referencePane, 0.1, 0.1)
    await clickPane(imagePane, 0.9, 0.1)
    await clickPane(referencePane, 0.9, 0.1)
    await clickPane(imagePane, 0.1, 0.9)
    await clickPane(referencePane, 0.1, 0.9)
    await expect(page.getByText('CLICK INDEPENDENT VALIDATION POINT (IMAGE)')).toBeVisible()
    await clickPane(imagePane, 0.85, 0.85)
    await expect(page.getByText('CLICK THE SAME VALIDATION POINT (REFERENCE)')).toBeVisible()
    await clickPane(referencePane, 0.85, 0.85)
    await expect(page.getByRole('button', { name: 'ACCEPT WITH VALIDATION' })).toBeVisible()
    await page.getByRole('button', { name: 'ACCEPT WITH VALIDATION' }).click()
    await expect(page.locator('.alignment-modal')).toBeHidden()
    await page.getByRole('button', { name: 'VERIFY PHYSICAL EVIDENCE' }).click()
    await expect(page.locator('.decision-banner')).toBeVisible({ timeout: 30_000 })
    const step = page.locator('.chain-step').nth(2)
    await expect(step).toContainText(/independent validation/)
  })
})

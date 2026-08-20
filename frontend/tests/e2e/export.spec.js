import { test, expect } from '@playwright/test'
import { IMAGES, uploadPair } from './helpers'

test.describe('RATIO export firewall and passport', () => {
  test('10: allowed export on the no-significant-change fast path', async ({ page }) => {
    await page.goto('/')
    await uploadPair(page, IMAGES.original, IMAGES.enhanced)
    // fast path: no reference required; the dataset select is disabled by design
    await page.getByRole('button', { name: 'VERIFY PHYSICAL EVIDENCE' }).click()
    await expect(page.locator('.fast-path')).toBeVisible({ timeout: 30_000 })
    const href = await page.locator('a.primary.small').first().getAttribute('href')
    const id = href.match(/[a-f0-9]{32}/)[0]
    const response = await page.request.post(`http://localhost:8000/api/analyses/${id}/export`)
    expect(response.status()).toBe(200)
    const body = await response.json()
    expect(body.designation).toBeTruthy()
  })

  test('11: blocked export surfaces the HTTP 409 policy firewall', async ({ page }) => {
    await page.goto('/')
    await uploadPair(page, IMAGES.original, IMAGES.hazard)
    const datasetSelect = page.locator('.dataset-control select')
    await datasetSelect.selectOption('NASA_SVS_LRO_SYNTHETIC_HAZARD')
    await page.getByRole('button', { name: 'VERIFY PHYSICAL EVIDENCE' }).click()
    await expect(page.locator('.decision-banner')).toBeVisible({ timeout: 30_000 })
    const decision = (await page.locator('.decision-banner strong').first().textContent()).trim()
    expect(['NOT SAFE', 'REVIEW REQUIRED']).toContain(decision)
    const href = await page.locator('a.primary.small').first().getAttribute('href')
    const id = href.match(/[a-f0-9]{32}/)[0]
    const response = await page.request.post(`http://localhost:8000/api/analyses/${id}/export`)
    expect(response.status()).toBe(409)
    const body = await response.json()
    expect(body.error).toBe('POLICY_BLOCKED_EXPORT')
    // the analysis report itself remains downloadable
    const report = await page.request.get(`http://localhost:8000/api/analyses/${id}/download`)
    expect(report.status()).toBe(200)
  })

  test('12: passport and evidence report download with provenance hashes', async ({ page }) => {
    await page.goto('/')
    await uploadPair(page, IMAGES.original, IMAGES.hazard)
    const datasetSelect = page.locator('.dataset-control select')
    await datasetSelect.selectOption('NASA_SVS_LRO_SYNTHETIC_HAZARD')
    await page.getByRole('button', { name: 'VERIFY PHYSICAL EVIDENCE' }).click()
    await expect(page.locator('.decision-banner')).toBeVisible({ timeout: 30_000 })
    const [download] = await Promise.all([
      page.waitForEvent('download'),
      page.getByRole('button', { name: 'PASSPORT' }).click(),
    ])
    const stream = await download.createReadStream()
    const chunks = []
    for await (const chunk of stream) chunks.push(chunk)
    const passport = JSON.parse(Buffer.concat(chunks).toString())
    expect(passport.passport_sha256).toMatch(/^[a-f0-9]{64}$/)
    expect(passport.analysis_version).toBe('PHASE_2')
    expect(passport.decision).toBeTruthy()
    const [evidenceDownload] = await Promise.all([
      page.waitForEvent('download'),
      page.getByRole('button', { name: 'EVIDENCE REPORT' }).click(),
    ])
    const evidenceStream = await evidenceDownload.createReadStream()
    const evidenceChunks = []
    for await (const chunk of evidenceStream) evidenceChunks.push(chunk)
    const evidence = JSON.parse(Buffer.concat(evidenceChunks).toString())
    expect(evidence.features.length).toBeGreaterThan(0)
  })
})

import path from 'node:path'

export const REPO_ROOT = path.resolve(process.cwd(), '..')
export const IMAGES = {
  original: path.join(REPO_ROOT, 'datasets/real/derived/lroc_nearside_original.png'),
  enhanced: path.join(REPO_ROOT, 'datasets/real/derived/lroc_nearside_enhanced.png'),
  hazard: path.join(REPO_ROOT, 'datasets/real/derived/lroc_nearside_synthetic_hazard.png'),
  psrShaded: path.join(REPO_ROOT, 'datasets/real/derived/psr_site001_shaded.png'),
  psrHazard: path.join(REPO_ROOT, 'datasets/real/derived/psr_site001_synth_hazard.png'),
  noise: path.join(process.cwd(), 'tests', 'fixtures', 'noise.png'),
}

export async function uploadPair(page, original = IMAGES.original, enhanced = IMAGES.hazard) {
  const inputs = page.locator('input[type="file"]')
  await inputs.nth(0).setInputFiles(original)
  await inputs.nth(1).setInputFiles(enhanced)
  await page.getByRole('button', { name: /VERIFY IMAGE PAIR/ }).click()
  await page.getByText('Visual evidence workspace').waitFor()
}
